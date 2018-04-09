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
    xml_data = OrderedDict((
        ("AcademicAreas", ("academicAreas", [campus, term, year])),
        (
            "AcademicClassification",
            ("academicClassification", [campus, term, year])
        ),
        ("Majors", ("majors", [campus, term, year])),
        ("Minors", ("minors", [campus, term, year])),
        ("Departments", ("departments", [campus, term, year])),
        ("BuildingsAndRooms", ("buildingsAndRooms",
                               [tt, campus, term, year])),
        ("Staff", ("staff", [tt, campus, term, year])),
        ("SubjectAreas", ("subjectAreas", [tt, campus, term, year])),
        ("Offerings", ("offerings", [tt, campus, term, year])),
        ("Students", ("students", [tt, campus, term, year])),
        ("StudentAccommodations", ("accomodations", [campus, term, year])),
        ("StudentGroups", ("groups", [campus, term, year])),
        (
            "LastLikeCourseDemands",
            ("lastLikeCourseDemands", [tt, tt_old, campus, term, year])
        ),
        (
            "StudentEnrollments",
            ("studentEnrollments", [tt, campus, term, year])
        ),
        (
            "StudentCourseRequests",
            ("studentCourseRequests", [tt, campus, term, year])
        ),
    ))
    session_id = None  # TODO: read session ID
    database_data = OrderedDict((
        ("ClassesTimePattern", ("timePatterns", [tt])),
        ("DefaultTimePattern", ("defaultTimePattern", [tt])),
        (
            "StaffTimePreferences",
            ("staffTimePreferences", [tt])
        ),
        (
            "ClassRoomPreferences",
            ("classRoomPreferences", [tt])
        ),
        (
            "RoomFeatures",
            ("roomFeatures", [tt])
        ),
        (
            "RoomTimePreferences",
            ("roomTimePreferences", [tt])
        ),
        (
            "SubjectRequirements",
            ("subjectRequirements", [tt])
        ),
    ))
    if what == 'xml_all':
        what = xml_data.keys()
    elif what == 'database_all':
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
            mod = import_module(module)
            module_data = getattr(mod, method)(*arguments)
        except ImportError as e:
            print(e)
        if module in xml_data:
            try:
                f = open("{0}.xml".format(module), "w")
                xml = create_xml(module_data)
                xml = xml.toprettyxml(indent="  ").encode('utf8')
                f.write(xml)
            finally:
                f.close()
