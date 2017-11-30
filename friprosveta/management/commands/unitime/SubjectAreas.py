# -*- coding: utf-8 -*-


'''
Created on 20. avg. 2012

@author: gregor
'''
from CreateXML import createXML

import friprosveta.models

# To so predmeti, ki se izvajajo


#TODO: added tt, campus, term, year as arguments
def subjectAreas(tt, campus, term, year):

    activityset = tt.activityset
    
    
    entries = []
    subjects = friprosveta.models.Subject.objects.filter(activities__activityset=activityset).distinct()
    
    for subject in subjects:
        entry = ["subjectArea", {
                 "externalId": str(subject.id),
                 "abbreviation": u"{0}".format(subject.code),  #TODO: id je zraven zato, da je koda unikatna. Upam, da je to OK.
                 "shortTitle": subject.short_name,
                 "longTitle": subject.name,
                 "schedBookOnly": "false",
                 "pseudoSubjArea": "false",
                 "department": "1"
        }, []]
        entries += entry        
    
    subjectAreas = ["subjectAreas", {"campus": campus, "term": term, "year": year}, entries]
    return subjectAreas

if __name__ == "__main__":
    doc = createXML(subjectAreas())
    print doc.toprettyxml(indent="  ").encode('utf8')