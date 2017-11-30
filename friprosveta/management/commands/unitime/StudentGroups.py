# -*- coding: utf-8 -*-
from CreateXML import createXML


def groups(campus, term, year):
    export_groups = ['BUN-RM', 'BUN-MM', 'BUN-UI', 'BM-PRI', 'BM-RM', 'BM-KO']
    export_classyears = [1, 2, 3]
    entries = []
    for group_name in export_groups:
        for classyear in export_classyears:
            entry = ["studentGroup",
                     {
                      "name": "{1}_{0}".format(group_name, classyear),
                      "code": "{1}_{0}".format(group_name, classyear)
                     },
                     []]
            entries += entry
    # Add group for izredni studenti
    entries += ["studentGroup",
                {"name": "IZ",
                 "code": "IZ"},
                []]
    studentGroups = ["studentGroups", {"campus": campus,
                                       "term": term,
                                       "year": year},
                     entries]
    return studentGroups

if __name__ == "__main__":
    doc = createXML(groups())
    print doc.toprettyxml(indent="  ").encode('utf8')
