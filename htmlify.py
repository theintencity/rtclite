# Copyright (c) 2016 Kundan Singh. All rights reserved. See LICENSE for details.
# Generate the html documentation based on the code and specification.

import sys, os, cgi, re, StringIO, urllib2
from highlight import build_html_page, analyze_python, html_highlight, default_html

default_css = {
    '.python': '{color: #404040;}',
    '.comment': '{color: forestgreen; font-style:italic;}',
    '.string':  '{color: olive;}',
    '.docstring': '{color: forestgreen;}',
    '.keyword': '{color: darkblue; font-weight:bold;}',
    '.builtin': '{color: purple;}',
    '.definition': '{color: darkblue; font-weight:bold;}',
    '.defname': '{color: darkviolet;}',
    '.operator': '{color: brown;}',
    '.package span': '''{
        display: inline-block; border: solid 1px #808080;
        background-color: #ffeeee; margin: 4px; padding: 4px;
        font-size: 20px; box-shadow: 0 0 10px 1px #a0a0a0;
    }''',
    '.commentbox a': '''{
        text-decoration: none;
    }''',
    '.commentbox': '''{
        border: none; width: 640px; box-shadow: 0 0 10px 1px #a0a0a0;
        background-color: #ffeeee; font-family: sans-serif; font-size: 10pt;
        margin-top: 4px; margin-bottom: -12px; padding: 4px;
    }''',
}

implements = re.compile('#\s*@implements\s+(?P<ref>\S+)\s+(?:(?:\((?P<sec>[^\)]+)\))|(?P<lines>[PL\d\-]+))')
linere     = re.compile('^(?P<begin>\S+)-(?P<end>\S+)') 

quote = lambda s: s.replace('<', '&lt;').replace('>', '&gt;').replace('&','&amp;')


def walkdir(srcdir, destdir):
    for path, subdirs, files in os.walk(srcdir):
        if '__init__.py' in files:
            for name in filter(lambda x: x.endswith('.py'), files):
                src = os.path.join(path, name)
                if name == '__init__.py':
                    dotted = re.sub(r'/', '.', path)
                    dest = (destdir + os.path.join(path, 'index')[len(srcdir):])
                    yield ('package', dotted, src, dest + '.html', None)
                else:
                    dotted = re.sub(r'/', '.', src[:-3])
                    dest = (destdir + src[len(srcdir):]) # TODO: should use os.path
                    yield ('module', dotted, src, dest + '.html', dest + '.txt' if name.startswith('rfc') else None)


def get_package_content(dirpath):
    modules, packages = [], []
    
    for child in os.listdir(dirpath):
        path = os.path.join(dirpath, child)
        if os.path.isfile(path) and child.endswith('.py') and child != '__init__.py': # module
            modules.append(child)
        elif os.path.isdir(path) and os.path.exists(os.path.join(dirpath, child, '__init__.py')):
            packages.append(child)
    return modules, packages

def openspec(filename, name=None):
    if not os.path.exists(filename):
        name = name.lower()
        if name.startswith('rfc'):
            input = urllib2.urlopen('http://www.ietf.org/rfc/' + name + '.txt')
        elif name.startswith('draft-'):
            input = urllib2.urlopen('http://www.ietf.org/internet-drafts/' + name + '.txt')
        else:
            input = None
        if input:
            file = open(filename, 'w')
            pnum, lnum = 1, -3
            for line in input:
                lnum = lnum+1
                if lnum>0 and lnum<=48 or lnum>48 and len(line)>4 and line[-2]!=']':
                    file.write('P'+str(pnum)+'L'+str(lnum)+'\t'+line)
                if ord(line[0]) == 12: # line break in RFCs
                    pnum, lnum = pnum + 1, -3
            input.close()
            file.close()
    return os.path.exists(filename) and open(filename, 'rU') or None

def replace_module_comments(html, spec):
    output = html.split('\n')
    for i in xrange(len(output)):
        line = output[i]
        m = implements.search(line)
        if m:
            line = None
            ref, sec, lines = m.group('ref'), m.group('sec'), m.group('lines')
            if sec:
                fp = openspec(spec, ref)  # so that the file is fetched.
                if fp:
                    fp.close()
                reflink = '<a href="http://www.ietf.org/rfc/%s.txt">%s</a>'%(ref.lower(), ref) if ref.startswith('RFC') else ref
                line = quote('This file implements ') + reflink + quote(' (' + sec + ')')
            elif lines:
                m = linere.match(lines)
                if m: 
                    begin, end = m.group('begin'), m.group('end')
                    fp = openspec(spec)
                    if fp:
                        state = 'before'
                        source = 'From ' + ref + ' p.' + begin[1:].partition('L')[0]
                        out = []
                        for line2 in fp:
                            num, sep, rest = line2.partition('\t')
                            rest = rest.rstrip()
                            if state == 'before' and num == begin:
                                state = 'during'
                                out.append(rest)
                            elif state == 'during':
                                out.append(rest)
                                if num == end:
                                    state = 'after'
                                    break
                        line = quote(source) + '\n<pre>' + '\n'.join(x for x in out) + '</pre>'
                        fp.close()
            if line:
                output[i] = '<div class="commentbox">%s</div>'%(line,)
    return '\n'.join(output)

def create_header(type, dotted, src=''):
    parts = dotted.split('.')
    upup = lambda i: ''.join(['../' for x in xrange(len(parts)-(type == 'module' and 2 or 1)-i)]) + 'index.html'
    parts[:-1] = ['<a href="%s">%s</a>'%(upup(i), quote(x)) for i, x in enumerate(parts[:-1])]
    result = ['<b>%s</b>: %s'%(type[:1].upper() + type[1:], '.'.join(parts))]
    if type == 'package':
        modules, packages = get_package_content(os.path.dirname(src))
        if packages:
            result.append('&nbsp;&nbsp;&nbsp;&nbsp;sub-packages: ' + \
                      ', '.join(['<span><a href="%s/index.html">%s</a></span>'%(x, quote(x),) for x in packages]))
        if modules:
            result.append('&nbsp;&nbsp;&nbsp;&nbsp;modules: ' + \
                      ', '.join(['<span><a href="%s.html">%s</a></span>'%(x, quote(x),) for x in modules]))
        
    return '\n<br/>'.join(result)


def htmlifier(srcdir=None, destdir=None):
    if not srcdir: srcdir = '.'
    if not destdir: destdir = srcdir
    for type, dotted, src, dest, spec in walkdir(srcdir, destdir):
        print src
        with open(src, 'rU') as fp:
            text = analyze_python(fp.read())
        if type == 'module':
            header = create_header(type, dotted)
            header = '<div class="commentbox">%s</div>'%(header,)
            html = re.sub('<body>', '<body>' + header, default_html)
            html = build_html_page(text, title=src, css=default_css, html=html)
            if spec:
                html = replace_module_comments(html, spec)
        elif type == 'package':
            header = create_header(type, dotted, src)
            header = '<div class="commentbox">%s</div>'%(header,)
            html = re.sub('<body>', '<body>' + header, default_html)
            html = build_html_page(text, title=src, css=default_css, html=html)
        with open(dest, 'w') as fp:
            fp.write(html)


htmlifier('rtclite')
sys.exit()
    




