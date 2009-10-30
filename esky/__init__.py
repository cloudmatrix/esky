

# Things to do:
#
#   * bundle package_data into the library.zip
#   * copy data_files into the distribution directory
#


class Esky(object):

    def __init__(self,**kwds):
        for opt in kwds:
            setattr(self,opt,kwds[opt])
        if not hasattr(self,"distdir"):
            self.distdir = "dist"
        if not hasattr(self,"includes"):
            self.includes = []
        if not hasattr(self,"excludes"):
            self.excludes = []

    def get_setup_args(self):
        kwds = {}
        for opt in ["name","license"]:
            kwds[opt] = getattr(self,opt)
        return kwds

    def freeze(self):
        from esky.freeze import freeze_esky
        freeze_esky(self)

