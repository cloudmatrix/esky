#  Copyright (c) 2009, Cloud Matrix Pty. Ltd.
#  All rights reserved; available under the terms of the BSD License.
"""

  esky.finder:  VersionFinder implementations for esky

This module provides the default VersionFinder implementations for esky. The
abstract base class "VersionFinder" defines the expected interface, while 
"DefaultVersionFinder" provides a simple default implementation that hits a
specified URL to look for new versions.

"""

import os
import re
import stat
import urllib2
import zipfile
import shutil
from urlparse import urljoin

from esky.bootstrap import parse_version, join_app_version
from esky.errors import *
from esky.util import extract_zipfile


class VersionFinder(object):
    """Base VersionFinder class.

    This class defines the interface expected of a VersionFinder object.
    The important methods expected from any VersionFinder are:

        cleanup:  perform maintenance/cleanup tasks in the workdir
                  (e.g. removing old or broken downloads)

        find_versions:  get a list of all available versions for a given esky

        fetch_version:  make the specified version available locally
                        (e.g. download it from the internet)

        has_version:  check that the specified version is available locally

    """

    def __init__(self):
        pass

    def cleanup(self,app):
        """Perform maintenance tasks in the working directory."""
        pass

    def find_versions(self,app):
        """Find available versions of the app, returned as a list."""
        raise NotImplementedError

    def fetch_version(self,app,version):
        """Fetch a specific version of the app into a local directory."""
        raise NotImplementedError

    def has_version(self,app,version):
        """Check whether a specific version of the app is available locally."""
        raise NotImplementedError



class DefaultVersionFinder(VersionFinder):
    """VersionFinder implementing simple default download scheme.

    DefaultVersionFinder expects to be given a download url, which it will
    hit looking for new versions packaged as zipfiles.  These are simply
    downloaded and extracted on request.

    Zipfiles suitable for use with this class can be produced using the
    "bdist_esky" distutils command.

    This class will eventually grow support for applying differential updates,
    but I haven't implemented it yet...
    """

    def __init__(self,download_url):
        self.download_url = download_url
        super(DefaultVersionFinder,self).__init__()
        self.version_urls = {}

    def _workdir(self,app,nm):
        """Get full path of named working directory, inside the given app."""
        workdir = os.path.join(app._get_update_dir(),nm)
        try:
            os.makedirs(workdir)
        except OSError, e:
            if e.errno not in (17,183):
                raise
        return workdir

    def cleanup(self,app):
        dldir = self._workdir(app,"downloads")
        for nm in os.listdir(dldir):
            os.unlink(os.path.join(dldir,nm))
        updir = self._workdir(app,"unpack")
        for nm in os.listdir(updir):
            shutil.rmtree(os.path.join(updir,nm))
        rddir = self._workdir(app,"ready")
        for nm in os.listdir(rddir):
            shutil.rmtree(os.path.join(rddir,nm))

    def open_url(self,url):
        return urllib2.urlopen(url)

    def find_versions(self,app):
        # TODO: would be nice not to have to guess encoding here.
        downloads = self.open_url(self.download_url).read().decode("utf-8")
        version_re = "(?P<version>[a-zA-Z0-9\\.-_]+)"
        version_re = join_app_version(app.name,version_re,app.platform)
        link_re = "href=['\"](?P<href>(.*/)?%s.zip)['\"]" % (version_re,)
        for match in re.finditer(link_re,downloads):
            self.version_urls[match.group("version")] = match.group("href")
        return self.version_urls.keys()

    def fetch_version(self,app,version):
        try:
            url = self.version_urls[version]
        except KeyError:
            raise EskyVersionError(version)
        infile = self.open_url(urljoin(self.download_url,url))
        outfilenm = self._download_name(app,version)+".part"
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
            os.rename(outfilenm,self._download_name(app,version))
        return self._prepare_version(app,version)

    def _download_name(self,app,version):
        version = join_app_version(app.name,version,app.platform)
        return os.path.join(self._workdir(app,"downloads"),"%s.zip"%(version,))

    def _ready_name(self,app,version):
        version = join_app_version(app.name,version,app.platform)
        return os.path.join(self._workdir(app,"ready"),version)

    def _prepare_version(self,app,version):
        """Prepare the request version from downloaded data.

        This method is responsible for unzipping the downloaded version
        and making it available as a local directory.  When I implement
        differential updates it will also be responsible for applying them.
        """
        uppath = self._workdir(app,"unpack")
        dlpath = self._download_name(app,version)
        rdpath = self._ready_name(app,version)
        vdir = join_app_version(app.name,version,app.platform)
        #  Anything in the root of the zipfile is part of the bootstrap
        #  env, so it gets placed in a special directory.
        def name_filter(nm):
            if not nm.startswith(vdir):
                return os.path.join(vdir,"esky-bootstrap",nm)
            return nm
        extract_zipfile(dlpath,uppath,name_filter)
        bspath = os.path.join(uppath,vdir,"esky-bootstrap")
        if not os.path.isdir(bspath):
            os.makedirs(bspath)
        os.rename(os.path.join(uppath,vdir),rdpath)
        os.unlink(dlpath)
        return rdpath

    def has_version(self,app,version):
        return os.path.exists(self._ready_name(app,version))



