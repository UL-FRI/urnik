'''
Created on 20. avg. 2012

@author: gregor
'''

from CreateXML import createXML

#TODO: added campus, term, year arguments
def departments(campus, term, year):
    department = ["department", 
                  {"externalId": "Urnik", 
                   "abbreviation": "Urnik", 
                   "name": "Oddelek za izdelavo urnika", 
                   "deptCode": "1"}, []]
    
    
    departments = ["departments", {"campus": campus, "term": term, "year": year}, department]
    return departments

if __name__ == "__main__":
    doc = createXML(departments())
    print doc.toprettyxml(indent="  ").encode('utf8')
