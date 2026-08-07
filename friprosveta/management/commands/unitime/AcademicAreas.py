from .CreateXML import create_xml


def academic_areas(campus, term, year):
    area = [
        "academicArea",
        {
            "externalId": "CS",
            "abbreviation": "CS",
            "shortTitle": "Computer science",
            "longTitle": "UL FRI, Computer Science",
        },
        [],
    ]
    return ["academicAreas", {"campus": campus, "term": term, "year": year}, area]


if __name__ == "__main__":
    doc = create_xml(academic_areas())
    print(doc.toprettyxml(indent="  ").encode("utf8"))
