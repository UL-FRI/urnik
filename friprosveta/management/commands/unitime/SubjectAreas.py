import friprosveta.models
from .CreateXML import create_xml


# To so predmeti, ki se izvajajo


# TODO: added tt, campus, term, year as arguments
def subject_areas(tt, campus, term, year):
    activityset = tt.activityset

    entries = []
    subjects = friprosveta.models.Subject.objects.filter(
        activities__activityset=activityset
    ).distinct()

    for subject in subjects:
        entry = [
            "subjectArea",
            {
                "externalId": str(subject.id),
                "abbreviation": "{0}".format(subject.code),
                # TODO: id je zraven zato, da je koda unikatna. Upam, da je to OK.
                "shortTitle": subject.short_name,
                "longTitle": subject.name,
                "schedBookOnly": "false",
                "pseudoSubjArea": "false",
                "department": "1",
            },
            [],
        ]
        entries += entry

    result = ["subjectAreas", {"campus": campus, "term": term, "year": year}, entries]
    return result


if __name__ == "__main__":
    doc = create_xml(subject_areas())
    print(doc.toprettyxml(indent="  ").encode("utf8"))
