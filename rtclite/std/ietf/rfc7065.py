# Copyright (c) 2016, Kundan Singh. All rights reserved. See LICENSE for details.
# @implements RFC7065 (TURN URI)
'''
TURN URI

It modifies URI class from rfc2396 module to include "turn" in list of schemes, so that
the "secure" property of the URI object can be used to convert "turn" to "turns" scheme,
and to test whether the URI is "turns" scheme.
'''

from .rfc2396 import URI

def patch():
    if 'turn' not in URI._schemes:
        URI._schemes.append('turn')
patch()

def parts(uri):
    '''Return TURN URI specific components in a tuple, (host, port, transport, secure).
    Here transport is one of 'udp', 'tcp', 'tls' or 'dtls'; secure is boolean, host is
    str and port is int.
    
    >>> print parts(URI('turn:example.org:8000?transport=tcp'))
    ('example.org', 8000, 'tcp', False)
    
    >>> for s in ('turn:example.org', 'turns:example.org', 'turn:example.org:8000',
    ...           'turn:example.org?transport=udp', 'turn:example.org?transport=tcp', 
    ...           'turns:example.org?transport=tcp', 'turns:example.org?transport=udp'):
    ...     print parts(URI(s))
    ('example.org', 3478, 'udp', False)
    ('example.org', 5349, 'tls', True)
    ('example.org', 8000, 'udp', False)
    ('example.org', 3478, 'udp', False)
    ('example.org', 3478, 'tcp', False)
    ('example.org', 5349, 'tls', True)
    ('example.org', 5349, 'dtls', True)
    '''
    if not uri or uri.scheme not in ('turn', 'turns'): raise ValueError('not a turn uri')
    transport, host, port, secure = 'udp' if not uri.secure else 'tcp', uri.host, uri.port, uri.secure
    if not uri.port: port = 5349 if uri.scheme == 'turns' else 3478
    if uri.header:
        transports = [h[10:] for h in uri.header if h.startswith('transport=')]
        if len(transports) > 1: raise ValueError('more than one transport header')
        if transports: transport = transports[0]
    if uri.secure: transport = {'udp': 'dtls', 'tcp': 'tls'}.get(transport, transport)
    return (host, port, transport, secure)
    
if __name__ == '__main__':
    import doctest
    doctest.testmod()
