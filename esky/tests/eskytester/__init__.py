
from HTMLParser import HTMLParser

def yes_i_am_working():
    assert True

class TestHTMLParser(HTMLParser):
   def __init__(self):
       HTMLParser.__init__(self)
       self.expecting = ["html","body","p","p"]
       self.feed("<html><body><p>hi</p><p>world</p></body></html>")
   def handle_starttag(self,tag,attrs):
       assert tag == self.expecting.pop(0)

def yes_my_deps_are_working():
    TestHTMLParser()
    

