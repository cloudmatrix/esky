"""

  esky.finder:  VersionFinder implementations for esky

"""

import os
import re
import stat
import urllib2
import zipfile
import uuid
from urlparse import urljoin

from esky.bootstrap import parse_version
from esky.errors import *


class VersionFinder(object):

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
            os.makedirs(os.path.join(self.workdir,"unpacked"))
        except OSError, e:
            if e.errno not in (17,183):
                raise

    def cleanup(self):
        dldir = os.path.join(self.workdir,"downloads")
        for nm in os.listdir(dldir):
            os.unlink(os.path.join(dldir,nm))
        updir = os.path.join(self.workdir,"unpacked")
        for nm in os.listdir(updir):
            os.unlink(os.path.join(updir,nm))

    def open_url(self,url):
        return urllib2.urlopen(url)

    def find_versions(self):
        downloads = self.open_url(self.download_url).read()
        link_re = "href=['\"](?P<href>(.*/)?%s-(?P<version>[a-zA-Z0-9\\.-]+).zip)['\"]" % (self.appname,)
        found = []
        for match in re.finditer(link_re,downloads):
            self.version_urls[match.group("version")] = match.group("href")
        return self.version_urls.keys()

    def fetch_version(self,version):
        try:
            url = self.version_urls[version]
        except KeyError:
            raise NoSuchVersionError(version)
        infile = self.open_url(urljoin(self.download_url,url))
        rand_id = uuid.uuid4().hex
        outfilenm = os.path.join(self.workdir,"downloads",rand_id)
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
            os.rename(outfilenm,os.path.join(self.workdir,"downloads","%s-%s.zip"%(self.appname,version,)))

    def has_version(self,version):
        return os.path.exists(os.path.join(self.workdir,"downloads","%s-%s.zip"%(self.appname,version,)))

    def prepare_version(self,version):
        rand_id = uuid.uuid4().hex
        dlpath = os.path.join(self.workdir,"downloads","%s-%s.zip"%(self.appname,version,))
        uppath = os.path.join(self.workdir,"unpacked",rand_id)
        os.mkdir(uppath)
        zf = zipfile.ZipFile(dlpath,"r")
        for nm in zf.namelist():
            infile = zf.open(nm,"r")
            outfilenm = os.path.join(uppath,nm)
            if not os.path.isdir(os.path.dirname(outfilenm)):
                os.makedirs(os.path.dirname(outfilenm))
            outfile = open(os.path.join(uppath,nm),"wb")
            try:
                data = infile.read(1024*512)
                while data:
                    outfile.write(data)
                    data = infile.read(1024*512)
            finally:
                infile.close()
                outfile.close()
            mode = zf.getinfo(nm).external_attr >> 16L
            os.chmod(outfilenm,mode)
        return uppath



