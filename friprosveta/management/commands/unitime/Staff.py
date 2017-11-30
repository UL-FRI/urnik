'''
Created on 20. avg. 2012

Important note from Unitime webpage:

Staff is imported into the staff table, to pull in the 
instructors use Manage Instructor List operation on the 
Instructors page (menu Courses > Input Data > Instructors).

@author: gregor
'''

import sys


import friprosveta.models

from xml.dom.minidom import Document
from CreateXML import createXML

#TODO: added tt, campus, term, year as arguments
def staff(tt, campus, term, year):
    entries = []
        
    for teacher in tt.teachers.all():
        entries += ["staffMember", {
                    "externalId": str(teacher.id),
                    "firstName": teacher.user.first_name, 
                    "middleName": "",
                    "lastName": teacher.user.last_name,
                    "positionType": "PROF",  #TODO: add profesor
                    "department": "1"
                    }, []
                    ]
    
    staff = ["staff", {"campus": campus, "term": term, "year": year}, entries]
    return staff

if __name__ == "__main__":
    doc = createXML(staff())
    print doc.toprettyxml(indent="  ").encode('utf8')