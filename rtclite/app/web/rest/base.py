# Copyright (c) 2009, Kundan Singh. All rights reserved.

'''
REST + Python + JSON + XML + SQLite + authentication.

This light-weight module allows quick prototyping of web services using the RESTful architecture and allows easy 
integration with sqlite3 database, and JSON and XML representation format. The approach is to provide all the 
appropriate tools which you can use to build your own application, instead of providing a intrusive framework.

Features:
1. Very lightweight module in pure Python and no other dependencies hence ideal for quick prototyping.
2. Two levels of API: one is not intrusive (for low level WSGI) and other is intrusive (for high level @resource).
3. High level API can conveniently use sqlite3 database for resource storage.
4. Common list and tuple-based representation that is converted to JSON and/or XML.
5. Supports pure REST as well as allows browser and Flash Player access (with GET, POST only).
6. Integrates unit testing using doctest module.
7. Handles HTTP cookies and authentication.

Please visit rest.md for description and how to get started.
'''

from wsgiref.util import setup_testing_defaults
from xml.dom import minidom
import os, re, sys, sqlite3, Cookie, base64, hashlib, time, traceback, json, logging


logger = logging.getLogger('rest')

defaultType = 'application/json' # default content type if ACCEPT is */*. Used in represent and router.

#------------------------------------------------------------------------------
# REST router
#------------------------------------------------------------------------------

def router(routes):
    '''This is the main low level REST router function that takes a list of routes and sequentially tries to match the
    request method and URL pattern. If a valid route is matched, request transformation is applied. If an application
    is specified for a route, then the (wsgiref) application is invoked and the response is returned. This is used
    together with wsgiref.make_server to launch a RESTful service.
    
    Your can use the routes to do several things: identify the response type (JSON, XML) from the URL, identify 
    some parts in the URL as variables available to your application handler, modify some HTTP header or message body
    based on the URL, convert a GET or POST URL from the browser with URL suffix of /put or /delete to PUT or DELETE
    URL to handle these commands from the browser, etc. For more details see the project web page.
    
    >>> def files_handler(env, start_response): 
    ...    return '<files><type>' + env['ACCEPT'] + '</type><file>somefile.txt</file></files>'
    >>> routes = [
    ...  (r'GET,PUT,POST /xml/(?P<path>.*)$', 'GET,PUT,POST /%(path)s', 'ACCEPT=text/xml'),
    ...  (r'GET /files$', files_handler) ]
    >>> r = router(routes)   # create the router using these routes
    >>> # and test using the following code
    >>> env, start_response = {'REQUEST_METHOD': 'GET', 'PATH_INFO': '/xml/files', 'SCRIPT_NAME': '', 'QUERY_STRING': ''}, lambda x,y: (x, y)
    >>> print r(env, start_response)
    <files><type>text/xml</type><file>somefile.txt</file></files>
    '''
    if isinstance(routes, dict) or hasattr(routes, 'items'): routes = routes.iteritems()
    
    def handler(env, start_response):
        setup_testing_defaults(env)
        if 'wsgiorg.routing_args' not in env: env['wsgiorg.routing_args'] = dict()
        env['COOKIE'] = Cookie.SimpleCookie()
        if 'HTTP_COOKIE' in env: env['COOKIE'].load(env['HTTP_COOKIE'])
        
        for route in routes:
            method, pattern = route[0].split(' ', 1)
            methods = method.split(',')
            if env['REQUEST_METHOD'] not in methods: continue
            path = env['PATH_INFO'] + ('?' + env['QUERY_STRING'] if env['QUERY_STRING'] else '')
            match = re.match(pattern, path)
            if match:
                app = None
                if callable(route[-1]): 
                    route, app = route[:-1], route[-1] # found the app
                if len(route) > 1:
                    new_methods, path = route[1].split(' ', 1)
                    env['REQUEST_METHOD'] = new_methods.split(',')[methods.index(env['REQUEST_METHOD'])]
                    env['PATH_INFO'], ignore, env['QUERY_STRING'] = (path % match.groupdict()).partition('?')
                    for name, value in [x.split('=', 1) for x in route[2:]]:
                        env[name] = value % match.groupdict()
                env['wsgiorg.routing_args'].update(match.groupdict())
                
                if app is not None:
                    matching = match.group(0)
                    env['PATH_INFO'], env['SCRIPT_NAME'] = env['PATH_INFO'][len(matching):], env['SCRIPT_NAME'] + env['PATH_INFO'][:len(matching)]
                    def my_response(status, headers):
                        if 'RESPONSE_HEADERS' not in env: env['RESPONSE_STATUS'], env['RESPONSE_HEADERS'] = status, headers
                    try: response = app(env, my_response)
                    except Status: response, env['RESPONSE_STATUS'] = None, str(sys.exc_info()[1])
                    except:
                        logger.exception('exception')
                        response, env['RESPONSE_STATUS'] = [traceback.format_exc()], '500 Internal Server Error'
                    if response is None: response = []
                    headers = env.get('RESPONSE_HEADERS', [('Content-Type', 'text/plain')])
                    orig = Cookie.SimpleCookie(); cookie = env['COOKIE']
                    if 'HTTP_COOKIE' in env: orig.load(env['HTTP_COOKIE'])
                    map(lambda x: cookie.__delitem__(x), [x for x in orig if x in cookie and str(orig[x]) == str(cookie[x])])
                    if len(cookie): headers.extend([(x[0], x[1].strip()) for x in [str(y).split(':', 1) for y in cookie.itervalues()]])
                    start_response(env.get('RESPONSE_STATUS', '200 OK'), headers)
                    if response: logger.debug('%r\n%s', headers, str(response)[:256])
                    return response

        start_response('404 Not Found', [('Content-Type', 'text/plain')])
        return ['Use one of these URL forms\n  ' + '\n  '.join(str(x[0]) for x in routes)]
    
    return handler

#------------------------------------------------------------------------------
# Representations: JSON, XML
#------------------------------------------------------------------------------

def tojson(value):
    '''The function converts the supplied value to JSON representation. It assumes the unified list format of value. 
    Typically you just call represent(value, type=request['ACCEPT']) instead of manually invoking this method. 
    To be consistent with str(obj) function which uses obj.__str__() method if available, tojson() uses obj._json_()
    method if available on value. Otherwise it checks obj._list_() method if available to get the unified list format.
    Otherwise it assumes that the value is in unified list format. The _json_ and _list_ semantics allow you to 
    customize the JSON representation of your object, if needed.
    
    >>> value = ('file', (('name', 'myfile.txt'), ('acl', [('allow', 'kundan'), ('allow', 'admin')])))
    >>> tojson(value)
    '{"file": {"name": "myfile.txt", "acl": [{"allow": "kundan"}, {"allow": "admin"}]}}'
    '''
    def list2dict(value):
        if hasattr(value, '_json_') and callable(value._json_): return value._json_()
        if hasattr(value, '_list_') and callable(value._list_): value = value._list_()
        if isinstance(value, tuple) and len(value) == 2 and isinstance(value[0], basestring):
            if isinstance(value[1], list):
                return {value[0]: [list2dict(x) for x in value[1]]}
            elif isinstance(value[1], tuple) and not [x for x in value[1] if not isinstance(x, tuple) or len(x) != 2 or not isinstance(x[0], basestring)]:
                return {value[0]: dict([(x[0], list2dict(x[1])) for x in value[1]])}
            else:
                return {value[0]: list2dict(value[1])}
        elif isinstance(value, tuple) and  not [x for x in value if not isinstance(x, tuple) or len(x) != 2 or not isinstance(x[0], basestring)]:
            return dict([(x[0], list2dict(x[1])) for x in value])
        elif isinstance(value, list):
            return [list2dict(x) for x in value]
        else: 
            return value
    return json.dumps(list2dict(value))

def xml(value):
    '''The function converts the supplied value to XML representation. It assumes the unified list format of value.
    Typically you just call represent(value, type=request['ACCEPT']) instead of manually invoking this method.
    To be consistent with str(obj) function which uses obj.__str__() method if available, xml() uses obj._xml_()
    method if available on value. Otherwise it checks obj._list_() method if available to get the unified list format.
    Otherwise it assumes that the value is in unified list format. The _xml_ and _list_ semantics allow you to 
    customize the XML representation of your object, if needed.
    
    >>> value = ('file', (('name', 'myfile.txt'), ('acl', [('allow', 'kundan'), ('allow', 'admin')])))
    >>> xml(value)
    '<file><name>myfile.txt</name><acl><allow>kundan</allow><allow>admin</allow></acl></file>'
    '''
    if hasattr(value, '_xml_') and callable(value._xml_): return value._xml_()
    if hasattr(value, '_list_') and callable(value._list_): value = value._list_()
    if isinstance(value, tuple) and len(value) == 2 and isinstance(value[0], basestring):
        if value[1] is None: return '<%s />'%(value[0])
        else: return '<%s>%s</%s>'%(value[0], xml(value[1]), value[0])
    elif isinstance(value, list) or isinstance(value, tuple):
        return ''.join(xml(x) for x in value)
    else:
        return str(value) if value is not None else None
        
def prettyxml(value):
    '''This function is similar to xml except that it invokes minidom's toprettyxml() function. Note that due to the
    addition of spaces even in text nodes of prettyxml result, you cannot use this reliably for structured data
    representation, and should use only for debug trace of XML.
    '''
    return minidom.parseString(xml(value)).toprettyxml().encode('utf-8')

def represent(value, type='*/*'):
    '''You can use this method to convert a unified value to JSON, XML or text based on the type. The JSON representation
    is preferred if type is default, otherwise the type values of "application/json", "text/xml" and 
    "text/plain" map to tojson, xml and str functions, respectively. If you would like to customize the representation of 
    your object, you can define _json_(), _xml_() and/or __str__() methods on your object. Note that _json_ and _xml_ 
    fall back to _list_ if available for getting the unified list representation, and __str__ falls back to __repr__ if 
    available. The return value is a tuple containing type and value.
    
    >>> class user: 
    ...    def __init__(self, name): self.name = name
    ...    def _list_(self): return  ('allow', self.name)
    >>> u1, u2 = user('kundan'), user('admin')
    >>> value = ('file', (('name', 'myfile.txt'), ('acl', [u1, u2])))
    >>> represent(value, type='application/json')[1]
    '{"file": {"name": "myfile.txt", "acl": [{"allow": "kundan"}, {"allow": "admin"}]}}'
    >>> represent(value, type='text/xml')[1]
    '<file><name>myfile.txt</name><acl><allow>kundan</allow><allow>admin</allow></acl></file>'
    '''
    types = map(lambda x: x.lower(), re.split(r'[, \t]+', type))
    if '*/*' in types: types.append(defaultType)
    for type, func in (('application/json', tojson), ('text/xml', xml), ('text/plain', str)):
        if type in types: return (type, func(value))
    return ('application/octet-stream', str(value))

#------------------------------------------------------------------------------
# High Level API: @resources
#------------------------------------------------------------------------------

class Request(dict):
    '''A request object is supplied to the resource definition in various methods: GET, PUT, POST, DELETE.
    It is a dictionary containing env information. Additionally, all the matching attributes from the router are
    stored as properties of this object, extracted from env['wsgiorg.routing_args'].'''
    def __init__(self, env, start_response):
        self.update(env.iteritems())
        self.__dict__.update(env.get('wsgiorg.routing_args', {}))
        self.start_response = start_response
    def response(self, value, type=None):
        type, result = represent(value, type if type is not None else self.get('ACCEPT', defaultType))
        self.start_response('200 OK', [('Content-Type', type)])
        return result

class Status(Exception):
    '''The exception object that is used to throw HTTP response exception, e.g., raise Status, '404 Not Found'. 
    The resource definition can throw this exception.
    '''
           
def resource(func):
    '''A decorator to convert a function with nested function GET, PUT, POST and/or DELETE to a resource. The resource
    object allows you to write applications in high-level semantics and translate it to wsgiref compatible handler that
    is handled the router. The GET and DELETE methods take one argument (request) of type Request, whereas PUT and POST
    take additional argument (first is request of type Request, and second is) entity extracted from message body.
    Note that the function definition that is made as a resource, must have a "return locals()" at the end so that all
    the methods GET, PUT, POST and/or DELETE are returned when function is called with no arguments.
    
    >>> @resource
    ... def files():
    ...    def GET(request):
    ...        return represent(('files', [('file', 'myfile.txt')]), type='text/xml')[1]
    ...    def PUT(request, entity):
    ...        pass
    ...    return locals()
    >>> # test using the following code
    >>> env, start_response = {'REQUEST_METHOD': 'GET', 'PATH_INFO': '/xml/files', 'SCRIPT_NAME': '', 'QUERY_STRING': ''}, lambda x,y: (x, y)
    >>> print files(env, start_response)
    ['<files><file>myfile.txt</file></files>']
    ''' 
    method_funcs = func()
    if method_funcs is None:
        raise Status, '500 No "return locals()" in the definition of resource "%r"'%(func.__name__)
    def handler(env, start_response):
        if env['REQUEST_METHOD'] not in method_funcs:
            raise Status, '405 Method Not Allowed'

        req = Request(env, start_response)
        if env['REQUEST_METHOD'] in ('GET', 'HEAD', 'DELETE'):
            result = method_funcs[env['REQUEST_METHOD']](req)
        elif env['REQUEST_METHOD'] in ('POST', 'PUT'):
            if 'BODY' not in env:
                try: env['BODY'] = env['wsgi.input'].read(int(env['CONTENT_LENGTH']))
                except (TypeError, ValueError): raise Status, '400 Invalid Content-Length'
            if env['CONTENT_TYPE'].lower() == 'application/json' and env['BODY']: 
                try: env['BODY'] = json.loads(env['BODY'])
                except: raise Status, '400 Invalid JSON content'
            result = method_funcs[env['REQUEST_METHOD']](req, env['BODY'])
        return [result] if result is not None else []
    return handler

def bind(obj):
    '''Bind the given object to a resource. It returns a wsgiref compliant application for that resource.
    Suppose an object obj={'kundan': user1, 'singh': user2} is bound to a resource '/users' 
    then GET, PUT, POST and DELETE are implemented on that obj as 
    'GET /users' returns the obj description with its properties and methods.
    'GET /users/kundan' returns the user1 object description.
    'PUT /users/kundan' replaces user1 with the supplied value.
    'POST /users' adds a new property, attribute or list element.
    '''
    def handler(env, start_response):
        current, result = obj, None
        if env['REQUEST_METHOD'] == 'GET':
            while env['PATH_INFO']:
                logger.debug('path=%r', env['PATH_INFO'])
                part, index = None, env['PATH_INFO'].find('/', 1)
                if index < 0: index = len(env['PATH_INFO'])
                part, env['SCRIPT_NAME'], env['PATH_INFO'] = env['PATH_INFO'][1:index], env['SCRIPT_NAME'] + env['PATH_INFO'][:index], env['PATH_INFO'][index:]
                if not part: break
                if current is None: raise Status, '404 Object Not Found'
                try: current = current[int(part)] if isinstance(current, list) else current[part] if isinstance(current, dict) else current.__dict__[part] if hasattr(current, part) else None
                except: logger.exception('exception'); raise Status, '400 Invalid Scope %r'%(part,)
            if current is None: result = None 
            elif isinstance(current, list): result = [('url', '%s/%d'%(env['SCRIPT_NAME'], i,)) for i in xrange(len(current))]
            elif isinstance(current, dict): result = tuple([(k, v if isinstance(v, basestring) else '%s/%s'%(env['SCRIPT_NAME'], k)) for k, v in current.iteritems()])
            else:result = current
            type, value = represent(('result', result), type=env.get('ACCEPT', 'application/json'))
            start_response('200 OK', [('Content-Type', type)])
            return [value]
        else: raise Status, '405 Method Not Allowed'
    return handler
    
#------------------------------------------------------------------------------
# Data Model with sqlite3
#------------------------------------------------------------------------------

class Model(dict):
    '''A data model that abstracts the SQL table creation and uses sqlite3. Instead of defining a ORM (object-relation
    mapping), this just lets the application handle the SQL commands. The only convenience of this class is to allow
    creating the SQL tables using text description of the data model, define python class for each table that can
    constructed using all the values of a row of that table, and define sql and sql1 convenience methods.
        
    >>> desc = """
    ... user
    ...     id        integer        primary key
    ...     name      text
    ...     
    ... files
    ...     id        integer        primary key
    ...     name      text           not null
    ...     owner     int
    ...     created   datetime
    ...     size      int            default 0
    ...     foreign key (owner) references user(id)
    ... """
    >>> m1 = Model()
    >>> m1.create(desc)
    >>> c1 = m1.sql('INSERT INTO user VALUES (NULL, ?)', ('Kundan Singh',))
    >>> c2 = m1.sql('INSERT INTO user VALUES (NULL, ?)', ('Alok Singh',))
    >>> row = m1.sql1('SELECT * FROM user WHERE id=?', (1,))
    >>> u1 = m1['user'](*row)
    >>> print u1
    'id'=1, 'name'=u'Kundan Singh'
    >>> print u1._list_()
    ('user', (('id', 1), ('name', u'Kundan Singh')))
    >>> print 'table=%r attrs=%r properties=%r'%(u1.__class__._table_, u1.__class__._attrs_, u1.__dict__)
    table='user' attrs=['id', 'name'] properties={'id': 1, 'name': u'Kundan Singh'}
    '''
    def __init__(self, conn=None):
        '''Construct the model using optional sqlite3 connection. If missing, use a in-memory database.'''
        if conn is None:
            self.conn = sqlite3.connect(':memory:')
            self.conn.isolation_level = None
        else:
            self.conn = conn

    def close(self):
        '''Close the connection with the database.'''
        self.conn.close()
        self.conn = None
        
    def sql(self, *args):
        '''Execute a single SQL command and return the cursor. For select commands application should use the 
        cursor as an iterator, or invoke fetchone or fetchall as applicable.'''
        logger.debug('SQL: %s', ': '.join(map(str, args)))
        return self.conn.execute(*args)
    
    def sql1(self, *args): 
        '''Execute a single SELECT SQL command and return a single row of the result.'''
        return self.sql(*args).fetchone()
    
    def create(self, data_model, createTable=True, createType=True):
        '''Create the SQL tables using the data_model text description. An example text description is shown below. It
        defines two tables, user and files. Note that the primary key of id must be defined as "integer" instead of
        "int" or other variation for auto-increment of the id to work.
        '''
        # list of tuples (table-name, [list of attributes])
        tables = [(x[0], [y.strip() for y in x[1:]]) for x in (z.split('\n') for z in re.split(r'\r?\n\r?\n', re.sub(r'[ \t]{2,}', ' ', '\n'.join(map(str.rstrip, data_model.strip().split('\n'))))))]
        if createTable:
            map(lambda t: self.sql("CREATE TABLE %s (%s)"%(t[0], ', '.join(t[1]))), tables)
        if createType:
            for name, attrs in tables:
                class klass(object):
                    _defn_ = [(y, z) for y, z in (x.split(' ', 1) for x in attrs) if y.lower() not in ('foreign', 'primary', 'key')]
                    __doc__ = name + '\n  ' + '\n  '.join(['%s\t%s'%(x, y) for x, y in _defn_])  
                    _table_, _attrs_, _defn_ = name, [x for x, y in _defn_], [y for x, y in _defn_]
                    def __init__(self, *args, **kwargs):
                        keys = self.__class__._attrs_
                        for x in keys: self.__dict__[x] = None
                        for x, y in zip(keys[:len(args)], args): self.__dict__[x] = y
                        for k, v in kwargs.iteritems(): self.__dict__[k] = v
                    def __str__(self):
                        return ', '.join(['%r=%r'%(x, self.__dict__[x]) for x in self.__class__._attrs_ if x in self.__dict__])
                    def _list_(self):
                        return (self.__class__._table_, tuple((k, self.__dict__[k]) for k in self.__class__._attrs_ if k in self.__dict__))
                self[name] = klass
        
#------------------------------------------------------------------------------
# Authentication
#------------------------------------------------------------------------------

_loginTable = '''
user_login
    id integer primary key
    email text not null
    realm text not null
    hash tinyblob(32) not null
    token tinyblob(32)
'''

class AuthModel(Model):
    '''Authenticated Model class, which creates a database table of type user_login and uses that to provide various
    authentication methods.'''
    def __init__(self, conn=None):
        Model.__init__(self, conn)
        self.mypass = hashlib.md5(str(id(self)) + str(time.time())).hexdigest()
        self.create(_loginTable)
        
    def hash(self, email, realm, password):
        return hashlib.md5('%s:%s:%s'%(email, realm, password)).hexdigest()
    
    def token(self, user_id):
        tm = '%010x'%(int(time.time()),)
        return hashlib.md5(self.mypass + str(user_id) + tm).hexdigest() + tm
    
    def valid(self, user_id, token):
        hash, tm = token[:-10], token[-10:]
        return hashlib.md5(self.mypass + str(user_id) + tm).hexdigest() == hash
    
    def register(self, email, realm, password='', hash=None):
        if not hash: hash = self.hash(email, realm, password)
        self.sql('INSERT INTO user_login VALUES (NULL, ?, ?, ?, NULL)', (email, realm, hash))
        user_id = self.sql1('SELECT last_insert_rowid()')[0]
        self.sql('UPDATE user_login SET token=? WHERE id=?', (self.token(user_id), user_id))
        return user_id

    def login(self, request):
        hdr = request.get('HTTP_AUTHORIZATION', None)
        if hdr:
            method, value = map(str.strip, hdr.split(' ', 1))
            if method == 'Basic':
                email, password = base64.b64decode(value).split(':', 1)
                found = self.sql1('SELECT id, hash FROM user_login WHERE email=?', (email,))
                if not found: 
                    request.start_response('401 Unauthorized', [('WWW-Authenticate', 'Basic realm="%s"'%('localhost',))])
                    raise Status, '401 Not Found'
                user_id, hash = found; 
                realm = "localhost" # TODO: implement this
                hash_recv = self.hash(email, realm, password)
                if hash != hash_recv: 
                    request.start_response('401 Unauthorized', [('WWW-Authenticate', 'Basic realm="%s"'%(realm,))])
                    raise Status, '401 Unauthorized'
                token = self.token(user_id)
                self.sql('UPDATE user_login SET token=? WHERE id=?', (token, user_id))
                request['COOKIE']['token'] = token; request['COOKIE']['token']['path'] = '/'
                request['COOKIE']['user_id'] = user_id; request['COOKIE']['user_id']['path'] = '/'
                return (user_id, email, token)
        elif (hasattr(request, 'user_id') or hasattr(request, 'email')) and hasattr(request, 'token'):
            if request.email == 'admin':
                adminhash = hashlib.md5('%s::%s'%(request.email, self.mypass)).hexdigest()
                logger.debug('request.token=%r adminhash=%r', request.token, adminhash)
                if adminhash != request.token: raise Status, '401 Not Authorized'
                user_id, email, token = 0, request.email, adminhash
            else:
                found = self.sql1('SELECT id, email, token FROM user_login WHERE (id=? OR email=?) AND (token=? OR hash=?)', (request.user_id, request.email, request.token, request.token))
                if not found:
                    if not self.sql1('SELECT id FROM user_login WHERE id=? OR email=?', (request.user_id, request.email)):
                        raise Status, '404 Not Found'
                    else:
                        raise Status, '401 Unauthorized'
                user_id, email, token = int(found[0]), found[1], found[2]
            if token != request.token:
                token = self.token(user_id)
                self.sql('UPDATE user_login SET token=? WHERE id=?', (token, user_id))
            request['COOKIE']['token'] = token; request['COOKIE']['token']['path'] = '/'
            request['COOKIE']['user_id'] = user_id; request['COOKIE']['user_id']['path'] = '/'
            return (user_id, email, token)
        elif 'COOKIE' in request and 'user_id' in request['COOKIE'] and 'token' in request['COOKIE']:
            user_id, token = int(request['COOKIE'].get('user_id').value), request['COOKIE'].get('token').value
            if user_id == 0:
                email = 'admin'; hash = hashlib.md5('%s::%s'%(email, self.mypass)).hexdigest()
                if hash != token:
                    raise Status, '401 Not Authorized as Admin'
            else:
                found = self.sql1('SELECT email FROM user_login WHERE id=? AND token=?', (user_id, token))
                if not found:
                    request['COOKIE']['user_id']['expires'] = 0
                    request['COOKIE']['user_id']['path'] = '/'
                    request['COOKIE']['token']['expires'] = 0
                    request['COOKIE']['token']['path'] = '/'
                    realm = "localhost"
                    request.start_response('401 Unauthorized', [('WWW-Authenticate', 'Basic realm="%s"'%(realm,))])
                    raise Status, '401 Unauthorized'
                email = found[0]
            return (user_id, email, token)
        else: 
            realm = "localhost"
            request.start_response('401 Unauthorized', [('WWW-Authenticate', 'Basic realm="%s"'%(realm,))])
            raise Status, '401 Unauthorized'

    def logout(self, request):
        if 'COOKIE' in request and 'user_id' in request['COOKIE'] and 'token' in request['COOKIE']:
            user_id, token, request['COOKIE']['token']['expires'] = request['COOKIE']['user_id'].value, request['COOKIE']['token'].value, 0
            if user_id != 0:
                self.sql('UPDATE user_login SET token=NULL WHERE id=? AND token=?', (user_id, token))

#------------------------------------------------------------------------------
# Test and Examples
#------------------------------------------------------------------------------

if __name__ == '__main__':
    import doctest
    logging.basicConfig()
    logger.setLevel(logging.CRITICAL)
    doctest.testmod()
