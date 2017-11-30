# -*- coding: utf-8 -*-

'''
Created on 20. avg. 2012

@author: gregor
'''

from CreateXML import createXML
import sys

# To so za nas študijske smeri, torej verjetno študiji


#TODO: added campus, term, year as arguments
def minors(campus, term, year):
    entries = []
    classifications = ["posMinors", {"campus": campus, "term": term, "year": year}, entries]
    return classifications

if __name__ == "__main__":
    doc = createXML(minors())
    print doc.toprettyxml(indent="  ").encode('utf8')
