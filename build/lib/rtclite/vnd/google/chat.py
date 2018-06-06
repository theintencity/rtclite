# Copyright (c) 2009, Kundan Singh. All rights reserved. See LICENSE for details.

'''
An example program that uses the XMPP modules (rfc3920 and rfc3921) to connect to
Google Chat and send messages.

  python -m rtclite.vnd.google.chat
  usage: python -m vnd.google.chat your-gmail-id target-gmail-id
  
  python -m rtclite.vnd.google.chat kundansingh99 kundan10
  Password: *****
  > hi there
  < hello how are you

Important: for this to work, you need to make sure that you change your account settings
associated with your-gmail-id so that your account is no longer protected by
modern security standards. Otherwise you can connect only via apps made by Google such
as Gmail, and not a third-party app such as this chat module. For changing the
settings, login to your gmail and then visit
https://www.google.com/settings/security/lesssecureapps

Also, this program only sends a message if allowed, i.e., the receiver has approved
receiving messages from the sender, e.g., by accepting the contact request.
'''

import sys, getpass, select, logging
try: import readline
except: readline = None

from ... import multitask
from ...std.ietf.rfc3921 import Message, User, Presence


def recv(h):
    while True:
        msg = yield h.recv()
        if msg.frm and msg.body:
            # msg.frm.partition('/')[0]
            print('< %s'%(msg.body.cdata,))
            #if readline:
            #    readline.redisplay()

def send(h, u):
    while True:
        input = yield multitask.read(sys.stdin.fileno(), 4096)
        if input == None or input.strip() == "exit":
            break
        yield h.send(Message(body=input.strip()))
    yield u.logout()
    sys.exit(0)
    

def main(username, password, targetname):
    user = User(server='gmail.com', username=username, password=password)
    result, error = yield user.login()
    if error:
        print('Failed to login as %s@gmail.com, may be due to no access to XMPP.'%(username,))
        print('Visit https://www.google.com/settings/security/lesssecureapps to enable access.')
        raise StopIteration()
    
    yield multitask.sleep(1)
    user.roster.presence = Presence(show=None, status='Online')

    history = user.chat(targetname + '@gmail.com')

    multitask.add(recv(history))
    multitask.add(send(history, user))


if __name__ == '__main__':
    if len(sys.argv) != 3:
        if len(sys.argv) > 1 and sys.argv[1] == '--test': sys.exit(0) # no tests to run
        print('usage: %s your-gmail-id target-gmail-id'%(sys.argv[0],))
        sys.exit(-1)
    
    logging.basicConfig()
    
    username, targetname = sys.argv[1:3]
    password = getpass.getpass()

    multitask.add(main(username, password, targetname))
    try: multitask.run()
    except KeyboardInterrupt: pass
    except select.error: print('select error'); pass
