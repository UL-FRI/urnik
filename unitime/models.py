# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
#
# Also note: You'll have to insert the output of 'django-admin.py sqlcustom [app_label]'
# into your database.
from __future__ import unicode_literals

from django.db import models


class AcademicArea(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    session = models.ForeignKey('Sessions', blank=True, null=True, on_delete=models.CASCADE)
    academic_area_abbreviation = models.CharField(max_length=10, blank=True)
    long_title = models.CharField(max_length=100, blank=True)
    external_uid = models.CharField(max_length=40, blank=True)

    class Meta:
        managed = False
        db_table = 'academic_area'


class AcademicClassification(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    session = models.ForeignKey('Sessions', blank=True, null=True, on_delete=models.CASCADE)
    code = models.CharField(max_length=10, blank=True)
    name = models.CharField(max_length=50, blank=True)
    external_uid = models.CharField(max_length=40, blank=True)

    class Meta:
        managed = False
        db_table = 'academic_classification'


class ApplicationConfig(models.Model):
    name = models.CharField(primary_key=True, max_length=255)
    value = models.CharField(max_length=4000, blank=True)
    description = models.CharField(max_length=500, blank=True)

    class Meta:
        managed = False
        db_table = 'application_config'


class AssignedInstructors(models.Model):
    assignment = models.ForeignKey('Assignment', on_delete=models.CASCADE)
    instructor = models.ForeignKey('DepartmentalInstructor', on_delete=models.CASCADE)
    last_modified_time = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'assigned_instructors'


class AssignedRooms(models.Model):
    assignment = models.ForeignKey('Assignment', on_delete=models.CASCADE)
    room = models.ForeignKey('Room', on_delete=models.CASCADE)
    last_modified_time = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'assigned_rooms'


class Assignment(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    days = models.BigIntegerField(blank=True, null=True)
    slot = models.BigIntegerField(blank=True, null=True)
    time_pattern = models.ForeignKey('TimePattern', blank=True, null=True, on_delete=models.CASCADE)
    solution = models.ForeignKey('Solution', blank=True, null=True, on_delete=models.CASCADE)
    class_field = models.ForeignKey('Class', db_column='class_id', blank=True, null=True, on_delete=models.CASCADE)  # Field renamed because it was a Python reserved word.
    class_name = models.CharField(max_length=100, blank=True)
    last_modified_time = models.DateTimeField(blank=True, null=True)
    date_pattern = models.ForeignKey('DatePattern', blank=True, null=True, on_delete=models.CASCADE)
    rooms = models.ManyToManyField('Room', through='AssignedRooms')
    instructors = models.ManyToManyField('DepartmentalInstructor',
                                         through='AssignedInstructors')

    class Meta:
        managed = False
        db_table = 'assignment'


class AttachmentType(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    reference = models.CharField(max_length=20)
    abbreviation = models.CharField(max_length=20)
    label = models.CharField(max_length=60)
    visibility = models.BigIntegerField()

    class Meta:
        managed = False
        db_table = 'attachment_type'


class Building(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    session = models.ForeignKey('Sessions', blank=True, null=True, on_delete=models.CASCADE)
    abbreviation = models.CharField(max_length=10, blank=True)
    name = models.CharField(max_length=100, blank=True)
    coordinate_x = models.FloatField(blank=True, null=True)
    coordinate_y = models.FloatField(blank=True, null=True)
    external_uid = models.CharField(max_length=40, blank=True)

    class Meta:
        managed = False
        db_table = 'building'


class BuildingPref(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    owner_id = models.DecimalField(max_digits=20, decimal_places=0, blank=True, null=True)
    pref_level = models.ForeignKey('PreferenceLevel', blank=True, null=True, on_delete=models.CASCADE)
    bldg = models.ForeignKey(Building, blank=True, null=True, on_delete=models.CASCADE)
    distance_from = models.IntegerField(blank=True, null=True)
    last_modified_time = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'building_pref'


class ChangeLog(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    session = models.ForeignKey('Sessions', blank=True, null=True, on_delete=models.CASCADE)
    manager = models.ForeignKey('TimetableManager', blank=True, null=True, on_delete=models.CASCADE)
    time_stamp = models.DateTimeField(blank=True, null=True)
    obj_type = models.CharField(max_length=255, blank=True)
    obj_uid = models.DecimalField(max_digits=20, decimal_places=0, blank=True, null=True)
    obj_title = models.CharField(max_length=255, blank=True)
    subj_area = models.ForeignKey('SubjectArea', blank=True, null=True, on_delete=models.CASCADE)
    department = models.ForeignKey('Department', blank=True, null=True, on_delete=models.CASCADE)
    source = models.CharField(max_length=50, blank=True)
    operation = models.CharField(max_length=50, blank=True)
    detail = models.TextField(blank=True)

    class Meta:
        managed = False
        db_table = 'change_log'


class Class(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    subpart = models.ForeignKey('SchedulingSubpart', blank=True, null=True, on_delete=models.CASCADE)
    expected_capacity = models.IntegerField(blank=True, null=True)
    nbr_rooms = models.IntegerField(blank=True, null=True)
    parent_class = models.ForeignKey('self', blank=True, null=True, on_delete=models.CASCADE)
    owner_id = models.DecimalField(max_digits=20, decimal_places=0, blank=True, null=True)
    room_capacity = models.IntegerField(blank=True, null=True)
    notes = models.CharField(max_length=1000, blank=True)
    date_pattern = models.ForeignKey('DatePattern', blank=True, null=True, on_delete=models.CASCADE)
    managing_dept = models.DecimalField(max_digits=20, decimal_places=0, blank=True, null=True)
    display_instructor = models.IntegerField(blank=True, null=True)
    sched_print_note = models.CharField(max_length=2000, blank=True)
    class_suffix = models.CharField(max_length=10, blank=True)
    display_in_sched_book = models.IntegerField(blank=True, null=True)
    max_expected_capacity = models.IntegerField(blank=True, null=True)
    room_ratio = models.FloatField(blank=True, null=True)
    section_number = models.IntegerField(blank=True, null=True)
    last_modified_time = models.DateTimeField(blank=True, null=True)
    uid_rolled_fwd_from = models.DecimalField(max_digits=20, decimal_places=0, blank=True, null=True)
    external_uid = models.CharField(max_length=40, blank=True)
    enrollment = models.IntegerField(blank=True, null=True)
    cancelled = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'class_'


class ClassInstructor(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    class_field = models.ForeignKey(Class, db_column='class_id', blank=True, null=True, on_delete=models.CASCADE)  # Field renamed because it was a Python reserved word.
    instructor = models.ForeignKey('DepartmentalInstructor', blank=True, null=True, on_delete=models.CASCADE)
    percent_share = models.IntegerField(blank=True, null=True)
    is_lead = models.IntegerField(blank=True, null=True)
    last_modified_time = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'class_instructor'


class ClassWaitlist(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    student = models.ForeignKey('Student', blank=True, null=True, on_delete=models.CASCADE)
    course_request = models.ForeignKey('CourseRequest', blank=True, null=True, on_delete=models.CASCADE)
    class_field = models.ForeignKey(Class, db_column='class_id', blank=True, null=True, on_delete=models.CASCADE)  # Field renamed because it was a Python reserved word.
    type = models.BigIntegerField(blank=True, null=True)
    timestamp = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'class_waitlist'


class ClusterDiscovery(models.Model):
    own_address = models.CharField(max_length=200)
    cluster_name = models.CharField(max_length=200)
    ping_data = models.TextField(blank=True)
    time_stamp = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'cluster_discovery'


class ConstraintInfo(models.Model):
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE)
    solver_info = models.ForeignKey('SolverInfo', on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'constraint_info'


class CourseCatalog(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    session_id = models.DecimalField(max_digits=20, decimal_places=0, blank=True, null=True)
    external_uid = models.CharField(max_length=40, blank=True)
    subject = models.CharField(max_length=10, blank=True)
    course_nbr = models.CharField(max_length=10, blank=True)
    title = models.CharField(max_length=100, blank=True)
    perm_id = models.CharField(max_length=20, blank=True)
    approval_type = models.CharField(max_length=20, blank=True)
    designator_req = models.IntegerField(blank=True, null=True)
    prev_subject = models.CharField(max_length=10, blank=True)
    prev_crs_nbr = models.CharField(max_length=10, blank=True)
    credit_type = models.CharField(max_length=20, blank=True)
    credit_unit_type = models.CharField(max_length=20, blank=True)
    credit_format = models.CharField(max_length=20, blank=True)
    fixed_min_credit = models.FloatField(blank=True, null=True)
    max_credit = models.FloatField(blank=True, null=True)
    frac_credit_allowed = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'course_catalog'


class CourseCreditType(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    reference = models.CharField(unique=True, max_length=20, blank=True)
    label = models.CharField(max_length=60, blank=True)
    abbreviation = models.CharField(max_length=10, blank=True)
    legacy_crse_master_code = models.CharField(max_length=10, blank=True)

    class Meta:
        managed = False
        db_table = 'course_credit_type'


class CourseCreditUnitConfig(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    credit_format = models.CharField(max_length=20, blank=True)
    owner = models.ForeignKey('SchedulingSubpart', blank=True, null=True, on_delete=models.CASCADE)
    credit_type = models.ForeignKey(CourseCreditType, db_column='credit_type', blank=True, null=True, on_delete=models.CASCADE)
    credit_unit_type = models.DecimalField(max_digits=20, decimal_places=0, blank=True, null=True)
    defines_credit_at_course_level = models.IntegerField(blank=True, null=True)
    fixed_units = models.FloatField(blank=True, null=True)
    min_units = models.FloatField(blank=True, null=True)
    max_units = models.FloatField(blank=True, null=True)
    fractional_incr_allowed = models.IntegerField(blank=True, null=True)
    last_modified_time = models.DateTimeField(blank=True, null=True)
    course = models.ForeignKey('CourseOffering', blank=True, null=True, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'course_credit_unit_config'


class CourseCreditUnitType(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    reference = models.CharField(unique=True, max_length=20, blank=True)
    label = models.CharField(max_length=60, blank=True)
    abbreviation = models.CharField(max_length=10, blank=True)

    class Meta:
        managed = False
        db_table = 'course_credit_unit_type'


class CourseDemand(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    student = models.ForeignKey('Student', blank=True, null=True, on_delete=models.CASCADE)
    priority = models.BigIntegerField(blank=True, null=True)
    waitlist = models.IntegerField(blank=True, null=True)
    is_alternative = models.IntegerField(blank=True, null=True)
    timestamp = models.DateTimeField(blank=True, null=True)
    free_time = models.ForeignKey('FreeTime', blank=True, null=True, on_delete=models.CASCADE)
    changed_by = models.CharField(max_length=40, blank=True)

    class Meta:
        managed = False
        db_table = 'course_demand'


class CourseOffering(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    course_nbr = models.CharField(max_length=10, blank=True)
    is_control = models.IntegerField(blank=True, null=True)
    perm_id = models.CharField(max_length=20, blank=True)
    proj_demand = models.BigIntegerField(blank=True, null=True)
    instr_offr = models.ForeignKey('InstructionalOffering', blank=True, null=True, on_delete=models.CASCADE)
    subject_area = models.ForeignKey('SubjectArea', blank=True, null=True, on_delete=models.CASCADE)
    title = models.CharField(max_length=90, blank=True)
    schedule_book_note = models.CharField(max_length=1000, blank=True)
    demand_offering = models.ForeignKey('self', blank=True, null=True, on_delete=models.CASCADE)
    demand_offering_type = models.DecimalField(max_digits=20, decimal_places=0, blank=True, null=True)
    nbr_expected_stdents = models.BigIntegerField(blank=True, null=True)
    external_uid = models.CharField(max_length=40, blank=True)
    last_modified_time = models.DateTimeField(blank=True, null=True)
    uid_rolled_fwd_from = models.DecimalField(max_digits=20, decimal_places=0, blank=True, null=True)
    lastlike_demand = models.BigIntegerField(blank=True, null=True)
    enrollment = models.BigIntegerField(blank=True, null=True)
    reservation = models.BigIntegerField(blank=True, null=True)
    course_type = models.ForeignKey('CourseType', blank=True, null=True, on_delete=models.CASCADE)
    consent_type = models.ForeignKey('OffrConsentType', db_column='consent_type', blank=True, null=True, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'course_offering'


class CourseRequest(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    course_demand = models.ForeignKey(CourseDemand, blank=True, null=True, on_delete=models.CASCADE)
    course_offering = models.ForeignKey(CourseOffering, blank=True, null=True, on_delete=models.CASCADE)
    ord = models.BigIntegerField(blank=True, null=True)
    allow_overlap = models.IntegerField(blank=True, null=True)
    credit = models.BigIntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'course_request'


class CourseRequestOption(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    course_request = models.ForeignKey(CourseRequest, blank=True, null=True, on_delete=models.CASCADE)
    option_type = models.BigIntegerField(blank=True, null=True)
    value = models.TextField(blank=True)

    class Meta:
        managed = False
        db_table = 'course_request_option'


class CourseSubpartCredit(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    course_catalog = models.ForeignKey(CourseCatalog, blank=True, null=True, on_delete=models.CASCADE)
    subpart_id = models.CharField(max_length=10, blank=True)
    credit_type = models.CharField(max_length=20, blank=True)
    credit_unit_type = models.CharField(max_length=20, blank=True)
    credit_format = models.CharField(max_length=20, blank=True)
    fixed_min_credit = models.FloatField(blank=True, null=True)
    max_credit = models.FloatField(blank=True, null=True)
    frac_credit_allowed = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'course_subpart_credit'


class CourseType(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    reference = models.CharField(max_length=20)
    label = models.CharField(max_length=60)

    class Meta:
        managed = False
        db_table = 'course_type'


class CrseCreditFormat(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    reference = models.CharField(unique=True, max_length=20, blank=True)
    label = models.CharField(max_length=60, blank=True)
    abbreviation = models.CharField(max_length=10, blank=True)

    class Meta:
        managed = False
        db_table = 'crse_credit_format'


class Curriculum(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    abbv = models.CharField(max_length=20)
    name = models.CharField(max_length=60)
    acad_area = models.ForeignKey(AcademicArea, blank=True, null=True, on_delete=models.CASCADE)
    dept = models.ForeignKey('Department', on_delete=models.CASCADE)
    multiple_majors = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'curriculum'


class CurriculumClasf(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    curriculum = models.ForeignKey(Curriculum, on_delete=models.CASCADE)
    name = models.CharField(max_length=20)
    acad_clasf = models.ForeignKey(AcademicClassification, blank=True, null=True, on_delete=models.CASCADE)
    nr_students = models.BigIntegerField()
    ord = models.BigIntegerField()
    students = models.TextField(blank=True)

    class Meta:
        managed = False
        db_table = 'curriculum_clasf'


class CurriculumCourse(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    course = models.ForeignKey(CourseOffering, on_delete=models.CASCADE)
    cur_clasf = models.ForeignKey(CurriculumClasf, on_delete=models.CASCADE)
    pr_share = models.FloatField()
    ord = models.BigIntegerField()

    class Meta:
        managed = False
        db_table = 'curriculum_course'


class CurriculumCourseGroup(models.Model):
    group = models.ForeignKey('CurriculumGroup', on_delete=models.CASCADE)
    cur_course = models.ForeignKey(CurriculumCourse, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'curriculum_course_group'


class CurriculumGroup(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    name = models.CharField(max_length=20)
    color = models.CharField(max_length=20, blank=True)
    type = models.BigIntegerField()
    curriculum = models.ForeignKey(Curriculum, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'curriculum_group'


class CurriculumMajor(models.Model):
    curriculum = models.ForeignKey(Curriculum, on_delete=models.CASCADE)
    major = models.ForeignKey('PosMajor', on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'curriculum_major'


class CurriculumRule(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    acad_area = models.ForeignKey(AcademicArea, on_delete=models.CASCADE)
    major = models.ForeignKey('PosMajor', blank=True, null=True, on_delete=models.CASCADE)
    acad_clasf = models.ForeignKey(AcademicClassification, on_delete=models.CASCADE)
    projection = models.FloatField()

    class Meta:
        managed = False
        db_table = 'curriculum_rule'


class DateMapping(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    session = models.ForeignKey('Sessions', on_delete=models.CASCADE)
    class_date = models.BigIntegerField()
    event_date = models.BigIntegerField()
    note = models.CharField(max_length=1000, blank=True)

    class Meta:
        managed = False
        db_table = 'date_mapping'


class DatePattern(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    name = models.CharField(max_length=50, blank=True)
    pattern = models.CharField(max_length=366, blank=True)
    offset = models.BigIntegerField(blank=True, null=True)
    type = models.BigIntegerField(blank=True, null=True)
    visible = models.IntegerField(blank=True, null=True)
    session = models.ForeignKey('Sessions', blank=True, null=True, on_delete=models.CASCADE)
    nr_weeks = models.FloatField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'date_pattern'


class DatePatternDept(models.Model):
    dept = models.ForeignKey('Department', on_delete=models.CASCADE)
    pattern = models.ForeignKey(DatePattern, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'date_pattern_dept'


class DatePatternParent(models.Model):
    date_pattern = models.ForeignKey(DatePattern, on_delete=models.CASCADE)
    parent = models.ForeignKey(DatePattern, related_name='child_set', on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'date_pattern_parent'


class DatePatternPref(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    owner_id = models.DecimalField(max_digits=20, decimal_places=0)
    pref_level = models.ForeignKey('PreferenceLevel', on_delete=models.CASCADE)
    date_pattern = models.ForeignKey(DatePattern, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'date_pattern_pref'


class DemandOffrType(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    reference = models.CharField(unique=True, max_length=20, blank=True)
    label = models.CharField(unique=True, max_length=60, blank=True)

    class Meta:
        managed = False
        db_table = 'demand_offr_type'


class Department(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    session_id = models.DecimalField(max_digits=20, decimal_places=0, blank=True, null=True)
    abbreviation = models.CharField(max_length=20, blank=True)
    name = models.CharField(max_length=100, blank=True)
    dept_code = models.CharField(max_length=50, blank=True)
    external_uid = models.CharField(max_length=40, blank=True)
    rs_color = models.CharField(max_length=6, blank=True)
    external_manager = models.IntegerField(blank=True, null=True)
    external_mgr_label = models.CharField(max_length=30, blank=True)
    external_mgr_abbv = models.CharField(max_length=10, blank=True)
    solver_group = models.ForeignKey('SolverGroup', blank=True, null=True, on_delete=models.CASCADE)
    status_type = models.ForeignKey('DeptStatusType', db_column='status_type', blank=True, null=True, on_delete=models.CASCADE)
    dist_priority = models.BigIntegerField(blank=True, null=True)
    allow_req_time = models.IntegerField(blank=True, null=True)
    allow_req_room = models.IntegerField(blank=True, null=True)
    last_modified_time = models.DateTimeField(blank=True, null=True)
    allow_req_dist = models.IntegerField(blank=True, null=True)
    allow_events = models.IntegerField(blank=True, null=True)
    instructor_pref = models.IntegerField(blank=True, null=True)
    allow_student_schd = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'department'


class DepartmentalInstructor(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    external_uid = models.CharField(max_length=40, blank=True)
    career_acct = models.CharField(max_length=20, blank=True)
    lname = models.CharField(max_length=100, blank=True)
    fname = models.CharField(max_length=100, blank=True)
    mname = models.CharField(max_length=100, blank=True)
    pos_code_type = models.ForeignKey('PositionType', db_column='pos_code_type', blank=True, null=True, on_delete=models.CASCADE)
    note = models.CharField(max_length=2048, blank=True)
    department_uniqueid = models.ForeignKey(Department, db_column='department_uniqueid', blank=True, null=True, on_delete=models.CASCADE)
    ignore_too_far = models.IntegerField(blank=True, null=True)
    last_modified_time = models.DateTimeField(blank=True, null=True)
    email = models.CharField(max_length=200, blank=True)
    role = models.ForeignKey('Roles', blank=True, null=True, on_delete=models.CASCADE)
    acad_title = models.CharField(max_length=50, blank=True)

    class Meta:
        managed = False
        db_table = 'departmental_instructor'


class DeptStatusType(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    reference = models.CharField(max_length=20, blank=True)
    label = models.CharField(max_length=60, blank=True)
    status = models.BigIntegerField(blank=True, null=True)
    apply = models.BigIntegerField(blank=True, null=True)
    ord = models.BigIntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'dept_status_type'


class DeptToTtMgr(models.Model):
    timetable_mgr = models.ForeignKey('TimetableManager', on_delete=models.CASCADE)
    department = models.ForeignKey(Department, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'dept_to_tt_mgr'


class Designator(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    subject_area = models.ForeignKey('SubjectArea', blank=True, null=True, on_delete=models.CASCADE)
    instructor = models.ForeignKey(DepartmentalInstructor, blank=True, null=True, on_delete=models.CASCADE)
    code = models.CharField(max_length=3, blank=True)
    last_modified_time = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'designator'


class DistTypeDept(models.Model):
    dist_type = models.ForeignKey('DistributionType', on_delete=models.CASCADE)
    dept = models.ForeignKey(Department, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'dist_type_dept'


class DistributionObject(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    dist_pref = models.ForeignKey('DistributionPref', blank=True, null=True, on_delete=models.CASCADE)
    sequence_number = models.IntegerField(blank=True, null=True)
    pref_group_id = models.DecimalField(max_digits=20, decimal_places=0, blank=True, null=True)
    last_modified_time = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'distribution_object'


class DistributionPref(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    owner_id = models.DecimalField(max_digits=20, decimal_places=0, blank=True, null=True)
    pref_level = models.ForeignKey('PreferenceLevel', blank=True, null=True, on_delete=models.CASCADE)
    dist_type = models.ForeignKey('DistributionType', blank=True, null=True, on_delete=models.CASCADE)
    grouping = models.BigIntegerField(blank=True, null=True)
    last_modified_time = models.DateTimeField(blank=True, null=True)
    uid_rolled_fwd_from = models.DecimalField(max_digits=20, decimal_places=0, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'distribution_pref'


class DistributionType(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    reference = models.CharField(max_length=20, blank=True)
    label = models.CharField(max_length=60, blank=True)
    sequencing_required = models.CharField(max_length=1, blank=True)
    req_id = models.IntegerField(unique=True, blank=True, null=True)
    allowed_pref = models.CharField(max_length=10, blank=True)
    description = models.CharField(max_length=2048, blank=True)
    abbreviation = models.CharField(max_length=20, blank=True)
    instructor_pref = models.IntegerField(blank=True, null=True)
    exam_pref = models.IntegerField(blank=True, null=True)
    visible = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'distribution_type'


class DurationType(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    reference = models.CharField(max_length=20)
    abbreviation = models.CharField(max_length=20)
    label = models.CharField(max_length=60)
    implementation = models.CharField(max_length=255)
    parameter = models.CharField(max_length=200, blank=True)
    visible = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'duration_type'


class Event(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    event_name = models.CharField(max_length=100, blank=True)
    min_capacity = models.BigIntegerField(blank=True, null=True)
    max_capacity = models.BigIntegerField(blank=True, null=True)
    sponsoring_org = models.DecimalField(max_digits=20, decimal_places=0, blank=True, null=True)
    main_contact = models.ForeignKey('EventContact', blank=True, null=True, on_delete=models.CASCADE)
    class_field = models.ForeignKey(Class, db_column='class_id', blank=True, null=True, on_delete=models.CASCADE)  # Field renamed because it was a Python reserved word.
    exam = models.ForeignKey('Exam', blank=True, null=True, on_delete=models.CASCADE)
    event_type = models.BigIntegerField(blank=True, null=True)
    req_attd = models.IntegerField(blank=True, null=True)
    email = models.CharField(max_length=1000, blank=True)
    sponsor_org = models.ForeignKey('SponsoringOrganization', blank=True, null=True, on_delete=models.CASCADE)
    expiration_date = models.DateField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'event'


class EventContact(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    external_id = models.CharField(max_length=40, blank=True)
    email = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=25, blank=True)
    firstname = models.CharField(max_length=100, blank=True)
    middlename = models.CharField(max_length=100, blank=True)
    lastname = models.CharField(max_length=100, blank=True)
    acad_title = models.CharField(max_length=50, blank=True)

    class Meta:
        managed = False
        db_table = 'event_contact'


class EventJoinEventContact(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    event_contact = models.ForeignKey(EventContact, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'event_join_event_contact'


class EventNote(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    text_note = models.CharField(max_length=1000, blank=True)
    time_stamp = models.DateTimeField(blank=True, null=True)
    note_type = models.BigIntegerField()
    uname = models.CharField(max_length=100, blank=True)
    meetings = models.TextField(blank=True)
    attached_file = models.TextField(blank=True)
    attached_name = models.CharField(max_length=260, blank=True)
    attached_content = models.CharField(max_length=260, blank=True)
    user_id = models.CharField(max_length=40, blank=True)

    class Meta:
        managed = False
        db_table = 'event_note'


class EventNoteMeeting(models.Model):
    note = models.ForeignKey(EventNote, on_delete=models.CASCADE)
    meeting = models.ForeignKey('Meeting', on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'event_note_meeting'


class ExactTimeMins(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    mins_min = models.IntegerField(blank=True, null=True)
    mins_max = models.IntegerField(blank=True, null=True)
    nr_slots = models.IntegerField(blank=True, null=True)
    break_time = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'exact_time_mins'


class Exam(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    session = models.ForeignKey('Sessions', on_delete=models.CASCADE)
    name = models.CharField(max_length=100, blank=True)
    note = models.CharField(max_length=1000, blank=True)
    length = models.BigIntegerField()
    max_nbr_rooms = models.BigIntegerField()
    seating_type = models.BigIntegerField()
    assigned_period = models.ForeignKey('ExamPeriod', db_column='assigned_period', blank=True, null=True, on_delete=models.CASCADE)
    assigned_pref = models.CharField(max_length=100, blank=True)
    avg_period = models.BigIntegerField(blank=True, null=True)
    uid_rolled_fwd_from = models.DecimalField(max_digits=20, decimal_places=0, blank=True, null=True)
    exam_size = models.BigIntegerField(blank=True, null=True)
    print_offset = models.BigIntegerField(blank=True, null=True)
    exam_type = models.ForeignKey('ExamType', on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'exam'


class ExamInstructor(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE)
    instructor = models.ForeignKey(DepartmentalInstructor, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'exam_instructor'


class ExamLocationPref(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    location_id = models.DecimalField(max_digits=20, decimal_places=0)
    pref_level = models.ForeignKey('PreferenceLevel', on_delete=models.CASCADE)
    period = models.ForeignKey('ExamPeriod', on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'exam_location_pref'


class ExamManagers(models.Model):
    session = models.ForeignKey('ExamStatus', on_delete=models.CASCADE)
    type = models.ForeignKey('ExamStatus', related_name='exam_manager_type_set', on_delete=models.CASCADE)
    manager = models.ForeignKey('TimetableManager', on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'exam_managers'


class ExamOwner(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE)
    owner_id = models.DecimalField(max_digits=20, decimal_places=0)
    owner_type = models.BigIntegerField()
    course = models.ForeignKey(CourseOffering, blank=True, null=True, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'exam_owner'


class ExamPeriod(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    session = models.ForeignKey('Sessions', on_delete=models.CASCADE)
    date_ofs = models.BigIntegerField()
    start_slot = models.BigIntegerField()
    length = models.BigIntegerField()
    pref_level = models.ForeignKey('PreferenceLevel', on_delete=models.CASCADE)
    event_start_offset = models.BigIntegerField()
    event_stop_offset = models.BigIntegerField()
    exam_type = models.ForeignKey('ExamType', on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'exam_period'


class ExamPeriodPref(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    owner_id = models.DecimalField(max_digits=20, decimal_places=0)
    pref_level = models.ForeignKey('PreferenceLevel', on_delete=models.CASCADE)
    period = models.ForeignKey(ExamPeriod, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'exam_period_pref'


class ExamRoomAssignment(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE)
    location_id = models.DecimalField(max_digits=20, decimal_places=0)

    class Meta:
        managed = False
        db_table = 'exam_room_assignment'


class ExamStatus(models.Model):
    session = models.ForeignKey('Sessions', on_delete=models.CASCADE)
    type = models.ForeignKey('ExamType', on_delete=models.CASCADE)
    status = models.ForeignKey(DeptStatusType, blank=True, null=True, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'exam_status'


class ExamType(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    reference = models.CharField(max_length=20)
    label = models.CharField(max_length=60)
    xtype = models.BigIntegerField()
    events = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'exam_type'


class ExternalBuilding(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    session_id = models.DecimalField(max_digits=20, decimal_places=0, blank=True, null=True)
    external_uid = models.CharField(max_length=40, blank=True)
    abbreviation = models.CharField(max_length=10, blank=True)
    coordinate_x = models.FloatField(blank=True, null=True)
    coordinate_y = models.FloatField(blank=True, null=True)
    display_name = models.CharField(max_length=100, blank=True)

    class Meta:
        managed = False
        db_table = 'external_building'


class ExternalRoom(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    external_bldg = models.ForeignKey(ExternalBuilding, blank=True, null=True, on_delete=models.CASCADE)
    external_uid = models.CharField(max_length=40, blank=True)
    room_number = models.CharField(max_length=10, blank=True)
    coordinate_x = models.FloatField(blank=True, null=True)
    coordinate_y = models.FloatField(blank=True, null=True)
    capacity = models.BigIntegerField(blank=True, null=True)
    classification = models.CharField(max_length=20, blank=True)
    instructional = models.IntegerField(blank=True, null=True)
    display_name = models.CharField(max_length=100, blank=True)
    exam_capacity = models.BigIntegerField(blank=True, null=True)
    room_type = models.ForeignKey('RoomType', db_column='room_type', blank=True, null=True, on_delete=models.CASCADE)
    area = models.FloatField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'external_room'


class ExternalRoomDepartment(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    external_room = models.ForeignKey(ExternalRoom, blank=True, null=True, on_delete=models.CASCADE)
    department_code = models.CharField(max_length=50, blank=True)
    percent = models.BigIntegerField(blank=True, null=True)
    assignment_type = models.CharField(max_length=20, blank=True)

    class Meta:
        managed = False
        db_table = 'external_room_department'


class ExternalRoomFeature(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    external_room = models.ForeignKey(ExternalRoom, blank=True, null=True, on_delete=models.CASCADE)
    name = models.CharField(max_length=20, blank=True)
    value = models.CharField(max_length=20, blank=True)

    class Meta:
        managed = False
        db_table = 'external_room_feature'


class FeatureType(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    reference = models.CharField(max_length=20)
    label = models.CharField(max_length=60)
    events = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'feature_type'


class FreeTime(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    name = models.CharField(max_length=50, blank=True)
    day_code = models.BigIntegerField(blank=True, null=True)
    start_slot = models.BigIntegerField(blank=True, null=True)
    length = models.BigIntegerField(blank=True, null=True)
    category = models.BigIntegerField(blank=True, null=True)
    session = models.ForeignKey('Sessions', blank=True, null=True, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'free_time'


class HashedQueries(models.Model):
    query_hash = models.CharField(primary_key=True, max_length=48)
    query_text = models.CharField(max_length=2048)
    ts_create = models.DateTimeField()
    nbr_use = models.DecimalField(max_digits=20, decimal_places=0)
    ts_use = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'hashed_queries'


class HibernateUniqueKey(models.Model):
    next_hi = models.DecimalField(max_digits=20, decimal_places=0, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'hibernate_unique_key'


class History(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    subclass = models.CharField(max_length=10, blank=True)
    old_value = models.CharField(max_length=20, blank=True)
    new_value = models.CharField(max_length=20, blank=True)
    old_number = models.CharField(max_length=20, blank=True)
    new_number = models.CharField(max_length=20, blank=True)
    session = models.ForeignKey('Sessions', blank=True, null=True, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'history'


class InstrOfferingConfig(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    config_limit = models.BigIntegerField(blank=True, null=True)
    instr_offr = models.ForeignKey('InstructionalOffering', blank=True, null=True, on_delete=models.CASCADE)
    unlimited_enrollment = models.IntegerField(blank=True, null=True)
    name = models.CharField(max_length=10, blank=True)
    last_modified_time = models.DateTimeField(blank=True, null=True)
    uid_rolled_fwd_from = models.DecimalField(max_digits=20, decimal_places=0, blank=True, null=True)
    duration_type = models.ForeignKey(DurationType, blank=True, null=True, on_delete=models.CASCADE)
    instr_method = models.ForeignKey('InstructionalMethod', blank=True, null=True, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'instr_offering_config'


class InstructionalMethod(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    reference = models.CharField(max_length=20)
    label = models.CharField(max_length=60)
    visible = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'instructional_method'


class InstructionalOffering(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    session_id = models.DecimalField(max_digits=20, decimal_places=0, blank=True, null=True)
    instr_offering_perm_id = models.BigIntegerField(blank=True, null=True)
    not_offered = models.IntegerField(blank=True, null=True)
    limit = models.IntegerField(blank=True, null=True)
    designator_required = models.IntegerField(blank=True, null=True)
    last_modified_time = models.DateTimeField(blank=True, null=True)
    uid_rolled_fwd_from = models.DecimalField(max_digits=20, decimal_places=0, blank=True, null=True)
    external_uid = models.CharField(max_length=40, blank=True)
    req_reservation = models.IntegerField()
    wk_enroll = models.BigIntegerField(blank=True, null=True)
    wk_change = models.BigIntegerField(blank=True, null=True)
    wk_drop = models.BigIntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'instructional_offering'


class ItypeDesc(models.Model):
    itype = models.IntegerField(primary_key=True)
    abbv = models.CharField(max_length=7, blank=True)
    description = models.CharField(max_length=50, blank=True)
    sis_ref = models.CharField(max_length=20, blank=True)
    basic = models.IntegerField(blank=True, null=True)
    parent = models.IntegerField(blank=True, null=True)
    organized = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'itype_desc'


class Jenrl(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    jenrl = models.FloatField(blank=True, null=True)
    solution = models.ForeignKey('Solution', blank=True, null=True, on_delete=models.CASCADE)
    class1 = models.ForeignKey(Class, blank=True, null=True, related_name='jenrl1_set', on_delete=models.CASCADE)
    class2 = models.ForeignKey(Class, blank=True, null=True, related_name='jentl2_set', on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'jenrl'


class LastlikeCourseDemand(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    student = models.ForeignKey('Student', blank=True, null=True, on_delete=models.CASCADE)
    subject_area = models.ForeignKey('SubjectArea', blank=True, null=True, on_delete=models.CASCADE)
    course_nbr = models.CharField(max_length=10, blank=True)
    priority = models.BigIntegerField(blank=True, null=True)
    course_perm_id = models.CharField(max_length=20, blank=True)

    class Meta:
        managed = False
        db_table = 'lastlike_course_demand'


class LocationPicture(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    location = models.ForeignKey('NonUniversityLocation', on_delete=models.CASCADE)
    data_file = models.TextField()
    file_name = models.CharField(max_length=260)
    content_type = models.CharField(max_length=260)
    time_stamp = models.DateTimeField()
    type = models.ForeignKey(AttachmentType, blank=True, null=True, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'location_picture'


class ManagerSettings(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    key = models.ForeignKey('Settings', blank=True, null=True, on_delete=models.CASCADE)
    value = models.CharField(max_length=100, blank=True)
    user_uniqueid = models.ForeignKey('TimetableManager', db_column='user_uniqueid', blank=True, null=True, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'manager_settings'


class Meeting(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    meeting_date = models.DateField()
    start_period = models.BigIntegerField()
    start_offset = models.BigIntegerField(blank=True, null=True)
    stop_period = models.BigIntegerField()
    stop_offset = models.BigIntegerField(blank=True, null=True)
    location_perm_id = models.DecimalField(max_digits=20, decimal_places=0, blank=True, null=True)
    class_can_override = models.IntegerField()
    approval_date = models.DateField(blank=True, null=True)
    approval_status = models.BigIntegerField()

    class Meta:
        managed = False
        db_table = 'meeting'


class MessageLog(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    time_stamp = models.DateTimeField()
    log_level = models.DecimalField(max_digits=10, decimal_places=0)
    message = models.TextField(blank=True)
    logger = models.CharField(max_length=255)
    thread = models.CharField(max_length=100, blank=True)
    ndc = models.TextField(blank=True)
    exception = models.TextField(blank=True)

    class Meta:
        managed = False
        db_table = 'message_log'


class NonUniversityLocation(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    session = models.ForeignKey('Sessions', blank=True, null=True, on_delete=models.CASCADE)
    name = models.CharField(max_length=20, blank=True)
    capacity = models.BigIntegerField(blank=True, null=True)
    coordinate_x = models.FloatField(blank=True, null=True)
    coordinate_y = models.FloatField(blank=True, null=True)
    ignore_too_far = models.IntegerField(blank=True, null=True)
    manager_ids = models.CharField(max_length=3000, blank=True)
    pattern = models.CharField(max_length=2048, blank=True)
    ignore_room_check = models.IntegerField(blank=True, null=True)
    display_name = models.CharField(max_length=100, blank=True)
    exam_capacity = models.BigIntegerField(blank=True, null=True)
    permanent_id = models.DecimalField(max_digits=20, decimal_places=0)
    room_type = models.ForeignKey('RoomType', db_column='room_type', blank=True, null=True, on_delete=models.CASCADE)
    event_dept = models.ForeignKey(Department, blank=True, null=True, on_delete=models.CASCADE)
    area = models.FloatField(blank=True, null=True)
    break_time = models.BigIntegerField(blank=True, null=True)
    event_status = models.BigIntegerField(blank=True, null=True)
    note = models.CharField(max_length=2048, blank=True)
    availability = models.CharField(max_length=2048, blank=True)
    external_uid = models.CharField(max_length=40, blank=True)
    share_note = models.CharField(max_length=2048, blank=True)

    class Meta:
        managed = False
        db_table = 'non_university_location'


class OfferingCoordinator(models.Model):
    offering = models.ForeignKey(InstructionalOffering, on_delete=models.CASCADE)
    instructor = models.ForeignKey(DepartmentalInstructor, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'offering_coordinator'


class OffrConsentType(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    reference = models.CharField(unique=True, max_length=20, blank=True)
    label = models.CharField(unique=True, max_length=60, blank=True)
    abbv = models.CharField(max_length=20, blank=True)

    class Meta:
        managed = False
        db_table = 'offr_consent_type'


class OffrGroup(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    session = models.ForeignKey('Sessions', blank=True, null=True, on_delete=models.CASCADE)
    name = models.CharField(max_length=20, blank=True)
    description = models.CharField(max_length=200, blank=True)
    department = models.ForeignKey(Department, blank=True, null=True, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'offr_group'


class OffrGroupOffering(models.Model):
    offr_group = models.ForeignKey(OffrGroup, on_delete=models.CASCADE)
    instr_offering = models.ForeignKey(InstructionalOffering, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'offr_group_offering'


class PosAcadAreaMajor(models.Model):
    academic_area = models.ForeignKey(AcademicArea, on_delete=models.CASCADE)
    major = models.ForeignKey('PosMajor', on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'pos_acad_area_major'


class PosAcadAreaMinor(models.Model):
    academic_area = models.ForeignKey(AcademicArea, on_delete=models.CASCADE)
    minor = models.ForeignKey('PosMinor', on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'pos_acad_area_minor'


class PosMajor(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    code = models.CharField(max_length=10, blank=True)
    name = models.CharField(max_length=50, blank=True)
    external_uid = models.CharField(max_length=20, blank=True)
    session = models.ForeignKey('Sessions', blank=True, null=True, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'pos_major'


class PosMinor(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    code = models.CharField(max_length=10, blank=True)
    name = models.CharField(max_length=50, blank=True)
    external_uid = models.CharField(max_length=40, blank=True)
    session = models.ForeignKey('Sessions', blank=True, null=True, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'pos_minor'


class PositionType(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    reference = models.CharField(unique=True, max_length=20, blank=True)
    label = models.CharField(unique=True, max_length=60, blank=True)
    sort_order = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'position_type'


class PreferenceLevel(models.Model):
    pref_id = models.IntegerField(unique=True, blank=True, null=True)
    pref_prolog = models.CharField(max_length=2, blank=True)
    pref_name = models.CharField(max_length=20, blank=True)
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    pref_abbv = models.CharField(max_length=10, blank=True)

    class Meta:
        managed = False
        db_table = 'preference_level'


class QueryLog(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    time_stamp = models.DateTimeField()
    time_spent = models.DecimalField(max_digits=20, decimal_places=0)
    uri = models.CharField(max_length=255)
    type = models.DecimalField(max_digits=10, decimal_places=0)
    session_id = models.CharField(max_length=32, blank=True)
    userid = models.CharField(max_length=40, blank=True)
    query = models.TextField(blank=True)
    exception = models.TextField(blank=True)

    class Meta:
        managed = False
        db_table = 'query_log'


class RelatedCourseInfo(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    owner_id = models.DecimalField(max_digits=20, decimal_places=0)
    owner_type = models.BigIntegerField()
    course = models.ForeignKey(CourseOffering, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'related_course_info'


class Reservation(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    reservation_type = models.BigIntegerField()
    expiration_date = models.DateField(blank=True, null=True)
    reservation_limit = models.BigIntegerField(blank=True, null=True)
    offering = models.ForeignKey(InstructionalOffering, on_delete=models.CASCADE)
    group = models.ForeignKey('StudentGroup', blank=True, null=True, on_delete=models.CASCADE)
    area = models.ForeignKey(AcademicArea, blank=True, null=True, on_delete=models.CASCADE)
    course = models.ForeignKey(CourseOffering, blank=True, null=True, related_name='reservation_set', on_delete=models.CASCADE)
    override_type = models.BigIntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'reservation'


class ReservationClasf(models.Model):
    reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE)
    acad_clasf = models.ForeignKey(AcademicClassification, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'reservation_clasf'


class ReservationClass(models.Model):
    reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE)
    class_field = models.ForeignKey(Class, db_column='class_id', on_delete=models.CASCADE)  # Field renamed because it was a Python reserved word.

    class Meta:
        managed = False
        db_table = 'reservation_class'


class ReservationConfig(models.Model):
    reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE)
    config = models.ForeignKey(InstrOfferingConfig, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'reservation_config'


class ReservationMajor(models.Model):
    reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE)
    major = models.ForeignKey(PosMajor, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'reservation_major'


class ReservationStudent(models.Model):
    reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE)
    student = models.ForeignKey('Student', on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'reservation_student'


class Rights(models.Model):
    role = models.ForeignKey('Roles', on_delete=models.CASCADE)
    value = models.CharField(max_length=200)

    class Meta:
        managed = False
        db_table = 'rights'


class Roles(models.Model):
    role_id = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    reference = models.CharField(unique=True, max_length=20, blank=True)
    abbv = models.CharField(unique=True, max_length=40, blank=True)
    manager = models.IntegerField(blank=True, null=True)
    enabled = models.IntegerField(blank=True, null=True)
    instructor = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'roles'


class Room(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    external_uid = models.CharField(max_length=40, blank=True)
    session = models.ForeignKey('Sessions', blank=True, null=True, on_delete=models.CASCADE)
    building = models.ForeignKey(Building, blank=True, null=True, on_delete=models.CASCADE)
    room_number = models.CharField(max_length=10, blank=True)
    capacity = models.BigIntegerField(blank=True, null=True)
    coordinate_x = models.FloatField(blank=True, null=True)
    coordinate_y = models.FloatField(blank=True, null=True)
    ignore_too_far = models.IntegerField(blank=True, null=True)
    manager_ids = models.CharField(max_length=3000, blank=True)
    pattern = models.CharField(max_length=2048, blank=True)
    ignore_room_check = models.IntegerField(blank=True, null=True)
    classification = models.CharField(max_length=20, blank=True)
    display_name = models.CharField(max_length=100, blank=True)
    exam_capacity = models.BigIntegerField(blank=True, null=True)
    permanent_id = models.DecimalField(max_digits=20, decimal_places=0)
    room_type = models.ForeignKey('RoomType', db_column='room_type', blank=True, null=True, on_delete=models.CASCADE)
    event_dept = models.ForeignKey(Department, blank=True, null=True, on_delete=models.CASCADE)
    area = models.FloatField(blank=True, null=True)
    break_time = models.BigIntegerField(blank=True, null=True)
    event_status = models.BigIntegerField(blank=True, null=True)
    note = models.CharField(max_length=2048, blank=True)
    availability = models.CharField(max_length=2048, blank=True)
    share_note = models.CharField(max_length=2048, blank=True)

    class Meta:
        managed = False
        db_table = 'room'


class RoomDept(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    room_id = models.DecimalField(max_digits=20, decimal_places=0, blank=True, null=True)
    department = models.ForeignKey(Department, blank=True, null=True, on_delete=models.CASCADE)
    is_control = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'room_dept'


class RoomExamType(models.Model):
    location_id = models.DecimalField(max_digits=20, decimal_places=0)
    exam_type = models.ForeignKey(ExamType, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'room_exam_type'


class RoomFeature(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    discriminator = models.CharField(max_length=10, blank=True)
    label = models.CharField(max_length=60, blank=True)
    sis_reference = models.CharField(max_length=20, blank=True)
    sis_value = models.CharField(max_length=20, blank=True)
    department = models.ForeignKey(Department, blank=True, null=True, on_delete=models.CASCADE)
    abbv = models.CharField(max_length=60, blank=True)
    session = models.ForeignKey('Sessions', blank=True, null=True, on_delete=models.CASCADE)
    feature_type = models.ForeignKey(FeatureType, blank=True, null=True, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'room_feature'


class RoomFeaturePref(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    owner_id = models.DecimalField(max_digits=20, decimal_places=0, blank=True, null=True)
    pref_level = models.ForeignKey(PreferenceLevel, blank=True, null=True, on_delete=models.CASCADE)
    room_feature = models.ForeignKey(RoomFeature, blank=True, null=True, on_delete=models.CASCADE)
    last_modified_time = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'room_feature_pref'


class RoomGroup(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    session = models.ForeignKey('Sessions', blank=True, null=True, on_delete=models.CASCADE)
    name = models.CharField(max_length=60, blank=True)
    description = models.CharField(max_length=200, blank=True)
    global_field = models.IntegerField(db_column='global', blank=True,
                                       null=True)  # Field renamed because it was a Python reserved word.
    default_group = models.IntegerField(blank=True, null=True)
    department = models.ForeignKey(Department, blank=True, null=True, on_delete=models.CASCADE)
    abbv = models.CharField(max_length=60, blank=True)

    class Meta:
        managed = False
        db_table = 'room_group'


class RoomGroupPref(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    owner_id = models.DecimalField(max_digits=20, decimal_places=0, blank=True, null=True)
    pref_level = models.ForeignKey(PreferenceLevel, blank=True, null=True, on_delete=models.CASCADE)
    room_group = models.ForeignKey(RoomGroup, blank=True, null=True, on_delete=models.CASCADE)
    last_modified_time = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'room_group_pref'


class RoomGroupRoom(models.Model):
    room_group = models.ForeignKey(RoomGroup, on_delete=models.CASCADE)
    room_id = models.DecimalField(max_digits=20, decimal_places=0)

    class Meta:
        managed = False
        db_table = 'room_group_room'


class RoomJoinRoomFeature(models.Model):
    room_id = models.DecimalField(max_digits=20, decimal_places=0, blank=True, null=True)
    feature = models.ForeignKey(RoomFeature, blank=True, null=True, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'room_join_room_feature'


class RoomPicture(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    location = models.ForeignKey(Room, on_delete=models.CASCADE)
    data_file = models.TextField()
    file_name = models.CharField(max_length=260)
    content_type = models.CharField(max_length=260)
    time_stamp = models.DateTimeField()
    type = models.ForeignKey(AttachmentType, blank=True, null=True, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'room_picture'


class RoomPref(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    owner_id = models.DecimalField(max_digits=20, decimal_places=0, blank=True, null=True)
    pref_level = models.ForeignKey(PreferenceLevel, blank=True, null=True, on_delete=models.CASCADE)
    room_id = models.DecimalField(max_digits=20, decimal_places=0, blank=True, null=True)
    last_modified_time = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'room_pref'


class RoomType(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    reference = models.CharField(max_length=20)
    label = models.CharField(max_length=60)
    ord = models.BigIntegerField()
    is_room = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'room_type'


class RoomTypeOption(models.Model):
    room_type = models.ForeignKey(RoomType, db_column='room_type', on_delete=models.CASCADE)
    status = models.BigIntegerField()
    message = models.CharField(max_length=2048, blank=True)
    break_time = models.BigIntegerField()
    department = models.ForeignKey(Department, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'room_type_option'


class SavedHql(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=1000, blank=True)
    query = models.TextField()
    type = models.DecimalField(max_digits=10, decimal_places=0)

    class Meta:
        managed = False
        db_table = 'saved_hql'


class SchedulingSubpart(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    min_per_wk = models.IntegerField(blank=True, null=True)
    parent = models.ForeignKey('self', db_column='parent', blank=True, null=True, on_delete=models.CASCADE)
    config = models.ForeignKey(InstrOfferingConfig, blank=True, null=True, on_delete=models.CASCADE)
    itype = models.ForeignKey(ItypeDesc, db_column='itype', blank=True, null=True, on_delete=models.CASCADE)
    date_pattern = models.ForeignKey(DatePattern, blank=True, null=True, on_delete=models.CASCADE)
    auto_time_spread = models.IntegerField(blank=True, null=True)
    subpart_suffix = models.CharField(max_length=5, blank=True)
    student_allow_overlap = models.IntegerField(blank=True, null=True)
    last_modified_time = models.DateTimeField(blank=True, null=True)
    uid_rolled_fwd_from = models.DecimalField(max_digits=20, decimal_places=0, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'scheduling_subpart'


class Script(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    name = models.CharField(max_length=128)
    description = models.CharField(max_length=1024, blank=True)
    engine = models.CharField(max_length=32)
    permission = models.CharField(max_length=128, blank=True)
    script = models.TextField()

    class Meta:
        managed = False
        db_table = 'script'


class ScriptParameter(models.Model):
    script = models.ForeignKey(Script, on_delete=models.CASCADE)
    name = models.CharField(max_length=128)
    label = models.CharField(max_length=256, blank=True)
    type = models.CharField(max_length=2048)
    default_value = models.CharField(max_length=2048, blank=True)

    class Meta:
        managed = False
        db_table = 'script_parameter'


class SectioningCourseTypes(models.Model):
    sectioning_status = models.ForeignKey('SectioningStatus', on_delete=models.CASCADE)
    course_type = models.ForeignKey(CourseType, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'sectioning_course_types'


class SectioningInfo(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    class_field = models.ForeignKey(Class, db_column='class_id', blank=True, null=True, on_delete=models.CASCADE)  # Field renamed because it was a Python reserved word.
    nbr_exp_students = models.FloatField(blank=True, null=True)
    nbr_hold_students = models.FloatField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'sectioning_info'


class SectioningLog(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    time_stamp = models.DateTimeField()
    student = models.CharField(max_length=40)
    session = models.ForeignKey('Sessions', on_delete=models.CASCADE)
    operation = models.CharField(max_length=20)
    action = models.TextField()
    result = models.BigIntegerField(blank=True, null=True)
    user_id = models.CharField(max_length=40, blank=True)

    class Meta:
        managed = False
        db_table = 'sectioning_log'


class SectioningQueue(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    session_id = models.DecimalField(max_digits=20, decimal_places=0)
    type = models.BigIntegerField()
    time_stamp = models.DateTimeField()
    message = models.TextField(blank=True)

    class Meta:
        managed = False
        db_table = 'sectioning_queue'


class SectioningStatus(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    reference = models.CharField(max_length=20)
    label = models.CharField(max_length=60)
    status = models.BigIntegerField()
    message = models.CharField(max_length=200, blank=True)

    class Meta:
        managed = False
        db_table = 'sectioning_status'


class SessionConfig(models.Model):
    session = models.ForeignKey('Sessions', on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    value = models.CharField(max_length=4000, blank=True)
    description = models.CharField(max_length=500, blank=True)

    class Meta:
        managed = False
        db_table = 'session_config'


class Sessions(models.Model):
    academic_initiative = models.CharField(max_length=20, blank=True)
    session_begin_date_time = models.DateTimeField(blank=True, null=True)
    classes_end_date_time = models.DateTimeField(blank=True, null=True)
    session_end_date_time = models.DateTimeField(blank=True, null=True)
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    holidays = models.CharField(max_length=400, blank=True)
    def_datepatt = models.ForeignKey(DatePattern, blank=True, null=True, on_delete=models.CASCADE)
    status_type = models.ForeignKey(DeptStatusType, db_column='status_type', blank=True, null=True, on_delete=models.CASCADE)
    last_modified_time = models.DateTimeField(blank=True, null=True)
    academic_year = models.CharField(max_length=4, blank=True)
    academic_term = models.CharField(max_length=20, blank=True)
    exam_begin_date = models.DateTimeField(blank=True, null=True)
    event_begin_date = models.DateTimeField(blank=True, null=True)
    event_end_date = models.DateTimeField(blank=True, null=True)
    sect_status = models.ForeignKey(SectioningStatus, db_column='sect_status', blank=True, null=True, on_delete=models.CASCADE)
    wk_enroll = models.BigIntegerField()
    wk_change = models.BigIntegerField()
    wk_drop = models.BigIntegerField()
    duration_type = models.ForeignKey(DurationType, blank=True, null=True, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'sessions'


class Settings(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    name = models.CharField(max_length=30, blank=True)
    default_value = models.CharField(max_length=100, blank=True)
    allowed_values = models.CharField(max_length=500, blank=True)
    description = models.CharField(max_length=100, blank=True)

    class Meta:
        managed = False
        db_table = 'settings'


class Solution(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    created = models.DateTimeField(blank=True, null=True)
    valid = models.IntegerField(blank=True, null=True)
    commited = models.IntegerField(blank=True, null=True)
    commit_date = models.DateTimeField(blank=True, null=True)
    note = models.CharField(max_length=1000, blank=True)
    creator = models.CharField(max_length=250, blank=True)
    owner = models.ForeignKey('SolverGroup', blank=True, null=True, on_delete=models.CASCADE)
    last_modified_time = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'solution'


class SolverGrToTtMgr(models.Model):
    solver_group = models.ForeignKey('SolverGroup', on_delete=models.CASCADE)
    timetable_mgr = models.ForeignKey('TimetableManager', on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'solver_gr_to_tt_mgr'


class SolverGroup(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    name = models.CharField(max_length=50, blank=True)
    abbv = models.CharField(max_length=50, blank=True)
    session = models.ForeignKey(Sessions, blank=True, null=True, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'solver_group'


class SolverInfo(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    type = models.BigIntegerField(blank=True, null=True)
    value = models.TextField(blank=True)
    opt = models.CharField(max_length=250, blank=True)
    solver_info_def = models.ForeignKey('SolverInfoDef', blank=True, null=True, on_delete=models.CASCADE)
    solution = models.ForeignKey(Solution, blank=True, null=True, on_delete=models.CASCADE)
    assignment = models.ForeignKey(Assignment, blank=True, null=True, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'solver_info'


class SolverInfoDef(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    name = models.CharField(max_length=100, blank=True)
    description = models.CharField(max_length=1000, blank=True)
    implementation = models.CharField(max_length=250, blank=True)

    class Meta:
        managed = False
        db_table = 'solver_info_def'


class SolverParameter(models.Model):
    uniqueid = models.DecimalField(max_digits=20, decimal_places=0, blank=True, null=True)
    value = models.CharField(max_length=2048, blank=True)
    solver_param_def = models.ForeignKey('SolverParameterDef', blank=True, null=True, on_delete=models.CASCADE)
    solution = models.ForeignKey(Solution, blank=True, null=True, on_delete=models.CASCADE)
    solver_predef_setting = models.ForeignKey('SolverPredefSetting', blank=True, null=True, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'solver_parameter'


class SolverParameterDef(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    name = models.CharField(max_length=100, blank=True)
    default_value = models.CharField(max_length=2048, blank=True)
    description = models.CharField(max_length=1000, blank=True)
    type = models.CharField(max_length=250, blank=True)
    ord = models.BigIntegerField(blank=True, null=True)
    visible = models.IntegerField(blank=True, null=True)
    solver_param_group = models.ForeignKey('SolverParameterGroup', blank=True, null=True, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'solver_parameter_def'


class SolverParameterGroup(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    name = models.CharField(max_length=100, blank=True)
    description = models.CharField(max_length=1000, blank=True)
    condition = models.CharField(max_length=250, blank=True)
    ord = models.BigIntegerField(blank=True, null=True)
    param_type = models.BigIntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'solver_parameter_group'


class SolverPredefSetting(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    name = models.CharField(max_length=100, blank=True)
    description = models.CharField(max_length=1000, blank=True)
    appearance = models.BigIntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'solver_predef_setting'


class SponsoringOrganization(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    name = models.CharField(max_length=100)
    email = models.CharField(max_length=200, blank=True)

    class Meta:
        managed = False
        db_table = 'sponsoring_organization'


class Staff(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    external_uid = models.CharField(max_length=40, blank=True)
    fname = models.CharField(max_length=100, blank=True)
    mname = models.CharField(max_length=100, blank=True)
    lname = models.CharField(max_length=100, blank=True)
    pos_code = models.CharField(max_length=20, blank=True)
    dept = models.CharField(max_length=50, blank=True)
    email = models.CharField(max_length=200, blank=True)
    pos_type = models.ForeignKey(PositionType, db_column='pos_type', blank=True, null=True, on_delete=models.CASCADE)
    acad_title = models.CharField(max_length=50, blank=True)

    class Meta:
        managed = False
        db_table = 'staff'


class StandardEventNote(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    reference = models.CharField(max_length=20, blank=True)
    note = models.CharField(max_length=1000, blank=True)
    discriminator = models.CharField(max_length=10, blank=True)
    session = models.ForeignKey(Sessions, blank=True, null=True, on_delete=models.CASCADE)
    department = models.ForeignKey(Department, blank=True, null=True, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'standard_event_note'


class Student(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    external_uid = models.CharField(max_length=40, blank=True)
    first_name = models.CharField(max_length=100, blank=True)
    middle_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    email = models.CharField(max_length=200, blank=True)
    free_time_cat = models.BigIntegerField(blank=True, null=True)
    schedule_preference = models.BigIntegerField(blank=True, null=True)
    session = models.ForeignKey(Sessions, blank=True, null=True, on_delete=models.CASCADE)
    sect_status = models.ForeignKey(SectioningStatus, db_column='sect_status', blank=True, null=True, on_delete=models.CASCADE)
    schedule_emailed = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'student'


class StudentAcadArea(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    student = models.ForeignKey(Student, blank=True, null=True, on_delete=models.CASCADE)
    acad_clasf = models.ForeignKey(AcademicClassification, blank=True, null=True, on_delete=models.CASCADE)
    acad_area = models.ForeignKey(AcademicArea, blank=True, null=True, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'student_acad_area'


class StudentAccomodation(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    name = models.CharField(max_length=50, blank=True)
    abbreviation = models.CharField(max_length=20, blank=True)
    external_uid = models.CharField(max_length=40, blank=True)
    session = models.ForeignKey(Sessions, blank=True, null=True, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'student_accomodation'


class StudentClassEnrl(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    student = models.ForeignKey(Student, blank=True, null=True, on_delete=models.CASCADE)
    course_request = models.ForeignKey(CourseRequest, blank=True, null=True, on_delete=models.CASCADE)
    class_field = models.ForeignKey(Class, db_column='class_id', blank=True, null=True, on_delete=models.CASCADE)  # Field renamed because it was a Python reserved word.
    timestamp = models.DateTimeField(blank=True, null=True)
    course_offering = models.ForeignKey(CourseOffering, blank=True, null=True, on_delete=models.CASCADE)
    approved_date = models.DateTimeField(blank=True, null=True)
    approved_by = models.CharField(max_length=40, blank=True)
    changed_by = models.CharField(max_length=40, blank=True)

    class Meta:
        managed = False
        db_table = 'student_class_enrl'


class StudentEnrl(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    student_id = models.DecimalField(max_digits=20, decimal_places=0, blank=True, null=True)
    solution = models.ForeignKey(Solution, blank=True, null=True, on_delete=models.CASCADE)
    class_field = models.ForeignKey(Class, db_column='class_id', blank=True, null=True, on_delete=models.CASCADE)  # Field renamed because it was a Python reserved word.
    last_modified_time = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'student_enrl'


class StudentEnrlMsg(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    message = models.CharField(max_length=255, blank=True)
    msg_level = models.BigIntegerField(blank=True, null=True)
    type = models.BigIntegerField(blank=True, null=True)
    timestamp = models.DateTimeField(blank=True, null=True)
    course_demand = models.ForeignKey(CourseDemand, blank=True, null=True, on_delete=models.CASCADE)
    ord = models.BigIntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'student_enrl_msg'


class StudentGroup(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    session = models.ForeignKey(Sessions, blank=True, null=True, on_delete=models.CASCADE)
    group_abbreviation = models.CharField(max_length=30, blank=True)
    group_name = models.CharField(max_length=90, blank=True)
    external_uid = models.CharField(max_length=40, blank=True)

    class Meta:
        managed = False
        db_table = 'student_group'


class StudentMajor(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    major = models.ForeignKey(PosMajor, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'student_major'


class StudentMinor(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    minor = models.ForeignKey(PosMinor, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'student_minor'


class StudentSectHist(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    student = models.ForeignKey(Student, blank=True, null=True, on_delete=models.CASCADE)
    data = models.TextField(blank=True)
    type = models.BigIntegerField(blank=True, null=True)
    timestamp = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'student_sect_hist'


class StudentToAcomodation(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    accomodation = models.ForeignKey(StudentAccomodation, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'student_to_acomodation'


class StudentToGroup(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    group = models.ForeignKey(StudentGroup, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'student_to_group'


class SubjectArea(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    session_id = models.DecimalField(max_digits=20, decimal_places=0, blank=True, null=True)
    subject_area_abbreviation = models.CharField(max_length=10, blank=True)
    long_title = models.CharField(max_length=100, blank=True)
    department_uniqueid = models.ForeignKey(Department, db_column='department_uniqueid', blank=True, null=True, on_delete=models.CASCADE)
    external_uid = models.CharField(max_length=40, blank=True)
    last_modified_time = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'subject_area'


class TimePattern(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    name = models.CharField(max_length=50, blank=True)
    mins_pmt = models.BigIntegerField(blank=True, null=True)
    slots_pmt = models.BigIntegerField(blank=True, null=True)
    nr_mtgs = models.BigIntegerField(blank=True, null=True)
    visible = models.IntegerField(blank=True, null=True)
    type = models.BigIntegerField(blank=True, null=True)
    break_time = models.IntegerField(blank=True, null=True)
    session = models.ForeignKey(Sessions, blank=True, null=True, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'time_pattern'


class TimePatternDays(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    day_code = models.BigIntegerField(blank=True, null=True)
    time_pattern = models.ForeignKey(TimePattern, blank=True, null=True, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'time_pattern_days'


class TimePatternDept(models.Model):
    dept = models.ForeignKey(Department, on_delete=models.CASCADE)
    pattern = models.ForeignKey(TimePattern, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'time_pattern_dept'


class TimePatternTime(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    start_slot = models.BigIntegerField(blank=True, null=True)
    time_pattern = models.ForeignKey(TimePattern, blank=True, null=True, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'time_pattern_time'


class TimePref(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    owner_id = models.DecimalField(max_digits=20, decimal_places=0, blank=True, null=True)
    pref_level = models.ForeignKey(PreferenceLevel, blank=True, null=True, on_delete=models.CASCADE)
    preference = models.CharField(max_length=2048, blank=True)
    time_pattern = models.ForeignKey(TimePattern, blank=True, null=True, on_delete=models.CASCADE)
    last_modified_time = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'time_pref'


class TimetableManager(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    external_uid = models.CharField(unique=True, max_length=40, blank=True)
    first_name = models.CharField(max_length=100, blank=True)
    middle_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    email_address = models.CharField(max_length=200, blank=True)
    last_modified_time = models.DateTimeField(blank=True, null=True)
    acad_title = models.CharField(max_length=50, blank=True)

    class Meta:
        managed = False
        db_table = 'timetable_manager'


class TmtblMgrToRoles(models.Model):
    manager = models.ForeignKey(TimetableManager, blank=True, null=True, on_delete=models.CASCADE)
    role = models.ForeignKey(Roles, blank=True, null=True, on_delete=models.CASCADE)
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    is_primary = models.IntegerField(blank=True, null=True)
    receive_emails = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'tmtbl_mgr_to_roles'


class TravelTime(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    session = models.ForeignKey(Sessions, on_delete=models.CASCADE)
    loc1_id = models.DecimalField(max_digits=20, decimal_places=0)
    loc2_id = models.DecimalField(max_digits=20, decimal_places=0)
    distance = models.DecimalField(max_digits=10, decimal_places=0)

    class Meta:
        managed = False
        db_table = 'travel_time'


class UserData(models.Model):
    external_uid = models.CharField(max_length=12)
    name = models.CharField(max_length=100)
    value = models.CharField(max_length=4000, blank=True)

    class Meta:
        managed = False
        db_table = 'user_data'


class Users(models.Model):
    username = models.CharField(primary_key=True, max_length=15)
    password = models.CharField(max_length=25, blank=True)
    external_uid = models.CharField(max_length=40, blank=True)

    class Meta:
        managed = False
        db_table = 'users'


class Waitlist(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    student = models.ForeignKey(Student, blank=True, null=True, on_delete=models.CASCADE)
    course_offering = models.ForeignKey(CourseOffering, blank=True, null=True, on_delete=models.CASCADE)
    type = models.BigIntegerField(blank=True, null=True)
    timestamp = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'waitlist'


class Xconflict(models.Model):
    uniqueid = models.DecimalField(primary_key=True, max_digits=20, decimal_places=0)
    conflict_type = models.BigIntegerField()
    distance = models.FloatField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'xconflict'


class XconflictExam(models.Model):
    conflict = models.ForeignKey(Xconflict, on_delete=models.CASCADE)
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'xconflict_exam'


class XconflictInstructor(models.Model):
    conflict = models.ForeignKey(Xconflict, on_delete=models.CASCADE)
    instructor = models.ForeignKey(DepartmentalInstructor, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'xconflict_instructor'


class XconflictStudent(models.Model):
    conflict = models.ForeignKey(Xconflict, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = 'xconflict_student'
