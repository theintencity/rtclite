# Copyright (c) 2007-2011, Kundan Singh. All rights reserved. See LICENSE for details.

'''
Implement common utilities that are needed in more than one modules.

These utility functions are important, do not exist in standard Python library,
and cannot logically be put under a single reference implementation, e.g.,
logging, timer, getting local IP address, etc.
'''


import os, socket, time


#--------------------------------------
# LOGGING
#--------------------------------------

import logging, os

# ColorizingStreamHandler
# Copyright (C) 2010, 2011 Vinay Sajip. All rights reserved.
# Copyright (C) 2011 Kundan Singh. All rights reserved.
# See http://plumberjack.blogspot.com/2010/12/colorizing-logging-output-in-terminals.html

class ColorizingStreamHandler(logging.StreamHandler):
    # color names to indices
    color_map = dict(list(zip('black red green yello blue magenta cyan white'.split(), list(range(8)))))
    #levels to (background, foreground, bold/intense)
    level_map = { logging.DEBUG: (None, 'blue', True), logging.INFO: (None, 'white', False),
        logging.WARNING: (None, 'yellow', True), logging.ERROR: (None, 'red', True),
        logging.CRITICAL: ('red', 'white', True), } if os.name == 'nt' else {
        logging.DEBUG: (None, 'black', False), logging.INFO: (None, 'blue', False),
        logging.WARNING: (None, 'red', False), logging.ERROR: (None, 'red', False),
        logging.CRITICAL: ('red', 'white', True), }
    csi, reset = '\x1b[', '\x1b[0m'

    @property
    def is_tty(self):
        isatty = getattr(self.stream, 'isatty', None)
        return isatty and isatty()

    def emit(self, record):
        try:
            message, stream = self.format(record), self.stream
            if not self.is_tty: stream.write(message)
            else: self.output_colorized(message)
            stream.write(getattr(self, 'terminator', '\n'))
            self.flush()
        except (KeyboardInterrupt, SystemExit): raise
        except: self.handleError(record)

    if os.name != 'nt':
        def output_colorized(self, message):
            self.stream.write(message)
    else:
        import ctypes, re
        ansi_esc = re.compile(r'\x1b\[((?:\d+)(?:;(?:\d+))*)m')

        nt_color_map = dict(enumerate((0x00, 0x04, 0x02, 0x06, 0x01, 0x05, 0x03, 0x07)))
        def output_colorized(self, message):
            parts, write, h, fd = self.ansi_esc.split(message), self.stream.write, None, getattr(self.stream, 'fileno', None)
            if fd is not None:
                fd = fd()
                if fd in (1, 2): # stdout or stderr
                    try: h = ctypes.windll.kernel32.GetStdHandle(-10 - fd)
                    except: # sometimes it throws "global name ctypes not defined" on Windows.
                        self.stream.write(message)
                        return
            while parts:
                text = parts.pop(0)
                if text: write(text)
                if parts:
                    params = parts.pop(0)
                    if h is not None:
                        params = [int(p) for p in params.split(';')]
                        color = 0
                        for p in params:
                            if 40 <= p <= 47: color |= self.nt_color_map[p - 40] << 4
                            elif 30 <= p <= 37: color |= self.nt_color_map[p - 30]
                            elif p == 1: color |= 0x08 # foreground intensity on
                            elif p == 0: color = 0x07 # reset to default color
                            else: pass # error condition ignored
                        ctypes.windll.kernel32.SetConsoleTextAttribute(h, color)

    def colorize(self, message, record):
        if record.levelno in self.level_map:
            bg, fg, bold = self.level_map[record.levelno]
            params = []
            if bg in self.color_map: params.append(str(self.color_map[bg] + 40))
            if fg in self.color_map: params.append(str(self.color_map[fg] + 30))
            if bold: params.append('1')
            if params: message = ''.join((self.csi, ';'.join(params), 'm', message, self.reset))
        return message

    def format(self, record):
        message = logging.StreamHandler.format(self, record)
        if self.is_tty: # Don't colorize any traceback
            parts = message.split('\n', 1)
            parts[0] = self.colorize(parts[0], record)
            message = '\n'.join(parts)
        return message


def _test_ColorizingStreamHandler():
    '''Test the ColorizingStreamHandler class.'''
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(ColorizingStreamHandler())
    logging.debug('DEBUG')
    logging.info('INFO')
    logging.warning('WARNING')
    logging.error('ERROR')
    logging.critical('CRITICAL')



_repeats = {}

def repeated_warning(context, logger, condition, message, count=500):
    '''
    Allows displaying repeated warning messages only onces and then periodically every count times
    instead of every time. This is useful for displaying media path related warning messages without overloading
    the log.
    
    @param  context: the context under which this warning happened. The repeat count is stored for each context
    for each message.
    @param logger: the logger object to use as logger.warning
    @param condition: the condition (boolean) for display or count the warning, and false to clear the warning.
    @param message: the error message should be exactly the same each time in repeated invocations.
    @param count: how many times to ignore for repeated display.
    @return: boolean indicating whether the message was displayed or not. If there are more details that change
    in each call to this within an error message, then the return value should be used to determine whether
    more details needs to be printed or not.
    '''
    global _repeats
    if context not in _repeats: messages = _repeats[context] = {}
    else: messages = _repeats[context]
    result = False
    if condition:
        if message not in messages:
            logger.warning(message)
            messages[message], result = 0, True
        elif messages[message] >= count:
            logger.warning(message + ' -- repeated %r times', messages[message])
            messages[message], result = 0, True
        else:
            messages[message] += 1
    elif message in messages:
        if messages[message] > 0:
            logger.warning(message + ' -- repeated %r times', messages[message])
            result = True
        del messages[message]
    return result


#--------------------------------------
# TIMER
#--------------------------------------


class Timer(object):
    '''Abstract Timer object.
    
    This defines the interface for sub-classes such as multitask_Timer or gevent_Timer.
    
    An application creates a timer by supplying a handler object. It starts the timer by supplying the
    delay in seconds, and when the timer expires, the timedout(timer) callback on the handler object
    is invoked. The application may stop the timer before it expires.
    
    First, import the right module for the sub-class.
    
    >>> from rtclite import multitask
    >>> from rtclite.multitask import multitask_Timer as Timer
    
    The handler object must have a "timedout(...)" method that takes the "timer" argument.
    
    >>> class MyApp(object):
    ...     def timedout(self, timer):
    ...         print 'timer %r triggered'%(timer,)
    >>> myapp = MyApp()
    
    Create a timer object from the Timer sub-class.
    
    >>> timer = Timer(app=myapp)  # construct a new timer object
    >>> timer.start(delay=2.5)  # will trigger after 2.5 seconds, i.e., 2500 ms
    
    Simply call stop, to stop the timer before it expires.
    
    >>> timer.stop()

    To restart the timer with the previous delay that was set in previous call to start, simply
    call start without any delay.
    
    >>> timer.start()
    
    @see multitask_Timer, gevent_Timer
    '''
    _index = 0
    def __init__(self, app):
        self.app, self.delay, self.running = app, 0., False
        self._index = Timer._index; Timer._index += 1
    
    def start(self, delay=None):
        self.running = True
        raise RuntimeError('not implemented')
    
    def stop(self):
        if self.running: self.running = False
    
    def run(self):
        raise RuntimeError('not implemented')
    
    def __repr__(self):
        return '%s[%d]'%(self.__class__.__name__, self._index)
    
    @staticmethod
    def create():
        pass
    


class multitask_Timer(Timer):
    '''Timer based on the included multitask module.'''
    def __init__(self, app):
        Timer.__init__(self, app)
        self.gen = None
    
    def start(self, delay=None):
        from rtclite import multitask
        if self.running: self.stop() # stop previous one first.
        if delay is not None: self.delay = delay # set the new delay
        self.running = True
        self.gen = self.run()
        multitask.add(self.gen)
        
    def stop(self):
        if self.running: self.running = False
        if self.gen: 
            try: self.gen.close()
            except: pass
            self.gen = None
    
    def run(self):
        try:
            from rtclite import multitask
            yield multitask.sleep(self.delay)
            if self.running: self.app.timedout(self)
        except:
            pass # probably stopped before timeout


def _test_multitask_Timer():
    '''A simple test that starts two timers, t1=4s and t2=2s. When t2 expires,
    t1 is stopped, and t2 is restarted with 3s. The output should print with delay:
     T: starting multitask_Timer[0], multitask_Timer[1]
     T+2: timedout multitask_Timer[1]
     T+2: stopping multitask_Timer[0]
     T+5: timedout multitask_Timer[1]
    '''
    class App(object):
        def timedout(self, timer):
            print(int(time.time()), 'timedout', timer)
            if timer == self.t2 and self.t1 is not None:
                print(int(time.time()), 'stopping', self.t1)
                self.t1.stop()
                self.t1 = None
                timer.start(3)
    app = App()
    t1 = multitask_Timer(app)
    t2 = multitask_Timer(app)
    print(int(time.time()), 'starting', t1, t2)
    t1.start(4)
    t2.start(2)
    app.t1 = t1
    app.t2 = t2
    
    from rtclite import multitask
    multitask.run()


class gevent_Timer(Timer):
    '''Timer based on the third-party gevent module.'''
    def __init__(self, app):
        Timer.__init__(self, app)
        self.gen = None
        
    def start(self, delay=None):
        import gevent
        if self.running: self.stop() # stop previous one first.
        if delay is not None: self.delay = delay # set the new delay
        self.running = True
        self.gen = gevent.spawn_later(self.delay, self.app.timedout, self)
        
    def stop(self):
        if self.running: self.running = False
        if self.gen: 
            try: self.gen.kill()
            except: pass
            self.gen = None



#--------------------------------------
# LOCAL INTERFACES
#--------------------------------------


_local_ip = None # if set, then use this when needed in getlocaladdr

def getlocaladdr(sock=None):
    '''Get the local ('addr', port) for the given socket. It uses the
    getsockname() to get the local IP and port. If the local IP is '0.0.0.0'
    then it uses gethostbyname(gethostname()) to get the local IP. The
    returned object's repr gives 'ip:port' string. If the sock is absent, then
    just gets the local IP and sets the port part as 0.
    '''
    global _local_ip
    # TODO: use a better mechanism to get the address such as getifaddr
    addr = sock and sock.getsockname() or ('0.0.0.0', 0)
    if addr and addr[0] == '0.0.0.0': 
        addr = (_local_ip if _local_ip else socket.gethostbyname(socket.gethostname()), addr[1])
    return addr

def setlocaladdr(ip):
    global _local_ip
    _local_ip = ip
    
def getintfaddr(dest):
    '''Get the local address that is used to connect to the given destination address.'''
    try: 
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect((dest, 5060))
        result = s.getsockname()[0]
        return result
    except: return None
    finally: s.close()



#--------------------------------------
# EVENT DISPATCHER
#--------------------------------------


from threading import Condition, Lock

class MessageCore():
    '''The message core that handles message transfer among different objects. In particular,
    it provides put and get methods to dispatch and (blocked) receive of messages. A message
    is a dict and get can specify criteria to match for incoming message. There is only
    one global Core in this module.
    
    Caution: This uses Condition and Lock, hence must not be used along with multitask's single
    threaded co-operative multitasking framework. MessageCore is meant only for multi-threaded
    applications.'''
    def __init__(self):
        self.pending = [] # pending list. item is (elem, expiry)
        self.waiting = 0  # number of waiting get() calls; don't need a semaphore for single threaded application.
        self.cond    = Condition(Lock())

    def put(self, elem, timeout=10.):
        '''Put a given elem in the queue, and signal one get that is waiting
        on this elem properties. An optional timeout can specify how long to keep the elem
        in the queue if no get is done on the elem, default is 10 seconds.'''
        # TODO: need to change this to allow signaling all waiting get(), but not multiple times.
        self.cond.acquire()
        now = time.time()
        self.pending = [x for x in self.pending if x[1]<=now] # remove expired ones
        self.pending.append((elem, now+timeout))
        self.cond.notifyAll()
        self.cond.release()
        
    def get(self, timeout=None, criteria=None):
        '''Get an elem from the queue that matches the properties specified using the criteria
        which is a function that gets invoked on every element. An optional timeout keyword 
        argument can specify how long to wait on the result. It returns None if a timeout 
        occurs'''
        result, start = None, time.time()
        self.cond.acquire()                                      # get the lock
        now, remaining = time.time(), (timeout or 0)-(time.time()-start)# in case we took long time to acquire the lock
        
        while timeout is None or remaining>=0:
            self.pending = [x for x in self.pending if x[1]<=now] # remove expired ones
            found = [x for x in self.pending if criteria(x[0])]   # check any matching criteria
            if found: # found in pending, return it.
                self.pending.remove(found[0]) # first remove that item
                self.cond.release()
                return found[0]
            self.cond.wait(timeout=remaining)
            remaining = (timeout or 0)-(time.time()-start)

        self.cond.release() # not found and timedout
        return None
    
import weakref

class Dispatcher(object):
    '''A event dispatcher. Should be used very very carefully, because all references are
    strong references and must be explictly removed for cleanup.'''
    #'''A event dispatcher. Should be used very very carefully, because all references are
    #weak references and be removed automatically when the event handler is removed.'''
    def __init__(self): self._handler = {}
    def __del__(self): self._handler.clear()
    
    def attach(self, event, func):
        '''Attach an event which is a lambda function taking one argument, to the event handler func.'''
        if event in iter(self._handler.keys()): 
            if func not in self._handler[event]: self._handler[event].append(func)
        else: self._handler[event] = [func]
    def detach(self, event, func):
        '''Detach the event handler func from the event (or all events if None)'''
        if event is not None:
            if event in self._handler and func in self._handler[event]: self._handler[event].remove(func)
            if len(self._handler[event]) == 0: del self._handler[event]
        else:
            for event in self._handler:
                if func in self._handler[event][:]:
                    self._handler[event].remove(func)
                    if len(self._handler[event]) == 0: del self._handler[event]
    def dispatch(self, data):
        '''Dispatch a given data to event handlers if the event lambda function returns true.'''
        for f in sum([y[1] for y in [x for x in iter(self._handler.items()) if x[0](data)]], []): 
            f(data)
            # TODO: ignore the exception 
                



#--------------------------------------
# WIN32 REGISTRY RESOLVE
#--------------------------------------

if os.name == 'nt':
    import string, winreg

    # Python Cookbook: 
    # http://my.safaribooksonline.com/0596001673/pythoncook-CHP-7-SECT-10
    # Modified to accommodate DhcpNameServer for XP/Vista

    def binipdisplay(s):
        "convert a binary array of ip addresses to a python list"
        if len(s)%4!= 0:
            raise EnvironmentError # well ...
        ol=[]
        for i in range(len(s)/4):
            s1=s[:4]
            s=s[4:]
            ip=[]
            for j in s1:
                ip.append(str(ord(j)))
            ol.append(string.join(ip,'.'))
        return ol
    
    def stringdisplay(s):
        'convert "d.d.d.d,d.d.d.d" to ["d.d.d.d","d.d.d.d"]'
        return string.split(s,",")
    
    def RegistryResolve():
        """ Return the list of dotted-quads addresses of name servers found in
        the registry -- tested on NT4 Server SP6a, Win/2000 Pro SP2, XP, ME
        (each of which has a different registry layout for nameservers!) """
    
        nameservers=[]
        x=winreg.ConnectRegistry(None,winreg.HKEY_LOCAL_MACHINE)
        try:
            y= winreg.OpenKey(x,
             r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters")
        except EnvironmentError: # so it isn't NT/2000/XP
            # Windows ME, perhaps?
            try: # for Windows ME
                y = winreg.OpenKey(x,
                  r"SYSTEM\CurrentControlSet\Services\VxD\MSTCP")
                nameserver, dummytype = winreg.QueryValueEx(y,'NameServer')
                if nameserver and not (nameserver in nameservers):
                    nameservers.extend(stringdisplay(nameserver))
            except EnvironmentError:
                pass # Must be another Windows dialect, so who knows?
            return nameservers
    
        nameserver = winreg.QueryValueEx(y,"NameServer")[0]
        if nameserver:
            nameservers = [nameserver]
        winreg.CloseKey(y)
        try: # for win2000
            y = winreg.OpenKey(x, r"SYSTEM\CurrentControlSet\Services\Tcpip"
                                   r"\Parameters\DNSRegisteredAdapters")
            for i in range(1000):
                try:
                    n = winreg.EnumKey(y,i)
                    z = winreg.OpenKey(y,n)
                    dnscount,dnscounttype = winreg.QueryValueEx(z,
                        'DNSServerAddressCount')
                    dnsvalues,dnsvaluestype = winreg.QueryValueEx(z,
                        'DNSServerAddresses')
                    nameservers.extend(binipdisplay(dnsvalues))
                    winreg.CloseKey(z)
                except EnvironmentError:
                    break
            winreg.CloseKey(y)
        except EnvironmentError:
            pass
    
        try: # for XP
            y = winreg.OpenKey(x,
             r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces")
            for i in range(1000):
                try:
                    n = winreg.EnumKey(y,i)
                    z = winreg.OpenKey(y,n)
                    try:
                        nameserver,dummytype = winreg.QueryValueEx(z,'NameServer')
                        if nameserver and not (nameserver in nameservers):
                            nameservers.extend(stringdisplay(nameserver))
                        if not nameserver: # try DhcpNameServer
                            nameserver,dummytype = winreg.QueryValueEx(z,'DhcpNameServer')
                            if nameserver and not (nameserver in nameservers):
                                nameservers.extend(stringdisplay(nameserver))
                    except EnvironmentError:
                        pass
                    winreg.CloseKey(z)
                except EnvironmentError:
                    break
            winreg.CloseKey(y)
        except EnvironmentError:
            # Print "Key Interfaces not found, just do nothing"
            pass
    
        winreg.CloseKey(x)
        return nameservers

def _test_RegistryResolve():
    print("Name servers:", RegistryResolve())


#--------------------------------------
# TEST
#--------------------------------------


if __name__ == '__main__':
    if os.name == 'nt':
        _test_RegistryResolve()
    _test_ColorizingStreamHandler()
    _test_multitask_Timer()
