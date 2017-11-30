'''
Created on 20. avg. 2012

@author: gregor
'''

from CreateXML import createXML

#TODO: added campus, term, year as arguments
def academicAreas(campus, term, year):    
    area = ["academicArea", {"externalId": "CS", "abbreviation": "CS", "shortTitle": "Computer science", "longTitle": "UL FRI, Computer Science"}, []]
    return ["academicAreas", {"campus": campus, "term": term, "year": year}, area]


if __name__ == "__main__":
    doc = createXML(academicAreas())
    print doc.toprettyxml(indent="  ").encode('utf8')
