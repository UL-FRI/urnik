# -*- coding: utf-8 -*-

'''
Created on 20. avg. 2012

@author: gregor
'''

from CreateXML import createXML

# To so za nas študijske smeri, torej verjetno študiji


#TODO: added campus, term, year as arguments
def majors(campus, term, year):
    entries = []
    for study in studies:
        
        if study.smer != None:  continue  #Only top-level studies
        entry = ["posMajor", 
                 {"externalId": str(study.id),
                  "code": study.shortname.replace(' ', '_'), #TODO: tukaj ne sme biti presledkov. Upam, da bo takole bolje.
                  "name": study.name[:50],  #Mora biti krajši od 50 znakov
                  "academicArea": "CS"}, []]
        entries += entry
    
    classifications = ["posMajors", {"campus": campus, "term": term, "year": year}, entries]
    return classifications


if __name__ == "__main__":
    doc = createXML(majors())
    print doc.toprettyxml(indent="  ").encode('utf8')
