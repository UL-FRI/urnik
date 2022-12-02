from .CreateXML import create_xml


# To so za nas študijske smeri, torej verjetno študiji


# TODO: added campus, term, year as arguments
def minors(campus, term, year):
    entries = []
    classifications = [
        "posMinors",
        {"campus": campus, "term": term, "year": year},
        entries,
    ]
    return classifications


if __name__ == "__main__":
    doc = create_xml(minors())
    print(doc.toprettyxml(indent="  ").encode("utf8"))
