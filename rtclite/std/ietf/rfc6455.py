# Copyright (c) 2016, Kundan Singh. All rights reserved. See LICENSE for details.
# @implements RFC6455 (WebSocket)

'''
Implementation of client and server for the WebSocket protocol, e.g.,

0) To view the command line usage
   $ python rfc6455.py -h

1) To start as server on port 80:
   $ python rfc6455.py -l tcp:0.0.0.0:80

2) To start as debug enabled server on localhost with TCP port 8080 (for ws) and TLS port 8443 (for wss):
   $ python rfc6455.py -l tcp:localhost:8080 -l tls:localhost:8443 --certfile cert.pem --keyfile cert.key -d

3) To start as client connecting to local server
   $ python rfc6455.py -c ws://localhost:8080/restserver
   
4) To start as debug client connecting to server on secure transport
   $ python rfc6455.py -c wss://someserver.com/path/to/app -d

-----
Usage

$ python rfc6455.py [options]

Options:
  -h, --help            show this help message and exit
  -d, --verbose         enable debug level logging instead of default info

  Server Options:
    Use these options to configure the server behavior. At the minimum use
    one --listen option to start a server.

    -l TYPE:HOST:PORT, --listen=TYPE:HOST:PORT
                        listening transport address of the form
                        TYPE:HOST:PORT. This option can appear multiple times,
                        e.g., -l tcp:0.0.0.0:8080 -l tls:0.0.0.0:443
    --certfile=FILE     certificate file in PEM format when a TLS listener is
                        specified.
    --keyfile=FILE      private key file in PEM format when a TLS listener is
                        specified.
    --path=PATH         restrict to only allowed path in request URI, and
                        return 404 otherwise. This option can appear multiple
                        times, e.g., --path /gateway --path /myapp
    --host=HOST[:PORT]  restrict to only allowed Host header values, and
                        return 403 otherwise. This option can appear multiple
                        times, e.g., --host myserver.com --host localhost:8080
    --origin=URL        restrict to only allowed Origin header values, and
                        return 403 otherwise. This option can appear multiple
                        times, e.g., --origin https://myserver:8443 --origin
                        http://myserver

  Client Options:
    Use these options to configure the client behavior

    -c URL, --connect=URL
                        target URL to connect to, e.g.,
                        ws://localhost:8080/myapp or wss://server/path/to/file
    --cacertfile=FILE   certificate bundle file in PEM format for all trusted
                        certificate authorities. This is only applicable for
                        wss URL.
    --verify-host       verify server host against its certificate. This is
                        only applicable for wss URL.
    --header=HEADERS    supply additional headers, e.g., --header "Cookie:
                        token=something" --header "Origin: https://something"
    --no-origin         avoid sending the default Origin header
    --proxy=HOST:PORT   use the supplied proxy to connect to first, before
                        sending handshake.
    --proxy-header=PROXY_HEADERS
                        supply addition headers to the proxy, e.g., --proxy-
                        header "Proxy-Authorization: Basic
                        ZWRuYW1vZGU6bm9jYXBlcyE="

-------------
Developer API

This section explains the developer API for creating a server or client. Both these
abstractions are multi-threaded, i.e., the callbacks such as onopen or onmessage are
invoked in a separate thread, and each connection has its own thread. You can override
the client or server classes to change the behavior in your application.

Server is implemented using the WebSocketHandler class and/or serve_forever function.
The serve_forever function is a higher level server function that creates a listening
socket server for TCP or TLS.

  def serve_forever(hostport, **kwargs)
  
  hostport - (mandatory) a tuple for listening host/IP and port, e.g., ('0.0.0.0', 80)
  onopen - a function that is invoked as onopen(request) on new incoming connection
  onclose - a function that is invoked as onclose(request) when the connection closes
  onmessage - a function that is invoked as onmessage(request, message) where message is
        either UTF-8 string or binary data depending on the received message opcode.
  certfile - a path to the certificate file for secure server
  keyfile - a path to the private key file for secure server.
        It uses SSL if both certfile and keyfile are supplied, otherwise just TCP.
  paths - a list of allowed URI path, or None to allow any
  origins - a list of allowed Origin header values, or None to allow any
  hosts - a list of allowed Host header values, or None to allow any
  
  An example is shown in echo_server. A simple usage is shown below.
  
  def echo(request, message):
    print 'path=', request.path
    request.send_message(message)
  serve_forever(('0.0.0.0', 80), onmessage=echo, paths=['/echo'])

The WebSocketHandler class is lower level handler derived from SocketServer.StreamSocketHandler.
See the implementation of serve_forever on how it is used in a multi-threaded server.
An instance of this handler class is used as the "request" argument on various callbacks of
the serve_forever function. A simple usage follows.

  server = SocketServer.TCPServer(('0.0.0.0', 80), WebSocketHandler)

The handler accesses various options from server attributes, such as onopen, onclose,
onmessage, certfile, keyfile, paths, origins and hosts. Additionally, a onhandshake callback
is allowed, and is invoked as oncallback(request, path, headers). The application may
throw an HTTPError to fail the handshake, or return None to success, or return a list of
headers to append to default set of handshake headers.

  def onhandshake(request, path, headers):
    if path != '/echo': raise HTTPError('404 Not Found')
  server.onhandshake = onhandshake
  server.onmessage = echo
  server.serve_forever() # this is different than this modules serve_forever function

The send_message method on the WebSocketHandler (or the request object of callbacks) takes
a message and an optional opcode of 1 or 2, for UTF-8 text or binary data, respectively.
  
  request.send_message("some text") # some UTF-8 text
  request.send_message("\x01\x02\x03\x04", opcode=2) # some binary data

    
Client is implemented using the WebSocket class. Please see interactive_client function for
an example of how the class is used. The WebSocket object is constructed by supplying a list
of configuration options.

  WebSocket(url, **kwargs)
  
  url - target URL, e.g., "ws://localhost/echo" or "wss://some-server:8443/path/to/resource"
  onopen - a function that is invoked a onopen(ws) when connection completes.
  onclose - a function that is invoked as onclose(ws) when connection terminates
  onmessage - a function that is invoked as onmessage(ws, message) where message is
        either UTF-8 string or binary data depending on the received message opcode.
  cacertfile - a path to the CA certificate bundle file.
  headers - list of additional headers to send in handshake request
  verify_host - whether to verify the hostname of the URL against server cerificate.
  has_origin - whether to send Origin header (default is True) or not (if False).
  proxy - the proxy host and port if needed, e.g., "some-proxy:80"
  proxy_headers - a list of additional headers to send in proxy request, if proxy is supplied.

An example is as follows,

  def onmessage(request, message):
    print message
  request = WebSocket("ws://localhost/echo", onmessage=onmessage)
  
The class has three important methods: connect, send and close. The connect method is implicitly
invoked if a URL is supplied in the constructor, or can be explicitly invoked by supplying the
URL, e.g.,

  request = WebSocket(onmessage=message)
  request.connect("ws://localhost/echo")

The send method takes a message data and optional opcode with value 1 (for UTF-8 string) or 2
(for arbitrary binary data), e.g.,

  request.send("some text") # some UTF-8 text
  request.send("\x01\x02\x03\x04", opcode=2) # some binary data

The close function closes the connection.

  request.close()
  
-------------
Low-level API

The low level API is for parsing and formatting WebSocket requests and responses.
It is independenct of the concurrency mechanism, and delegates that to the application.

  result, data, path = receive_handshake(data, verify_handshake=None, userdata=None)
  
To receive handshake message at the server, and to return the appropriate response.
It returns tuple (result, pending, path) where result is either None or a string to respond,
and pending is unparsed/remaining data from the supplied received data. The path value is only
valid if the handshake was successful and is from the request line.
When result is None, it means the handshake is waiting for more received data. 

The function does some verification, e.g., to check for necessary headers or websocket
minimum version of 13. Additional verification can be done by supplying the
verify_handshake and userdata arguments as follows.

  def verify_handshake(userdata=None, path='/', headers=None): 
    ...
Here path is from the request line and headers is of type mimetools.Message. The function
may return a list of additional headers to send in the successful handshake response.
For example, the caller can check for websocket protocol of "sip", and respond with that
header as follows.

    if headers.get('Sec-WebSocket-Protocol', None) != 'sip':
      raise HTTPError('400 Bad Request', 'missing or wrong Sec-WebSocket-Protocol')
    return ['Sec-WebSocket-Protocol: sip']
     
The receive_handshake function can process the HTTPError exception from verify_handshake
and return the appropriate response. The caller should keep track of whether the handshake
was successful or not by checking the return result and path values.

Once the handshake is successful, the application can receive subsequent messages or events
using the receive_server_event function as follows. First receive the data on the connection.
Then append it to any previous remaining data. Call the function with the combined data.

  while True:
      type, value, data, state = receive_server_event(data, state)
      # handle type and value if applicable
      if type == 'notenough': break

Here, data is the received data supplied to the function, and the unparsed/remaining data
returned from the function. The state is used internally by the function, and must be
set to None for the first invocation on a connection. Internally, it builds the local
state containing any partial frame, and returns that. Subsequent call to this function must
supply the state value that was returned in the previous call.

The type and value contain the event type and associated value. If the type is "onclose", it
means the connection was closed, or a close frame was received. If the type is "onmessage",
the value is the received message. If the type is "send", then value is the outgoing
message that should be sent back to the client on the connection, e.g., for "ping" response.
If type is None or "notenough" then more data should be received and supplied by
calling this function again.

When the returned "state" is None, the caller should close the socket connection, after
handling the "type".
'''


import sys, traceback, random, logging, re, struct, base64, uuid, hashlib, mimetools, urlparse, ssl, thread, time, socket, SocketServer
from StringIO import StringIO


logger = logging.getLogger('websocket')

_magic = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
_buffer_size = 1024  # just some value for socket recv()


# invoke callback obj.methodname(*args, **kwargs) if possible
def _callit(obj, methodname, *args, **kwargs):
    if hasattr(obj, methodname) and callable(getattr(obj, methodname)):
        try: return getattr(obj, methodname)(*args, **kwargs)
        except: logger.exception('error in callback')
    else: logger.debug('missing callback %s'%(methodname,))


# HTTP response types for error responses
class HTTPError(Exception):
    def __init__(self, response, entity=''):
        Exception.__init__(self, response)
        self.response, self.entity = response, entity
    def __str__(self):
        if self.entity: return 'HTTP/1.1 %s\r\nContent-Length: %d\r\nContent-Type: %s\r\n\r\n%s'%(self.response, len(self.entity), 'text/plain', self.entity)
        else: return 'HTTP/1.1 %s\r\nContent-Length: 0\r\n\r\n'%(self.response, )

# connection is closed
class Terminated(Exception):
    def __init__(self, reason = 'closed', response = ''):
        Exception.__init__(self, reason)
        self.response = response

# not enough data yet
class NotEnough(Exception):
    def __init__(self):
        Exception.__init__(self, 'not enough')



# Server handler class, which can be used with SocketServer.TCPServer and any mix-in.
# It uses server attribute to invoke callbacks such as onopen, onmessage, onclose as well
# as to access any server options such as allowed paths or origins.
class WebSocketHandler(SocketServer.StreamRequestHandler):

    # setup is called on a new incoming connection. Set socket options. Define object members.
    def setup(self):
        SocketServer.StreamRequestHandler.setup(self)
        logger.info('connection from %r', self.client_address)
        self.request.setsockopt(socket.SOL_TCP, socket.TCP_NODELAY, 1)
        self._pending, self._frame, self._frame_opcode, self._handshake_done, self._rxstate = '', '', 0, False, None
    
    # handle is called to process the incoming connection. Invoke handshake or read frame.
    def handle(self):
        while True:
            # receive some data; will block
            data = self.request.recv(_buffer_size)
            if not self._handshake_done:
                logger.debug('received handshake %d bytes\n%s', len(data) if data else 0, data or 'None')
                if self._handshake(data): break
            else:
                if self._read_frame(data): break
        logger.info('closing connection from %r', self.client_address)
    
    # close the connection
    def close(self):
        try:
            self.request.sendall(struct.pack('>BB', 0x88, 0))
            self.request.shutdown(socket.SHUT_WR)
            # TODO: should close the socket after a brief timeout, instead of waiting for other end
        except: pass
    
    # perform handshake
    def _handshake(self, data):
        if not data: # connection was closed during handshake
            return True # so that handle() returns
        self._pending += data # store the received data in _pending and check if enough data received
        verify_handshake = userdata = None
        if hasattr(self.server, 'onhandshake') and callable(self.server.onhandshake):
            verify_handshake, userdata = self.server.onhandshake, self.request
        response, self._pending, path = receive_handshake(self._pending, verify_handshake=verify_handshake, userdata=userdata)

        if response: # send the response, and finish handshake phase. _pending contains remaining data if any.
            logger.debug('sending handshake %d bytes\n%s', len(response), response)
            self.request.sendall(response)
            logger.info('%s - GET %s HTTP/1.1 - %s', self.client_address, path, response.split('\r\n', 1)[0])
            if path:  # success handshake
                self.path, self._handshake_done = path, True
                _callit(self.server, 'onopen', self)
            else:
                return True # handshake failed, so that handle() returns

    # read a single frame and invoke any onmessage or onclose callback
    def _read_frame(self, data):
        if data: self._pending += data # store the received data in _pending and check if enough
        while True:
            typ, value, self._pending, self._rxstate = receive_server_event(data=self._pending, state=self._rxstate)
            if typ == 'send':
                self.request.sendall(value)
            elif typ == 'onmessage':
                _callit(self.server, 'onmessage', self, value)
            if self._rxstate is None or typ == 'notenough' and not data: # connection was closed
                logger.info('%r - closed', self.client_address)
                _callit(self.server, 'onclose', self)
                return True # so that handle() returns
            elif typ == 'notenough':
                break # break from loop

    # send one message in one frame. The opcode argument must be either 1 (text) or 2 (binary).
    def send_message(self, message, opcode=1):
        if opcode != 1 and opcode != 2: raise RuntimeError('invalid opcode')
        if opcode == 1: message = message.encode('utf-8') # convert to binary
        length = len(message)
        logger.debug('sending %d bytes frame', length)
        
        if length <= 125:
            self.request.sendall(struct.pack('>BB', 0x80 | opcode, length) + message)
        elif length >= 126 and length <= 65535:
            self.request.sendall(struct.pack('>BBH', 0x80 | opcode, 126, length) + message)
        else:
            self.request.sendall(struct.pack('>BBQ', 0x80 | opcode, 127, length) + message)
 

def receive_server_event(data, state):
    try:
        if state is None: state = dict(frame='', opcode=0)
        if len(data) < 2: raise NotEnough
    
        final, opcode, length = (ord(data[0]) & 0x80) != 0, ord(data[0]) & 0x0f, ord(data[1]) & 0x7f
        if final and opcode == 0x08: raise Terminated
        offset = 2
        #if length == 0: raise HTTPError('closed')
        if length == 126:
            if len(data) < offset+2: raise NotEnough
            length, offset = struct.unpack('>H', data[offset:offset+2])[0], offset+2
        elif length == 127:
            if len(data) < offset+8: raise NotEnough
            length, offset = struct.unpack('>Q', data[offset:offset+8])[0], offset+8
                
        logger.debug('0x%x 0x%x', ord(data[0]), ord(data[1]))
        if ord(data[1]) & 0x80 != 0:
            masks, offset = [ord(byte) for byte in data[offset:offset+4]], offset+4
        else:
            logger.debug('invalid mask not present')
            raise Terminated(response=struct.pack('>BB', 0x88, 0)) # mask must be present from client
        
        if len(data) < offset+length: raise NotEnough
        logger.debug('received %d bytes frame of opcode=0x%x', length, opcode)
        decoded = ''.join((chr(ord(char) ^ masks[index % 4]) for index, char in enumerate(data[offset:offset+length])))
        offset += length
        data = data[offset:] # remaining data
        
        if opcode == 0 or opcode == 1 or opcode == 2:
            if opcode != 0: state['opcode'] = opcode # first fragment opcode
            state['frame'] += decoded # store the fragment in frame
            if final: # invoke onmessage on full frame
                decoded, state['frame'] = state['frame'], ''
                if state['opcode'] == 1: # text, utf-8
                    try: decoded = decoded.decode('utf-8')
                    except UnicodeDecodeError:
                        logger.info('unicode decode error %r', decoded)
                        raise Terminated(response=struct.pack('>BB', 0x88, 0))
                return ('onmessage', decoded, data, state)
        elif final and opcode == 0x9 and length < 126: # ping
            return ('send', struct.pack('>BB', 0x8a, length) + decoded, data, state)
        
        return ('notenough', None, data, state) # not enough
    except NotEnough:
        return ('notenough', None, data, state)
    except Terminated, e:
        if e.response:
            return ('send', e.response, '', None)
        else:
            return ('onclose', None, '', None)
    except:
        logger.exception('exception')
        return ('onclose', None, '', None)
 

def receive_handshake(msg, verify_handshake=None, userdata=None):
    index1, index2 = msg.find('\n\n'), msg.find('\n\r\n') # handle both LFLF and CRLFCRLF
    if index2 > 0 and index1 > 0: index = (index1 + 2) if index1 < index2 else (index2 + 3)
    elif index1 > 0: index = index1 + 2
    elif index2 > 0: index = index2 + 3
    else:
        logger.debug('no CRLF found')
        return (None, msg, '') # not enough header data yet
    
    # verify if enough data is available for content-length, if any
    match = re.search(r'content-length\s*:\s*(\d+)\r?\n', msg[:index].lower())
    length = int(match.group(1)) if match else 0
    if len(msg) < index+length:
        logger.debug('has more content %d < %d (%d+%d)', len(msg), index+length, index, length)
        return (None, msg, '') # pending further content.

    # extract the first HTTP request, and store remaining as pending
    data, body, msg = msg[:index], msg[index:index+length], msg[index+length:]
    try:
        firstline, data = data.split('\n', 1)
        firstline = firstline.rstrip()
        headers = mimetools.Message(StringIO(data))
        # validate firstline and some headers
        method, path, protocol = firstline.split(' ', 2)
        if method != 'GET':
            raise HTTPError('405 Method Not Allowed')
        if protocol != "HTTP/1.1":
            raise HTTPError('505 HTTP Version Not Supported')
        if headers.get('Upgrade', None) != 'websocket':
            raise HTTPError('403 Forbidden', 'missing or invalid Upgrade header')
        if headers.get('Connection', None) != 'Upgrade':
            raise HTTPError('400 Bad Request', 'missing or invalid Connection header')
        if 'Sec-WebSocket-Key' not in headers:
            raise HTTPError('400 Bad Request', 'missing Sec-WebSocket-Key header')
        if int(headers.get('Sec-WebSocket-Version', '0')) < 13: # version too old
            raise HTTPError('400 Bad Request', 'missing or unsupported Sec-WebSocket-Version')
        
        result = None # invoke app below for result if needed
        if verify_handshake is not None and callable(verify_handshake):
            try:
                result = verify_handshake(userdata=userdata, path=path, headers=headers)
            except HTTPError:
                raise # re-raise only HTTPError, and mask all others
            except:
                logger.exception('exception in server app: verify_handshake')
                raise HTTPError('500 Server Error', 'exception in server app: verify_handshake')
        
        # generate the response, and append result returned by onhandshake if applicable
        key = headers['Sec-WebSocket-Key']
        digest = base64.b64encode(hashlib.sha1(key + _magic).hexdigest().decode('hex'))
        response = ['HTTP/1.1 101 Switching Protocols', 'Upgrade: websocket', 'Connection: Upgrade',
                    'Sec-WebSocket-Accept: %s' % digest]
        if result: response.extend(result)
        response = '\r\n'.join(response) + '\r\n\r\n' # we always respond with CRLF line ending
        
        return (response, msg, path)
    except HTTPError, e: # send error response
        return (str(e), msg, '')
        

# The server function that listens on a socket and responds to websocket handshake.
# It creates a thread that runs forever, until interrupted.
# The onopen, onmessage and onclose callback functions can be supplied, along with
# configuration properties such as paths, origins, hosts, certfile and keyfile.
def serve_forever(hostport, **kwargs):
    # configuration options
    class Options: pass
    options = Options()
    for attr in 'paths hosts origins certfile keyfile'.split():
        setattr(options, attr, kwargs.get(attr, None))
    
    # if certfile and keyfile are supplied, start TLS server
    if options.certfile and options.keyfile:
        class ThreadedServer(SocketServer.ThreadingMixIn, SocketServer.TCPServer):
            allow_reuse_address = True
            daemon_threads = True
            
            def server_bind(self):
                SocketServer.TCPServer.server_bind(self)
                self.socket = ssl.wrap_socket(
                    self.socket, server_side=True, certfile=options.certfile, keyfile=options.keyfile,
                    ssl_version=ssl.PROTOCOL_TLSv1, do_handshake_on_connect=False)
        
            def get_request(self):
                (socket, addr) = SocketServer.TCPServer.get_request(self)
                socket.do_handshake()
                return (socket, addr)
            
        logger.debug("secure server on %r", hostport)
    else: # otherwise start TCP server
        class ThreadedServer(SocketServer.ThreadingMixIn, SocketServer.TCPServer):
            allow_reuse_address = True
            daemon_threads = True
        logger.debug("server on %r", hostport)
        
    server = ThreadedServer(hostport, WebSocketHandler)

    # basic handshake header verification - using paths, hosts and origins options
    def onhandshake(userdata, path, headers):
        if headers.get('Sec-WebSocket-Version', None) != '13': # require version 13, not more.
            raise HTTPError('400 Bad Request', 'requires WebSocket version only 13')
        if options.paths is not None and path not in options.paths:
            raise HTTPError('404 Not Found')
        if options.hosts is not None and headers.get('Host', None) not in options.hosts:
            raise HTTPError('403 Forbidden', 'missing or forbidden Host header')
        if options.origins is not None and 'Origin' in headers and headers.get('Origin') not in options.origins:
            raise HTTPError('403 Forbidden', 'forbidden Origin header')
        if 'onhandshake' in kwargs:
            kwargs['onhandshake'](userdata, path, headers)
    
    # setup server callbacks
    server.onhandshake = onhandshake
    server.onopen = kwargs.get('onopen', None)
    server.onclose = kwargs.get('onclose', None)
    server.onmessage = kwargs.get('onmessage', None)
    
    # and run the server thread until interrupted
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        # server.close()
        raise


# check if the hostname matches either subject commonName or one of the subjectAltName in the certificate
def match_hostname(cert, hostname):
    for field in cert['subject']:
        if field[0][0] == 'commonName' and field[0][1] == hostname: return True
    for field in cert.get('subjectAltName', []):
        if field[1] == hostname: return True
    raise ssl.SSLError('certificate subject commonName or subjectAltName does not match hostname %r' % (hostname,))


# A websocket client connector can be used to connect to a websocket server.
# It has callbacks for onopen, onmessage, onclose supplied in the constructor.
class WebSocket(object):
    
    # construct using the optional server URL. If supplied, will attempt connection,
    # otherwise call connect(url) explicitly later.
    def __init__(self, url=None, **kwargs):
        self.thread = self.sock = self.url = None
        args = 'onopen onclose onerror onmessage cacertfile headers verify_host has_origin proxy proxy_headers'.split()
        for name in args: setattr(self, name, kwargs.get(name, None))
        if url: self.connect(url)
    
    # the main connect function creates a thread to connect, send handshake and receive frames.
    def connect(self, url):
        if self.thread:
            raise RuntimeError('already connected')
        
        # thread function
        def func(self, url):
            try:
                key = self._send_handshake(url)
                pending = self._recv_handshake(key)
                self._recv_frames(pending)
            except:
                logger.debug('closing connection: %s', sys.exc_info()[1])
                # traceback.print_exc()
                try: self.sock.close()
                except: pass
            _callit(self, 'onclose', self)
        
        self.thread = thread.start_new_thread(func, (self, url))
    
    
    # create a TCP socket and apply any socket options
    def _create_socket(self):                
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_TCP, socket.TCP_NODELAY, 1)
        if hasattr(socket, 'SO_KEEPALIVE'):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        if hasattr(socket, "TCP_KEEPIDLE"):
            sock.setsockopt(socket.SOL_TCP, socket.TCP_KEEPIDLE, 30)
        if hasattr(socket, "TCP_KEEPINTVL"):
            sock.setsockopt(socket.SOL_TCP, socket.TCP_KEEPINTVL, 10)
        if hasattr(socket, "TCP_KEEPCNT"):
            sock.setsockopt(socket.SOL_TCP, socket.TCP_KEEPCNT, 3)
        return sock
    
    
    # connect socket, perform SSL if needed, send handshake, return key
    def _send_handshake(self, url):
        # parse URL and connect socket
        parsed = urlparse.urlparse(url)
        self.sock = self._create_socket()
        port = parsed.port or parsed.scheme == 'wss' and 443 or 80
        if not self.proxy:
            logger.debug('connecting to %r', (parsed.hostname, port))
            self.sock.connect((parsed.hostname, port))
        else: # with proxy assume non-secure transport
            proxy_host, ignore, proxy_port = self.proxy.partition(':')
            proxy_port = proxy_port and int(proxy_port) or 80 # always HTTP
            self.sock.connect((proxy_host, proxy_port))
            
            # perform proxy handshake before initiating SSL or websocket handshake
            self._proxy_handshake(parsed.hostname, port) # TODO: we ignore result (pending data) if any
        
        # for secure connection, use ssl
        if parsed.scheme == 'wss':
            self.sock = ssl.wrap_socket(self.sock, ca_certs=self.cacertfile,
                       cert_reqs=ssl.CERT_REQUIRED, ssl_version=ssl.PROTOCOL_TLSv1)
            if self.verify_host:
                match_hostname(self.sock.getpeercert(), parsed.hostname)
        
        # create random key for Sec-WebSocket-Key
        key = base64.b64encode(uuid.uuid4().bytes).decode('utf-8').strip()
        
        # extract the origin from supplied headers, or set as default
        origin = self.headers and [x for x in self.headers if x.lower().startswith('origin:')]
        if not origin and self.has_origin: # build a default origin
            origin = ['Origin: %s://%s'%(parsed.scheme == 'wss' and 'https' or 'http', parsed.netloc)]
            
        # remove the supplied headers that we set explicitly
        self.headers = [x for x in self.headers or [] if x.lower().split(':')[0].strip() not in ('upgrade', 'connection', 'host', 'origin', 'sec-websocket-key', 'sec-websocket-version')]
        
        # construct the message with its headers
        message = ['GET %s HTTP/1.1'%(parsed.path,),
                'Upgrade: websocket', 'Connection: Upgrade', 'Host: %s'%(parsed.netloc,)]
        if origin: message.extend(origin[:1])
        message.extend(['Sec-WebSocket-Key: %s'%(key,), 'Sec-WebSocket-Version: 13'])
        if self.headers: message.extend(self.headers)
            
        data = '\r\n'.join(message) + '\r\n\r\n'
        logger.debug('sending %d bytes\n%s', len(data), data)
        
        # send the initial handshake
        self.sock.sendall(data)
        
        return key

    # wait for handshake response from the server, and invoke onopen callback when done, and return remaining data
    def _recv_handshake(self, key):
        pending = ''
        while True:
            if pending.find('\r\n\r\n') < 0:
                data = self.sock.recv(_buffer_size)
                logger.debug('received %d bytes\n%s', len(data), data)
                if not data:
                    raise Terminated()
                pending += data
                
            if pending.find('\r\n\r\n') >= 0:
                data, pending = pending.split('\r\n\r\n', 1)
                
                firstline, headers = data.split('\r\n', 1) if data.find('\r\n') >= 0 else (data, '')
                protocol, code, reason = firstline.split(' ', 2)
                if code != '101': raise HTTPError(code + ' ' + reason)
                
                headers = mimetools.Message(StringIO(headers))
                if headers.get('Upgrade', '').lower() != 'websocket': raise HTTPError('invalid Upgrade header')
                if headers.get('Connection', '').lower() != 'upgrade': raise HTTPError('invalid Connection header')
                
                accept = headers.get('Sec-WebSocket-Accept', '')
                digest = base64.b64encode(hashlib.sha1(key + _magic).hexdigest().decode('hex'))
                if accept.lower() != digest.lower(): raise HTTPError('invalid Sec-WebSocket-Accept header')
                
                _callit(self, 'onopen', self)
                break
        return pending
    
    # perform handshake with any configured proxy, and wait for response
    def _proxy_handshake(self, hostname, port, proxy_headers=None):
        # send connect request to the proxy
        headers =['CONNECT %s:%d HTTP/1.1'%(hostname, port), 'Host: %s'%(hostname,)]
        if proxy_headers: headers.extend(proxy_headers)
        self.sock.sendall('\r\n'.join(headers) + '\r\n\r\n')
        
        # wait for response
        pending = ''
        while True:
            if pending.find('\r\n\r\n') < 0:
                data = self.sock.recv(_buffer_size)
                logger.debug('received %d bytes\n%s', len(data), data)
                if not data:
                    raise Terminated()
                pending += data
                
            if pending.find('\r\n\r\n') >= 0:
                data, pending = pending.split('\r\n\r\n', 1)
                
                firstline, headers = data.split('\r\n', 1) if data.find('\r\n') >= 0 else (data, '')
                protocol, code, reason = firstline.split(' ', 2)
                if code != '200': raise HTTPError(code + ' ' + reason)
                
                break # ignore all proxy response headers
        return pending
    
    # receive in a loop, frames, and invoke callback, until connection is closed.
    def _recv_frames(self, pending):
        need_more = False
        frame, frame_opcode = '', 0
        while True:
            if need_more or len(pending) < 2:
                data = self.sock.recv(_buffer_size)
                logger.debug('received %d bytes', len(data))
                if not data: raise Terminated()
                pending += data
            
            data = pending
            if len(data) >= 2:
                need_more = True
                final, opcode, mask = ord(data[0]) & 0x80 != 0, ord(data[0]) & 0x0f, ord(data[1]) & 0x80 != 0
                length, index = ord(data[1]) & 127, 2
                if mask or opcode == 0x8:
                    logger.debug('invalid mask %r or close opcode %r', mask, opcode)
                    self.sock.sendall(struct.pack('>BBI', 0x88, 0x80, 0)) # close bit
                    raise Terminated()
                
                if length == 126: # read length in next two bytes
                    if len(data) < 4: continue
                    length, index = struct.unpack('>H', data[2:4])[0], 4
                elif length == 127: # read length in next 8 bytes
                    if len(data) < 10: continue
                    length, index = struct.unpack('>Q', data[2:10])[0], 10
                if len(data) < index + length: continue # not enough data present
                
                need_more = False # may not need more data in pending
                decoded, pending = data[index:index+length], data[index+length:]
                logger.debug('received frame %d bytes', length)
                
                if opcode == 1: decoded = decoded.decode('utf-8')
                _callit(self, 'onmessage', self, decoded)
                
    
    # given a message bytes, return masked bytes.
    def _masked(self, message):
        masks = [random.randint(0, 255) for x in range(4)]
        converted = [(ord(char) ^ masks[index % 4]) for index, char in enumerate(message)]
        return ''.join([chr(x) for x in (masks+converted)])
    
    # send message. Optional opcode of 1 (default) for utf-8 text, or 2 for binary data.
    def send(self, message, opcode=1):
        if self.sock:
            if opcode != 1 and opcode != 2: raise RuntimeError('invalid opcode')
            if opcode == 1: message = message.encode('utf-8')
            length = len(message)
            logger.debug('sending frame %d bytes', length)
            if length <= 125:
                self.sock.sendall(struct.pack('>BB', 0x80 | opcode, 0x80 | length) + self._masked(message))
            elif length >= 126 and length <= 65535:
                self.sock.sendall(struct.pack('>BBH', 0x80 | opcode, 0x80 | 126, length) + self._masked(message))
            else:
                self.sock.sendall(struct.pack('>BBQ', 0x80 | opcode, 0x80 | 127, length) + self._masked(message))
        
    
    # close the client connection.
    # TODO: unlike the recommendation, it closes the socket immediately.
    def close(self):
        if not self.thread:
            raise RuntimeError('not connected')
        if self.sock:
            self.sock.sendall(struct.pack('>BBI', 0x88, 0x80, 0))
            self.sock.close()
            self.sock = None


# The echo server uses command line options to listen on one or more sockets, and
# respond to any websocket connection, and echoes back any websocket message to the client.
# This function can be used as a template for creating your own websocket service.
def echo_server(options):
    def onopen(request):
        logger.debug("onopen %r", request.client_address)
        
    def onclose(request):
        logger.debug("onclose %r", request.client_address)
    
    def onmessage(request, message):
        logger.debug("onmessage %r: %r", request.client_address, message)
        request.send_message(message)
    
    for option in options.listen:
        if not re.match('(tcp|tls):[a-z0-9_\-\.]+:\d{1,5}$', option):
            raise RuntimeError('Invalid listen option %r'%(option,))
        
    listen = list(((x, y, int(z)) for x, y, z in (x.split(':') for x in options.listen)))
    if [x for x,y,z in listen if x == 'tls']:
        if not options.certfile or not options.keyfile:
            raise RuntimeError('Missing certfile or keyfile option')
    
    params = dict(onopen=onopen, onmessage=onmessage, onclose=onclose)
    params['paths'] = options.paths or None
    params['hosts'] = options.hosts or None
    params['origins'] = options.origins or None
        
    for typ, host, port in listen:
        args = params.copy()
        args.update(hostport=(host, port))
        if typ == 'tls':
            args.update(certfile=options.certfile, keyfile=options.keyfile)
        th = thread.start_new_thread(serve_forever, (), args)
    
    while True:
        time.sleep(60)


# The interactive client uses command line options to connect to a websocket server, and
# send text types on the terminal as message, and display any received message to terminal.
def interactive_client(options):
    def onopen(request):
        logger.debug('connected')
        
    def onmessage(request, message):
        print '<', message
    
    try:
        c = WebSocket(options.connect, onopen=onopen, onmessage=onmessage, cacertfile=options.cacertfile,
                      headers=options.headers, verify_host=options.verify_host, has_origin=not not options.has_origin,
                      proxy=options.proxy, proxy_headers=options.proxy_headers)
        while True:
            try: message = raw_input('> ')
            except EOFError: break # input stopped
            if not message or message.strip() == 'exit': break # script exiting
            c.send(message)
        c.close()
    except:
        logger.exception('failed')
        print 'failed', sys.exc_info()[1]
   

# command line options for client and server, 
if __name__ == "__main__":

    from optparse import OptionParser, OptionGroup
    parser = OptionParser()
    parser.add_option('-d', '--verbose', dest='verbose', default=False, action='store_true',
                      help='enable debug level logging instead of default info')
    parser.add_option('--test', dest='test', default=False, action='store_true',
                      help='perform tests, and exit')
    
    group1 = OptionGroup(parser, 'Server Options', 'Use these options to configure the server behavior. At the minimum use one --listen option to start a server.')
    group1.add_option('-l', '--listen', dest='listen', default=[], action='append', metavar='TYPE:HOST:PORT',
                      help='listening transport address of the form TYPE:HOST:PORT. This option can appear multiple times, e.g., -l tcp:0.0.0.0:8080 -l tls:0.0.0.0:443')
    group1.add_option('--certfile', dest='certfile', metavar='FILE',
                      help='certificate file in PEM format when a TLS listener is specified.')
    group1.add_option('--keyfile', dest='keyfile', metavar='FILE',
                      help='private key file in PEM format when a TLS listener is specified.')
    group1.add_option('--path', dest='paths', default=[], metavar='PATH', action='append',
                      help='restrict to only allowed path in request URI, and return 404 otherwise. This option can appear multiple times, e.g., --path /gateway --path /myapp')
    group1.add_option('--host', dest='hosts', default=[], metavar='HOST[:PORT]', action='append',
                      help='restrict to only allowed Host header values, and return 403 otherwise. This option can appear multiple times, e.g., --host myserver.com --host localhost:8080')
    group1.add_option('--origin', dest='origins', default=[], metavar='URL', action='append',
                      help='restrict to only allowed Origin header values, and return 403 otherwise. This option can appear multiple times, e.g., --origin https://myserver:8443 --origin http://myserver')
    parser.add_option_group(group1)
    
    group2 = OptionGroup(parser, 'Client Options', 'Use these options to configure the client behavior')
    group2.add_option('-c', '--connect', dest='connect', default='', metavar='URL',
                      help='target URL to connect to, e.g., ws://localhost:8080/myapp or wss://server/path/to/file')
    group2.add_option('--cacertfile', dest='cacertfile', metavar='FILE',
                      help='certificate bundle file in PEM format for all trusted certificate authorities. This is only applicable for wss URL.')
    group2.add_option('--verify-host', dest='verify_host', default=False, action='store_true',
                      help='verify server host against its certificate. This is only applicable for wss URL.')
    group2.add_option('--header', dest='headers', default=[], action='append',
                      help='supply additional headers, e.g., --header "Cookie: token=something" --header "Origin: https://something"')
    group2.add_option('--no-origin', dest='has_origin', default=True, action='store_false',
                      help='avoid sending the default Origin header')
    group2.add_option('--proxy', dest='proxy', default='', metavar='HOST:PORT',
                      help='use the supplied proxy to connect to first, before sending handshake.')
    group2.add_option('--proxy-header', dest='proxy_headers', default=[], action='append',
                      help='supply additional headers to the proxy, e.g., --proxy-header "Proxy-Authorization: Basic ZWRuYW1vZGU6bm9jYXBlcyE="')
    parser.add_option_group(group2)
    
    (options, args) = parser.parse_args()
    
    logging.basicConfig(level=logging.DEBUG if options.verbose else logging.INFO, format='%(asctime)s.%(msecs)d %(name)s %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    
    if options.test:
        # TODO: run doctest
        sys.exit(0) # no tests

    if len(sys.argv) == 1: # show usage if no options supplied
        parser.print_help()
        sys.exit(0)
        
    try:
        if not options.listen and not options.connect or options.listen and options.connect:
            raise RuntimeError('Either server or client options, not both, must be used')
        
        if options.listen:
            echo_server(options)
        elif options.connect:
            interactive_client(options)
    except KeyboardInterrupt:
        logger.debug('interrupted, exiting')
    except RuntimeError, e:
        logger.error(str(e))
