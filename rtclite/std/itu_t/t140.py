# Copyright (c) 2011, Kundan Singh. All rights reserved. See LICENSE for details.
# implements ITU-T's T.140 standard

'''
Implements the codes of T.140 for real-time text.

>>> print '%r'%([BEL, BS, NEWLINE, CRLF, SOS, ST, ESC, INT, BOM])
['\\x07', '\\x08', '\\xe2\\x80\\xa8', '\\r\\n', '\\xc2\\x98', '\\xc2\\x9c', '\\x1b', '\\x1ba', '\\xef\\xbb\\xbf']
'''

_names = 'BEL BS NEWLINE CRLF SOS ST ESC INT BOM' 
_codes = (u'\u0007', u'\u0008', u'\u2028', u'\u000D\u000A', u'\u0098', u'\u009C', u'\u001B', u'\u001B\u0061', u'\uFEFF')
names = dict([(k.encode('utf-8'), v) for k, v in zip(_codes, _names.split())])
codes = dict([(v, k) for k, v in names.iteritems()])
for code, name in names.iteritems(): exec('%s=%r'%(name, code)) 

if __name__ == '__main__':
    import doctest
    doctest.testmod()
