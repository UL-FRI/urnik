from friprosveta.models import Study

from .CreateXML import create_xml

# To so za nas študijske smeri, torej verjetno študiji


# TODO: added campus, term, year as arguments
def majors(tt, campus, term, year):
    entries = []
    for study in Study.objects.all():
        entry = [
            "posMajor",
            {
                "externalId": str(study.id),
                "code": study.short_name.replace(" ", "_"),
                # TODO: tukaj ne sme biti presledkov. Upam, da bo takole bolje.
                "name": study.name[:50],  # Mora biti krajši od 50 znakov
                "academicArea": "CS",
            },
            [],
        ]
        entries += entry

    classifications = [
        "posMajors",
        {"campus": campus, "term": term, "year": year},
        entries,
    ]
    return classifications


if __name__ == "__main__":
    doc = create_xml(majors())
    print(doc.toprettyxml(indent="  ").encode("utf8"))
