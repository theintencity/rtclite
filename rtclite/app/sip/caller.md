# Command line SIP endpoint

This article describe the command line SIP endpoint.

> *module*: rtclite.app.sip.caller, 
> file [caller.py](caller.py), also see [blog post](http://blog.kundansingh.com/2016/07/how-to-make-phone-calls-from-command.html), [video demo](https://youtu.be/eiepNTLZCvU)

### Motivation

It is useful in a number of scenarios, that cannot easily be done using existing user interface based web, 
installed or mobile apps, such as:

* dialing out a phone number from command line, 
* performing automated VoIP system tests, 
* showing quick demos of communication systems, or
* experimenting with media processing on the voice path, e.g., for speech recognition, recording or text-to-speech.

### Software Structure

The `caller` module has a `Caller` class that implements all the application logic. It uses various 
`rtclite.std.ietf` modules such as `rfc2361`, `rfc3550`, `rfc4566` and `rfc2833` for SIP, RTP, SDP and DTMF,
and the external `py-audio` project's `audiodev`, `audiospeex` and `audiotts` modules for media processing. 
The individual protocol modules such as `rfc3261` or `rfc3550` delegate the concurrency model to the main 
application, which uses `gevent` for concurrency.

A `Caller` object is created based on the command line options. It creates SIP listening endpoint,
and one or more SIP user agents (UAC or UAS)
for registration, message or call. It has the `wait` function which waits
for the requested function to complete. The individual user agent objects for `Call`, `Message` or `Register`
take care of sending or receiving the appropriate messages. A separate task is created to captrue user input
on `stdin`, which is then delivered to the caller object, e.g., to send as text, DTMF or text-to-speech in the voice
path.

### Using the Caller class

The following code snippet shows how to make an outbound call in your software. First import the relevant
modules. We also change the `lineending` of the SDP (rfc4566) module to use LF instead of CRLF, to workaround
wrong SIP implementation of the VoIP provider.
```
from rtclite.app.sip.caller import Caller, default_options
from rtclite.std.ietf.rfc2396 import Address, URI
from rtclite.std.ietf import rfc4566
rfc4566.lineending = '\n'
```
You should set the logging level to `INFO` to see the call progress. Alternatively, set it to `DEBUG` for full
trace.
```
import logging
logging.basicConfig(level=logging.INFO)
```
Then configure the options including the target address in the `To` header and request `URI`. Additionally
change the `samplerate` to match your machine's capture sample rate, and change other options.
```
options = default_options()
options.to = Address('sip:18007741500@tollfree.alcazarnetworks.com')
options.uri = URI('sip:18007741500@tollfree.alcazarnetworks.com')
options.samplerate = 48000
options.domain = 'example.net'
options.use_lf = True
```
Finally, create the caller object with these options, and wait for it to complete.
You can press the `ctrl-C` keys to terminate this wait. When done, close the caller object,
so that it closes the call.
```
caller = Caller(options)
try: caller.wait()
except: pass
caller.close()
```
These steps are automatically done when you invoke the `caller.py` module from the command line,
as described later on this page. Additionally, you can change other options to further configure, or
use the `caller` object differently in your software. The options are also described later on this page.


## Getting Started

### Dependencies

The software depends on Python 2.7. Make sure to install or use this version of Python.
```
$ python --version
Python 2.7.11
```
Download the `rtclite` source repository, and the `py-audio` dependency.
```
$ git clone https://github.com/theintencity/rtclite.git
$ git clone https://github.com/theintencity/py-audio.git
```
Also install the gevent dependency.
```
$ pip install gevent
```
On OS X, you can use the pre-built binaries of the voice processing modules as shown below. 
For Linux, you will need to compile the software to create those binary modules. Make sure that 
the modules `.so` files are in the `py-audio` directory.
```
$ tar -zxvf py-audio/py-audio1.0-python2.7-*.tgz
$ cp py-audio1.0-*/*.so py-audio/
```
Set the PYTHONPATH to include rtclite and py-audio projects.
```
$ export PYTHONPATH=rtclite:py-audio
```
Then start the caller module with `-h` option to see its command line usage.
```
$ python -m rtclite.app.sip.caller -h
```
This will show the complete set of command line options. More details are described later, but one of `--to` 
or `--listen` options is required, to make or receive call. Once the software is started, it will attempt to
make or receive call. In listen mode, the received calls are automatically answered.

The software is terminated by pressing `ctrl-C`. Before termination, it performs any cleanup
such as to close an ongoing call or to unregister a previous registration.

### Command Line Options

The command line options are explained below.
```
Usage: caller.py [options]

Options:
  -h, --help            show this help message and exit
  -v, --verbose         enable verbose mode for this module
  -q, --quiet           enable quiet mode with only critical logging
```
The verbose mode is useful to enable logging when something does not work. If you have a 
bug report to file, please include the logging trace generated using `-v` option in your ticket.

**Network**: Use these options for network configuration.
```
    --int-ip=INT_IP     listening IP address for SIP and RTP. Use this option
                        only if you wish to select one out of multiple IP
                        interfaces. Default "0.0.0.0"
    --ext-ip=EXT_IP     IP address to advertise in SIP/SDP. Use this to
                        specify external IP if running on EC2. Default is to
                        use "--int-ip" if supplied or any local interface,
                        which is "192.168.1.5"
```
Generally you do not need to change the internal (listening) or external IP addresses
as the software automatically picks the default IP address. However, if you have multiple
IP interfaces, and want to prefer one over another, then use the `int-ip` option. If your
machine is behind a unrestricted NAT, such running on Amazon EC2, where the IP interface 
is different than the external public IP address, then you should specify the external
IP address using the `ext-ip` option so that various protocol modules of SIP/SDP use this external
IP address to advertise signaling and media reachability. 
```
    --transport=TRANSPORTS
                        the transport type is one of "udp", "tcp" or "tls".
                        Default is "udp"
```
Typically, SIP over UDP is enough for many applications. I have not tested the software extensively for 
SIP over TCP or TLS transports. If you don't specify the transport, it will prefer UDP, but will use NAPTR
resolved transport if possible.
```
    --port=PORT         listening port number for SIP UDP/TCP. TLS is one more
                        than this. Default is 5092
```
You can also use 0 to pick a new random port number for local SIP listening endpoint.
```
    --listen-queue=LISTEN_QUEUE
                        listen queue for TCP socket. Default is 5
    --max-size=MAX_SIZE
                        size of received socket data. Default is 4096
```
These options usually do not need to be altered. They apply to the `socket` function calls
when listening for incoming connection or packet.
```
    --fix-nat           enable fixing NAT IP address in Contact and SDP
```
This changes the SIP `Contact` header in the received INVITE or MESSAGE request or response to
reflect the sender's IP address and port number. This may be useful if remote side is behind
a NAT, and sends private IP address in its `Contact` header.

**SIP**: Use these options for SIP configuration.
```
    --user-agent=USER_AGENT
                        set this as User-Agent header in outbound SIP request.
                        Default is empty "" to not set
    --subject=SUBJECT   set this as Subject header in outbound SIP request.
                        Default is empty "" to not set
```
Setting the `User-Agent` or `Subject` header may be useful for server-side logging on the 
other side. Furthermore, the `Subject` header may be shown to the receiver in the 
incoming call prompt. Generally, these are not needed.
```
    --user=USER         username to use in my SIP URI and contacts. Default is
                        "*login*"
    --domain=DOMAIN     domain portion of my SIP URI. Default is to use local
                        hostname, which is "*hostname*"
```
By default, the software picks the local username and domain from the machine's user login and
hostname. These are used in the SIP `From` header. If the remote side requires a fully-qualified
domain name, then you should specify that using the `domain` option. If remote side requires
authentication then you may have to set the `user` option to your SIP account username, in addition
to the `authuser` option described later.
```
    --proxy=PROXY       IP address of the SIP proxy to use. Default is empty
                        "" to mean disable outbound proxy
    --strict-route      use strict routing instead of default loose routing
                        when proxy option is specified
```
By default the software uses the `uri` option to send the outgoing request. However, you can 
specify an outbound proxy different than the `uri`, if your system is setup to require an
outbound proxy. This must be an IP address with optional port number, e.g., "192.1.2.3:5062", 
and not a URI. All outbound requests are sent to that address. By default, it uses loose-route to the
proxy as recommended by RFC 3261, but that can be changed using the `strict-route` option. 
```
    --authuser=AUTHUSER
                        username to use for authentication. Default is to not
                        use authentication
    --authpass=AUTHPASS
                        password to use for authentication. Only used together
                        with --authuser
```
Some VoIP providers require the full *user@domain* as the authentication username. These options
correspond to your SIP login credentials, if applicable. They are used in registration as well as 
outbound call, whenever needed. If these are not supplied, and the remote side challenges for
authentication, the request is failed.
```
    --to=TO             the target SIP address, e.g., '"Henry Sinnreich"
                        <sip:henry@iptel.org>'. This is mandatory
    --uri=URI           the target request-URI, e.g., "sip:henry@iptel.org".
                        Default is to derive from the --to option
```
The `to` option is mandatory for using the software in caller mode to make an outbound call
or message. Especially, this is required if there is no `listen` option supplied.
The difference between the `To` header and the request `URI` is explained in RFC 3261.
Note that the NAPTR and SRV looksup are performed as per RFC 3263 to derive the actual target
address to send SIP request to.
```
    --listen            enable listen mode with or without REGISTER and wait for
                        incoming INVITE or MESSAGE
```
Either the `to` or the `listen` option must be present. The `to` option creates an outbound request, whereas
the `listen` option waits for inbound requests, e.g., to receive call or message. The `listen`
option may be used together with `to` in which case it will send the outbound request, but also
wait for incoming future requests, such as for IMs and future incoming calls.
```
    --register          send REGISTER to SIP server. This is used with --listen to
                        receive incoming INVITE or MESSAGE and with --to if the
                        SIP server requires registration for outbound calls
    --register-interval=REGISTER_INTERVAL
                        registration refresh interval in seconds. Default is
                        3600
    --retry-interval=RETRY_INTERVAL
                        retry interval in seconds to re-try if register or
                        subscribe fails. Default is 60
```
These options do outbound SIP registration to the
application SIP server available at `domain` or `proxy` addresses.
```
    --send=SEND         enable outbound instant message. The supplied text
                        with this option is sent in outbound MESSAGE request
```
Send an outbound instant message instead of a call request using the supplied text in this option.
When used in conjunction with `textspeech` option, it enables interactive messaging session.
```
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
```
These options enable non-interactive actions useful during testing. For example, to automatically
respond to incoming call or message, either immediately or after sometime, or to terminate the 
call after sometime.
```
    --use-lf            use LF as line ending instead of default CRLF
```
Some VoIP providers or systems do not correctly handle the CRLF as line endings in SIP and SDP
messages. Use this option to work-around those systems by always using LF "\n" instead of CRLF "\r\n"
as line endings. You would know such a problem in the remote system 
if you get a response such as incorrect content-length
in outbound request generated by this software.

**Media**: Use these options for media configuration.
```
    --no-sdp            disable sending SDP in outbound INVITE
```
This may be useful for some testing, where you do not want to send SDP in the first INVITE.
The media stack is not created when the INVITE is sent out when this option is used.
```
    --no-audio          disable audio in a call
```
Sometimes you may want to test only the SIP/SDP signaling path without any voice path. 
You can use `no-audio` to disable the use of `py-audio` project's modules. The SDP still contains
the voice codecs and transport information, but only the audio capture and playback are disabled.
```
    --audio-loopback    enable audio loopback mode where this agent sends back
                        the received audio to the other end
```
The audio loopback is useful for testing the voice path in automated testing of the remote side.
This software acts as the loopback for the voice path, sending the receive audio back to the
remote side in the call.
```
    --samplerate=SAMPLERATE
                        audio samplerate for capture and playback. Default is
                        44100. Use 48000 on OS X
```
Some machines or audio stacks have limited set of allowed sampling rate, e.g.,
on Mac OS X, it may be 48000. If using the default capture sample rate of 44100, it
fails to open the audio input device. Use this option to specify the non-default capture
rate. This rate applies to the audio device input and output, and is different than the 
codec sample rate.
```
    --no-touchtone      disable sending touch tone (DTMF) digits when typed.
                        By default touch tone sending is enabled
```
By default, touch tone input is enabled. Any digits, or star (*) or hash (#) that you type
on the terminal after the call is established is sent out as DTMF touch tone using RFC 2833
in the media path. It is also signaled in the SDP as the touchtone voice codec. You can disable
this feature, e.g., if the remote side does not correctly work when touchtone is enabled in SDP.
```
    --recognize         enable speech recognition to show the received audio
                        as text
    --textspeech        enable text to speech to send typed text as audio. If
                        touchtone is also enabled, it distinguishes between
                        typed digits and non-digits to determine whether to
                        use touchtone or textspeech for the typed text.
```
The speec recognition and synthesis modules are enabled using the `audiotts` and
`speech_recognition` modules. These modules are not loaded unless one of these options is used.
The speech recognition currently uses the Google's engine, whereas the text-to-speech is based
on flite project. The recognized spoken voice in the received media path is printed as text 
periodically, and the typed text (if not just digits) are sent out as spoken voice in the 
sent media path.

## Common Tasks

### How to send/receive message or call using included SIP server?

The [server](server.py) module has basic SIP registration and proxy server that you can register with.
For testing, open three terminals - for the server and two endpoints. The two endpoints will use
names of `alice` and `bob`.

On the first terminal, start the server. You may optionally supply the `-d` option to enable
debug-level logging. The server listens on default port 5060 for UDP, can be changed to listen on
other transport using command line option, and can be terminated using `ctrl-C`.
```
$ python -m rtclite.app.sip.server -d
09:12:56.668 sip.api INFO - starting agent on 0.0.0.0:5060 with transport udp
```

On the second terminal, start this software as follows. Replace the `domain` option to the
server hostname or IP address if the server is not running on local host.
```
$ python -m rtclite.app.sip.caller --listen --register --user=alice --domain=localhost
09:10:02.575 caller INFO - registered with SIP server as sip:alice@localhost
<<< hello
<<< how are you?
I am good, and you?
<<< good thank you
^CKeyboardInterrupt
```
The `listen` and `register` options tell the software to register with the SIP server of
domain `localhost` with the local user's name of `alice` and wait for incoming requests.

On the third terminal start this software as follows. Use the `send` option to initiate an
outbound instant message request, instead of the default call request. Again, the
`listen` and `register` options tell the software to register with the SIP server and wait
for incoming requests, in addition to sending the outbound request. If testing on the same
machine, make sure to sue a different listening `port` than the first instance.
```
$ python -m rtclite.app.sip.caller --listen --register --user=bob --domain=localhost \
         --port=5094 --to=sip:alice@localhost --send=hello
09:10:04.736 caller INFO - registered with SIP server as sip:bob@localhost
how are you?
<<< I am good, and you?
good thank you
are you still there?
09:10:30.775 caller INFO - received response: 480 Temporarily Unavailable
^CKeyboardInterrupt
```
The above examples also show an example text chat conversation, where the user types a
message on the terminal, and sees the received message. It also shows what happens when a
message cannot be delivered.

To test out a voice call, use the similar approach but do not specify the `send` option.
Also, depending on your machine's audio device, you may need to specify the `samplerate` option.
The command line for the second terminal is shown below.
```
$ python -m rtclite.app.sip.caller --listen --register --user=alice --domain=localhost \
         --samplerate=48000
```
The command line for the third terminal is shown below. It does not use `listen` or `register`
because it does not expect any incoming call. The `user` and `domain` options are also skipped
so that it picks up the default user name and machine name.
```
$ python -m rtclite.app.sip.caller --to=sip:alice@localhost  --port=5064 --samplerate=48000
```

The SIP server we use in the above example does not require authentication. For servers that
require authentication, you may also need to supply the `authuser` and `authpass` options.

### How to send/receive call using iptel.org SIP service?

The [iptel.org](http://www.iptel.org/service) site has a free SIP service that you can register for.
For testing, register two separate accounts. The following example, assume the registration usernames
as `alice` and `bob` and passwords as `alicepass` and `bobpass` respectively. The process described
here are generally true for other SIP providers too. 

This service requires authentication hence `authuser` and `authpass` are supplied. 
The local test machine is Mac OS X hence `samplerate` of 48000 is used.

First, try the `echo` or `music` target to test the echo or music sound. For example, replace `echo` with
`music` below to test the received sound only.
```
$ python -m rtclite.app.sip.caller --to=sip:echo@iptel.org \
         --user=alice --domain=iptel.org --authpass=alicepass --authuser=alice --samplerate=48000
```

Open two terminals. On the first terminal, start the software as a listener registering as user `bob`.
```
$ python -m rtclite.app.sip.caller --listen --register \
         --user=bob --domain=iptel.org --authpass=bobpass --authuser=bob --samplerate=48000
```
On the second terminal, start the software as a caller as user `alice` calling out to `bob`.
```
$ python -m rtclite.app.sip.caller --to=sip:bob@iptel.org \
         --user=alice --domain=iptel.org --authpass=alicepass --authuser=alice --samplerate=48000
```
Press `ctrl-C` on both terminals when the call needs to be stopped.

Similar steps can be used to call out to other targets or numbers on this SIP provider.
For example, you can register another SIP user agent such as X-lite as the other user, and make or
receive call between this software and X-lite.

### How to dial phone numbers using a VoIP provider?

There are several VoIP providers that allow dialing out phone numbers either free with in the 
United States or for a small cost. For example, [Alcazar Networks](https://www.alcazarnetworks.com/termination_tf.php)
offers free toll free number termination service for all your calls in the US, without 
registration. 

```
$ python -m rtclite.app.sip.caller --to=sip:18007741500@tollfree.alcazarnetworks.com \
         --use-lf --samplerate=48000 --domain=example.net
```
When not using authentication, you do not need to supply the `authuser` or
`authpass` options. However, you may still need to supply the `domain` option if your machine's
hostname is not set to fully qualified domain name, to avoid failure from this VoIP service.
I use a dummy but valid domain for local user. I also use `use-lf` option to work-around the
line-ending problem with this provider.

Once the call is connected, you can hear the automated response, and can enter the touch tone
digits on the terminal. The following shows the log traces for call progress, and various 
user input via touch-tone. When done, you can press the ctrl-C keys to terminate the call. 
While the call is ongoing, you will be able to hear and speak through your local 
machine's audio devices.
```
$ python -m rtclite.app.sip.caller ...
10:13:38.835 caller INFO - received response in state 'inviting': 100 trying -- your call is important to us
10:13:39.990 caller INFO - received response in state 'inviting': 183 Session Progress
10:13:40.789 caller INFO - received response in state 'inviting': 200 OK
10:13:41.409 caller WARNING - media received 160
2
10:13:51.414 caller WARNING - media received 160 -- repeated 500 times
1
123456#
10:14:01.434 caller WARNING - media received 160 -- repeated 500 times
^CKeyboardInterrupt
10:14:06.864 caller INFO - received response in state 'terminating': 200 OK
```
For non-tollfree numbers, you typically need to signup and pay for the call. Hence, authentication
(and sometimes SIP registration) is required.

### How to enable media processing on the voice path?

The text-to-speech feature uses the external `py-audio` project's `audiotts` module. The installation is described earlier
on this page. The speech recognition feature needs the [speech_recognition](https://github.com/Uberi/speech_recognition) 
module. You can install it as follows.
```
pip install SpeechRecognition
```
You can enable speech recognition and text-to-speech in a call as follows. The other options are not shown for brevity. 
It is also recommended to use `quiet` option to avoid call information logging.
```
$ python -m rtclite.app.sip.caller ... --quiet --recognize --textspeech
```
This enables speech recognition and synthesis. The received voice is converted to text using Google engine,
and printed on the terminal.
Any typed text is sent out as spoken voice.
Due to the way current IVRs are processed and the delay in recognizing the speech, often times the prompts are repeated
before you get the recognized text printed.
