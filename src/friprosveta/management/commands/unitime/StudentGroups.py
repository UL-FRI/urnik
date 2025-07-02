from .CreateXML import create_xml


def groups(campus, term, year):
    export_groups = ["BUN-RM", "BUN-MM", "BUN-UI", "BM-PRI", "BM-RM", "BM-KO"]
    export_classyears = [1, 2, 3]
    entries = []
    for group_name in export_groups:
        for classyear in export_classyears:
            entry = [
                "studentGroup",
                {
                    "name": "{1}_{0}".format(group_name, classyear),
                    "code": "{1}_{0}".format(group_name, classyear),
                },
                [],
            ]
            entries += entry
    # Add group for izredni studenti
    entries += ["studentGroup", {"name": "IZ", "code": "IZ"}, []]
    student_groups = [
        "studentGroups",
        {"campus": campus, "term": term, "year": year},
        entries,
    ]
    return student_groups


if __name__ == "__main__":
    doc = create_xml(groups())
    print(doc.toprettyxml(indent="  ").encode("utf8"))
