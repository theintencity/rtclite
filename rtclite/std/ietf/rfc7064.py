# Copyright (c) 2016, Kundan Singh. All rights reserved. See LICENSE for details.
# @implements RFC7064 (STUN URI)
'''
STUN URI

It modifies URI class from rfc2396 module to include "stun" in list of schemes, so that
the "secure" property of the URI object can be used to convert "stun" to "stuns" scheme,
and to test whether the URI is "stuns" scheme.
'''

from .rfc2396 import URI

def patch():
    if 'stun' not in URI._schemes:
        URI._schemes.append('stun')
patch()

def parts(uri):
    '''Return STUN URI specific components in a tuple, (host, port, transport, secure).
    Here, secure is boolean, host is str and port is int.
    
    >>> print parts(URI('stun:example.org'))
    ('example.org', 3478, False)
    >>> print parts(URI('stuns:example.org'))
    ('example.org', 5349, True)
    >>> print parts(URI('stun:example.org:8000'))
    ('example.org', 8000, False)
    '''
    if not uri or uri.scheme not in ('stun', 'stuns'): raise ValueError('not a stun uri')
    host, port, secure = uri.host, uri.port, uri.secure
    if not uri.port: port = 5349 if uri.scheme == 'stuns' else 3478
    return (host, port, secure)
    
if __name__ == '__main__':
    import doctest
    doctest.testmod()
