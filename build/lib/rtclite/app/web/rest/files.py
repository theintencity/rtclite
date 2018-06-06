# Copyright (c) 2009, Kundan Singh. All rights reserved.

'''
Expose the local file structure as resources using rest module.
'''

import os
from .. import rest

# The top-level directory for all file requests

directory = '.'

# The resource to get or set the top-level directory

@rest.resource
def config():
    def GET(request):
        global directory
        return request.response(('config', ('directory', directory)))
    def PUT(request, entity):
        global directory
        directory = str(entity)
    return locals()

# The resource to list all the file information under path relative to the top-level directory

@rest.resource
def files():
    def GET(request):
        global directory
        if '..' in request['PATH_INFO']: raise rest.Status('400 Invalid Path')
        path = os.path.join(directory, request['PATH_INFO'][1:] if request['PATH_INFO'] else '')
        try:
            files = [(name, os.path.join(path, name), request['PATH_INFO'] + '/' + name) for name in os.listdir(path)]
        except: raise rest.Status('404 Not Found')
        def desc(name, path, url):
            if os.path.isfile(path):
                return ('file', (('name', name), ('url', '/file'+url), ('size', os.path.getsize(path)), ('mtime', int(os.path.getmtime(path)))))
            elif os.path.isdir(path):
                return ('dir', (('name', name), ('url', '/files'+url)))
        files = [desc(*file) for file in files]
        return request.response(('files', files))
    return locals()

# download a given file from the path under top-level directory

def file(env, start_response):
    global directory
    path = os.path.join(directory, env['PATH_INFO'][1:] if env['PATH_INFO'] else '')
    if not os.path.isfile(path): raise rest.Status('404 Not Found')
    start_response('200 OK', [('Content-Type', 'application/octet-stream')])
    try:
        with open(path, 'rb') as f: result = f.read()
    except: raise rest.Status('400 Error Reading File')
    return [result]

# convert a Python object to resource

users = [{'username': 'kundan', 'name': 'Kundan Singh', 'email': 'kundan10@gmail.com'}, {'username': 'alok'}]
users = rest.bind(users)

# create an authenticated data model with one user and perform authentication for the resource

model = rest.AuthModel()
model.register('kundan10@gmail.com', 'localhost', 'somepass')

@rest.resource
def private():
    def GET(request):
        global model
        model.login(request)
        return request.response(('path', request['PATH_INFO']))
    return locals()

# all the routes

routes = [
    (r'GET,PUT,POST /(?P<type>((xml)|(plain)))/(?P<path>.*)', 'GET,PUT,POST /%(path)s', 'ACCEPT=text/%(type)s'),
    (r'GET,PUT,POST /(?P<type>((json)))/(?P<path>.*)', 'GET,PUT,POST /%(path)s', 'ACCEPT=application/%(type)s'),
    (r'GET /config\?directory=(?P<directory>.*)', 'PUT /config', 'CONTENT_TYPE=text/plain', 'BODY=%(directory)s', config),
    (r'GET,PUT,POST /config$', 'GET,PUT,PUT /config', config),
    (r'GET /files', files),
    (r'GET /file', file),
    (r'GET /users', users),
    (r'GET /private/', private)
]        

# launch the server on port 8000
    
if __name__ == '__main__':
    import sys, _thread
    from wsgiref.simple_server import make_server
    
    httpd = make_server('', 8000, rest.router(routes))
    
    # if unit test is desired, perform unit testing
    if len(sys.argv) > 1 and sys.argv[1] == '--test':
        import urllib.request, urllib.error, urllib.parse, http.cookiejar
        password_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        top_level_url = "localhost:8000"
        password_mgr.add_password(None, top_level_url, "kundan10@gmail.com", "somepass")
        cj = http.cookiejar.CookieJar()
        urllib.request.install_opener(urllib.request.build_opener(urllib.request.HTTPBasicAuthHandler(password_mgr), urllib.request.HTTPCookieProcessor(cj)))
        
        def urlopen(url, prefix="http://localhost:8000"):
            try: return urllib.request.urlopen(prefix + url).read()
            except: return sys.exc_info()[1]
            
        def test():
            print(urlopen('/config'))
            print(urlopen('/config?directory=rtclite/app'))
            print(urlopen('/config'))
            print(urlopen('/xml/files'))
            print(urlopen('/xml/files/web'))
            print(urlopen('/json/files'))
            print(urlopen('/json/files/web'))
            print('\n'.join(urlopen('/file/web/rest/base.py').split('\n')[:6]))
            print(urlopen('/json/users'))
            print(urlopen('/json/users/0'))
            print(urlopen('/json/users/1/username'))
            print(urlopen('/json/private/something/is/here'))
            print(urlopen('/json/private/otherthing/is/also/here'))
            httpd.shutdown()

        _thread.start_new_thread(test, ())
    
    try: httpd.serve_forever()
    except KeyboardInterrupt: pass
