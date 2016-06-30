# Light-weight RESTful server tools in Python #

# What is restlite? #
Restlite is a light-weight Python implementation of server tools for quick prototyping of your RESTful web service. Instead of building a complex framework, it aims at providing functions and classes that allows your to build your own application.

>> rest = REST + Python + JSON + XML + SQLite + authentication

### Features ###

  1. Very lightweight module with single file in pure Python and no other dependencies hence ideal for quick prototyping.
  1. Two levels of API: one is not intrusive (for low level WSGI) and other is intrusive (for high level @resource).
  1. High level API can conveniently use sqlite3 database for resource storage.
  1. Common list and tuple-based representation that is converted to JSON and/or XML.
  1. Supports pure REST as well as allows browser and Flash Player access (with GET, POST only).
  1. Integrates unit testing using doctest module.
  1. Handles HTTP cookies and authentication.
  1. Integrates well with WSGI compliant applications.


# Getting Started #

This section describes how to start using rest.

## What is WSGI? ##

The web server and gateway interface (WSGI) specification defines a uniform interface that allows you to build consistent and compliant web services for a wide variety of use cases. Python comes with a reference implementation in [wsgiref](http://docs.python.org/library/wsgiref.html) module. The basic idea that is each web application is callable with two arguments, environment dictionary and a `start_response` function. The application invokes the function to start the response, and returns an `iterable` object which is returned in the response. The HTTP methods and path are available in the environment dictionary.

For example, you can write a simple WSGI compliant "hello world" web application as follows. If you execute the following code fragment, point your web-browser to localhost:8000, you will see the "Hello World!" message.

```
def handle_request(env, start_response):
    start_response('200 OK', [('Content-Type', 'text/plain')]
    return ['Hello World!']

from wsgiref.simple_server import make_server
httpd = make_server('', 8000, handle_request)
httpd.serve_forever()
```


## REST URL router ##

At the core of rest, there is a URL router. The router itself is a WSGI application, which in turn takes a list of patterns for HTTP method and URL, performs pattern matching, applies any request transformation for matching request, and invokes another WSGI application for matching request, if any. You can use the routes to do several things: identify the required response type from part of URL, identify and store some parts of the URL in variables, modify some HTTP header or body, or transform the method or URL. The router uses standard regular expression for pattern matching and string formatting for transformation.

Consider the following example which defines a `files_handler` application and a route which maps `GET /files` to the application.
```
def files_handler(env, start_response): 
   return '<files><type>' + env['ACCEPT'] + '</type><file>somefile.txt</file></files>'

routes = [
 (r'GET,PUT,POST /xml/(?P<path>.*)$', 'GET,PUT,POST /%(path)s', 'ACCEPT=text/xml'),
 (r'GET /files$', files_handler) 
]

import wsgiref
from rtclite.app.web import rest
httpd = wsgiref.simple_server.make_server('', 8000, rest.router(routes))
httpd.serve_forever()
```

Learn how the routes are specified as a list of tuples, where each tuple is a route entry. The first item in a route entry is used for matching the request. A request matches if the method matches one of the comma-separated method and the URL matches the regular expression of the URL. Note that internally it invokes `re.match` which matches the URL pattern at the beginning of the request URL. If you would like to match the full URL in your pattern, you must end your regular expression using `$`. If you would like to match only a prefix of a URL, do not use `$` at the end. The second item in the tuple gives the optional transformation. In this case, the first route transforms a URL of the form `/xml/some/path/here` to `/some/path/here` and sets the `ACCEPT` header to "text/xml". The string formatting syntax is used to substitute the matching `path` regular expression variable in the second item. The request method is substituted in order, e.g., in our case there is no change in the request method. The subsequent items in the route specify any modifications to the request, such as changing a header or body.

The second route actually invokes the handler application. The first item of the second route is, as before, the pattern for method and URL. The last item of the route may be a callable application, in which case a matching request invokes that callable application and stops further routes for this request. The route matching happens sequentially and stops when a matching route has specified an application. The net result of these two routes is that, it supports `GET /files` as well as `GET /xml/files` where the latter assumes that the ACCEPT header is "text/xml".

The HTTP headers are identified in the environment dictionary using capitalized names for the headers and `_` instead of `-`, similar to the convention used in CGI. For example, the `Content-Type` header is identified as `CONTENT_TYPE`. You can set a environment variable in the router as mentioned before, or you can access the environment variable in the application if needed.

The following example is a more realistic use case, where the `file` application is used to read a file on the disk relative to some `directory`. The routes specify only `GET /file` without the trailing `$`, so that it can be invoked as `GET /file/data.py`. When the application `file` is invoked, the first argument, `env`, holds all the environment dictionary. The WSGI standard says that `PATH_INFO` environment contains the remaining path, in this case, `rest.py`, that are not matched by the router. The application retrieves the file relative to the `directory` and returns the content using `Content-Type` of "application/octet-stream". There is a `Status` exception object that you can use to send an immediate failure response. Alternatively, you can also use `start_response` and return.
```
import os, wsgiref
from rtclite.app.web import rest

directory = '.'

def file(env, start_response):
    global directory
    path = os.path.join(directory, env['PATH_INFO'][1:] if env['PATH_INFO'] else '')
    if not os.path.isfile(path): raise rest.Status, '404 Not Found'
    start_response('200 OK', [('Content-Type', 'application/octet-stream')])
    try:
        with open(path, 'rb') as f: result = f.read()
    except: raise rest.Status, '400 Error Reading File'
    return [result]

routes = [
    (r'GET /file', file)
]

httpd = wsgiref.simple_server.make_server('', 8000, rest.router(routes))
httpd.serve_forever()
```

The `router` is actually a function that takes a list of route tuples, and returns a WSGI application that performs route matching and application invocation. For most low-level applications, the `router` is the only function you need to implement your RESTful web service. When using the router or supplying a WSGI application as a route application, please pay particular attention to the following:
  1. The matching happens sequentially in the list of routes. A matching route performs transformation, if any, and invokes application, if any. If a matching route has an application, the process stops, otherwise it continues to the next matching route.
  1. The return value must be iterable. In most cases you can return a list containing the value. This is as specified by WSGI.
  1. Any matching regular expression variable will be available in `wsgiorg.routing_args` environment. For example if your regular expression has `(?P<path>...)` then the matching component of the URL will be in `env['wsgiorg.routing_args']['path']`.
  1. You can set any header in the response using `start_response` function.
  1. To allow browser or Flash Player to access (PUT, DELETE) your resources, you may need to use route transforms to map POST or GET to these methods.

Please see a complete example in example.py available in the repository.

## High level resource ##

Rest also includes a decorator, `@resource`, that allows you to define high level resource. The basic idea is to convert a function containing HTTP method handlers to a WSGI application, which can be given to the `router`. Consider the following example where a resource is created out of `config` function. The code fragment creates a resource for representing the top-level `directory` we used in the previous example.
```
directory = '.'

@rest.resource
def config():
    def GET(request):
        global directory
        return request.response(('config', ('directory', directory)))
    def PUT(request, entity):
        global directory
        directory = str(entity)
    return locals()
```
Note that the `request` argument to the method handler function actually is an extension of the environment dictionary, hence all the key-values of the environment are also available in `request`. Additionally, `request.start_response` is a reference to the `start_response` function of the WSGI appllication.

Once your have create a resource using this mechanism, you can supply the application to the router. The following example allows GET, PUT and POST methods on this resource accessed as `/config`, such that POST is transformed to PUT. Hence you only need to define GET and PUT in the resource `config`.
```
routes = [
    ...
    (r'GET /config\?directory=(?P<directory>.*)', 'PUT /config', 'CONTENT_TYPE=text/plain', 'BODY=%(directory)s', config),
    (r'GET,PUT,POST /config$', 'GET,PUT,PUT /config', config),
]
```

The key points to remember are:
  1. Must use `return locals()` at the end of your resource function.
  1. The GET and DELETE methods take one argument, `request`, and the PUT and POST methods take two arguments, `request` and `entity`. The entity is basically the message body.
  1. The `request.start_response` method is also available, if you need.
  1. You can raise the `Status` exception to return an error response.
  1. The handlers can be implemented for GET, PUT, POST and DELETE. You do not need to implement all handlers, in which case it will return '405 Method Not Allowed' response.

## Binding to Python variables ##

Rest also allows you to bind to a Python variable such as object, list, tuple or dictionary. The following example shows that the list `users` is converted to WSGI application, which is used in the routes to match `GET /users`.

```
users = [{'username': 'kundan', 'name': 'Kundan Singh', 'email': 'kundan10@gmail.com'},
         {'username': 'alok'}]
users = rest.bind(users)

routes = [
    ...
    (r'GET /users', users),
]
```

Note that there is no trailing `$` in the regular expression, hence it matches the prefix `/users` and can handle several URLs of the form `/users`, `/users/0`, `/users/1/username`. The basic idea behind the `bind` function is to take a Python object and return a WSGI application that allows accessing the object hierarchically. For example, if the top-level object `users` is bound to `/users` and represents a list, then `/users/i` represents the i'th item in that list. Similarly, if `/users/1` is a dictionary then `/users/1/username` represents the value of index `username` in that dictionary. Similarly, an object attribute is accessed by sub-scoping.

Future work: You may extend the `bind` function to support update and new operations as well.

## Representation ##

Rest supports two representations, XML and JSON, identified by "text/xml" and "application/json" content type. It also supports primitive "text/plain" representation using the built-in `str` function.

There is a `rest.defaultType` variable, which you can modify in your application to use a particular default representation. I use "application/json" as my default.

To support different representations for structured data, I assume a unified list representation, which gets converted to the XML or JSON representation using the `rest.represent` or `request.response` function. You might have noticed the use of `request.response` function in the `config` example above.

The basic idea behind unified list representation is to represent structured data using tuples or list, instead of using dictionary. Why? because the order is lost in dictionary, which may be needed in XML representation. For example, the following represents a 'file' with 'name' and 'acl' properties. The 'acl' property itself is a list of two names.
```
value = ('file', (('name', 'myfile.txt'), 
                  ('acl', [('allow', 'kundan'), ('allow', 'admin')])))
```
You can get the corresponding XML and JSON representations as follows. Note that the `represent` function takes a value and optional type, returns a tuple of type and formatted value. If type is not supplied or contains "**/**", then the `defaultType` is assumed.
```
rest.represent(value, type='application/json')[1]
# '{"file": {"name": "myfile.txt", "acl": [{"allow": "kundan"}, {"allow": "admin"}]}}'

rest.represent(value, type='text/xml')[1]
# '<file><name>myfile.txt</name><acl><allow>kundan</allow><allow>admin</allow></acl>
```

If you would like to customize a particular representation, of a `value` object, you can override the `__str__`, `_json_` or `_xml_` methods. Alternatively, you can override the `_list_` method to customize the unified list representation. The following example shows the user object is customized, and produces the same representation as before.
```
class user: 
   def __init__(self, name): self.name = name
   def _list_(self): return  ('allow', self.name)
   def __str(self): return 'allow=' + self.name
u1, u2 = user('kundan'), user('admin')
value = ('file', (('name', 'myfile.txt'), ('acl', [u1, u2])))
```

The `rest.represent` and `request.response` function are available for convenience if you want to support multiple representations of your structured data. By default, `request.response` function understands the `ACCEPT` header in the request and tries to create a representation that best matches the header value. On the other hand, the `rest.represent` function should be given the desired type if different from default. If you do not wish to support multiple representations of your structured data, you may return the actual representation from your resource or application directly instead of using these functions.

## Data model ##

Rest has a `Model` class which you can use to create you sqlite3 based data model. You can describe your database tables in text or use the `sql` method. An example is shown below to create two tables:

```
data = '''
files
    id integer primary key
    name text not null
    path text not null

keywords
    id integer primary key
    file_id int
    keyword text
'''
m = rest.Model()
m.create(data)
m.sql('INSERT INTO files VALUES (NULL, ?, ?)', ('myfile.txt', '/path/to/myfile.txt'))
```

The `sql` method returns a cursor, whereas `sql1` method returns the first row item in the query, which is useful typically for `SELECT` queries.

The `Model` class is provides for convenience and is not related to resource or router described before. However, if you use a data model in your application, you can store your data and access it as needed in various method handlers of your resource or application.

## Authentication ##

Rest supports two types of authentication: HTTP basic authentication or using cookies and parameters. The `AuthModel` class extends the data model to provide authentication, and stores the user information in `user_login` SQL table. It also provides several methods such as `login`, `logout`, `register`, `hash`, `token`, etc., related to authentication. If you want to use the authentication feature, I encourage you to look at the implementation of `AuthModel`. The following example creates a `private` resource mapped to 'GET /private', and uses `login` method on `AuthModel` to perform authentication.
```
model = rest.AuthModel()
model.register('kundan10@gmail.com', 'localhost', 'somepass')

@rest.resource
def private():
    def GET(request):
        global model
        model.login(request)
        return request.response(('path', request['PATH_INFO']))
    return locals()

routes = [
    ...
    (r'GET /private/', private)
]
```
When you visit the URL, you will be prompted with authentication dialog box, where you can enter username as "kundan10@gmail.com" and password as "somepass" to authenticate.

The authentication can be done either using HTTP basic or by supplying the `user_id` or `email` in addition to the `token` property to the request. Once authenticated, it creates a `token` which is set in the cookies, so that subsequent requests from the browser will not need to be authenticated using HTTP basic or parameters again.

If you include authentication in your application, you may also want to incorporate 'GET /login' and 'GET /logout' URL resources that allows the user to login and logout, respectively.

## Testing ##

I have written several unit test code in `rest.py` which you can invoke by running that module.
```
python -m rtclite.app.web.rest -v
```

Additionally, there is `example.py` which implements a real file server application using RESTful architecture. It also demonstrates how to use `@resource`, `bind` and authentication. Moreover, it has client-side of the code using Python's `urllib2` module, which implements several unit tests. To perform the unit tests:
```
python example.py --unittest
```

To run the web-based file access server:
```
python example.py
```

# Motivation #

As you may have noticed, the software provides tools such as (1) regular expression based request matching and dispatching WSGI compliant `router`, (2) high-level resource representation using a decorator and variable binding, (3) functions for converting from unified list representation to JSON and XML, and (3) data model and authentication classes. These tools can be used independent of each other. For example, you just need the `router` function to implement RESTful web services. If you also want to do high-level definitions of your resources you can use the `@resource` decorator, or `bind` functions to convert your function or object to WSGI compliant application that can be given to the `router`. You can return any representation from your application. However, if you want to support multiple consistent representations of XML and JSON, you can use the `represent` function of `request.response` method to do so. Finally, you can have any data model you like, but implementations of common SQL style data model and HTTP basic and cookie based authentication are provided for you to use if needed.

This software is provided with a hope to help you quickly realize RESTful services in your application without having to deal with the burden of large and complex frameworks. Any feedback is appreciated. If you have trouble using the software or want to learn more on how to use, feel free to send me a note!



