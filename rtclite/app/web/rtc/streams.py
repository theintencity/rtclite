# Copyright (c) 2019, Kundan Singh. All rights reserved.

'''
A publish-subscribe server for named streams abstraction applied to  WebRTC signaling 
negotiations over WebSocket.
See http://blog.kundansingh.com/2019/06/webrtc-notification-system-and.html for more
information

== How does it work? ==

It receives a websocket connection with path of the form /stream/{id}?mode={mode}, 
e.g., /stream/1234?mode=publish or /stream/1234?mode=subscribe

There may be at most one connection in publish mode, and zero or more connections in 
subscribe mode for a specific path. The server maintains publishers and subscribers for 
all the active paths, and informs about them to each other for specific paths. Furthermore,
the server allows sending signaling negotiation messages between the publisher and 
subscribers of a path.

When a publisher is connected, it gets notification about its id as the first message.

 S->C: {"method": "EVENT", "data": {"type": "created", "id": ...}}

After that, it gets notification about all the active subscribers. Zero or more such 
messages may be received.

 S->C: {"method": "EVENT", "data": {"type": "subscribed", "id": ...}}

When a subscriber joins or leaves after the publisher has connected, the publisher gets
notified too as follows.

 S->C: {"method": "EVENT", "data": {"type": "subscribed", "id": ...}}
 S->C: {"method": "EVENT", "data": {"type": "unsubscribed", "id": ...}}

The id attribute identifies the subscriber in the context of this path, and is unique 
per connection to that path.

When a subscriber is connected, it gets notification about its id as the first message.

 S->C: {"method": "EVENT", "data": {"type": "created", "id": ...}}

After that if the publisher is already connected or connects later, it gets notified.
 
 S->C: {"method": "EVENT", "data": {"type": "published", "id": ...}}
 S->C: {"method": "EVENT", "data": {"type": "unpublished", "id": ...}}

The id attribute identifies the publisher in the context of this path, and is unique.

Thus, the server informs about all the subscribers to the publisher, and about the 
publisher to every subscriber. Note that this server does not inform about the id 
of the subscriber to other subscribers. However, the client application may leak 
such id values among the subscribers.

Beyond the initial setup for publisher and subscriber, the client can send directed
messages by specifying the id.

 C->S: {"method": "NOTIFY", "to": ..., "data": {"type": "offer", sdp": ...}}

The message is forwarded to the other client, without modification,

 S->C: {"method": "NOTIFY", "from": ..., "data": {"type": "offer", "sdp": ...}}

The "to" and "from" attributes represent the id of the intended receiver and original
sender respectively. If the intended receiver is not connected, or got disconnected,
then the message is ignored by the server, and another "unsubscribed" or "unpublished"
is delivered to that client.

== Primitive access control == 

If the stream path is known to the malicious applications, they can publish on that
stream path and disrupt ongoing conversation, streaming or application logic. 
One of the simplest form of access control is where the publisher knows the stream
path, whereas the subscriber knows only a hash (e.g., md5, sha1) of the path and
cannot easy guess the stream path for publishing.

The server supports such an access control. It can be enabled simply by picking the stream
name that starts with sha1, e.g., the publisher uses /sha1/stream/1234?mode=publish
and the subscriber uses
/sha1/3a3e02ea6695cd608ac9f84980e60ce702e9c715?mode=subscribe
The server interprets the subscribed path as hash of the actual path without the /sha1
prefix. The server does not allow publish with hash path, and a publisher must supply
the original stream path. The subscriber may subscribe must supply the hash of the
stream path, in this case sha1("/stream/1234") in lowercase hex.

/sha1/3a3e02ea6695cd608ac9f84980e60ce702e9c715

== Configuration for creating peer connection ==

Additionally, a client may request configuration data to create RTCPeerConnection,

 C->S: {"method": "GET", "msg_id": 123, "resource": "/peerconnection"}

and the server responds with the data, duplicating the received "msg_id", so that the
client knows which request this response corresponds to.

 S->C: {"msg_id": 123, "code": "success", "result": {"configuration": {"iceServers": [...]}}}


== How to create the client in JavaScript? ==

Please see streams.html for an example web page that connects to this server over WebSocket
to exchange signaling negotiations, to establish a named stream, and stream audio and video
from a publisher to two subscribers.
'''

import sys, traceback, logging, re, json, random, hashlib
from ....std.ietf.rfc6455 import HTTPError, serve_forever as websocket_serve_forever


logger = logging.getLogger('streams')
configuration = {'iceServers': [{"url": "stun:stun.l.google.com:19302"}]}


class Stream(object):
    '''Represents a single stream at the server. A stream has a unique path at the server,
    and zero or more connections (requests). Among them, at most one can be a publisher, and
    all others subscribers. When a connection is added to a stream, a unique random ID is 
    generated for the subscriber connection, and ID of 0 is used for publisher connection.
    '''
    def __init__(self, path):
        self.path, self.requests = path, dict() # index 0 is publisher, all others are subscribers
        logger.info('creating stream %r', self.path)
    
    def __del__(self):
        logger.info('deleting stream %r', self.path)
    
    @property
    def publisher(self):
        try: return self.requests[0]
        except: return None
    
    @property
    def subscribers(self):
        return [v for k, v in self.requests.iteritems() if k != 0]
    
    @property
    def is_empty(self):
        return len(self.requests) == 0

    def add(self, request):
        index = None
        if request.mode == 'publish': index = 0
        else:
            while True:
                index = random.randint(1, 10000)
                if index not in self.requests: break
        request.stream, request.index = self, index
        self.requests[index] = request
        return index
    
    def remove(self, request):
        request.stream = None
        index = request.index
        del self.requests[index]
    
    def get(self, index):
        return self.requests[index]
    
    

streams = {} # table from path to Stream object


def onhandshake(request, path, headers):
    '''If a publisher exists for the stream and a new publisher is being connection, then
    reject the connection at the handshake stage.'''
    match = re.match(r'^(.*)\?mode=(publish|subscribe)$', path)
    if not match: 
        raise HTTPError('400 Bad Request - incorrect path or mode')
    if match and match.group(2) == 'publish':
        match1 = match.group(1)
        if match1[:6] == '/sha1/':
            match1 = '/sha1/' + hashlib.sha1(match1[5:]).hexdigest()
        stream = streams.get(match1)
        if stream and stream.publisher is not None:
            raise HTTPError('400 Bad Request - publisher exists')

def onopen(request):
    '''On new connection, add it to the corresponding stream. If stream does not exist, then
    create a new stream. Then inform the new connection about its unique ID. Finally, inform
    all the connections including the new one about the other relevant connections: a 
    publisher is informed about the subscribers, and a subscriber about the publisher. Thus,
    when a publisher joins, then it gets information about all the subscribers, and all the 
    subscribers get information about the new publisher. And when a subscriber joins, it gets
    information about any active publisher, and the active publisher gets information about 
    the new subscriber.
    '''
    logger.debug('onopen %s', request.path)
    match = re.match(r'^(.*)\?mode=(publish|subscribe)$', request.path) # must match
    path, mode = match.groups()
    request.mode = mode
    if mode == 'publish' and path[:6] == '/sha1/':
        path = '/sha1/' + hashlib.sha1(path[5:]).hexdigest()
    if path in streams:
        stream = streams[path]
    else:
        stream = streams[path] = Stream(path)
    index = stream.add(request)
    
    request.send_message(json.dumps({'method': 'EVENT', 'data': {'type': 'created', 'id': str(index)}}))
    if request.mode == 'publish': # inform subscribers
        for subscriber in stream.subscribers:
            subscriber.send_message(json.dumps({'method': 'EVENT', 'data': {'type': 'published', 'id': str(index)}}))
            request.send_message(json.dumps({'method': 'EVENT', 'data': {'type': 'subscribed', 'id': str(subscriber.index)}}))
    else: # inform publisher
        if stream.publisher:
            request.send_message(json.dumps({'method': 'EVENT', 'data': {'type': 'published', 'id': str(stream.publisher.index)}}))
            stream.publisher.send_message(json.dumps({'method': 'EVENT', 'data': {'type': 'subscribed', 'id': str(index)}}))


def onclose(request):
    '''When a connection is closed, it is removed from the corresponding stream. If no
    more connections exist in the stream, the stream is removed too. If other connections
    exist, then they are informed about the change. A publisher close is informed to all
    the subscribers, and a subscriber close is informed to any active publisher.
    '''
    logger.debug('onclose %s', request.path)
    stream = request.stream
    if stream:
        stream.remove(request)
        if stream.is_empty:
            del streams[stream.path]
        else:
            index = request.index
            if request.mode == 'publish': # inform subscribers
                for subscriber in stream.subscribers:
                    subscriber.send_message(json.dumps({'method': 'EVENT', 'data': {'type': 'unpublished', 'id': str(index)}}))
            else: # inform publisher
                if stream.publisher:
                    stream.publisher.send_message(json.dumps({'method': 'EVENT', 'data': {'type': 'unsubscribed', 'id': str(index)}}))



def onmessage(request, message):
    '''A message sent by a client connection can be either a GET or NOTIFY. A GET is typically
    to fetch the default peer connection configuration. A NOTIFY request is for end-to-end
    data transfer, from one client to another. The target connection ID is obtained from the 
    "to" attribute from the sender client, and the source connection ID is put in the "from"
    attribute to the receiver client.
    '''
    logger.debug("onmessage %r:\n%r", "%s:%d" % request.client_address, message)
    data = json.loads(message)
    
    if data['method'] == 'GET' and data['resource'] == '/peerconnection':
        response = {'code': 'success', 'result': {'configuration': configuration}}
        if 'msg_id' in data:
            response['msg_id'] = data['msg_id']
        request.send_message(json.dumps(response))    
    
    elif data['method'] == 'NOTIFY':
        stream = request.stream
        target = stream.get(int(data['to']))
        if target:
            del data['to']
            data['from'] = str(request.index)
            target.send_message(json.dumps(data))
        else:
            logger.warn("failed to send message, %r does not exist", data['to'])
        

def serve_forever(options):
    '''Start a websocket server, and invoke the handlers above.'''
    if not re.match('(tcp|tls):[a-z0-9_\-\.]+:\d{1,5}$', options.listen):
        raise RuntimeError('Invalid listen option %r'%(options.listen,))
        
    typ, host, port = options.listen.split(":", 2)
    if typ == 'tls' and (not options.certfile or not options.keyfile):
        raise RuntimeError('Missing certfile or keyfile option')
    
    params = dict(onopen=onopen, onmessage=onmessage, onclose=onclose, onhandshake=onhandshake)
    params['paths'] = options.paths or None
    params['hosts'] = options.hosts or None
    params['origins'] = options.origins or None
        
    params.update(hostport=(host, int(port)))
    if typ == 'tls':
        params.update(certfile=options.certfile, keyfile=options.keyfile)
    
    websocket_serve_forever(**params)


if __name__ == "__main__":
    from optparse import OptionParser, OptionGroup
    parser = OptionParser()
    parser.add_option('-d', '--verbose', dest='verbose', default=False, action='store_true',
                      help='enable debug level logging instead of default info')
    parser.add_option('-q', '--quiet', dest='quiet', default=False, action='store_true',
                      help='quiet mode with only critical debug level instead of default info')
    parser.add_option('-l', '--listen', dest='listen', metavar='TYPE:HOST:PORT',
                      help='listening transport address of the form TYPE:HOST:PORT, e.g., -l tcp:0.0.0.0:8080 or -l tls:0.0.0.0:443')
    parser.add_option('--certfile', dest='certfile', metavar='FILE',
                      help='certificate file in PEM format when a TLS listener is specified.')
    parser.add_option('--keyfile', dest='keyfile', metavar='FILE',
                      help='private key file in PEM format when a TLS listener is specified.')
    parser.add_option('--path', dest='paths', default=[], metavar='PATH', action='append',
                      help='restrict to only allowed path in request URI, and return 404 otherwise. This option can appear multiple times, e.g., --path /gateway --path /myapp')
    parser.add_option('--host', dest='hosts', default=[], metavar='HOST[:PORT]', action='append',
                      help='restrict to only allowed Host header values, and return 403 otherwise. This option can appear multiple times, e.g., --host myserver.com --host localhost:8080')
    parser.add_option('--origin', dest='origins', default=[], metavar='URL', action='append',
                      help='restrict to only allowed Origin header values, and return 403 otherwise. This option can appear multiple times, e.g., --origin https://myserver:8443 --origin http://myserver')
    
    (options, args) = parser.parse_args()

        
    logging.basicConfig(level=logging.CRITICAL if options.quiet else logging.DEBUG if options.verbose else logging.INFO, format='%(asctime)s.%(msecs)d %(name)s %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    
        
    if len(sys.argv) == 1: # show usage if no options supplied
        parser.print_help()
        sys.exit(-1)
        
    try:
        if not options.listen:
            raise RuntimeError('missing --listen TYPE:HOST:PORT argument')

        serve_forever(options)
    except KeyboardInterrupt:
        logger.debug('interrupted, exiting')
    except RuntimeError, e:
        logger.error(str(e))
