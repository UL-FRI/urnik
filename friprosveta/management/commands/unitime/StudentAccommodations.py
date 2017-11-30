# -*- coding: utf-8 -*-


'''
Created on 20. avg. 2012

@author: gregor
'''
from CreateXML import createXML


#TODO: added campus, term, year as arguments
def accomodations(campus, term, year):
    entries = ["studentAccomodation", 
               {"externalId": "WCh", "abbreviation":u"Voziček", "name":u"Uporablja invalidski voziček"}, 
               [],
               "studentAccomodation", 
               {"externalId": "Hear", "abbreviation":"Sluh", "name":u"Težave s sluhom"}, 
               [],         
               ]
    
    studentAccomodations = ["studentAccomodations", {"campus": campus, "term": term, "year": year}, entries]
    return studentAccomodations

if __name__ == "__main__":
    doc = createXML(accomodations())
    print doc.toprettyxml(indent="  ").encode('utf8')