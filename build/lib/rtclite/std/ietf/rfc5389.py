# Copyright (c) 2007, Kundan Singh. All rights reserved. See LICENSE for details.
# @implements RFC5389 (STUN)

r'''
To create a message, supply the message type and method.

>>> msg = Message()
>>> msg.method, msg.type = Message.BINDING, Message.REQUEST
>>> msg.tid = '5JXY60DkLznI' # some random 8-octet data

To add attributes to the message, create the attribute object and add to the attrs list.
The Attribute class does not care about the specific value, and does not check its syntax or length.

>>> msg.attrs.append(Attribute(type=Attribute.USERNAME, value='YjY3NjQzNjMtYTY0:f+oIZIKgGwzJ/vRj'))
>>> msg.attrs.append(Attribute(type=Attribute.ICE_CONTROLLED, value='l\xb1\xb8\xc1\xach\x8a\xdc'))
>>> msg.attrs.append(Attribute(type=Attribute.PRIORITY, value='n\x7f\x1e\xff'))

To add message integrity and fingerprint, use the predefined methods, by supplying the password
as applicable.

>>> msg.appendIntegrity(password='MmYxZDIyYWUtNWYwYy00NGRi')
>>> msg.appendFingerprint()

To print readable message, use the "repr" function or "%r" in format-string.

>>> print repr(msg)
<Message method=1 type=0 tid='5JXY60DkLznI'>
   <Attribute type='USERNAME' value='YjY3NjQzNjMtYTY0:f+oIZIKgGwzJ/vRj' />
   <Attribute type='ICE-CONTROLLED' value='l\xb1\xb8\xc1\xach\x8a\xdc' />
   <Attribute type='PRIORITY' value='n\x7f\x1e\xff' />
   <Attribute type='MESSAGE-INTEGRITY' value=' \x834\xb6\xc6\xec\xcb\xca\xb4e\xcf\xb7\x9f\x83\x87\xf1cB\xae`' />
   <Attribute type='FINGERPRINT' value='\xbb(\xee~' />
</Message>

To parse a message, simply create the Message object with the raw data.

>>> raw = '\x01\x01\x00,!\x12\xa4BIOeRVeE1jN7w\x00 \x00\x08\x00\x01\xf5\x8f\xe1\xba\xa5K\x00\x08\x00\x14\xb5\xbcgi\xa5\x98J7\xa7\xc7\x0eV\x7f\xfeJ=\xd1.x{\x80(\x00\x04\xfc\xces\xdb'
>>> msg = Message(value=raw)
>>> print repr(msg)
<Message method=1 type=2 tid='IOeRVeE1jN7w'>
   <Attribute type='XOR-MAPPED-ADDRESS' value='\x00\x01\xf5\x8f\xe1\xba\xa5K' />
   <Attribute type='MESSAGE-INTEGRITY' value='\xb5\xbcgi\xa5\x98J7\xa7\xc7\x0eV\x7f\xfeJ=\xd1.x{' />
   <Attribute type='FINGERPRINT' value='\xfc\xces\xdb' />
</Message>

The specific attributes can be extracted from the attrs list. For IP address type attribute use the
address property and for XOR'ed address use the xorAddress property to extract its readable value.
These read-only properties return the tuple (type, ip, port) where type is one of socket.SOCK_DGRAM
or socket.SOCK_STERAM, ip is a string, and port is an int in host-order.

>>> print msg.attrs[0].xorAddress
(2, '192.168.1.9', 54429)

If the packet has message-integrity and fingerprint, you can verify them. The verification function
returns True (successful), False (failed) or None (no such attribute found).

>>> print msg.verifyIntegrity(password='gb8cIbvzjRiyv+Dfb/kDBKTN')
True
>>> print msg.verifyFingerprint()
True


>>> raw = '\x01\x01\x00,!\x12\xa4B\xfdeA\xaaF[0\xdc\xbb\x14<t\x00 \x00\x08\x00\x01\xf74\xe1\xba\xa5J\x00\x08\x00\x14\xafO\xb2}z\xdf$\x92\x8e,e\x90\\\x9b\xa6&\xa9\xa4\xfb\x85\x80(\x00\x04aEv{'
>>> msg = Message(value=raw)
>>> print repr(msg)
<Message method=1 type=2 tid='\xfdeA\xaaF[0\xdc\xbb\x14<t'>
   <Attribute type='XOR-MAPPED-ADDRESS' value='\x00\x01\xf74\xe1\xba\xa5J' />
   <Attribute type='MESSAGE-INTEGRITY' value='\xafO\xb2}z\xdf$\x92\x8e,e\x90\\\x9b\xa6&\xa9\xa4\xfb\x85' />
   <Attribute type='FINGERPRINT' value='aEv{' />
</Message>
>>> print msg.verifyIntegrity(password='/QT5Xz7pXkht6WQg0gn9/4G8')
True
'''

import sys, struct, hashlib, hmac, binascii
from . import rfc3489


_debug = False


class Attribute(rfc3489.Attribute):
    '''A single attribute in STUN message. Only type (int) and value (str) are
    valid fields in this object.'''

    # comprehension required 0x0000-0x7fff
    MAPPED_ADDRESS      = 0x0001
    USERNAME            = 0x0006
    MESSAGE_INTEGRITY   = 0x0008
    ERROR_CODE          = 0x0009
    UNKNOWN_ATTRIBUTES  = 0x000A
    REALM               = 0x0014
    NONCE               = 0x0015
    XOR_MAPPED_ADDRESS  = 0x0020

    # comprehension optional 0x8000-0xffff
    SOFTWARE            = 0x8022
    ALTERNATE_SERVER    = 0x8023
    FINGERPRINT         = 0x8028

    # defined in ICE RFC5245
    PRIORITY            = 0x0024
    USE_CANDIDATE       = 0x0025
    ICE_CONTROLLED      = 0x8029
    ICE_CONTROLLING     = 0x802A

    @staticmethod
    def type2str(value):
        return {
            0x0001: 'MAPPED-ADDRESS', 0x0006: 'USERNAME', 0x0008: 'MESSAGE-INTEGRITY', 0x0009: 'ERROR-CODE',
            0x000A: 'UNKNOWN-ATTRIBUTE', 0x0014: 'REALM', 0x0015: 'NONCE', 0x0020: 'XOR-MAPPED-ADDRESS',
            0x8022: 'SOFTWARE', 0x8023: 'ALTERNATE-SERVER', 0x8028: 'FINGERPRINT',
            0x0024: 'PRIORITY', 0x0025: 'USE-CANDIDATE', 0x8029: 'ICE-CONTROLLED', 0x802A: 'ICE-CONTROLLING',
        }.get(value, None)
    
    def __repr__(self):
        return '<%s type=%r value=%r />'%(self.__class__.__name__, self.type2str(self.type) or '0x%04x'%self.type, (self.type in [Attribute.MAPPED_ADDRESS, Attribute.ALTERNATE_SERVER]) and self.address or self.value)

rfc3489.Attribute = Attribute

class Message(rfc3489.Message):
    '''A STUN message definition. The properties method, type and tid are defined in the spec.
    The attrs property is a list of STUN attributes in this Message object.'''
    
    BINDING = 1
    
    def appendIntegrity(self, password):
        value = str(self)
        size = struct.unpack('!H', value[2:4])[0]
        value = value[:2] + struct.pack('!H', size+24) + value[4:]
        mivalue = hmac.new(password, value, hashlib.sha1).digest()
        self.attrs.append(Attribute(type=Attribute.MESSAGE_INTEGRITY, value=mivalue))
    
    def verifyIntegrity(self, password):
        mivalue, milen, pos = '', 0, 0 # header size
        for x in self.attrs:
            if x.type == Attribute.MESSAGE_INTEGRITY:
                mivalue = x.value
                milen = len(x.value)
                if milen % 4 != 0:
                    milen += (4 - (milen % 4))
                break
            pos += 4 + len(x.value)
            if len(x.value) % 4 != 0:
                pos += (4 - (len(x.value) % 4))
        if milen and mivalue:
            value = str(self) # TODO: should save origin value during parsing
            value = value[:2] + struct.pack('!H', pos + 4 + milen) + value[4:20+pos]
            return mivalue == hmac.new(password, value, hashlib.sha1).digest()
        # return None indicates the attribute was not found.
    
    def appendFingerprint(self):
        value = str(self)
        size = struct.unpack('!H', value[2:4])[0]
        value = value[:2] + struct.pack('!H', size+8) + value[4:]
        crc = binascii.crc32(value, 0) & 0xffffffff
        self.attrs.append(Attribute(type=Attribute.FINGERPRINT, value=struct.pack('!I', crc ^ 0x5354554e)))
    
    def verifyFingerprint(self):
        if len(self.attrs) > 0 and self.attrs[-1].type == Attribute.FINGERPRINT: # must be the last one if present
            value = str(self)
            value = value[:len(value)-8]
            crc = binascii.crc32(value, 0) & 0xffffffff
            return crc == (struct.unpack('!I', self.attrs[-1].value)[0] ^ 0x5354554e)
    


#----------------------------------- Testing ------------------------------
    
if __name__ == "__main__":
    import doctest
    doctest.testmod()
    
    
