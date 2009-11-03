#  Copyright (c) 2009, Cloud Matrix Pty. Ltd.
#  All rights reserved; available under the terms of the BSD License.
"""

  esky.finder:  VersionFinder implementations for esky

This module provides the default VersionFinder implementains for esky. The
abstract base class 'VersionFinder' defines the expected interface, while 
'SimpleVersionFinder' provides a simple default implementation that hits a
specified URL to look for new versions.

"""

import os
import re
import stat
import urllib2
import zipfile
import shutil
from urlparse import urljoin

from distutils.util import get_platform

from esky.bootstrap import parse_version
from esky.errors import *


class VersionFinder(object):
    """Base VersionFinder class.

    This class defines the interface expected of a VersionFinder object.
    It will be given two properties at initialisation time:

        appname:  name of the application being managed
        workdir:  directory in which updates can be downloaded, extracted, etc

    The important methods expected from any VersionFinder are:

        cleanup:  perform maintenance/cleanup tasks in the workdir
                  (e.g. removing old or broken downloads)

        find_versions:  get a list of all available versions

        fetch_version:  make the specified version available locally
                        (e.g. download it from the internet)

        has_version:  check that the specified version is available locally

        prepare_version:  extract the specific version into a directory
                          that can be linked into the application

    """

    def __init__(self,appname=None,workdir=None):
        self.appname = appname
        self.workdir = workdir

    def cleanup(self):
        """Perform maintenance tasks in the working directory."""
        pass

    def find_versions(self):
        """Find available versions of the app, returned as a list."""
        raise NotImplementedError

    def fetch_version(self,version):
        """Fetch a specific version of the app into local storage."""
        raise NotImplementedError

    def has_version(self,version):
        """Check whether a specific version of the app is available locally."""
        raise NotImplementedError

    def prepare_version(self,version):
        """Extract a specific version of the app into a local directory."""
        raise NotImplementedError


class SimpleVersionFinder(VersionFinder):
    """VersionFinder implementing simple download scheme.

    SimpleVersionFinder expects to be given a download url, which it will
    hit looking for new versions packaged as zipfiles.  These are simply
    downloaded and extracted on request.

    Zipfiles suitable for use with this class can be produced using the
    "bdist_esky" distutils command.
    """

    def __init__(self,download_url,**kwds):
        self.download_url = download_url
        super(SimpleVersionFinder,self).__init__(**kwds)
        self.version_urls = {}
        try:
            os.makedirs(os.path.join(self.workdir,"downloads"))
        except OSError, e:
            if e.errno not in (17,183):
                raise
        try:
            os.makedirs(os.path.join(self.workdir,"unpack"))
        except OSError, e:
            if e.errno not in (17,183):
                raise

    def cleanup(self):
        dldir = os.path.join(self.workdir,"downloads")
        for nm in os.listdir(dldir):
            os.unlink(os.path.join(dldir,nm))
        updir = os.path.join(self.workdir,"unpack")
        for nm in os.listdir(updir):
            os.unlink(os.path.join(updir,nm))

    def open_url(self,url):
        return urllib2.urlopen(url)

    def find_versions(self):
        downloads = self.open_url(self.download_url).read()
        link_re = "href=['\"](?P<href>(.*/)?%s-(?P<version>[a-zA-Z0-9\\.-]+).%s.zip)['\"]" % (self.appname,get_platform(),)
        found = []
        for match in re.finditer(link_re,downloads):
            self.version_urls[match.group("version")] = match.group("href")
        return self.version_urls.keys()

    def fetch_version(self,version):
        try:
            url = self.version_urls[version]
        except KeyError:
            raise EskyVersionError(version)
        infile = self.open_url(urljoin(self.download_url,url))
        outfilenm = self._download_name(version)+".part"
        outfile = open(outfilenm,"wb")
        try:
            data = infile.read(1024*512)
            while data:
                outfile.write(data)
                data = infile.read(1024*512)
        except Exception:
            infile.close()
            outfile.close()
            os.unlink(outfilenm)
            raise
        else:
            infile.close()
            outfile.close()
            os.rename(outfilenm,self._download_name(version))

    def _download_name(self,version):
        return os.path.join(self.workdir,"downloads","%s-%s.%s.zip" % (self.appname,version,get_platform(),))

    def has_version(self,version):
        return os.path.exists(self._download_name(version))

    def prepare_version(self,version):
        dlpath = self._download_name(version)
        vdir = "%s-%s" % (self.appname,version,)
        uppath = os.path.join(self.workdir,"unpack")
        zf = zipfile.ZipFile(dlpath,"r")
        for nm in zf.namelist():
            if not nm.startswith(vdir):
                continue
            infile = zf.open(nm,"r")
            outfilenm = os.path.join(uppath,nm)
            if not os.path.isdir(os.path.dirname(outfilenm)):
                os.makedirs(os.path.dirname(outfilenm))
            outfile = open(outfilenm,"wb")
            try:
                shutil.copyfileobj(infile,outfile)
            finally:
                infile.close()
                outfile.close()
            mode = zf.getinfo(nm).external_attr >> 16L
            os.chmod(outfilenm,mode)
        return os.path.join(uppath,vdir)


