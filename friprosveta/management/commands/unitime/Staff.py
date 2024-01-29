"""
Important note from Unitime webpage:

Staff is imported into the staff table, to pull in the
instructors use Manage Instructor List operation on the
Instructors page (menu Courses > Input Data > Instructors).
"""

from .CreateXML import create_xml


# TODO: added tt, campus, term, year as arguments
def staff(tt, campus, term, year):
    entries = []

    for teacher in tt.teachers.all():
        entries += [
            "staffMember",
            {
                "externalId": str(teacher.code),
                "firstName": teacher.user.first_name,
                "middleName": "",
                "lastName": teacher.user.last_name,
                "positionType": "PROF",  # TODO: add profesor
                "department": "1",
            },
            [],
        ]

    staff = ["staff", {"campus": campus, "term": term, "year": year}, entries]
    return staff


if __name__ == "__main__":
    doc = create_xml(staff())
    print(doc.toprettyxml(indent="  ").encode("utf8"))
