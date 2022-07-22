# Copyright (c) 2011, Kundan Singh. All rights reserved. See LICENSE for details.

'''
A caller application to initiate or receive VoIP calls from command line.
It using SIP, SDP, RTP, client modules and external py-audio project.

You need to include py-audio module from https://github.com/theintencity/py-audio in your path.
Make sure it contains audiodev.so module.

$ export PYTHONPATH=.:~/py-audio

You can get the full usage information using the -h option.

$ python -m rtclite.app.sip.caller -h
Usage: caller.py [options]

Options:
  -h, --help            show this help message and exit
  -v, --verbose         enable verbose mode for this module
  -q, --quiet'          enable quiet mode with only critical logging

  Network:
    Use these options for network configuration

    --int-ip=INT_IP     listening IP address for SIP and RTP. Use this option
                        only if you wish to select one out of multiple IP
                        interfaces. Default "0.0.0.0"
    --ext-ip=EXT_IP     IP address to advertise in SIP/SDP. Use this to
                        specify external IP if running on EC2. Default is to
                        use "--int-ip" if supplied or any local interface,
                        which is "192.168.1.10"
    --transport=TRANSPORTS
                        the transport type is one of "udp", "tcp" or "tls".
                        Default is "udp"
    --port=PORT         listening port number for SIP UDP/TCP. TLS is one more
                        than this. Default is 5092
    --listen-queue=LISTEN_QUEUE
                        listen queue for TCP socket. Default is 5
    --max-size=MAX_SIZE
                        size of received socket data. Default is 4096
    --fix-nat           enable fixing NAT IP address in Contact and SDP

  SIP:
    Use these options for SIP configuration

    --user-agent=USER_AGENT
                        set this as User-Agent header in outbound SIP request.
                        Default is empty "" to not set
    --subject=SUBJECT   set this as Subject header in outbound SIP request.
                        Default is empty "" to not set
    --user=USER         username to use in my SIP URI and contacts. Default is
                        "kundan"
    --domain=DOMAIN     domain portion of my SIP URI. Default is to use local
                        hostname, which is "Macintosh-2.local"
    --proxy=PROXY       IP address of the SIP proxy to use. Default is empty
                        "" to mean disable outbound proxy
    --authuser=AUTHUSER username to use for authentication. Default is none.
    --authpass=AUTHPASS password to use for authentication. Default is none.
    --strict-route      use strict routing instead of default loose routing
                        when proxy option is specified
    --to=TO             the target SIP address, e.g., '"Henry Sinnreich"
                        <sip:henry@iptel.org>'. This is mandatory
    --uri=URI           the target request-URI, e.g., "sip:henry@iptel.org".
                        Default is to derive from the --to option
    --listen            enable listen mode with or without REGISTER and wait
                        for incoming INVITE or MESSAGE
    --register          send REGISTER to SIP server. This is used with --listen to
                        receive incoming INVITE or MESSAGE and with --to if the
                        SIP server requires registration for outbound calls
    --register-interval=REGISTER_INTERVAL
                        registration refresh interval in seconds. Default is
                        3600
    --retry-interval=RETRY_INTERVAL
                        retry interval in seconds to re-try if register or
                        subscribe fails. Default is 60
    --send=SEND         enable outbound instant message. The supplied text
                        with this option is sent in outbound MESSAGE request
    --auto-respond=AUTO_RESPOND
                        automatically respond to an incoming INVITE or MESSAGE
                        if we are not already in a call. Default is 200 to
                        auto accept. Use 0 to not respond
    --auto-respond-after=AUTO_RESPOND_AFTER
                        number of seconds after which to auto-respond an
                        incoming call if we are available. Default is 3
    --auto-terminate-after=AUTO_TERMINATE_AFTER
                        number of seconds after which to auto-terminate an
                        accepted incoming call. Default is 0 to not auto-
                        terminate
    --use-lf            use LF as line ending instead of the default CRLF

  Media:
    Use these options for media configuration

    --no-sdp            disable sending SDP in outbound INVITE
    --no-audio          disable audio in a call
    --audio-loopback    enable audio loopback mode where this agent sends back
                        the received audio to the other end
    --samplerate        audio samplerate for capture and playback. Default is
                        44100. Use 48000 on OS X
    --no-touchtone      disable sending touch tone (DTMF) digits when typed.
                        By default touch tone sending is enabled.
    --recognize         enable speech recognition to show the received audio
                        as text
    --textspeech        enable text to speech to send typed text as audio.
                        If touchtone is also enabled, it distinguishes between
                        typed digits and non-digits to determine whether to use
                        touchtone or textspeech for the typed text.

To place an outbound call to sip:target@192.168.1.10:5090:
$ python -m rtclite.app.sip.caller --to sip:target@192.168.1.10:5090

To register with a server running on 192.168.1.10:
$ python -m rtclite.app.sip.caller --to sip:kundan@192.168.1.10 --domain 192.168.1.10 --register

To listen for incoming call on port 5080:
$ python -m rtclite.app.sip.caller --listen --port 5080

To test out a call to tollfree number using a free VoIP provider. Note that this
provider fails with CRLF, so use LF for line-ending. And on OS X use sample rate
of 48000 if that is used for microphone capture.

$ python -m rtclite.app.sip.caller -v --user=test --domain=example.net \
  --to=sip:18007741500@tollfree.alcazarnetworks.com --use-lf --samplerate=48000

Feel free to explore other command line options.

To report any problem in this software, use the -v option to generate the full debug trace,
and send it along with your bug report to the author or support mailing list.
'''

try: import gevent
except ImportError: print('Please install gevent and its dependencies and include them in your PYTHONPATH'); raise
from gevent import monkey, Greenlet, GreenletExit
monkey.patch_socket()

from gevent.queue import Queue 
import os, sys, re, traceback, socket, random, logging, time, threading
from queue import Queue as thread_Queue

from .client import MediaSession
from ...std.ietf import rfc3261, rfc2396, rfc3550, rfc4566, rfc2833
from ...common import repeated_warning, ColorizingStreamHandler, getlocaladdr, setlocaladdr, gevent_Timer as Timer

try: import audiodev, audiospeex, audiotts, audioop
except ImportError: audiodev = audiospeex = audiotts = audioop = None

try: import speech_recognition as sr
except ImportError: sr = None


logger = logging.getLogger('caller')

default_ext_ip, default_domain = getlocaladdr()[0], socket.gethostname()
try: default_login = os.getlogin()
except: default_login = 'caller'

def default_options():
    class Options(object): pass
    options = Options()
    options.__dict__ = dict(verbose=False, quiet=False, test=False,
       int_ip='0.0.0.0', ext_ip=default_ext_ip, transports='udp', port=5092, listen_queue=5, max_size=4096, fix_nat=False,
       user_agent='', subject='', user=default_login, domain=default_domain, proxy='', authuser='', authpass='',
       strict_route=False, to=None, uri=None, listen=False, register=False, register_interval=3600, retry_interval=60,
       send='', auto_respond=200, auto_respond_after=3, auto_terminate_after=0, use_lf=False,
       has_sdp=True, audio=True, audio_loopback=False, samplerate=44100, touchtone=True, recognize=False, textspeech=False
    ).copy()
    return options

if __name__ == '__main__': # parse command line options, and set the high level properties
    from optparse import OptionParser, OptionGroup
    parser = OptionParser()
    parser.add_option('-v', '--verbose',   dest='verbose', default=False, action='store_true', help='enable verbose mode for this module')
    parser.add_option('-q', '--quiet',     dest='quiet', default=False, action='store_true', help='enable quiet mode with only critical logging')
    parser.add_option('--test', dest='test', default=False, action='store_true', help='run any tests and exit')
    
    group1 = OptionGroup(parser, 'Network', 'Use these options for network configuration')
    group1.add_option('',   '--int-ip',  dest='int_ip',  default='0.0.0.0', help='listening IP address for SIP and RTP. Use this option only if you wish to select one out of multiple IP interfaces. Default "0.0.0.0"')
    group1.add_option('',   '--ext-ip',  dest='ext_ip',  default=default_ext_ip, help='IP address to advertise in SIP/SDP. Use this to specify external IP if running on EC2. Default is to use "--int-ip" if supplied or any local interface, which is "%s"'%(default_ext_ip,))
    group1.add_option('',   '--transport', dest='transports', default='udp', help='the transport type is one of "udp", "tcp" or "tls". Default is "udp"')
    group1.add_option('',   '--port',    dest='port',    default=5092, type="int", help='listening port number for SIP UDP/TCP. TLS is one more than this. Default is 5092')
    group1.add_option('',   '--listen-queue', dest='listen_queue', default=5, type='int', help='listen queue for TCP socket. Default is 5')
    group1.add_option('',   '--max-size',dest='max_size', default=4096, type='int', help='size of received socket data. Default is 4096')
    group1.add_option('',   '--fix-nat', dest='fix_nat', default=False, action='store_true', help='enable fixing NAT IP address in Contact and SDP')
    parser.add_option_group(group1)
    
    group2 = OptionGroup(parser, 'SIP', 'Use these options for SIP configuration')
    group2.add_option('',   '--user-agent', dest='user_agent', default='', help='set this as User-Agent header in outbound SIP request. Default is empty "" to not set')
    group2.add_option('',   '--subject', dest='subject', default='', help='set this as Subject header in outbound SIP request. Default is empty "" to not set')
    group2.add_option('',   '--user',    dest='user',    default=default_login,   help='username to use in my SIP URI and contacts. Default is "%s"'%(default_login,))
    group2.add_option('',   '--domain',  dest='domain',  default=default_domain, help='domain portion of my SIP URI. Default is to use local hostname, which is "%s"'%(default_domain,))
    group2.add_option('',   '--proxy',   dest='proxy',   default='', help='IP address of the SIP proxy to use. Default is empty "" to mean disable outbound proxy')
    group2.add_option('',   '--authuser',dest='authuser',default='', help='username to use for authentication. Default is to not use authentication')
    group2.add_option('',   '--authpass',dest='authpass',default='', help='password to use for authentication. Only used together with --authuser')
    group2.add_option('',   '--strict-route',dest='strict_route', default=False, action='store_true', help='use strict routing instead of default loose routing when proxy option is specified')
    group2.add_option('',   '--to',      dest='to', default=None, help='the target SIP address, e.g., \'"Henry Sinnreich" <sip:henry@iptel.org>\'. This is mandatory')
    group2.add_option('',   '--uri',     dest='uri', default=None, help='the target request-URI, e.g., "sip:henry@iptel.org". Default is to derive from the --to option')
    group2.add_option('',   '--listen',  dest='listen', default=False, action='store_true', help='enable listen mode with or without REGISTER and wait for incoming INVITE or MESSAGE')
    group2.add_option('',   '--register',dest='register',default=False, action='store_true', help='send REGISTER to SIP server. This is used with --listen to receive incoming INVITE or MESSAGE and with --to if the SIP server requires registration for outbound calls')
    group2.add_option('',   '--register-interval', dest='register_interval', default=3600, type='int', help='registration refresh interval in seconds. Default is 3600')
    group2.add_option('',   '--retry-interval', dest='retry_interval', default=60, type='int', help='retry interval in seconds to re-try if register or subscribe fails. Default is 60')
    group2.add_option('',   '--send',    dest='send',    default='', help='enable outbound instant message. The supplied text with this option is sent in outbound MESSAGE request')
    group2.add_option('',   '--auto-respond', dest='auto_respond', default=200, type='int', help='automatically respond to an incoming INVITE or MESSAGE if we are not already in a call. Default is 200 to auto accept. Use 0 to not respond')
    group2.add_option('',   '--auto-respond-after', dest='auto_respond_after', default=3, type='int', help='number of seconds after which to auto-respond an incoming call if we are available. Default is 3')
    group2.add_option('',   '--auto-terminate-after', dest='auto_terminate_after', default=0, type='int', help='number of seconds after which to auto-terminate an accepted incoming call. Default is 0 to not auto-terminate')
    group2.add_option('',   '--use-lf',  dest='use_lf', default=False, action='store_true', help='use LF as line ending instead of default CRLF')
    parser.add_option_group(group2)
    
    group4 = OptionGroup(parser, 'Media', 'Use these options for media configuration')
    group4.add_option('',   '--no-sdp', dest='has_sdp',default=True, action='store_false', help='disable sending SDP in outbound INVITE')
    group4.add_option('',   '--no-audio',dest='audio',default=True, action='store_false', help='disable audio in a call')
    group4.add_option('',   '--audio-loopback',dest='audio_loopback',default=False, action='store_true', help='enable audio loopback mode where this agent sends back the received audio to the other end')
    group4.add_option('',   '--samplerate', dest='samplerate', default=44100, type=int, help='audio samplerate for capture and playback. Default is 44100. Use 48000 on OS X')
    group4.add_option('',   '--no-touchtone', dest='touchtone', default=True, action='store_false', help='disable sending touch tone (DTMF) digits when typed. By default touch tone sending is enabled')
    group4.add_option('',   '--recognize', dest='recognize', default=False, action='store_true', help='enable speech recognition to show the received audio as text')
    group4.add_option('',   '--textspeech', dest='textspeech', default=False, action='store_true', help='enable text to speech to send typed text as audio. If touchtone is also enabled, it distinguishes between typed digits and non-digits to determine whether to use touchtone or textspeech for the typed text.')

    parser.add_option_group(group4)
    
    (options, args) = parser.parse_args()
    
    if options.test: sys.exit(0) # no tests
    
    if options.recognize and sr is None:
        raise ImportError('please install speech_recognition module in your PYTHONPATH to use --recognize option')
    if options.textspeech and audiotts is None:
        raise ImportError('please install py-audio in your PYTHONPATH to use --textspeech option')
    if options.audio and audiodev is None:
        raise ImportError('please install py-audio in your PYTHONPATH to use audio, otherwise start with --no-audio option')
        
    
    handler = ColorizingStreamHandler(stream=sys.stdout)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter('%(asctime)s.%(msecs)d %(name)s %(levelname)s - %(message)s', datefmt='%H:%M:%S'))
    logging.getLogger().addHandler(handler)
    
    logger.setLevel(options.quiet and logging.CRITICAL or options.verbose and logging.DEBUG or logging.INFO)
    
    if options.use_lf:
        rfc4566.lineending = '\n'
    
    if options.register and not options.to:
        options.listen = True
        
    if not options.listen and not options.to: 
        print('must supply --to option with the target SIP address')
        sys.exit(-1)
    
    if options.ext_ip: setlocaladdr(options.ext_ip)
    elif options.int_ip != '0.0.0.0': setlocaladdr(options.int_ip)
    
    if options.to:
        options.to = rfc2396.Address(options.to)
        options.uri = rfc2396.URI(options.uri) if options.uri else options.to.uri.dup()
    

class Stacks(object):
    UDP, TCP, TLS = 'udp', 'tcp', 'tls' # transport values
    def __init__(self, app, options):
        self.app, self.options, self._stack, self._gin, self._transport, self._conn = app, options, {}, {}, None, {}
        self.allow_outbound = False # don't allow outbound connection from a server
    
    @property
    def default(self): 
        '''The rfc3261.Stack object associated with the default transport.'''
        return self._stack.get(self._transport, None)
    
    def start(self):
        for transport in self.options.transports.split(','):
            if not self._transport: self._transport = transport # default transport
            sock = socket.socket(type=socket.SOCK_DGRAM if transport == Stacks.UDP else socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((self.options.int_ip, (self.options.port+1) if transport == Stacks.TLS else self.options.port))
            if transport != Stacks.UDP: sock.listen(int(self.options.listen_queue))
            stack = self._stack[transport] = rfc3261.Stack(self, rfc3261.TransportInfo(sock, secure=(transport == Stacks.TLS)), fix_nat=self.options.fix_nat)
            stack.sock = sock
            logger.debug('created listening stack on %r %r', transport, sock.getsockname())
            self._gin[transport] = gevent.spawn(self._sipreceiver, stack)
        if not self._transport: raise ValueError('invalid transports, cannot start Stack')

    def stop(self):
        for gen in list(self._gin.values()): gen.kill()
        self._gin.clear()
        for stack in list(self._stack.values()):
            if stack.sock is not None: stack.sock.close(); stack.sock = None
        self._stack.clear()
        
    def _sipreceiver(self, stack): # listen for UDP messages or TCP connections
        while True:
            if stack.sock.type == socket.SOCK_DGRAM:
                logger.debug('waiting on sock.recvfrom %r %r', stack.sock, self.options.max_size)
                data, remote = stack.sock.recvfrom(self.options.max_size)
                logger.debug('received %r=>%r on type=%r\n%s', remote, stack.sock.getsockname(), stack.sock.type, data)
                if data: stack.received(data, remote)
            elif stack.sock.type == socket.SOCK_STREAM:
                logger.debug('waiting on sock.accept %r', stack.sock)
                conn, remote = stack.sock.accept()
                if conn:
                    self._conn[remote] = conn
                    logger.debug('received %r=>%r connection', remote, conn.getsockname())
                    gevent.spawn(self._siptcpreceiver, stack, conn, remote)
            else: raise ValueError('invalid socket type')
    
    def _siptcpreceiver(self, stack, sock, remote): # handle the messages on the given TCP connection.
        pending = ''
        while True:
            data = sock.recv(self.options.max_size)
            logger.debug('received %r=>%r on type=%r\n%s', remote, sock.getsockname(), sock.type, data)
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
                        logger.debug('upto index\n%s', msg[:index])
                        logger.debug('body\n%s', msg[index:index+length])
                        if len(msg) < index+length: logger.debug('has more content %d < %d (%d+%d)', len(msg), index+length, index, length); break # pending further content.
                        total, pending = msg[:index+length], msg[index+length:]
                        stack.received(total, remote)
            else: 
                break
            # else signal a failure
            
    def _proxyToApp(self, function, ua, *args):
        if hasattr(ua, 'app') and hasattr(ua.app, function) and callable(eval('ua.app.' + function)): 
            eval('ua.app.' + function)(ua, *args)
            return True
        return False
    
    def receivedRequest(self, ua, request, stack):
        if not self._proxyToApp('receivedRequest', ua, request):
            method = 'received' + request.method[:1].upper() + request.method[1:].lower()
            if hasattr(self.app, method) and callable(eval('self.app.' + method)): eval('self.app.' + method)(ua, request)
            elif request.method != 'ACK': ua.sendResponse(501, 'Method Not Implemented') 

    def receivedResponse(self, ua, response, stack): self._proxyToApp('receivedResponse', ua, response)
    def cancelled(self, ua, request, stack): logger.debug('cancelled'); self._proxyToApp('cancelled', ua, request)
    def dialogCreated(self, dialog, ua, stack): self._proxyToApp('dialogCreated', ua, dialog)
    def createServer(self, request, uri, stack):  return rfc3261.UserAgent(stack, request) if request.method != 'CANCEL' else None
    def createTimer(self, app, stack): return Timer(app)
    
    def authenticate(self, ua, obj, stack):
        obj.username, obj.password = self.options.authuser, self.options.authpass
        return obj.username and obj.password and True or False

    def send(self, data, addr, stack):
        logger.debug('sending %r=>%r on type %s\n%s', stack.sock.getsockname(), addr, stack.transport.type, data)
        if stack.sock:
            try:
                if self.options.use_lf: data = re.sub(r'\r\n', '\n', data)
                if stack.transport.type == Stacks.UDP: stack.sock.sendto(data.encode('utf-8'), addr)
                elif addr in self._conn: self._conn[addr].sendall(data)
                elif self.allow_outbound:
                    conn = self._conn[addr] = socket.socket(type=socket.SOCK_STREAM)
                    try:
                        logger.debug('first connecting to %r', addr)
                        conn.connect(addr)
                        conn.sendall(data)
                        gevent.spawn(self._siptcpreceiver, stack, conn, addr)
                    except:
                        logger.exception('failed to connect to %r', addr)
                else: logger.warning('ignoring as cannot create outbound socket connection')
            except socket.error:
                logger.exception('socket error in sending') 


class UA(object):
    def __init__(self, app, stack):
        self.app, self.options, self._stack = app, app.options, stack
        self._closeQ = self._ua = self._gen = None
        self.scheme = self._stack.transport.secure and 'sips' or 'sip' 
        self.localParty =  rfc2396.Address('%s:%s@%s'%(self.scheme, self.options.user, self.options.domain))
        self.proxy = rfc2396.URI('%s:%s'%(self.scheme, self.options.proxy)) if self.options.proxy else None
        
    def _waitOnClose(self): # Wait on close event to be signaled by another task
        if self._closeQ is None: self._closeQ = Queue(); self._closeQ.get(); self._closeQ = None
        else: raise ValueError('some other task is already waiting on close')
        
    def _signalClose(self): # Signal the close event on this object.
        if self._closeQ is not None: self._closeQ.put(None)
            
    def _createClient(self, localParty, remoteParty, remoteTarget):
        ua = self._ua = rfc3261.UserAgent(self._stack)
        ua.app, ua.localParty, ua.remoteParty, ua.remoteTarget = self, localParty.dup(), remoteParty.dup(), remoteTarget.dup()
        
    def _scheduleRefresh(self, response, handler): # Schedule handler to be invoked before response.Expires or self._interval
        interval = int(response.Expires.value) if response.Expires else self._interval
        interval = max(interval-random.randint(5000, 15000)/1000.0, 5)
        if interval > 0:
            logger.debug('scheduling refresh after %r', interval)
            self._gen = gevent.spawn_later(interval, handler)
            
    def _scheduleRetry(self, handler): # Schedule handler to be invoked after retry_interval.
        logger.debug('scheduling retry after %r', self.options.retry_interval)
        self._gen = gevent.spawn_later(self.options.retry_interval, handler)
        
    def _closeGen(self):
        if self._gen is not None: self._gen.kill(); self._gen = None
            
    def _closeUA(self):
        if self._ua is not None: self._ua.app = None; self._ua = None
        self.app = None # remove reference
        
    def dialogCreated(self, ua, dialog): # Invoked by SIP stack to inform that UserAgent is converted to Dialog.
        if self._ua is not None: self._ua.app = None
        self._ua, dialog.app = dialog, self

       
class Register(UA):
    IDLE, REGISTERING, REGISTERED, UNREGISTERING = 'idle', 'registering', 'registered', 'unregistering' # state values
    def __init__(self, app, stack):
        UA.__init__(self, app, stack)
        self.state, self._interval = self.IDLE, self.options.register_interval
        self._createClient(self.localParty, self.localParty, self.proxy if self.proxy else self.localParty.uri)
        self._register()
        
    def close(self):
        self._closeGen()
        if self._ua is not None and self.state in (self.REGISTERING, self.REGISTERED):
            self.state = self.UNREGISTERING
            self._ua.sendRequest(self._createRequest(False))
            self._waitOnClose()
        self.state = self.IDLE
        self._closeUA()
            
    def _register(self):
        self.state = self.REGISTERING
        self._ua.sendRequest(self._createRequest())
        
    def _createRequest(self, register=True):
        m = self._ua.createRequest('REGISTER')
        m.Contact = rfc3261.Header(str(self._stack.uri), 'Contact')
        m.Contact.value.uri.user = self.options.user
        m.Expires = rfc3261.Header(str(self.options.register_interval if register else 0), 'Expires')
        return m
    
    def receivedResponse(self, ua, response):
        if self.state == self.REGISTERING:
            if response.is2xx:
                logger.info('registered with SIP server as %r', self.localParty)
                self.state = self.REGISTERED
                self._scheduleRefresh(response, self._register)
            elif response.isfinal:
                logger.warning('failed to register with response %r'%(response.response,))
                self.state = self.IDLE
                self._scheduleRetry(self._register)
        elif self.state == self.UNREGISTERING:
            if response.isfinal:
                self.state = self.IDLE
                self._signalClose()


class Caller(object):
    def __init__(self, options):
        self.options, self._ua, self._closeQueue, self.stacks = options, [], Queue(), Stacks(self, options)
        self.stacks.allow_outbound = True
        self.stacks.start()
        if self.options.register:
            self._ua.append(Register(self, self.stacks.default))
        if self.options.to:
            if self.options.send:
                self._ua.append(Message(self, self.stacks.default))
            else:
                call = Call(self, self.stacks.default)
                call.sample_rate = self.options.samplerate or 44100
                self._ua.append(call)
                call.sendInvite()
            
    def wait(self):
        self._closeQueue.get()
        
    def close(self):
        [ua.close() for ua in self._ua]
        self._ua[:] = []
        self.stacks.stop()
    
    # following callbacks are invoked by Stacks when corresponding new incoming request is received in a new UAS.
    def receivedMessage(self, ua, request):
        if not self.options.listen:
            ua.sendResponse(ua.createResponse(501, 'Not Implemented'))
        else:
            print('<<<', request.body)
            # logger.info('received: %s', request.body)
            if not [m for m in self._ua if isinstance(m, Message)]: # not found any message item
                self._ua.append(Message(self, self.stacks.default, ua, request))
            if options.auto_respond:
                ua.sendResponse(ua.createResponse(options.auto_respond, 'OK' if options.auto_respond >= 200 and options.auto_respond < 300 else 'Decline'))
            
    def receivedInvite(self, ua, request):
        if not self.options.listen:
            ua.sendResponse(ua.createResponse(501, 'Not Implemented'))
        else:
            logger.info('received INVITE')
            if self.options.auto_respond >= 200 and self.options.auto_respond < 300:
                call = Call(self, ua.stack)
                call.sample_rate = self.options.samplerate or 44100
                self._ua.append(call)
                call.receivedRequest(ua, request)
            elif self.options.auto_respond:
                ua.sendResponse(ua.createResponse(self.options.auto_respond, 'Decline'))
    
    def callClosed(self, ua):
        if ua in self._ua:
            self._ua.remove(ua)
        if not self.options.listen:
            self._closeQueue.put(None)

    def sendText(self, text): # called from a different greenlet
        for ua in self._ua:
            if hasattr(ua, 'sendText') and callable(ua.sendText):
                logger.debug('sendText on %r', ua)
                ua.sendText(text)

        
class Message(UA):
    def __init__(self, app, stack, ua=None, request=None):
        UA.__init__(self, app, stack)
        if ua is not None and request is not None: # receive message
            self._ua, ua.app = ua, self
            if self.options.proxy:
                self.proxy = rfc2396.URI('%s:%s'%(self.scheme, self.options.proxy, '' if self.options.strict_route else ';lr'))
                self._ua.routeSet = [rfc3261.Header('<%s>'%(str(self.proxy),), 'Route')]
        else:
            remoteParty = self.options.to
            remoteTarget = self.options.uri
            self._createClient(self.localParty, remoteParty, remoteTarget)
            if self.options.proxy:
                self.proxy = rfc2396.URI('%s:%s'%(self.scheme, self.options.proxy, '' if self.options.strict_route else ';lr'))
                self._ua.routeSet = [rfc3261.Header('<%s>'%(str(self.proxy),), 'Route')]
            self._ua.sendRequest(self._createRequest(self.options.send))
        
    def close(self):
        self.app.callClosed(self)
        self._closeGen()
        self._closeUA()
            
    def _createRequest(self, text):
        m = self._ua.createRequest('MESSAGE')
        m.Contact = rfc3261.Header(str(self._stack.uri), 'Contact')
        m.Contact.value.uri.user = self.options.user
        if self.options.user_agent:
            m['User-Agent'] = rfc3261.Header(self.options.user_agent, 'User-Agent')
        if self.options.subject:
            m['Subject'] = rfc3261.Header(self.options.subject, 'Subject')
        m['Content-Type'] = rfc3261.Header('text/plain', 'Content-Type')
        m.body = text
        
        return m
    
    def sendText(self, text):
        self._ua.sendRequest(self._createRequest(text))
    
    def receivedResponse(self, ua, response):
        if response.response >= 300:
            logger.info('received response: %d %s'%(response.response, response.responsetext))
    
    
class Call(UA):
    def __init__(self, app, stack):
        UA.__init__(self, app, stack)
        self.media, self.audio, self.state, self.sample_rate = None, None, 'idle', 44100
        audio, self._pcmu, self._pcma = rfc4566.SDP.media(media='audio'), rfc4566.attrs(pt=0, name='pcmu', rate=8000), rfc4566.attrs(pt=8, name='pcma', rate=8000)
        self._touchtone = rfc4566.attrs(pt=100, name='telephone-event', rate=8000)
        audio.fmt = [self._pcmu, self._pcma]
        if self.options.touchtone: audio.fmt.append(self._touchtone)
        self._audio, self._queue, self._outqueue, self._resample1, self._resample2 = [audio], [], [], None, None
        self._thqueue = None
        if self.options.recognize:
            self._thqueue = thread_Queue()
            self._th = threading.Thread(target=self.recognizer)
            self._th.daemon = False
            self._th.start()
        
    def close(self):
        logger.debug('closing the call in state=%r', self.state)
        self.app.callClosed(self)
        self._closeGen()
        if self._ua is not None:
            self._closeCall()
        self._closeUA()
        self.stopAudio()
        if self.media is not None:
            self.media.close()
            self.media = None
        if self._thqueue is not None:
            self._thqueue.put(None)
            self._thqueue = None
            self._th = None

    def recognizer(self):
        r = sr.Recognizer()
        
        energy_threshold = 300    
        pause_threshold = 0.8
        phrase_threshold = 0.3
        total_threshold = 1.0
        phrase_time = pause_time = 0.0
        frames = []
    
        while True:
            frame = self._thqueue.get()
            if frame is None:
                break
            
            if not frames:
                energy = audioop.rms(frame, 2) 
                if energy <= energy_threshold:
                    continue # ignore, not loud enough
                
            frames.append(frame)
            
            energy = audioop.rms(frame, 2) # energy of the audio signal
            if energy > energy_threshold:
                pause_time = 0.0
                phrase_time += 0.020
            else:
                pause_time += 0.020
            if phrase_time > phrase_threshold and pause_time > pause_threshold:
                logger.debug('creating audio data')
                frames.append('\x00\x00'*50) # one second of silence
                audio = sr.AudioData("".join(frames), 8000, 2)
                phrase_time = pause_time = 0.0
                frames[:] = []
                logger.debug('recognizing')
                #try: print 'text=', r.recognize_sphinx(audio)
                #except: pass
                try: print(r.recognize_google(audio))
                except: pass
    
    def sendInvite(self):
        remoteParty = self.options.to
        remoteTarget = self.options.uri
        self._createClient(self.localParty, remoteParty, remoteTarget)
        if self.options.proxy:
            self.proxy = rfc2396.URI('%s:%s%s'%(self.scheme, self.options.proxy, '' if self.options.strict_route else ';lr'))
            self._ua.routeSet = [rfc3261.Header('<%s>'%(str(self.proxy),), 'Route')]
            
        m = self._ua.createRequest('INVITE')
        m.Contact = rfc3261.Header(str(self._stack.uri), 'Contact')
        m.Contact.value.uri.user = self.options.user
        if self.options.user_agent:
            m['User-Agent'] = rfc3261.Header(self.options.user_agent, 'User-Agent')
        if self.options.subject:
            m['Subject'] = rfc3261.Header(self.options.subject, 'Subject')

        if self.options.has_sdp:
            self.media = MediaSession(app=self, streams=self._audio, listen_ip=self.options.int_ip, NetworkClass=rfc3550.gevent_Network) # create local media session
            m['Content-Type'] = rfc3261.Header('application/sdp', 'Content-Type')
            m.body = str(self.media.mysdp)
            
        self.state = 'inviting'
        self._ua.sendRequest(m)
    
    def receivedResponse(self, ua, response):
        logger.info('received response in state %r: %d %s'%(self.state, response.response, response.responsetext))
        if self.state == 'inviting':
            if response.is2xx:
                self.state = 'active'
                logger.debug('changed state to %r', self.state)
                if response.body and response['Content-Type'] and response['Content-Type'].value.lower() == 'application/sdp':
                    sdp = rfc4566.SDP(response.body)
                    if self.media:
                        if not self.options.audio_loopback and self.options.audio:
                            self.startAudio()
                        self.media.setRemote(sdp)
                    else:
                        logger.warning('invalid media received in 200 OK')
            elif response.response == 183:
                logger.debug('received early media')
                if response.body and response['Content-Type'] and response['Content-Type'].value.lower() == 'application/sdp':
                    sdp = rfc4566.SDP(response.body)
                    if self.media:
                        if not self.options.audio_loopback and self.options.audio:
                            self.startAudio()
                        self.media.setRemote(sdp)
                    else:
                        logger.warning('invalid media received in 200 OK')
            elif response.isfinal:
                self.state = 'idle'
                self.close()
                self._signalClose()
        elif self.state == 'terminating':
            if response.isfinal:
                self._signalClose()
                
    def receivedRequest(self, ua, request):
        if request.method == 'INVITE':
            if self.state == 'idle':
                if self._ua is None:
                    self._ua, ua.app = ua, self
                logger.info('received incoming call from %s', request.first('From').value)
                self.state = 'invited'
                
                req = request if request.body and request['Content-Type'] and request['Content-Type'].value.lower() == 'application/sdp' else None
                self.media = MediaSession(app=self, streams=self._audio, request=req, listen_ip=self.options.int_ip, NetworkClass=rfc3550.gevent_Network) # create local media session
                if self.media.mysdp is None:
                    self.state = 'idle'
                    logger.info('rejected incoming call with incompatible SDP')
                    ua.sendResponse(ua.createResponse(488, 'Incompatible SDP'))
                    self.close()
                elif self.options.auto_respond:
                    self._gen = gevent.spawn_later(self.options.auto_respond_after, self._autoRespond)
            else:
                logger.info('rejecting incoming call as already busy')
                ua.sendResponse(ua.createResponse(486, 'Busy Here'))
        elif request.method == 'BYE':
            if self._ua == ua:
                self.stopAudio()
                if self.state != 'idle':
                    logger.info('call closed by remote party')
                    self.state = 'idle'
                    ua.sendResponse(ua.createResponse(200, 'OK'))
                self.close()
            else:
                ua.sendResponse(ua.createResponse(481, 'Dialog Not Found'))
        elif request.method == 'ACK':
            if self._ua == ua:
                if self.state == 'accepted':
                    self.state = 'active'
                    if request.body and request['Content-Type'] and request['Content-Type'].value.lower() == 'application/sdp':
                        sdp = rfc4566.SDP(request.body)
                        if self.media:
                            self.media.setRemote(sdp)
                        else:
                            logger.warning('invalid media in processing received ACK')
                    else:
                        logger.debug('no SDP in received ACK') 
                    if not self.options.audio_loopback and self.options.audio:
                        self.startAudio()
                else:
                    logger.warning('ignoring ACK in state %r'%(self.state,))
            else:
                logger.warning('received ACK for invalid UA')
                
    def _closeCall(self):
        if self.state == 'active' or self.state == 'inviting' or self.state == 'accepted':
            if self.state == 'inviting':
                self.state = 'terminating'
                self._ua.sendCancel()
            else:
                self.state = 'terminating'
                self._ua.sendRequest(self._ua.createRequest('BYE'))
            self.stopAudio()
            self._waitOnClose()
        elif self.state == 'invited':
            self._ua.sendRequest(self._ua.createResponse(480, 'Temporarily Unavailable'))

    def _autoRespond(self):
        self._gen = None
        if self.options.auto_respond >= 200 and self.options.auto_respond < 300:
            logger.info('accepting incoming call')
            self.state = 'accepted'
            m = self._ua.createResponse(200, 'OK')
            m['Content-Type'] = rfc3261.Header('application/sdp', 'Content-Type')
            m.body = str(self.media.mysdp)
            if self.options.auto_terminate_after:
                self._gen = gevent.spawn_later(self.options.auto_terminate_after, self._autoTerminate)
        else:
            logger.info('rejecting incoming call with code %r', self.options.auto_respond)
            self.state = 'idle'
            m = self._ua.createResponse(self.options.auto_respond, 'Decline')
        self._ua.sendResponse(m)
        if self.options.auto_respond >= 300:
            self.close()
    
    def _autoTerminate(self):
        self._gen = None
        if self._ua != None:
            m = self._ua.createRequest('BYE')
            self._ua.sendRequest(m)
            gevent.spawn_later(0.5, self.close)
    
    def cancelled(self, ua, request): 
        if self._ua == ua:
            self.close()
            
    def received(self, media, fmt, packet): # an RTP packet is received. Loop it back to caller.
        if self.options.audio_loopback:
            media.send(payload=packet.payload, ts=packet.ts, marker=packet.marker, fmt=fmt)
        elif self.options.audio:
            repeated_warning(self, logger, True, 'media received %d'%(len(packet.payload),))
            self._queue.append((fmt, packet))
    
    def startAudio(self):
        logger.debug('starting audio device')
        try:
            self._ts = 0
            self._record = open('record.au', 'wb')
            if audiodev is not None and not audiodev.is_open():
                audiodev.open(self._inout, output='default', output_channels=1, input='default', input_channels=1, format='l16', 
                              sample_rate=self.sample_rate, frame_duration=20)
        except:
            logger.exception('failed to start audio device')
    
    def stopAudio(self):
        if audiodev is not None and audiodev.is_open():
            try:
                audiodev.close()
                self._record.close()
            except:
                logger.exception('failed to close audio device')
    
    def _inout(self, linear, stream_time, userdata):
        # logger.debug('audio capture %d', len(linear))
        self._ts += 160
        if self.media and (self.media.hasYourFormat(self._pcmu) or self.media.hasYourFormat(self._pcma)):
            if self._outqueue:
                # logger.debug('sending packet from out queue, not mic')
                linear8 = self._outqueue.pop(0)
            else:
                linear8, self._resample1 = audiospeex.resample(linear, input_rate=self.sample_rate, output_rate=8000, state=self._resample1)
            if self.media.hasYourFormat(self._pcmu):
                fmt, payload = self._pcmu, audioop.lin2ulaw(linear8, 2)
            elif self.media.hasYourFormat(self._pcma):
                fmt, payload = self._pcma, audioop.lin2alaw(linear8, 2)
            self.media.send(payload=payload, ts=self._ts, marker=False, fmt=fmt)
        if self._queue:
            fmt, packet = self._queue.pop(0)
            linear8 = None
            if str(fmt.name).lower() == 'pcmu' and fmt.rate == 8000 or fmt.pt == 0:
                linear8 = audioop.ulaw2lin(packet.payload, 2)
            elif str(fmt.name).lower() == 'pcma' and fmt.rate == 8000 or fmt.pt == 8:
                linear8 = audioop.alaw2lin(packet.payload, 2)
            if linear8:
                self._record.write(linear8)
                if self._thqueue is not None:
                    self._thqueue.put(linear8)
                linear, self._resample2 = audiospeex.resample(linear8, input_rate=8000, output_rate=self.sample_rate, state=self._resample2)
                # logger.debug('audio play %d', len(linear))
                return linear
        return ''
        
    def sendText(self, text):
        if self.options.touchtone and re.match(r'[0-9#*]+$', text):
            logger.debug('sending digits %r', text)
            for ch in text:
                self.sendDtmf(ch)
                gevent.sleep(0.2)
        elif self.options.textspeech and audiotts is not None:
            data = audiotts.convert(text)
            packets = [data[i:i+320] for i in range(0, len(data), 320)]
            logger.debug('sending textspeech %r size=%d packets=%d', text, len(data), len(packets))
            self._outqueue.extend(packets)
            
    def sendDtmf(self, digit):
        if self.media and self.media.hasYourFormat(self._touchtone):
            payload = repr(rfc2833.DTMF(key=digit, end=True))
            logger.debug('sending DTMF payload %r', payload)
            self.media.send(payload=payload, ts=self._ts, marker=False, fmt=self._touchtone)
    
    
if __name__ == '__main__':
    try:
        caller = Caller(options)
        
        if options.textspeech or options.touchtone:
            def readinput():
                while True: # should check if caller is valid or not?
                    gevent.socket.wait_read(sys.stdin.fileno())
                    try: line = sys.stdin.readline().strip()
                    except EOFError: break
                    caller.sendText(line)
            gevent.spawn(readinput)
            
        caller.wait()
    except KeyboardInterrupt:
        print('') # to print a new line after ^C
    except: 
        logger.exception('exception')
        sys.exit(-1)
    try:
        caller.close()
    except KeyboardInterrupt:
        print('')


