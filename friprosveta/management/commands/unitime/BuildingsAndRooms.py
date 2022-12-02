"""
Important note from Unitime web page:

Buildings and rooms are imported as external buildings and rooms,
you need to use Update Data operation on Buildings page
(menu Administration > Academic Sessions > Buildings)
for the buildings and rooms to show up in the application.

Global room features need to be crated before this update,
and their abbreviation must match the roomFeature.feature attribute.
"""

from .CreateXML import create_xml

import timetable.models


def buildings_and_rooms(tt, campus, term, year):
    entries = []
    # TODO: zaenkrat nimamo koordinat učilnic
    # TODO: kasneje se jih lahko uporabi za optimizacijo,
    #       sploh če si bomo delili učilnice z drugimi fakultetemi.
    # INFO: Distance between two buildings is computed as Euclidean
    #       distance between coordinates × 10 meters (e.g., distance
    #       between coordinates [0,0] and [3,4] is 50 meters)

    enlarge_factor = 1.2
    locations = timetable.models.Location.objects.all()
    computer_resource_name = "Računalnik"
    for location in locations:
        rooms = []
        for room in location.classroom_set.all():
            if room not in tt.classrooms.all():
                continue
            features = []
            for resource in room.resources.all():
                features += [
                    "roomFeature",
                    {
                        "feature": str(resource.id),
                        "value": resource.name[:20],
                    },
                    [],
                ]

            # INFO:
            # scheduledRoomType = genClassroom, computingLab or departmental
            # instructional = T or F  {T ==> typically used for instruction}.

            is_computer_classroom = (
                room.resources.filter(name=computer_resource_name).count() == 1
            )
            scheduled_room_type = (
                "computingLab" if is_computer_classroom else "genClassroom"
            )

            roomarray = [
                "room",
                {
                    "externalId": str(room.id),
                    "locationX": "0",
                    "locationY": "0",
                    "roomNumber": room.short_name,
                    "roomClassification": "classroom",
                    "capacity": str(int(room.capacity * enlarge_factor)),
                    "examCapacity": str((4 * room.capacity) // 9),
                    "instructional": "True",
                    "scheduledRoomType": scheduled_room_type,
                    "displayName": room.name,
                },
                [
                    "roomDepartments",
                    {},
                    ["assigned", {"departmentNumber": "1", "percent": "100"}, []],
                    "roomFeatures",
                    {},
                    features,
                ],
            ]
            rooms += roomarray
        entries += [
            "building",
            {
                "externalId": str(location.id),
                "abbreviation": location.name,
                "locationX": "0",  # See above at location
                "locationY": "0",
                "name": location.name,
            },
            rooms,
        ]
    buildings = [
        "buildingsRooms",
        {"campus": campus, "term": term, "year": year},
        entries,
    ]
    return buildings


if __name__ == "__main__":
    doc = create_xml(buildings_and_rooms())
    print(doc.toprettyxml(indent="  ").encode("utf8"))
