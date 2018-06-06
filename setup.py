# Copyright (c) 2007-2011 Kundan Singh. All rights reserved. See LICENSE for details.

"""rtclite setup script

Install or create a distribution of the rtclite package.
"""

from os import listdir, path, remove, rename, walk
from sys import argv
from pickle import dump, load
from distutils.core import setup
from distutils.command.install import INSTALL_SCHEMES

# Make the root for data file installations the same as Python code
for scheme in list(INSTALL_SCHEMES.values()):
    scheme['data'] = scheme['purelib']

NAME = "rtclite"
VERSION = "3.0"

DIST_DIR = "dist"
FORMAT_TO_SUFFIX = { "zip": ".zip", "gztar": ".tar.gz", "bztar": ".tar.bz2", "ztar": ".tar.Z", "tar": ".tar" }

def invoke_setup(data_files=None):
    data_files_file, data_files_file_created = "data_files", False
    try:
        if data_files: # Save the value of data_files with the distribution archive
            data_files_file_created = True
            with open(data_files_file, "wb") as fl:
                dump(data_files, fl)
            data_files.append(('', [data_files_file]),)
        else: # Load data_files from the distribution archive, if present
            try:
                with open(data_files_file, "rb") as fl:
                    data_files = load(fl)
            except IOError:
                data_files = []
        data_files.append(('rtclite', ["Makefile", "LICENSE", "README.md"]),)
        packages = [x[0] for x in walk('rtclite') if path.exists(x[0] + '/__init__.py')]
        setup(name=NAME, version=VERSION,
              description="Light weight implementations of real-time communication protocols and applications in Python",
              author="Kundan Singh", author_email="theintencity@gmail.com",
              url="https://github.com/theintencity/rtclite", license="LICENSE",
              long_description=open("README.md").read(),
              packages=packages, package_data={"std": ["specs/*"]},
              python_requires=">=3.3"
              data_files=data_files)
    finally:
        if data_files_file_created:
            try:
                remove(data_files_file)
            except OSError:
                pass

if __name__ == "__main__":
    invoke_setup()
