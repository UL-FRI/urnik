from .CreateXML import create_xml


# To so za nas študijske smeri, torej verjetno študiji


# TODO: added campus, term, year as arguments
def majors(campus, term, year):
    entries = []
    for study in studies:

        if study.smer is not None:
            continue  # Only top-level studies
        entry = ["posMajor",
                 {"externalId": str(study.id),
                  "code": study.shortname.replace(' ', '_'),
                  # TODO: tukaj ne sme biti presledkov. Upam, da bo takole bolje.
                  "name": study.name[:50],  # Mora biti krajši od 50 znakov
                  "academicArea": "CS"}, []]
        entries += entry

    classifications = ["posMajors", {"campus": campus, "term": term, "year": year}, entries]
    return classifications


if __name__ == "__main__":
    doc = create_xml(majors())
    print(doc.toprettyxml(indent="  ").encode('utf8'))
