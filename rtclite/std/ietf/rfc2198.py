# Copyright (c) 2007, Kundan Singh. All rights reserved. See LICENSE for details.
# @implements RFC2198 (Redundant RTP payload)

'''
Implements RTP payload for redundant audio data as per RFC 2198.

Create the redundant payload using list of tuples, each item (pt, timestamp, payload), where
the first item is the primary with largest timestamp and subsequent ones are redundants.

>>> packet = createRedundant(packets=[(126, 0x0002, '\x01\x01\x01\x01'), (127, 0x0001, '\x02\x02')])
>>> print packet.encode('hex')
ff0001027e020201010101

To parse the redundant payload, also supply the primary timestamp from the RTP header, so that
all the redundant packets' timestamps can be adjusted accordingly.

>>> parseRedundant(packet, 0x1002) == [(126, 0x1002, '\x01\x01\x01\x01'), (127, 0x1001, '\x02\x02')]
True
'''

import struct

def createRedundant(packets):
    '''Create redundant payload using the individual RTP packets. The packets arg is assumed
    to be a list of tuples (pt, timestamp, payload). The first packet is assumed to be 
    primary, and is put the last. All other packets are put in the reverse order'''
    hdr, data = '', ''
    first = packets[0][1]
    for pt, ts, payload in reversed(packets[1:]):
        hdr += struct.pack('!BHB', 0x80 | pt, (first - ts) & 0xffff, len(payload) & 0xff)
        data += payload
    hdr += struct.pack('!B', 0x7f & packets[0][0])
    data += packets[0][2]
    return hdr + data

def parseRedundant(packet, ts):
    '''Parse a redundant payload and return the individual payloads. The first in the result
    is the primary payload. Each payload is tuple (pt, timestamp, payload). The ts of the 
    original RTP packet should be supplied as well.'''
    all = []
    while packet:
        pt = struct.unpack('!B', packet[:1])[0]
        packet = packet[1:]
        if pt & 0x80 == 0: 
            all.insert(0, (pt,))
            break
        else:
            tsoffset, length = struct.unpack('!HB', packet[:3])
            tsoffset = tsoffset & 0x3fff
            packet = packet[3:]
            all.insert(0, (pt & 0x7f, tsoffset, length))
    result = []
    for pt, tsoffset, length in all[1:]: # for all secondary data
        result.append((pt, ts-tsoffset, packet[:length] if length > 0 else ''))
        if length > 0: packet = packet[length:]
    if all:
        result.insert(0, (all[0][0], ts, packet)) # put remaining data as primary
    return result

if __name__ == '__main__':
    import doctest
    doctest.testmod()
