from .CreateXML import create_xml


# TODO: added campus, term, year as arguments
def accommodations(campus, term, year):
    entries = [
        "studentAccomodation",
        {
            "externalId": "WCh",
            "abbreviation": "Voziček",
            "name": "Uporablja invalidski voziček",
        },
        [],
        "studentAccomodation",
        {"externalId": "Hear", "abbreviation": "Sluh", "name": "Težave s sluhom"},
        [],
    ]

    student_accomodations = [
        "studentAccomodations",
        {"campus": campus, "term": term, "year": year},
        entries,
    ]
    return student_accomodations


if __name__ == "__main__":
    doc = create_xml(accommodations())
    print(doc.toprettyxml(indent="  ").encode("utf8"))
