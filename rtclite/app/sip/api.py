# Copyright (c) 2007, Kundan Singh. All rights reserved. See LICENSE for details.

'''
High level application programming interface (API) to program SIP devices such as user agents and servers.
The language is derived from understanding of (1) CPL, (2) LESS, (3) SER, (3) VoiceXML?
TODO: Should the script file be a top-level controller (like SER) or installable plugin (like CPL)?

See the server.py module as an example on how to implement a SIP proxy and registrar server.
'''

import os, sys, socket, time, traceback, logging, re, base64, hashlib, struct
from exceptions import Exception
from ... import multitask
from ...std.ietf.rfc2396 import Address, URI
from ...std.ietf.rfc3261 import Stack, Message, Header, UserAgent, Proxy, TransportInfo
from ...std.ietf.rfc2617 import createAuthenticate
from ...std.ietf.rfc6455 import receive_handshake, receive_server_event, HTTPError
from ...common import getlocaladdr, multitask_Timer as Timer

logger = logging.getLogger('sip.api')


class Event(object):
    '''Base class for all events that are handled by Dispatcher. The type property determines the event type.'''
    def __init__(self, type, **kwargs): 
        self.type = type
        for k,w in kwargs.iteritems(): self.__dict__[k] = w
    
class MessageEvent(Event):
    '''A MessageEvent encapsulates a SIP message and provides container and attribute access for SIP headers.'''
    def __init__(self, type, msg, **kwargs):
        Event.__init__(self, type, msg=msg, **kwargs)
    def __str__(self): return str(self.msg)
    # attribute access: use the msg
    def __getattr__(self, name): return self.msg.__getattribute__(name)
    def __getitem__(self, name): return self.msg[name]
    def __setitem__(self, name, value): self.msg[name] = value
    def __delitem__(self, name): del self.msg[name]
    def __contains__(self, name): return name in self.msg

class IncomingEvent(MessageEvent):
    '''An IncomingEvenet indicates an incoming message, and has action property to support accept, reject, proxy, redirect, etc.'''
    def __init__(self, type, msg, **kwargs):
        MessageEvent.__init__(self, type, msg, **kwargs)
        self.action = self; self.location = []
    def accept(self, contacts=None):
        response = self.ua.createResponse(200, 'OK');
        if contacts is not None: 
            for h in map(lambda x: Header(str(x), 'Contact'), contacts): response.insert(h, append=True)
            response.Expires = self['Expires'] if self['Expires'] else Header('3600', 'Expires')
        self.ua.sendResponse(response)
    def reject(self, code, reason=None):
        self.ua.sendResponse(code, reason)
    def challenge(self, realm):
        response = self.ua.createResponse(401, 'Unauthorized')
        response.insert(Header(createAuthenticate(realm=realm, domain=str(self.uri), stale='FALSE'), 'WWW-Authenticate'), append=True)
        self.ua.sendResponse(response)
    def proxy(self, recordRoute=False):
        location = self.location if isinstance(self.location, list) else [self.location]
        for c in location:
            proxied = self.ua.createRequest(self.method, c, recordRoute=recordRoute)
            self.ua.sendRequest(proxied)
        if not location:
            if self.ua.request.method != 'ACK':
                self.ua.sendResponse(480, 'Temporarily Unavailable')
    def redirect(self):
        location = self.location if isinstance(self.location, list) else [self.location]
        response = self.ua.createResponse(302, 'Moved Temporarily')
        for c in location: response.insert(c, append=True)
        self.ua.sendResponse(response)
    def default(self): # invoked when nothing else (action) was invoked in the application
        logger.debug('IncomingEvent default handler called')
        self.ua.sendResponse(501, 'Not Implemented')
    
class OutgoingEvent(MessageEvent):
    def __init__(self, type, msg, **kwargs):
        MessageEvent.__init__(self, type, msg, **kwargs)
        
class Dispatcher(object): # TODO: move this to kutil.py module
    '''A event dispatcher similar to ActionScript's EventDispatcher. Should be used very very carefully, because all references are
    strong references and must be explictly removed for cleanup.'''
    def __init__(self): self._handler = {}
    def __del__(self): self._handler.clear()
    
    def attach(self, event, func):
        '''Attach an event name (str) to the event handler func which takes one argument (event).'''
        if event in self._handler: 
            if func not in self._handler[event]: self._handler[event].append(func)
        else: self._handler[event] = [func]
    def detach(self, event, func):
        '''Detach the event name (str) from the event handler func. If no event is supplied, remove all handlers.'''
        if event is not None:
            if event in self._handler and func in self._handler[event]: self._handler[event].remove(func)
            if len(self._handler[event]) == 0: del self._handler[event]
        else: self._handler.clear()
    def dispatch(self, event):
        '''Dispatch a given event to all the handlers that were attached to the event type.'''
        count = 0
        if event.type in self._handler:
            for func in self._handler[event.type]:
                func(event) # TODO: should we suppress the exceptions?
                count = count + 1
        if not count and hasattr(event, 'action') and hasattr(event.action, 'default') and callable(event.action.default):
            event.action.default() # invoke the default handler if no other handler was found.
        
class Agent(Dispatcher):
    '''This represents a listening endpoint that interfaces with the SIP stack and exposes various API methods on the endpoint.'''
    def __init__(self, listen=(('udp', '0.0.0.0', 5060), ('tcp', '0.0.0.0', 5060)), stack=Stack):
        '''Construct a new Agent. The sipaddr argument indicates the listening address for incoming SIP messages or connections, and
        transports tuple contains list of supported transports such as 'udp' and 'tcp'. The caller may change the SIP stack from the 
        default one defined in rfc3261.py module.'''
        Dispatcher.__init__(self)
        logger.info('starting agent on ' + ', '.join(['%s:%d with transport %s'%(x[1], x[2], x[0]) for x in listen]))
        self.conn, self.stack = dict(), dict()  # tables: (host, port)=>TCP sock, (transport type=>stack)
        for transport, host, port in listen:
            sock = socket.socket(type=socket.SOCK_DGRAM if transport == 'udp' else socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((host, port))
            if transport != 'udp': sock.listen(5)
            t = TransportInfo(sock)
            t.type = transport
            self.stack[transport] = s = stack(self, t)
            s.sock = sock
        self._gens = []
    
    def __del__(self):
        '''Delete the object and internal member references.'''
        try: 
            for s in self.stack.values(): s.sock.close()
            del self.stack, self._gens
        except: pass
        Dispatcher.__del__(self)
        
    def start(self):
        '''Start the listening tasks in this agent. It returns self for cascaded method calls.'''
        for s in self.stack.values(): gen = self._sipreceiver(s); self._gens.append(gen); multitask.add(gen)
        return self
    
    def stop(self):
        '''Stop the listening tasks in this agent. It returns self for cascaded method calls.'''
        for gen in self._gens: gen.close();
        self._gens[:] = []
        return self
    
    def _sipreceiver(self, stack, maxsize=16386):
        '''Handle the messages or connections on the given SIP stack's socket, and pass it to the stack so that stack can invoke 
        appropriate callback on this object such as receivedRequest.'''
        sock = stack.sock
        while True:
            if sock.type == socket.SOCK_DGRAM:
                try: data, remote = yield multitask.recvfrom(sock, maxsize)
                except socket.error: logger.exception('socket.recvfrom'); break
                logger.debug('%r=>%r on type=%r\n%s', remote, sock.getsockname(), stack.transport.type, data)
                if data: 
                    try: stack.received(data, remote)
                    except: logger.exception('received')
            elif sock.type == socket.SOCK_STREAM:
                conn, remote = yield multitask.accept(sock)
                if conn:
                    logger.debug('%r=>%r connection type %r', remote, conn.getsockname(), stack.transport.type)
                    if stack.transport.type in ('ws', 'wss'):
                        multitask.add(self._wsreceiver(stack, conn, remote, maxsize))
                    else:
                        multitask.add(self._tcpreceiver(stack, conn, remote, maxsize))
            else: raise ValueError, 'invalid socket type'
    
    def _tcpreceiver(self, stack, sock, remote, maxsize=16386): # handle the messages on the given TCP connection.
        self.conn[remote] = sock
        pending = ''
        while True:
            try: data = yield multitask.recv(sock, maxsize)
            except socket.error: logger.exception('socket.recv'); break
            logger.debug('%r=>%r on type=%r\n%s', remote, sock.getsockname(), stack.transport.type, data)
            if data: 
                pending += data
                while True:
                    msg = pending
                    index1, index2 = msg.find('\n\n'), msg.find('\n\r\n')
                    if index2 > 0 and index1 > 0:
                        if index1 < index2:
                            index = index1 + 2
                        else: 
                            index = index2 + 3
                    elif index1 > 0: 
                        index = index1 + 2
                    elif index2 > 0:
                        index = index2 + 3
                    else:
                        logger.debug('no CRLF found'); break # no header part yet
                    
                    match = re.search(r'content-length\s*:\s*(\d+)\r?\n', msg.lower())
                    if not match: logger.debug('no content-length found'); break # no content length yet
                    length = int(match.group(1))
                    if len(msg) < index+length: logger.debug('has more content %d < %d (%d+%d)', len(msg), index+length, index, length); break # pending further content.
                    total, pending = msg[:index+length], msg[index+length:]
                    try: stack.received(total, remote)
                    except: logger.exception('receiving')
            else: # socket closed
                break
        try: del self.conn[remote]
        except: pass
            
    def _wsreceiver(self, stack, sock, remote, maxsize=16386): # handle the messages on the given TCP connection.
        handshake = False
        pending = ''
        state = None
        while True:
            try: data = yield multitask.recv(sock, maxsize)
            except socket.error: logger.exception('socket.recv'); break
            logger.debug('%r=>%r on type=%r length %d', sock.getpeername(), sock.getsockname(), stack.transport.type, len(data))
            if data: 
                pending += data
                if not handshake:
                    # do handshake first
                    logger.debug('handshake\n%s', data)
                    if pending.startswith('<policy-file-request/>'):
                        logger.debug('received policy-file-request, responding for port %r'%(stack.transport.port,))
                        sock.sendall('''<!DOCTYPE cross-domain-policy SYSTEM "http://www.macromedia.com/xml/dtds/cross-domain-policy.dtd">
<cross-domain-policy><allow-access-from domain="*" to-ports="%d"/></cross-domain-policy>'''%(stack.transport.port,))
                        sock.close()
                        break
                    else:
                        def verify_handshake(userdata, path, headers):
                            if headers.get('Sec-WebSocket-Protocol', None) != 'sip':
                                raise HTTPError('400 Bad Request', 'missing or unsupported Sec-WebSocket-Protocol, must be sip')
                            data = dict(headers.items())
                            data.update(method='GET', path=path, protocol='HTTP/1.1')
                            userdata.websocket = data # store the handshake parameters
                            return ['Sec-WebSocket-Protocol: sip']
                        
                        response, pending, path = receive_handshake(pending, verify_handshake=verify_handshake, userdata=stack)
                        if response is None: break # wait for more
                        
                        logger.debug('%r=>%r\n%s', sock.getsockname(), sock.getpeername(), response)
                        sock.sendall(response)
                        if path:
                            handshake = True
                            self.conn[remote] = sock
                        else:
                            sock.close()
                            break
                else:
                    # process request
                    while True:
                        typ, value, pending, state = receive_server_event(data=pending, state=state)
                        if typ == 'send':
                            sock.sendall(value)
                        elif typ == 'onmessage':
                            logger.debug('websocket received\n%s', value)
                            if isinstance(value, unicode): value = value.encode('utf-8')
                            try: stack.received(value, remote)
                            except: logger.exception('receiving')
                        if state is None:
                            sock.close()
                            break
                        elif typ == 'notenough':
                            break
            else: # socket closed
                break
        try: del self.conn[remote]
        except: pass
            
    # following callbacks are invoked by the SIP stack
    def send(self, data, remote, stack):
        '''Send a given data to remote for the SIP stack.'''
        def _send(self, data, remote, stack): # a generator function that does the sending
            logger.debug('%r=>%r on type=%r\n%s', stack.sock.getsockname(), remote, stack.transport.type, data)
            try:
                if stack.sock.type == socket.SOCK_STREAM: # for TCP send only if a connection exists to the remote.
                    if stack.transport.type in ('ws', 'wss'):
                        if len(data) < 126:
                            init = struct.pack('>BB', 0x81, len(data))
                        elif len(data) < 65536:
                            init = struct.pack('>BBH', 0x81, 126, len(data))
                        else:
                            raise ValueError, 'cannot send long message'
                        data = init + data
                    if remote in self.conn:
                        yield multitask.send(self.conn[remote], data) # and send using that connected TCP socket.
                    else:
                        logger.warning('ignoring message to %r as no existing connection', remote)
                else: # for UDP send using the stack's UDP socket.
                    yield multitask.sendto(stack.sock, data, remote)
            except StopIteration: pass
            except: 
                logger.exception('sending')
        multitask.add(_send(self, data, remote, stack))
        
    def createServer(self, request, uri, stack): 
        '''Create a Proxy UAS for all requests except CANCEL.'''
        return (request.method != 'CANCEL') and Proxy(stack, request) or None
    
    def sending(self, ua, message, stack):
        if message.method:
            logger.debug('sending request on stack %r', message.method)
            self.dispatch(OutgoingEvent(type='outgoing', msg=message, ua=ua, stack=stack, agent=self))

    def receivedRequest(self, ua, request, stack): 
        logger.debug('received request from stack %r', request.method)
        self.dispatch(IncomingEvent(type='incoming', msg=request, ua=ua, stack=stack, agent=self))
    
    def receivedResponse(self, ua, response, stack): pass
    def cancelled(self, ua, request, stack): pass
    def dialogCreated(self, dialog, ua, stack): pass
    def authenticate(self, ua, header, stack): return True
    def createTimer(self, app, stack): return Timer(app)
    

# Methods and classes inspired by SER (SIP Express Router) to support server functions 
        
class Subscriber(dict):
    '''A simple subscriber table using in-memory dict. The application can store subscribers in this, and use this to authenticate
    incoming SIP request. '''
    def __init__(self):
        dict.__init__(self)
    def store(self, uri, realm, password):
        '''Store a new user and his realm and password in this table.'''
        self[uri] = [realm, password]
    def authenticate(self, request, realm='localhost'):
        '''Returns 200 on success, 401 on failure, 0 if missing or invalid nonce, and 404 if no password/user information available.'''
        auths = filter(lambda x: x['realm']==realm, request.all('Authorization', 'Proxy-Authorization')) # search all our authenticate headers
        if not auths: return 0 # missing authenticate header
        # TODO: check for valid nonce. for now just assume all nonce to be valid.
        uri = request.From.value.uri
        if uri not in self: return 404
        return 200
        
class Location(dict):
    '''A simple location service using in-memory dict. Subclass may override this to support databases such as MySQL.'''
    def __init__(self):
        dict.__init__(self)
    def save(self, msg, uri, defaultExpires=3600):
        '''Save the contacts from REGISTER or PUBLISH msg.'''
        expires = int(msg['Expires'].value if msg['Expires'] else defaultExpires)
        if uri in self: existing = self[uri]
        else: existing = self[uri] = [] # initialize that user's contacts list
        if msg['Contact'] and msg.first('Contact').value == '*': # single contact: * header
            if msg['Expires'] and msg['Expires'].value == '0': # unregistration msg
                del self[uri] # unregister by removing the contacts
        else: # handle individual contact headers in the msg
            now = time.time()
            for c in msg.all('Contact'): # for all contacts in the new msg
                e = now + (expires if 'expires' not in c else int(c.expires)) # expiration for this contact.
                t = None # a NATed target to be used in locate
                if c['+sip.instance'] and c['reg-id']:
                    existing[:] = filter(lambda x: x[0]['+sip.instance']!=c['+sip.instance'] or x[0]['reg-id']!=c['reg-id'], existing) # remove matching contacts
                    instanceId = c['+sip.instance']
                    if instanceId[0] == '<' and instanceId[-1] == '>': instanceId = instanceId[1:-1] 
                    c['pub-gruu'] = '%s;gr=%s'%(msg.To.value.uri, instanceId)
                    # TODO: need to send back temp-gruu also
                    t = msg.first('Via').viaUri.dup()
                    t.user = c.value.uri.user
                else:
                    existing[:] = filter(lambda x: x[0].value.uri!=c.value.uri, existing)  # remove matching contacts
                existing.insert(0, (c, e, t)) # insert the new contact in the beginning
            existing[:] = filter(lambda x: x[1]>now, existing) # filter out expired contacts
            if not existing: # no more contacts
                del self[uri] # remove from the table as well
        logger.debug('save %r', self)
        return True
    def locate(self, uri):
        '''Return all saved contacts for the given uri.'''
        logger.debug('locate %r in\n%r', uri, self)
        existing = self.get(str(uri), [])
        now = time.time()
        existing[:] = filter(lambda x: x[1]>now, existing) # remove expired headers
        for c in existing: 
            c[0]['expires'] = str(int(c[1]-now)) # update the expires header with relative seconds
            if c[2]: c[0].value.uri = c[2]
        return map(lambda x: x[0], existing) # return the contact headers

# Global methods available to the controller script 

def run():
    '''The run loop which runs the multitask's main loop. This can be terminated by KeyboardInterrupt.'''
    try: multitask.run()
    except KeyboardInterrupt: pass


# Unit testing    
if __name__ == '__main__':
    import doctest
    doctest.testmod()
