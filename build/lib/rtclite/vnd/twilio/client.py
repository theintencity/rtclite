# Copyright (c) 2016, Kundan Singh. All rights reserved. See LICENSE for details.

'''
A command line Twilio client application to create a voice pipe from your local machine to
Twilio service.

## Dependency

This uses RTMP based connection as used in twiliojs version 1.2, albeit from command line,
using the rtmpclient module of the rtclite project.

The project depends on twilio supporting library for generating the capability token.
It also depends on the py-audio project's audiodev and audiospeex modules for audio
capture, playback and speex codec.

## Get Started

To get started, first get a developer account from www.twilio.com, and note down your
account SID and auth token from the console web page. Create a new application or use an
existing one, and note down its application SID.

To see the full command line options,
  
  $ python -m rtclite.vnd.twilio.client -h

To connect the voice pipe between local machine and your Twilio service/app,

  $ python -m rtclite.vnd.twilio.client --account=ACXXXXX --token=YYYYY --app=ZZZZZ

Here account SID, auth token and application SID are mandatory, and can be supplied on
the command line. For privacy if you do not want to supply one or more of these on command
line, it will prompt you to enter those.

If the connection fails, it shows the error.

If the connection succeeds, it connects the voice pipe between the local machine and your
Twilio app.

To terminate the software, press control-C keys.

## Software Logic

Generate the capability token, and supply that in the RTMP NetConnection.
Create the NetStream objects for publish and play.
Wait for a callback from the server, which can be ignored.
Then publish the "input" stream and play the "output" stream.
After that use the voice pipe created by the two NetStream objects.

Note that rtmpclient needs multitask for concurrency, but the audiodev module
needs to be run in the regular thread. Hence, I use queues to connect the two
threads, and use those queues to exchange audio data in two directions.

## Command line options

Usage: python -m rtclite.vnd.twilio.client [options]

Options:
  -h, --help            show this help message and exit
  -v, --verbose         enable verbose mode for this module
  -q, --quiet           enable quiet mode with only critical logging
  --test                run any tests and exit
  --account=ACCOUNT     Account SID (mandatory) shown on your Twilio console
                        at www.twilio.com/console
  --token=TOKEN         Auth Token (mandatory) shown on your Twilio console at
                        www.twilio.com/console
  --app=APP             Application SID (mandatory) representing the Twilio
                        application to connect to
  --samplerate=SAMPLERATE
                        audio samplerate for capture and playback. Default is
                        48000.
  --timeout=TIMEOUT     timeout for various connection and socket operations
                        in seconds. Default is 10.0
  --url=URL             RTMP URL to connect to. Default is
                        rtmp://chunder.twilio.com/chunder
  --info=INFO           JSON formatted string containing client information
                        sent to the URL. You do not need to change this
  --version=VERSION     client version string to send to URL. Default is 1.2
                        to support flash/RTMP connection
  --no-audio-out        disable playing of audio to speaker
  --no-audio-in         disable capture of audio from microphone
  --file-out=FILE_OUT   record received voice to this writable FLV file path.
                        Default is not to record.
  --file-in=FILE_IN     send voice from this readable FLV file path. Default
                        is not to use any file. When --file-in is used, --no-
                        audio-in must also be used

'''

import sys, json, logging, threading, time
from queue import Queue as thread_Queue

from ... import multitask
from ..adobe.rtmpclient import NetConnection, NetStream, Message, Header, FLVReader, FLVWriter, logger as logger_rtmpclient

try: from twilio.util import TwilioCapability
except ImportError: print('please install twilio module from https://github.com/twilio/twilio-python'); raise
try: import audiodev, audiospeex
except ImportError: print('please install py-audio modules from https://github.com/theintencity/py-audio'); raise


logger = logging.getLogger('twilio.client')

default_info = json.dumps({"p":"browser","v":"1.2","h":"5c1f1e8","browser":{"userAgent":"rtclite/1.0","platform":"MacIntel"},"plugin":"flash","flash":{"v":{"major":22,"minor":0,"release":0}}})

def connect(queue_mic, queue_spk, account, token, app,
            url="rtmp://chunder.twilio.com/chunder", info=default_info, version="1.2", timeout=10,
            audio_in=True, audio_out=True, file_in=None, file_out=None):
    
    capability = TwilioCapability(account, token)
    capability.allow_client_outgoing(app)
    ctoken = capability.generate()
    
    nc = NetConnection()

    params = [ctoken, None, '', info, account, version]
    result = yield nc.connect(url, timeout, *params)
    if not result: raise StopIteration('Failed to connect %r: %r'%(url, nc.error))
    logger.info('connected to %r with args %r', url, params)
    
    ns1 = yield NetStream().create(nc, timeout=timeout)
    if not ns1: raise StopIteration('Failed to create publish stream')
    
    yield nc.client.call('startCall')
    
    ns2 = yield NetStream().create(nc, timeout=timeout)
    if not ns2: raise StopIteration('Failed to create play stream')

    # get the callsid, how is this used?
    cmd = yield nc.client.queue.get(timeout=timeout)
    if cmd.name == 'callsid': logger.debug('callsid() args=%r', cmd.args)
        
    result = yield ns1.publish('input', timeout=timeout)
    if not result: yield nc.close(); raise StopIteration('Failed to publish stream')
    
    result = yield ns2.play('output', timeout=timeout)
    if not result: yield nc.close(); raise StopIteration('Failed to play stream')

    def stream_receiver(ns2, queue_spk, file_writer):
        try:
            while True:
                msg = yield ns2.stream.queue.get(timeout=timeout, criteria=lambda x: x is None or x.type in (Message.AUDIO, Message.VIDEO))
                if queue_spk is not None and msg.type == Message.AUDIO:
                    queue_spk.put(msg)
                if file_writer is not None:
                    yield file_writer.put(msg)
        except multitask.Timeout: logger.debug('timedout')
            
    def stream_sender_from_device(ns1, queue_mic):
        try:
            while True:
                try:
                    msg = queue_mic.get(block=False)
                    yield ns1.stream.send(msg)
                except Empty: pass
                yield multitask.sleep(0.020)
        except multitask.Timeout: logger.debug("timeout")
    
    def stream_sender_from_file(ns1, file_reader):
        try:
            while True:
                try:
                    msg = yield file_reader.get(timeout=timeout)
                    if msg:
                        yield ns1.stream.send(msg)
                except multitask.Timeout: break
                yield multitask.sleep(0.020)
        except multitask.Timeout: logger.debug('timedout')
    
    writer = reader = None
    gens = []
    if audio_out or file_out:
        if file_out: writer = yield FLVWriter().open(file_out)
        gens.append(stream_receiver(ns2, queue_spk if audio_out else None, writer))
        multitask.add(gens[-1])
    if file_in:
        reader = yield FLVReader().open(file_in)
        gens.append(stream_sender_from_file(ns1, reader))
        multitask.add(gens[-1])
    elif audio_in:
        gens.append(stream_sender_from_device(ns1, queue_mic))
        multitask.add(gens[-1])

    try:
        while True:
            try:
                logger.debug('waiting on connection to terminate')
                yield nc.client.close_queue.get(timeout=60) # if the remote side terminates
                logger.debug('received closed connection')
                break
            except multitask.Timeout: pass
    except (KeyboardInterrupt, GeneratorExit): # else wait until duration
        logger.debug('exiting')
    
    if reader is not None: reader.close()
    if writer is not None: writer.close()
    for gen in gens:
        try: gen.close()
        except: pass
    gens[:] = []
    
    yield nc.close()

    raise StopIteration(None)


def main(*args, **kwargs):
    def connector():
        result = yield connect(*args, **kwargs)
        if result:
            logger.info('%s', result)
    
    multitask.add(connector())
    multitask.run()
    

# The audio procedure that opens the audio device for input and output
def audio_proc(queue_mic, queue_spk, samplerate=48000, audio_in=True, audio_out=True):
    
    def inout(linear, stream_time, userdata):
        try:
            if audio_in:
                linear, userdata[2] = audiospeex.resample(linear, input_rate=samplerate, output_rate=16000, state=userdata[2])
                payload, userdata[3] = audiospeex.lin2speex(linear, sample_rate=16000, state=userdata[3])
                payload = '\xb2' + payload
                userdata[4] += 20  # millisec
                header = Header(time=userdata[4], size=len(payload), type=Message.AUDIO, streamId=0)
                msg = Message(header, payload)
                queue_mic.put(msg)
        except: logger.exception('audio inout exception: resample, encode')
        
        try:
            # ignore mic input (linear) for now
            if audio_out:
                msg = queue_spk.get(block=False)
                first, payload = msg.data[0], msg.data[1:]
                if first == '\xb2': # speex
                    linear, userdata[0] = audiospeex.speex2lin(payload, sample_rate=16000, state=userdata[0])
                    linear, userdata[1] = audiospeex.resample(linear, input_rate=16000, output_rate=samplerate, state=userdata[1])
                    return linear
        except Empty: pass
        except: logger.exception('audio inout exception: decode, resample')
        return ''
    
    if audio_in or audio_out:
        logger.info('opening audio device with samplerate=%r, audio_in=%r, audio_out=%r', samplerate, audio_in, audio_out)
        audiodev.open(inout, output='default', output_channels=1, input='default', input_channels=1,
                      format='l16', sample_rate=samplerate, frame_duration=20, userdata=[None, None, None, None, 0])
    try:
        while True:
            time.sleep(10)
    finally:
        if audiodev.is_open():
            logger.info('closing audio device')
            audiodev.close()
    

if __name__ == '__main__':
    from optparse import OptionParser, OptionGroup
    parser = OptionParser()
    parser.add_option('-v', '--verbose',   dest='verbose', default=False, action='store_true', help='enable verbose mode for this module')
    parser.add_option('-q', '--quiet',     dest='quiet', default=False, action='store_true', help='enable quiet mode with only critical logging')
    parser.add_option('--test', dest='test', default=False, action='store_true', help='run any tests and exit')

    parser.add_option('--account', dest='account', default=None, help='Account SID (mandatory) shown on your Twilio console at www.twilio.com/console')
    parser.add_option('--token', dest='token', default=None, help='Auth Token (mandatory) shown on your Twilio console at www.twilio.com/console')
    parser.add_option('--app', dest='app', default=None, help='Application SID (mandatory) representing the Twilio application to connect to')
    
    parser.add_option('--samplerate', dest='samplerate', default=48000, type=int, help='audio samplerate for capture and playback. Default is 48000.')
    parser.add_option('--timeout', dest='timeout', default=10, help='timeout for various connection and socket operations in seconds. Default is 10.0')
    parser.add_option('--url', dest='url', default=None, help='RTMP URL to connect to. Default is rtmp://chunder.twilio.com/chunder')
    parser.add_option('--info', dest='info', default=None, help='JSON formatted string containing client information sent to the URL. You do not need to change this')
    parser.add_option('--version', dest='version', default=None, help='client version string to send to URL. Default is 1.2 to support flash/RTMP connection')
    parser.add_option('--no-audio-out', dest='audio_out', default=True, action='store_false', help='disable playing of audio to speaker')
    parser.add_option('--no-audio-in', dest='audio_in', default=True, action='store_false', help='disable capture of audio from microphone')
    parser.add_option('--file-out', dest='file_out', default=None, help='record received voice to this writable FLV file path. Default is not to record.')
    parser.add_option('--file-in', dest='file_in', default=None, help='send voice from this readable FLV file path. Default is not to use any file. When --file-in is used, --no-audio-in must also be used')
    
    (options, args) = parser.parse_args()
    
    if options.test: sys.exit() # no tests
    
    if options.file_in and options.audio_in:
        print('when --file-in is used, --no-audio-in must also be used')
        sys.exit()
    
    params = dict(account=options.account, token=options.token, app=options.app,
                  timeout=options.timeout, audio_out=options.audio_out, audio_in=options.audio_in,
                  file_out=options.file_out, file_in=options.file_in)
    if options.url: params['url'] = options.url
    if options.info: params['info'] = options.info
    if options.version: params['version'] = options.version

    try:
        if not params['account']:
            params['account'] = input('Account SID: ').strip()
            if not params['account']: raise RuntimeError
        if not params['token']:
            import getpass
            params['token'] = getpass.getpass('Auth Token: ').strip()
            if not params['token']: raise RuntimeError
        if not params['app']:
            params['app'] = input('Application SID: ').strip()
            if not params['app']: raise RuntimeError
    except:
        print('missing one or more mandatory parameters: account, token or app')
        sys.exit()
    
    logging.basicConfig()
    logger.setLevel(options.quiet and logging.CRITICAL or options.verbose and logging.DEBUG or logging.INFO)
    logger_rtmpclient.setLevel(options.quiet and logging.CRITICAL or options.verbose and logging.DEBUG or logging.INFO)

    # separate thread to do connection using multitask and rtmpclient modules.
    queue_mic, queue_spk = thread_Queue(), thread_Queue()
    thread = threading.Thread(target=main, args=(queue_mic, queue_spk), kwargs=params)
    thread.daemon = True
    thread.start()
    
    # main thread to do audio processing. communicate using queue.
    try:
        audio_proc(queue_mic=queue_mic, queue_spk=queue_spk,
                   samplerate=options.samplerate, audio_in=options.audio_in, audio_out=options.audio_out)
    except KeyboardInterrupt:
        logger.info('keyboard interrupt')
    except:
        import traceback
        traceback.print_exc()
