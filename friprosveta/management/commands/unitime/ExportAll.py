import inspect
import os
import sys
from collections import OrderedDict
from importlib import import_module

from .CreateXML import create_xml


def export(tt, tt_old, campus, term, year, what):
    """
    What can be xml_all, database_all or one of the keys in the
    data dictionary.
    """
    abs_path = os.path.abspath(inspect.getfile(inspect.currentframe()))
    current_path = os.path.dirname(abs_path)
    sys.path.append(current_path)

    # dictionary of form: module: (method, file_prefix)
    # the order of insertion is important!!
    # Data X that depends on other data Y should be exported AFTER data Y
    xml_data = OrderedDict(
        (
            ("AcademicAreas", ("academic_areas", [campus, term, year])),
            (
                "AcademicClassification",
                ("academic_classification", [campus, term, year]),
            ),
            ("Majors", ("majors", [tt, campus, term, year])),
            ("Minors", ("minors", [campus, term, year])),
            ("Departments", ("departments", [campus, term, year])),
            ("BuildingsAndRooms", ("buildings_and_rooms", [tt, campus, term, year])),
            ("Staff", ("staff", [tt, campus, term, year])),
            ("SubjectAreas", ("subject_areas", [tt, campus, term, year])),
            ("Offerings", ("offerings", [tt, campus, term, year])),
            ("Students", ("students", [tt, campus, term, year])),
            ("StudentAccommodations", ("accommodations", [campus, term, year])),
            ("StudentGroups", ("groups", [campus, term, year])),
            (
                "LastLikeCourseDemands",
                ("last_like_course_demands", [tt, tt_old, campus, term, year]),
            ),
            ("StudentEnrollments", ("student_enrollments", [tt, campus, term, year])),
            (
                "StudentCourseRequests",
                ("student_course_requests", [tt, campus, term, year]),
            ),
        )
    )
    session_id = None  # TODO: read session ID
    database_data = OrderedDict(
        (
            ("ClassesTimePattern", ("time_patterns", [tt])),
            ("DefaultTimePattern", ("default_time_pattern", [tt])),
            ("StaffTimePreferences", ("staff_time_preferences", [tt])),
            ("ClassRoomPreferences", ("class_room_preferences", [tt])),
            ("RoomFeatures", ("room_features", [tt])),
            ("RoomTimePreferences", ("room_time_preferences", [tt])),
            ("SubjectRequirements", ("subject_requirements", [tt])),
        )
    )

    parent = "friprosveta.management.commands.unitime."
    if what == "xml_all":
        what = xml_data.keys()
    elif what == "database_all":
        what = database_data.keys()
    else:
        what = [what]
    for module in what:
        # (method, arguments) = xml_data.get(module, database_data[module])
        if module in xml_data:
            (method, arguments) = xml_data[module]
        else:
            (method, arguments) = database_data[module]
        print("Running {0}".format(module))
        module_data = None
        try:
            print("Importing module", module)
            mod = import_module(parent + module)
            print("Imported", mod)
            module_data = getattr(mod, method)(*arguments)
        except ImportError as e:
            print("Exception", e)
        if module in xml_data:
            try:
                print(f"Processing XML module {module}.")
                print(f"Got module data: {module_data}.")
                f = open("{0}.xml".format(module), "w")
                xml = create_xml(module_data)
                xml = xml.toprettyxml(indent="  ")  # .encode('utf8')
                print("Got XML", xml)
                f.write(xml)
            finally:
                f.close()
