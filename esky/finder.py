#  Copyright (c) 2009-2010, Cloud Matrix Pty. Ltd.
#  All rights reserved; available under the terms of the BSD License.
"""

  esky.finder:  VersionFinder implementations for esky

This module provides the default VersionFinder implementations for esky. The
abstract base class "VersionFinder" defines the expected interface, while 
"DefaultVersionFinder" provides a simple default implementation that hits a
specified URL to look for new versions.

"""

from __future__ import with_statement

import os
import re
import stat
import urllib2
import zipfile
import shutil
import tempfile
from urlparse import urlparse, urljoin

from esky.bootstrap import parse_version, join_app_version
from esky.errors import *
from esky.util import extract_zipfile, copy_ownership_info
from esky.patch import apply_patch, PatchError


class VersionFinder(object):
    """Base VersionFinder class.

    This class defines the interface expected of a VersionFinder object.
    The important methods expected from any VersionFinder are:

        find_versions:  get a list of all available versions for a given esky

        fetch_version:  make the specified version available locally
                        (e.g. download it from the internet)

        has_version:  check that the specified version is available locally

        cleanup:  perform maintenance/cleanup tasks in the workdir
                  (e.g. removing old or broken downloads)

        needs_cleanup:  check whether maintenance/cleanup tasks are required

    """

    def __init__(self):
        pass

    def needs_cleanup(self,app):
        """Check whether the cleanup() method has any work to do."""
        return False

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
        """Check whether a specific version of the app is available locally.

        Returns either False, or the paths to the unpacked version directory.
        """
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
        self.version_graph = VersionGraph()

    def _workdir(self,app,nm,create=True):
        """Get full path of named working directory, inside the given app."""
        updir = app._get_update_dir()
        workdir = os.path.join(updir,nm)
        if create:
            for target in (updir,workdir):
                try:
                    os.mkdir(target)
                except OSError, e:
                    if e.errno not in (17,183):
                        raise
                else:
                    copy_ownership_info(app.appdir,target)
        return workdir

    def needs_cleanup(self,app):
        """Check whether the cleanup() method has any work to do."""
        dldir = self._workdir(app,"downloads",create=False)
        if os.path.isdir(dldir):
            for nm in os.listdir(dldir):
                return True
        updir = self._workdir(app,"unpack",create=False)
        if os.path.isdir(updir):
            for nm in os.listdir(updir):
                return True
        rddir = self._workdir(app,"ready",create=False)
        if os.path.isdir(rddir):
            for nm in os.listdir(rddir):
                return True
        return False

    def cleanup(self,app):
        # TODO: hang onto the latest downloaded version
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
        version_re = "[a-zA-Z0-9\\.-_]+"
        appname_re = "(?P<version>%s)" % (version_re,)
        appname_re = join_app_version(app.name,appname_re,app.platform)
        filename_re = "%s\\.(zip|exe|from-(?P<from_version>%s)\\.patch)"
        filename_re = filename_re % (appname_re,version_re,)
        link_re = "href=['\"](?P<href>([^'\"]*/)?%s)['\"]" % (filename_re,)
        # TODO: would be nice not to have to guess encoding here.
        df = self.open_url(self.download_url)
        try:
            downloads = df.read().decode("utf-8")
        finally:
            df.close()
        for match in re.finditer(link_re,downloads,re.I):
            version = match.group("version")
            href = match.group("href")
            from_version = match.group("from_version")
            # TODO: try to assign costs based on file size.
            if from_version is None:
                cost = 40
            else:
                cost = 1
            self.version_graph.add_link(from_version or "",version,href,cost)
        return self.version_graph.get_versions(app.version)

    def fetch_version(self,app,version):
        #  There's always the possibility that a patch fails to apply.
        #  _prepare_version will remove such patches from the version graph;
        #  we loop until we find a path that applies, or we run out of options.
        name = self._ready_name(app,version)
        while not os.path.exists(name):
            try:
                path = self.version_graph.get_best_path(app.version,version)
            except KeyError:
                raise EskyVersionError(version)
            if path is None:
                raise EskyVersionError(version)
            local_path = []
            for url in path:
                local_path.append((self._fetch_file(app,url),url))
            try:
                self._prepare_version(app,version,local_path)
            except PatchError:
                pass
        return name

    def _fetch_file(self,app,url):
        nm = os.path.basename(urlparse(url).path)
        outfilenm = os.path.join(self._workdir(app,"downloads"),nm)
        if not os.path.exists(outfilenm):
            infile = self.open_url(urljoin(self.download_url,url))
            try:
                partfilenm = outfilenm + ".part"
                partfile = open(partfilenm,"wb")
                try:
                    data = infile.read(1024*512)
                    while data:
                        partfile.write(data)
                        data = infile.read(1024*512)
                except Exception:
                    partfile.close()
                    os.unlink(partfilenm)
                    raise
                else:
                    partfile.close()
                    os.rename(partfilenm,outfilenm)
            finally:
                infile.close()
        return outfilenm

    def _prepare_version(self,app,version,path):
        """Prepare the requested version from downloaded data.

        This method is responsible for unzipping downloaded versions, applying
        patches and so-forth, and making the result available as a local
        directory ready for renaming into the appdir.
        """
        uppath = tempfile.mkdtemp(dir=self._workdir(app,"unpack"))
        try:
            if not path:
                self._copy_best_version(app,uppath)
            else:
                if path[0][0].endswith(".patch"):
                    try:
                        self._copy_best_version(app,uppath)
                    except EnvironmentError, e:
                        self.version_graph.remove_all_links(path[0][1])
                        err = "couldn't copy current version: %s" % (e,)
                        raise PatchError(err)
                    patches = path
                else:
                    try:
                        extract_zipfile(path[0][0],uppath)
                    except (zipfile.BadZipfile,zipfile.LargeZipFile):
                        self.version_graph.remove_all_links(path[0][1])
                        try:
                            os.unlink(path[0][0])
                        except EnvironmentError:
                            pass
                        raise
                    patches = path[1:]
                for (patchfile,patchurl) in patches:
                    try:
                        with open(patchfile,"rb") as f:
                            apply_patch(uppath,f)
                    except PatchError:
                        self.version_graph.remove_all_links(patchurl)
                        try:
                            os.unlink(pathfile)
                        except EnvironmentError:
                            pass
                        raise
            # Move anything that's not the version dir into esky-bootstrap
            vdir = join_app_version(app.name,version,app.platform)
            bspath = os.path.join(uppath,vdir,"esky-bootstrap")
            if not os.path.isdir(bspath):
                os.makedirs(bspath)
            for nm in os.listdir(uppath):
                if nm != vdir:
                    os.rename(os.path.join(uppath,nm),os.path.join(bspath,nm))
            # Check that it has an esky-bootstrap.txt file
            bsfile = os.path.join(uppath,vdir,"esky-bootstrap.txt")
            if not os.path.exists(bsfile):
                self.version_graph.remove_all_links(path[0][1])
                raise PatchError("patch didn't create esky-bootstrap.txt")
            # Make it available for upgrading
            rdpath = self._ready_name(app,version)
            if os.path.exists(rdpath):
                shutil.rmtree(rdpath)
            os.rename(os.path.join(uppath,vdir),rdpath)
            for (filenm,_) in path:
                os.unlink(filenm)
        finally:
            shutil.rmtree(uppath)

    def _copy_best_version(self,app,uppath):
        best_vdir = join_app_version(app.name,app.version,app.platform)
        source = os.path.join(app.appdir,best_vdir)
        shutil.copytree(source,os.path.join(uppath,best_vdir))
        with open(os.path.join(source,"esky-bootstrap.txt"),"r") as manifest:
            for nm in manifest:
                nm = nm.strip()
                bspath = os.path.join(app.appdir,nm)
                dstpath = os.path.join(uppath,nm)
                if os.path.isdir(bspath):
                    shutil.copytree(bspath,dstpath)
                else:
                    if not os.path.isdir(os.path.dirname(dstpath)):
                        os.makedirs(os.path.dirname(dstpath))
                    shutil.copy2(bspath,dstpath)

    def has_version(self,app,version):
        path = self._ready_name(app,version)
        if os.path.exists(path):
            return path
        return False

    def _ready_name(self,app,version):
        version = join_app_version(app.name,version,app.platform)
        return os.path.join(self._workdir(app,"ready"),version)


class LocalVersionFinder(DefaultVersionFinder):
    """VersionFinder that looks only in a local directory.

    This VersionFinder subclass looks for updates in a specific local
    directory.  It's probably only useful for testing purposes.
    """

    def find_versions(self,app):
        version_re = "[a-zA-Z0-9\\.-_]+"
        appname_re = "(?P<version>%s)" % (version_re,)
        appname_re = join_app_version(app.name,appname_re,app.platform)
        filename_re = "%s\\.(zip|exe|from-(?P<from_version>%s)\\.patch)"
        filename_re = filename_re % (appname_re,version_re,)
        for nm in os.listdir(self.download_url):
            match = re.match(filename_re,nm)
            if match:
                version = match.group("version")
                from_version = match.group("from_version")
                if from_version is None:
                    cost = 40
                else:
                    cost = 1
                self.version_graph.add_link(from_version or "",version,nm,cost)
        return self.version_graph.get_versions(app.version)

    def _fetch_file(self,app,nm):
        infile = open(os.path.join(self.download_url,nm),"rb")
        outfilenm = os.path.join(self._workdir(app,"downloads"),nm)
        if not os.path.exists(outfilenm):
            partfilenm = outfilenm + ".part"
            partfile = open(partfilenm,"wb")
            try:
                data = infile.read(1024*512)
                while data:
                    partfile.write(data)
                    data = infile.read(1024*512)
            except Exception:
                infile.close()
                partfile.close()
                os.unlink(partfilenm)
                raise
            else:
                infile.close()
                partfile.close()
                os.rename(partfilenm,outfilenm)
        return outfilenm


class VersionGraph(object):
    """Class for managing links between different versions.

    This class implements a simple graph-based approach to planning upgrades
    between versions.  It allow syou to specify "links" from one version to
    another, each with an associated cost.  You can then do a graph traversal
    to find the lowest-cose route between two versions.

    There is always a special source node with value "", which it is possible
    to reach at zero cost from any other version.  Use this to represent a full
    download, which can reach a specific version from any other version.
    """

    def __init__(self):
        self._links = {"":{}}

    def add_link(self,source,target,via,cost):
        """Add a link from source to target."""
        if source not in self._links:
            self._links[source] = {}
        if target not in self._links:
            self._links[target] = {}
        from_source = self._links[source]
        to_target = from_source.setdefault(target,{})
        if via in to_target:
            to_target[via] = min(to_target[via],cost)
        else:
            to_target[via] = cost

    def remove_all_links(self,via):
        for source in self._links:
            for target in self._links[source]:
                self._links[source][target].pop(via,None)

    def get_versions(self,source):
        """List all versions reachable from the given source version."""
        # TODO: be more efficient here
        best_paths = self.get_best_paths(source)
        return [k for (k,v) in best_paths.iteritems() if k and v]

    def get_best_path(self,source,target):
        """Get the best path from source to target.

        This method returns a list of "via" links representing the lowest-cost
        path from source to target.
        """
        return self.get_best_paths(source)[target]

    def get_best_paths(self,source):
        """Get the best path from source to every other version.

        This returns a dictionary mapping versions to lists of "via" links.
        Each entry gives the lowest-cost path from the given source version
        to that version.
        """
        remaining = set(v for v in self._links)
        best_costs = dict((v,_inf) for v in remaining)
        best_paths = dict((v,None) for v in remaining)
        best_costs[source] = 0
        best_paths[source] = []
        best_costs[""] = 0
        best_paths[""] = []
        while remaining:
            (cost,best) = sorted((best_costs[v],v) for v in remaining)[0]
            if cost is _inf:
                break
            remaining.remove(best)
            for v in self._links[best]:
                (v_cost,v_link) = self._get_best_link(best,v)
                if cost + v_cost < best_costs[v]:
                    best_costs[v] = cost + v_cost
                    best_paths[v] = best_paths[best] + [v_link]
        return best_paths
                
    def _get_best_link(self,source,target):
        if source not in self._links:
            return (_inf,"")
        if target not in self._links[source]:
            return (_inf,"")
        vias = self._links[source][target]
        if not vias:
            return (_inf,"")
        vias = sorted((cost,via) for (via,cost) in vias.iteritems())
        return vias[0]


class _Inf(object):
    """Object that is greater than everything."""
    def __lt__(self,other):
        return False
    def __le__(self,other):
        return False
    def __gt__(self,other):
        return True
    def __ge__(self,other):
        return True
    def __eq__(self,other):
        return other is self
    def __ne__(self,other):
        return other is not self
    def __cmp___(self,other):
        return 1
    def __add__(self,other):
        return self
    def __radd__(self,other):
        return self
    def __iadd__(self,other):
        return self
    def __sub__(self,other):
        return self
    def __rsub__(self,other):
        return self
    def __isub__(self,other):
        return self
_inf = _Inf()


