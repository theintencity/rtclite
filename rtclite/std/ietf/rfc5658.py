# Copyright (c) 2016, Kundan Singh. All rights reserved. See LICENSE for details.
# @implements RFC5658 (Fix Record-Route in SIP)
# TODO: this module is "work in progress"

'''
Redefine Stack and Proxy based on rfc3261.py to fix certain Record-Route handling in SIP,
e.g., use double record-route headers to proxy from one transport type to another.

See rtclite.app.sip.server and rtclite.app.sip.api modules on how this is used.
In particular, this is useful for proxy from WebSocket to UDP and vice-versa, for using that
SIP server with the sip-js project.

To use this module, create the Stack and Proxy objects from this module instead of rfc3261.
After all the Stack objects are created, invoke rfc5658.combine_stacks on that list so that
all those objects are associated with each other to correctly proxy from one to another as
needed.
'''

import logging, re
from .rfc2396 import URI, Address
from .rfc3261 import Proxy as rfc3261_Proxy, Stack as rfc3261_Stack, Message
from socket import gethostbyname # TODO: should replace with getifaddr, SRV, NAPTR or similar

logger = logging.getLogger('rfc5658')


def combine_stacks(stacks):
    '''Make these stacks available to each other for proxy and double Record-Route when applicable.'''
    for stack in stacks:
        stack._stacks = [stack] + [s for s in stacks if s != stack] # move self to front


class Stack(rfc3261_Stack):
    '''Extend rfc3261.Stack to support multiple Stack objects. The base represents primary.'''
    def __init__(self, *args, **kwargs):
        super(Stack, self).__init__(*args, **kwargs)
        self._stacks = None
    
    def close(self): # this is needed because __del__ may never be called due to circular references
        self._stacks = None
    
    def received(self, *args, **kwargs): # assumed to be the first function in Proxy.
        assert self._stacks is not None, 'must combine rfc5658.Stack objects using rfc5658.combine_stacks'
        return super(Stack, self).received(*args, **kwargs)
        
    def findDialog(self, arg):
        for stack in self._stacks:
            result = super(Stack, stack).findDialog(arg)
            if result: return result
        return None

    def findOtherTransaction(self, r, orig):
        for stack in self._stacks:
            result = super(Stack, stack).findOtherTransaction(r, orig)
            if result: return result
        return None
    
    def isLocal(self, uri):
        for stack in self._stacks:
            if super(Stack, stack).isLocal(uri):
                return True
        return False
    
    def createBranch(self, ua, request, target):
        logger.debug('createBranch method=%r target=%r', request.method, target)
        if isinstance(target, URI) and 'lr' in target.param and self.isLocal(target):
            stack = self.forTarget(target)
            if stack != self: # do not send on network, just invoke received callback
                logger.debug('handover %r to %r', self.transport.type, stack.transport.type)
                request = request.dup()
                request.delete('Via', position=0) # remove the top Via added by this stack.
                return super(Stack, stack)._receivedRequest(request, self.uri.dup())
        if isinstance(target, URI) and 'transport' in target.param and target.param['transport'] != self.transport.type:
            stack = self.forTarget(target) # find another stack that matches
            if stack and stack != self:
                request = self.forStack(request, stack)
                return super(Stack, stack).createBranch(ua, request, target)
            elif not stack:
                raise RuntimeError('not implemented')
        return super(Stack, self).createBranch(ua, request, target)
    
    def send(self, data, dest=None, transport=None):
        logger.debug('send dest=%r', dest)
        if isinstance(data, Message) and data.method and transport is None \
        and isinstance(dest, URI) and 'lr' in dest.param and self.isLocal(dest):
            stack = self.forTarget(dest)
            if stack != self: # do not send on network, just invoke received callback
                logger.debug('handover %r to %r', self.transport.type, stack.transport.type)
                data.delete('Via', position=0) # remove the top Via added by this stack.
                return super(Stack, stack)._receivedRequest(data, self.uri.dup())
        if isinstance(data, Message) and data.method and transport is None \
        and isinstance(dest, URI) and 'transport' in dest.param and dest.param['transport'] != self.transport.type:
            stack = self.forTarget(dest) # find another stack that matches.
            if stack and stack != self:
                data = self.forStack(data, stack)
                return super(Stack, stack).send(data, dest, transport)
            elif not stack:
                raise RuntimeError('not implemented')
        if isinstance(data, Message) and not data.method and data.first('Via').viaUri.param['transport'] != self.transport.type:
            stack = self.forTarget(data.first('Via').viaUri)
            if stack != self:
                return super(Stack, stack).send(data, dest, transport)
        return super(Stack, self).send(data, dest, transport)
    
    def forTarget(self, target):
        if 'transport' in target.param:
            return next((s for s in self._stacks if s.transport.type == target.param['transport']), None)
        return self # return default if no transport param
    
    def forStack(self, request, stack):
        '''Return a copy of the request, modified to be sent on the target stack.
        The top-level Via is changed, additional Record-Route may be added if one exists for local stack,
        and transport parameter may be added to existing Record-Route.'''
        request = request.dup()
        match = re.match(r'(.*/.*/)(.*)(\s.*)$', request.first('Via').value)
        if match: request.first('Via').value = match.group(1) + stack.transport.type.upper() + match.group(3)
        if 'Record-Route' in request and super(Stack, self).isLocal(request.first('Record-Route').value.uri):
            request.first('Record-Route').value.uri.param['transport'] = self.transport.type
            request.insert(stack.createRecordRoute())
            request.first('Record-Route').value.uri.param['transport'] = stack.transport.type
        logger.debug('forStack %r to %r', self.transport.type, stack.transport.type)
        return request
    
    def sendResponse(self, response, *args, **kwargs):
        logger.debug('sendResponse %r %r %r', isinstance(response, Message), response.first('Via').viaUri, self.transport.type)
        if isinstance(response, Message) and response.first('Via').viaUri.param['transport'] != self.transport.type:
            stack = self.forTarget(response.first('Via').viaUri)
            if stack != self:
                return super(Stack, stack).sendResponse(response, *args, **kwargs)
        return super(Stack, self).sendResponse(response, *args, **kwargs)

class Proxy(rfc3261_Proxy):
    '''Extends rfc3261.Proxy to support multiple Stack objects.'''
    def __init__(self, *args, **kwargs):
        super(Proxy, self).__init__(*args, **kwargs)
        assert isinstance(self.stack, Stack), 'must use rfc5658.Stack instead of rfc3261.Stack'
        
