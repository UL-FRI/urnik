from .CreateXML import create_xml

from friprosveta.models import Study


def academic_classification(campus, term, year):
    entries = []
    for study in Study.objects.all():
        entry = ["academicClassification",
                 {"externalId": str(study.id),
                  "code": study.short_name.replace(' ', '_'),
                  "name": study.short_name},
                 []]
        entries += entry
    classifications = ["academicClassifications",
                       {"campus": campus, "term": term, "year": year},
                       entries]
    return classifications


if __name__ == "__main__":
    doc = create_xml(academic_classification())
    print(doc.toprettyxml(indent="  ").encode('utf8'))
