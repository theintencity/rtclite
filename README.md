# Light weight implementations of real-time communication protocols and applications in Python

This project aims to create an open source repository of light weight implementations 
of real-time communication (RTC) protocols and applications.
In a nutshell, it contains reference implementations, 
prototypes and sample applications, mostly written in Python, of various RTC standards defined in 
the IETF, W3C and elsewhere, e.g., RFC 3261 (SIP), RFC 3550 (RTP), RFC 3920 (XMPP), RTMP, etc.


## Background

> This project was migrated from <https://code.google.com/p/rtclite> on May 17, 2015  
> Keywords: *Python*, *Realtime*, *Communication*, *Library*, *Academic*, *SIP*, *RTP*, *WebRTC*, *RTMP*  
> Members: *kundan10*, *theintencity*, *mamtasingh05*, *voipresearcher*  
> Links: [Project](http://39peers.net/), [Support](http://groups.google.com/group/myprojectguide)  
> License: [GNU Lesser GPL](http://www.gnu.org/licenses/lgpl.html)  

The "rtclite" project is created to host the source code of the "39 peers"
project, and the two project names are used interchangeably here.
Please visit the [project website](http://39peers.net) for further details.

This project is an effort to unify my Python-based projects related to SIP, RTP, RTMP, Web
into a single theme of real-time communication (RTC). In particular, the initial source code
is borrowed after cleanup from these projects, without adding any significant new functionality:

> [p2p-sip](https://github.com/theintencity/p2p-sip): SIP, P2P, XMPP and other related code.
> [rtmplite](https://github.com/theintencity/rtmplite): RTMP, RTMFP and SIP-RTMP translation.
> [restlite](https://github.com/theintencity/restlite): REST web APIs

## Motivation

The primary motivation is described in my earlier blog article,
[a proposal for reference implementation repositiory for RFCs](http://blog.kundansingh.com/2011/06/proposal-for-reference-implementation.html).

With growing number of emerging RTC standards, the trend of
creating specifications without implementations, and consecutively the interoperability
problems have increased. This project will hopefully simplify the
job of an RTC programmer and, in the long term, will result in more interoperable
and robust RTC products.
This project contains source code of various RTC specifications.
The source code is annotated with text snippets from
the relevant specification to show (a) how the code fragment implements
the specification, (b) which part of the specification is relevant to the
code fragment, and vice-versa, and (c) the implicit code documentation 
borrowed from the text in the specification.

[Browse annotated source code](http://kundansingh.com/p/rtclite/index.html),
e.g., [rfc3550.py (RTP)](http://kundansingh.com/p/rtclite/std/ietf/rfc3550.py.html),
[rfc3261.py (SIP)](http://kundansingh.com/p/rtclite/std/ietf/rfc3261.py.html),
[caller.py](http://kundansingh.com/p/rtclite/app/sip/caller.py.html),
[chat.py](http://kundansingh.com/p/rtclite/vnd/google/chat.py.html).

Furthermore, the project contains various applications built on top of these
open standards and open source implementations to demonstrate real use cases, e.g.,
SIP proxy server, XMPP client, command line SIP dialer, SIP-RTMP gateway, etc.
The light-weight nature of the various Python modules enables other developers to
easily use these in their projects, without other complex framework dependencies.

## Design Goals

The primary design goal of this project is to provide reference implementation
of popular real-time communication protocols. The implementation is done in
Python 2.7 programming language, but may be ported in future to others. There are
two parts in the source code -- the protocols and
the applications.
Following goals are met in the current implementations of the protocols.

* System Portability: apart from the Python standard library, the
  project should not rely on other third-party libraries. If such third-
  party libraries become necessary, consider including them in the
  repository or provide clear instructions for such dependency.
  The module should isolate such dependencies to smaller part if possible.
  The project should therefore be portable to many interpreters and
  runtime environments.
* Threading: threading vs event-driven programming style is decision that
  best left to the application developer instead of forcing a particular
  choice in the library. The project should not impose such decision in
  reference implementation. If it is necessary to include such choice,
  then it should provide reasonable set of alternatives pre-built in the
  module.
* Concise and Precise Code: Python enables expressing ideas in code in
  less number of lines. The programmer should further honor the Pythonic
  programming style. Less number of lines means that one can write software
  faster, and with less garbage (syntactic sugar), one can read and
  understand the code easily. Moreover, testing and review efforts are less.
  The resulting improvement in programmer's efficiency reflects in her
  motivation to write more clean code.
* Testing: testing is an integral part of all code in this project. It
  uses doctest whereever possible to integrate code with documentation and
  testing. Alternatively, dedicated test and sample applications are
  included for manual or automated testing. Generally, running a protocol module
  on command line via Python interpreter should run its test cases and
  report any errors.
* Logging: standard logging module is used at various log levels. The code
  should avoid using the standard print statements as much as possible
  for logging - helps in migrating to Python3 in future, and reduces
  unwanted output when the module is included elsewhere.

On the other hand, implementation of an application may depend on
the specific system, e.g., for audio/video interface, or specific threading vs. event
programming style, or custom user interface, e.g., web vs. curses vs. command line.
These applications are for demonstration purpose, and not for production use.

## Software Structure

The `std`, `app` and `vnd` packages under top-level `rtclite` include the implementations
of the protocols and the applications. The `std` package further includes sub-packages
for standard bodies, e.g., `ietf` and `w3c`. The `app` package contains not only the
applications but also supporting library modules classified under high level
categories such as `net`, `sip` or `sec`, and the `vnd` package contains vendor specific 
protocol implementations such as `adobe` sub-package for `rtmp` and `siprtmp`.

In an application, a module from this project should always be imported with the
package hierarchy, e.g.,
```
import rfc3261 # WRONG
from rtclite.std.ietf import rfc3261 # RIGHT
from rtclite.std.ietf.rfc3261 import UserAgent # RIGHT AGAIN
import rtclite.std.ietf.rfc3261 # STILL RIGHT
```

Similarly, a protocol or application module should be invoked with the right package
hierarchy, e.g.,
```
cd rtclite/std/ietf; python rfc3921.py  # WRONG
python -m rtclite.std.ietf.rfc3921 # RIGHT
```

The included `Makefile` can be used on Unix-like systems to test all the protocol
modules, to generate annotated source file documentations, and to create
installable distribution.
```
make test
make doc
```
