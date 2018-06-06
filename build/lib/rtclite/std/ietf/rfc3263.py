# Copyright (c) 2008, Kundan Singh. All rights reserved. See LICENSE for details.
# @implements RFC3263 (Locating SIP servers)

'''
Uses DNS to resolve a domain name into SIP servers using NAPTR, SRV and A/AAAA records.
TODO: (1) need to make it multitask compatible or have a separate thread, (3) need to return priority and weight.

>>> print resolve('sip:192.1.2.3')                    # with numeric IP
[('192.1.2.3', 5060, 'udp'), ('192.1.2.3', 5060, 'tcp'), ('192.1.2.3', 5061, 'tls')]
>>> print resolve('sip:192.1.2.3;maddr=192.3.3.3')    #    and maddr param
[('192.3.3.3', 5060, 'udp'), ('192.3.3.3', 5060, 'tcp'), ('192.3.3.3', 5061, 'tls')]
>>> print resolve('sip:192.1.2.3:5062;transport=tcp') #    and port, transport param
[('192.1.2.3', 5062, 'tcp')]
>>> print resolve('sips:192.1.2.3')                   #    and sips
[('192.1.2.3', 5061, 'tls')]
>>> print resolve('sips:192.1.2.3:5062')              #    and sips, port
[('192.1.2.3', 5062, 'tls')]
>>> print resolve('sip:39peers.net')                  # with non-numeric without NAPTR/SRV
[('74.220.215.84', 5060, 'udp'), ('74.220.215.84', 5060, 'tcp'), ('74.220.215.84', 5061, 'tls')]
>>> print resolve('sip:39peers.net:5062')             #    and port  
[('74.220.215.84', 5062, 'udp'), ('74.220.215.84', 5062, 'tcp'), ('74.220.215.84', 5062, 'tls')]
>>> print resolve('sip:39peers.net;transport=tcp')    #    and transport  
[('74.220.215.84', 5060, 'tcp')]
>>> print resolve('sips:39peers.net')                 #    and sips  
[('74.220.215.84', 5061, 'tls')]
>>> print resolve('sip:iptel.org')                    # with no NAPTR but has SRV records
[('212.79.111.157', 5060, 'udp'), ('212.79.111.157', 5060, 'tcp')]
>>> print resolve('sips:iptel.org')                   #    and sips
[('212.79.111.155', 5061, 'tls')]
>>> print resolve('sip:columbia.edu')                 # with one NAPTR and two SRV records
[('128.59.59.208', 5060, 'udp'), ('128.59.59.229', 5060, 'udp')]
>>> print resolve('sips:columbia.edu')                #    and sips (no NAPTR for sips)
[('128.59.105.24', 5061, 'tls')]
>>> print resolve('sip:adobe.com')                    # with multiple NAPTR and multiple SRV
[('192.150.16.117', 5060, 'udp')]
>>> print resolve('sip:adobe.com', supported=('tcp', 'tls')) # if udp is not supported
[('192.150.16.117', 5060, 'tcp')]
>>> print resolve('sips:adobe.com')                    # with multiple NAPTR and multiple SRV
[('192.150.12.115', 5061, 'tls')]
>>> print list(sorted(resolve('sip:twilio.com')))
[('50.31.227.68', 5060, 'udp'), ('50.31.227.69', 5060, 'udp'), ('50.31.227.70', 5060, 'udp'), ('69.5.92.68', 5060, 'udp'), ('69.5.92.69', 5060, 'udp'), ('69.5.92.70', 5060, 'udp')]
'''

import sys, os, time, random, logging
if os.name == 'nt': # on windows import RegistryResolve
    from common import RegistryResolve
    _nameservers = RegistryResolve()
else: _nameservers = None

from .rfc2396 import URI, isIPv4
from .rfc1035 import Resolver, C_IN, T_NAPTR, T_SRV, T_A

logger = logging.getLogger('rfc3263')

_resolver, _cache = None, {} # Name servers, resolver and DNS cache (plus negative cache)
_proto = {'udp': ('sip+d2u', 5060), 'tcp': ('sip+d2t', 5060), 'tls': ('sips+d2t', 5061), 'sctp': ('sip+d2s', 5060)} # map from transport to details
_rproto = dict([(x[1][0], x[0]) for x in _proto.items()]) # reverse mapping {'sip+d2u': 'udp', ...} 
_xproto = dict([(x[0], '_%s._%s'%(x[1][0].split('+')[0], x[0] if x[0] != 'tls' else 'tcp')) for x in _proto.items()]) # mapping {'udp' : '_sip._udp', ...}
_rxproto = dict([(x[1], x[0]) for x in _xproto.items()]) # mapping { '_sips._tcp': 'tls', ...} 
_zxproto = dict([(x[0], _proto[x[1]]) for x in _rxproto.items()]) # mapping { '_sips._tcp': ('sip+d2t, 5061), ...}
_group = lambda x: sorted(x, lambda a,b: a[1]-b[1]) # sort a list of tuples based on priority

def _query(key, negTimeout=60): # key is (target, type)
    '''Perform a single DNS query, and return the ANSWER section. Uses internal cache to avoid repeating the queries. 
    The timeout of the cache entry is determined by TTL obtained in the results. It always returns a list, even if empty.'''
    global _resolver; resolver = _resolver or Resolver(_nameservers)
    if key in _cache and _cache[key][1] < time.time(): return random.shuffle(_cache[key][0]) and _cache[key][0]
    try:
        raw = resolver.Raw(key[0], key[1], C_IN, recursion=True, proto=None)
        if raw and raw['HEADER']['OPCODES']['TC']: # if truncated, try with TCP
            raw = resolver.Raw(key[0], key[1], C_IN, recursion=False, proto='tcp')
        answer = raw and raw['HEADER']['ANCOUNT'] > 0 and raw['ANSWER'] or []; random.shuffle(answer)
    except Exception as e:
        logger.exception('_query(%r) exception', key) 
        answer = []
    _cache[key] = (answer, time.time() + min([(x['TTL'] if 'TTL' in x else negTimeout) for x in answer] + [negTimeout]))
    return answer
 
# @implements RFC3263 P1L27-P1L32
def resolve(uri, supported=('udp', 'tcp', 'tls'), secproto=('tls',)):
    '''Resolve a URI using RFC3263 to list of (IP address, port) tuples each with its order, preference, transport and 
    TTL information. The application can supply a list of supported protocols if needed.'''
    if not isinstance(uri, URI): uri = URI(uri)
    transport = uri.param['transport'] if 'transport' in uri.param else None
    target = uri.param['maddr'] if 'maddr' in uri.param else uri.host
    numeric, port, naptr, srv, result = isIPv4(target), uri.port, None, None, None
    if uri.secure: supported = secproto # only support secproto for "sips"
    #@implements rfc3263 P6L10-P8L32
    if transport: transports = (transport,) if transport in supported else () # only the given transport is used
    elif numeric or port is not None: transports = supported
    else:
        naptr = _query((target, T_NAPTR))
        if naptr: # find the first that is supported
            ordered = [r for r in sorted([(r['RDATA']['ORDER'], _rproto.get(r['RDATA']['SERVICE'].lower(), ''), r) for r in naptr], lambda a,b: a[0]-b[0]) if r[1] in supported] # filter out unsupported transports
            if ordered:
                selected = [r for r in ordered if r[0] == ordered[0][0]] # keep only top-ordered values, ignore rest
                transports, naptr = [r[1] for r in selected], [r[2] for r in selected] # unzip to transports and naptr values
            else: transports, naptr = supported, None # assume failure if not found; clear the naptr response
        if not naptr: # do not use "else", because naptr may be cleared in "if"
            srv = [r for r in [(_rxproto.get(p, ''), _query(('%s.%s'%(p, target), T_SRV))) for p in [_xproto[t] for t in supported]] if r[1]]
            if srv: transports = [s[0] for s in srv]
            else: transports = supported
    #@implements rfc3263 P8L34-P9L31
    if numeric: result = [(target, port or _proto[t][1], t) for t in transports]
    elif port: result = sum([[(r['RDATA'], port, t) for r in _query((target, T_A))] for t in transports], [])
    else:
        service = None
        if naptr: service = sorted([(x['RDATA']['REPLACEMENT'].lower(), x['RDATA']['ORDER'], x['RDATA']['PREFERENCE'], x['RDATA']['SERVICE'].lower()) for x in naptr], lambda a,b: a[1]-b[1])
        elif transport: service = [('%s.%s'%(_xproto[transport], target), 0, 0, _proto[transport][0])]
        if not srv:
            srv = [y for y in [(_rproto[s[3].lower()], _query((s[0], T_SRV))) for s in service] if y[1]] if service else []
        if srv:
            # to fix for twilio.com: srv = map(lambda x: (x[0], filter(lambda s: s['TYPE'] == T_SRV, x[1])), srv)
            out = list(sorted(sum([[(r['RDATA']['DOMAIN'].lower(), r['RDATA']['PRIORITY'], r['RDATA']['WEIGHT'], r['RDATA']['PORT'], s[0]) for r in s[1]] for s in srv], []),  lambda a,b: a[1]-b[1]))
            result = sum([[(y['RDATA'], x[1], x[2]) for y in (_query((x[0], T_A)) or [])] for x in [(r[0], r[3], r[4]) for r in out]], [])
    return result or [(x[0], port or _proto[x[1]][1], x[1]) for x in sum([[(a, b) for a in [x['RDATA'] for x in _query((target, T_A))]] for b in transports], [])] # finally do A record on target, if nothing else worked

if __name__ == '__main__': # Unit test of this module
    logging.basicConfig()
    logger.setLevel(logging.CRITICAL)
    import doctest
    doctest.testmod()

