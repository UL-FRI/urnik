import sys
from datetime import datetime, timedelta

import itertools
from typing import List

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.conf import settings

from exchange.controllers import (
    get_allocations_for_subject,
    get_available_exchanges,
    get_student_exchanges,
    get_teacher_subject_list,
    get_student_subject_list,
    teacher_teaches_subject,
    parse_student_from_ambiguous_identifier,
    get_current_student_subject_allocation,
    process_exchange_request_matches,
    get_allocation_student_group,
    process_new_exchange_request,
    number_of_students_in_allocation,
    get_subject_exchanges,
    get_student_subject_other_allocations,
    is_exchange_acceptable,
)
from exchange.models import (
    Exchange,
    FormProcessingError,
    ExchangeType,
    SubjectPreference,
)
from friprosveta.models import Student, Subject, Timetable, Teacher, Activity
from timetable.models import Allocation


class BaseTestCase(TestCase):
    """
    The general testing configuration is slightly unusual due to the fact that there were zero tests before the
    Exchange component. We use a copy of the production database and define several variables here that change
    through the lifetime of this application. This has several advantages:
      - no need to manually create a testing-only database or mocks
      - testing in production without any drawbacks
      - handle real-world data, with no chance of making a mistake when creating testing data
    but also some disadvantages:
      - increased complexity due to the unconventional approach
      - performance, because we use the complete database
      - needs changes if the schema changes
      - the tests run for quite a while due to all the data that needs to be imported

    All constants are (should be) documented with their raisons d'etre, assumptions and potentials for change.

    Exporting the database can be done with:
    $ python manage.py dumpdata --verbosity 1 -o <filename> \
        --exclude sessions.Session --natural-primary --natural-foreign
    (--natural-primary and --natural-foreign need to be specified for integrity reasons, see the dumpdata docs)
    """

    PERSISTENT_FIXTURE = (
        "../test_fixtures/urnik-2017-11-09-00-00-02-shortnamerename.json"
    )
    """A django dump of the whole database. Must NOT be inside `cls.fixtures` because we use a different strategy."""

    TESTING_TIMETABLE_SLUG = "fri-2017_2018-zimski"
    """Perform tests within this scope.
    
    Assumptions:
      - no exchanges exist (existed before the exchange era)
      - will not change any dependents in the future
    """

    KNOWN_STUDENT = ("ss3055@student.uni-lj.si", "63120284")
    """A student we know the email -> enrollment number of."""

    #                SP,      RSO,     Mat2
    SUBJECT_CODES = ["63255", "63541", "63506"]
    """Subject codes for subjects. Mapped into self.subjects.
    
    Assumptions:
      - students[0] is enrolled into [0]
      - there is only one allocation for lectures of [0]
      - each subjects has at least 2 allocations in `TESTING_TIMETABLE_SLUG`
      - [1] has at least three lab cycles
      - [2] has at least 2 lab cycles
      - all lab cycles for [0, 1] are at or above capacity
    """

    #                             SS,         MO,         JM,         DG,         NA
    STUDENT_ENROLLMENT_NUMBERS = [
        "63120284",
        "63120294",
        "63130144",
        "63120183",
        "63120220",
    ]
    """Enrollment numbers for students. Mapped into self.students.
    
    Assumptions:
      - each has n > 1 subjects in `TESTING_TIMETABLE_SLUG`
      - [0] is enrolled into subjects[0, 1]
      - [1] is enrolled into subjects[0]
      - [2] is enrolled into subjects[1]
      - [3] is enrolled into subjects[1, 2]
      - [4] is enrolled into subjects[1]
      - [0] and [1] do not attend the same lab cycle in subjects[0]
      - [2] and [3] do not attend the same lab cycle in subjects[1]
      - the lab cycle [1] attends in subjects[0] must be exactly at 100 % capacity
    """

    #                Lavbič,   Jurič
    TEACHER_CODES = ["630827", "630006"]
    """Teacher codes for teachers
    
    Assumptions:
      - [0] teaches subjects[0]
      - [1] has at least two subjects
    """

    def __init__(self, methodName="runTest"):
        # short-circuit if this would run too long
        if not self._has_keepdb():
            print(
                "Tests must be run with --keepdb to preserve the test database between runs."
            )
            print("The database is only loaded on the first run.")
            raise Exception("Running tests with --keepdb is mandatory.")

        if not self._has_serialize_false():
            print(
                "Tests must be run with DATABASES[dbname]['TEST']['SERIALIZE'] = False in settings."
            )
            print(
                "Otherwise, the tests take several tens of orders of magnitude longer."
            )
            print("See: https://docs.djangoproject.com/en/2.0/ref/settings/#serialize")
            raise Exception(
                "Running tests with DATABASES->TEST->SERIALIZE is mandatory."
            )
        super().__init__(methodName)

    @classmethod
    def _has_keepdb(cls):
        """Running tests with --keepdb is required to preserve the database between runs."""
        return "--keepdb" in [a.lower() for a in sys.argv]

    @classmethod
    def _has_serialize_false(cls):
        return any(settings.DATABASES) and all(
            db.get("TEST", {}).get("SERIALIZE", True) == False
            for db in settings.DATABASES.values()
        )

    @classmethod
    def _has_data(cls):
        """Determine whether the database is a skeleton or if it actually contains any data."""
        return User.objects.count() > 0

    @classmethod
    def setUpClass(cls):
        # custom logic for preserving the long-loading test fixtures in the database
        if not cls._has_data():
            print("No data for testing, setting up...")
            # logic from django.TestCase.setUpClass
            for db_name in cls._databases_names(include_mirrors=False):
                print("Inserting into {}...".format(db_name))
                try:
                    call_command(
                        "loaddata",
                        cls.PERSISTENT_FIXTURE,
                        **{
                            "verbosity": 0,
                            "commit": False,
                            "database": db_name,
                        }
                    )
                except Exception:
                    cls._rollback_atomics(cls.cls_atomics)
                    raise

        # needs to be after everything because this sets up transactions which are then rolled back
        # also, because a super call calls setUpTestData, which depends on these imports
        super().setUpClass()

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        # transformation from the test input data
        cls.timetable = Timetable.objects.get(slug=BaseTestCase.TESTING_TIMETABLE_SLUG)
        cls.known_student_user = User.objects.get(email=BaseTestCase.KNOWN_STUDENT[0])
        cls.known_student_student = Student.objects.get(
            studentId=BaseTestCase.KNOWN_STUDENT[1]
        )
        cls.students = [
            Student.objects.get(studentId=studentId)
            for studentId in BaseTestCase.STUDENT_ENROLLMENT_NUMBERS
        ]
        cls.subjects = [
            Subject.objects.get(code=code) for code in BaseTestCase.SUBJECT_CODES
        ]
        cls.teachers = [
            Teacher.objects.get(code=code) for code in BaseTestCase.TEACHER_CODES
        ]

        # additional processing based on the input data
        cls.subjects_lab_allocations = [
            get_allocations_for_subject(cls.timetable, s, ["LAB", "LV", "AV"])
            for s in cls.subjects
        ]

        assert all(
            len(sals) >= 2 for sals in cls.subjects_lab_allocations
        ), "Test constraint: minimum 2 allocations per subject."


class ExchangeUtilsTestCase(BaseTestCase):
    def test_get_student_from_user_exists(self):
        result = Student.from_user(self.known_student_user)
        self.assertEqual(self.known_student_student, result)

    def test_get_student_from_user_does_not_exist(self):
        admin_user = User.objects.get(username="urnik")
        with self.assertRaises(Student.DoesNotExist):
            Student.from_user(admin_user)

    def test_get_teacher_subject_list(self):
        subjects = get_teacher_subject_list(self.timetable, self.teachers[1])
        self.assertEqual(len(subjects), 4)
        for s in subjects:
            self.assertIn(self.teachers[1], s.teachers(self.timetable))

    def test_get_teacher_subject_list_null_timetable(self):
        with self.assertRaises(ValueError):
            get_teacher_subject_list(None, self.teachers[0])

    def test_get_teacher_subject_list_null_teacher(self):
        with self.assertRaises(ValueError):
            get_teacher_subject_list(self.timetable, None)

    def test_get_student_subject_list(self):
        subjects = get_student_subject_list(self.timetable, self.students[0])
        for s in subjects:
            self.assertIn(self.students[0], s.students.all())

    def test_teacher_teaches_subject_yes(self):
        self.assertTrue(
            teacher_teaches_subject(self.timetable, self.teachers[0], self.subjects[0])
        )

    def test_teacher_teaches_subject_no(self):
        self.assertFalse(
            teacher_teaches_subject(self.timetable, self.teachers[1], self.subjects[0])
        )

    def test_get_allocations_for_subject(self):
        allocations_all = get_allocations_for_subject(self.timetable, self.subjects[0])
        allocations_labs = get_allocations_for_subject(
            self.timetable, self.subjects[0], activity_types=["LAB", "LV", "AV"]
        )
        allocations_lectures = get_allocations_for_subject(
            self.timetable, self.subjects[0], activity_types=["P"]
        )
        self.assertGreater(len(allocations_all), 1)
        self.assertGreater(len(allocations_labs), 0)
        self.assertEqual(1, len(allocations_lectures))
        self.assertEqual(
            len(allocations_all), len(allocations_labs) + len(allocations_lectures)
        )

    def test_get_allocations_for_subject_null_timetable(self):
        with self.assertRaises(ValueError):
            get_allocations_for_subject(
                None, self.subjects[0], activity_types=["LAB", "LV", "AV"]
            )

    def test_get_allocations_for_subject_null_subject(self):
        with self.assertRaises(ValueError):
            get_allocations_for_subject(
                self.timetable, None, activity_types=["LAB", "LV", "AV"]
            )

    def test_parse_student_from_ambiguous_identifier_email_id_equal(self):
        student_mail = parse_student_from_ambiguous_identifier(self.KNOWN_STUDENT[0])
        student_id = parse_student_from_ambiguous_identifier(self.KNOWN_STUDENT[1])
        self.assertEqual(student_mail, student_id)

    def test_parse_student_from_ambiguous_identifier_email(self):
        self.assertEqual(
            self.students[0],
            parse_student_from_ambiguous_identifier("ss3055@student.uni-lj.si"),
        )

    def test_parse_student_from_ambiguous_identifier_id(self):
        self.assertEqual(
            self.students[0], parse_student_from_ambiguous_identifier("63120284")
        )

    def test_parse_student_from_ambiguous_identifier_unknown(self):
        with self.assertRaises(FormProcessingError):
            parse_student_from_ambiguous_identifier("unknown identifier")

    def test_get_current_student_subject_allocation(self):
        lab = get_current_student_subject_allocation(
            self.timetable,
            self.students[0],
            self.subjects[0],
            activity_types=["LAB", "LV", "AV"],
        )
        lec = get_current_student_subject_allocation(
            self.timetable, self.students[0], self.subjects[0], activity_types=["P"]
        )
        self.assertEqual(self.timetable, lab.timetable)
        self.assertEqual(self.timetable, lec.timetable)
        self.assertEqual(
            self.subjects[0],
            Activity.from_timetable_activity(lab.activityRealization.activity).subject,
        )
        self.assertEqual(
            self.subjects[0],
            Activity.from_timetable_activity(lec.activityRealization.activity).subject,
        )

    def test_get_current_student_subject_allocation_null_timetable(self):
        with self.assertRaises(ValueError):
            get_current_student_subject_allocation(
                None, self.students[0], self.subjects[0], ["LAB", "LV", "AV"]
            )

    def test_get_current_student_subject_allocation_null_student(self):
        with self.assertRaises(ValueError):
            get_current_student_subject_allocation(
                self.timetable, None, self.subjects[0], ["LAB", "LV", "AV"]
            )

    def test_get_current_student_subject_allocation_null_subject(self):
        with self.assertRaises(ValueError):
            get_current_student_subject_allocation(
                self.timetable, self.students[0], None, ["LAB", "LV", "AV"]
            )

    def test_get_student_subject_other_allocations(self):
        labs = get_student_subject_other_allocations(
            self.timetable,
            self.students[0],
            self.subjects[0],
            activity_types=["LAB", "LV", "AV"],
        )
        lecs = get_student_subject_other_allocations(
            self.timetable, self.students[0], self.subjects[0], activity_types=["P"]
        )
        self.assertEqual(5, len(labs))
        self.assertEqual(0, len(lecs))
        self.assertEqual(
            self.subjects[0],
            Activity.from_timetable_activity(
                labs[0].activityRealization.activity
            ).subject,
        )

    def test_get_student_subject_other_allocations_null_timetable(self):
        with self.assertRaises(ValueError):
            get_student_subject_other_allocations(
                None, self.students[0], self.subjects[0], ["LAB", "LV", "AV"]
            )

    def test_get_student_subject_other_allocations_null_student(self):
        with self.assertRaises(ValueError):
            get_student_subject_other_allocations(
                self.timetable, None, self.subjects[0], ["LAB", "LV", "AV"]
            )

    def test_get_student_subject_other_allocations_null_subject(self):
        with self.assertRaises(ValueError):
            get_student_subject_other_allocations(
                self.timetable, self.students[0], None, ["LAB", "LV", "AV"]
            )

    def test_get_allocation_student_group_exists(self):
        # quite a roundabout way, but reliable I guess
        self.assertIsNotNone(
            get_allocation_student_group(
                get_current_student_subject_allocation(
                    self.timetable,
                    self.students[0],
                    self.subjects[0],
                    ["LAB", "LV", "AV"],
                ),
                self.students[0],
            )
        )

    def test_get_allocation_student_group_does_not_exist(self):
        self.assertIsNone(
            get_allocation_student_group(
                get_current_student_subject_allocation(
                    self.timetable,
                    self.students[0],
                    self.subjects[0],
                    ["LAB", "LV", "AV"],
                ),
                self.students[4],
            )
        )

    def test_number_of_students_in_allocation(self):
        num = number_of_students_in_allocation(
            get_current_student_subject_allocation(
                self.timetable, self.students[0], self.subjects[0], ["LAB", "LV", "AV"]
            )
        )
        # change this as needed
        self.assertEqual(20, num)

    def test_number_of_students_in_allocation_null_allocation(self):
        with self.assertRaises(ValueError):
            number_of_students_in_allocation(None)


class ExchangeTestCase(BaseTestCase):
    @classmethod
    def setUpTestData(cls):
        """IMPORTANT: Do not delete any objects, because they are not automatically recovered."""
        super().setUpTestData()

        lv = ["LAB", "LV", "AV"]
        cls.exchanges: List[Exchange] = []

        # ensure datetimes are generated distinctly and logically
        def get_datetime_iterator():
            base_datetime = datetime.utcnow() - timedelta(hours=1)
            iteration = 0
            while True:
                yield base_datetime + timedelta(seconds=iteration)
                iteration += 1

        datetime_iterator = get_datetime_iterator()

        # 0: initiator, by students[0], subjects[0], to students[1]'s allocation
        cls.exchanges.append(
            Exchange.objects.create(
                allocation_from=get_current_student_subject_allocation(
                    cls.timetable, cls.students[0], cls.subjects[0], lv
                ),
                allocation_to=get_current_student_subject_allocation(
                    cls.timetable, cls.students[1], cls.subjects[0], lv
                ),
                initiator_student=cls.students[0],
                requested_finalizer_student=None,
                date_created=next(datetime_iterator),
            )
        )

        # 1: finaliser, by students[1], subjects[0], counterpart to 0)
        cls.exchanges.append(
            Exchange.objects.create(
                allocation_from=get_current_student_subject_allocation(
                    cls.timetable, cls.students[1], cls.subjects[0], lv
                ),
                allocation_to=get_current_student_subject_allocation(
                    cls.timetable, cls.students[0], cls.subjects[0], lv
                ),
                initiator_student=cls.students[1],
                requested_finalizer_student=None,
                date_created=next(datetime_iterator),
            )
        )

        # 2: initiator, by students[0], subjects[1], has no match (when a correct destination allocation is selected)
        cls.exchanges.append(
            Exchange.objects.create(
                allocation_from=get_current_student_subject_allocation(
                    cls.timetable, cls.students[0], cls.subjects[1], lv
                ),
                allocation_to=cls._get_student_subject_allocation_inverse(
                    cls.timetable, cls.students[0], cls.subjects[1], lv, skip=2
                ),
                initiator_student=cls.students[0],
                requested_finalizer_student=None,
                date_created=next(datetime_iterator),
            )
        )

        # 3: initiator, by students[0], subjects[1], different destination lab cycle than 2)
        cls.exchanges.append(
            Exchange.objects.create(
                allocation_from=get_current_student_subject_allocation(
                    cls.timetable, cls.students[0], cls.subjects[1], lv
                ),
                allocation_to=cls._get_student_subject_allocation_inverse(
                    cls.timetable, cls.students[0], cls.subjects[1], lv, skip=1
                ),
                initiator_student=cls.students[0],
                requested_finalizer_student=None,
                date_created=next(datetime_iterator),
            )
        )

        # 4: finalizer, by teachers[1], subjects[1], matches above (teacher offer)
        cls.exchanges.append(
            Exchange.objects.create(
                allocation_from=cls._get_student_subject_allocation_inverse(
                    cls.timetable, cls.students[0], cls.subjects[1], lv, skip=1
                ),
                allocation_to=get_current_student_subject_allocation(
                    cls.timetable, cls.students[0], cls.subjects[1], lv
                ),
                initiator_student=None,
                requested_finalizer_student=cls.students[0],
                date_created=next(datetime_iterator),
            )
        )

        # 5: initiator, by students[2], subjects[1], same destination than 3), but chronologically after so lower prio
        cls.exchanges.append(
            Exchange.objects.create(
                allocation_from=get_current_student_subject_allocation(
                    cls.timetable, cls.students[2], cls.subjects[1], lv
                ),
                allocation_to=cls._get_student_subject_allocation_inverse(
                    cls.timetable, cls.students[0], cls.subjects[1], lv, skip=1
                ),
                initiator_student=cls.students[2],
                requested_finalizer_student=None,
                date_created=next(datetime_iterator),
            )
        )

        # 6: initiator, by students[2], subjects[1], specified students[3], chronologically after 2, 3, 4, 5
        cls.exchanges.append(
            Exchange.objects.create(
                allocation_from=get_current_student_subject_allocation(
                    cls.timetable, cls.students[2], cls.subjects[1], lv
                ),
                allocation_to=get_current_student_subject_allocation(
                    cls.timetable, cls.students[3], cls.subjects[1], lv
                ),
                initiator_student=cls.students[2],
                requested_finalizer_student=cls.students[3],
                date_created=next(datetime_iterator),
            )
        )

        # 7: finalizer, by students[3], subjects[1], specified students[2], chronologically after 2, 3, 4, 5, 6
        cls.exchanges.append(
            Exchange.objects.create(
                allocation_from=get_current_student_subject_allocation(
                    cls.timetable, cls.students[3], cls.subjects[1], lv
                ),
                allocation_to=get_current_student_subject_allocation(
                    cls.timetable, cls.students[2], cls.subjects[1], lv
                ),
                initiator_student=cls.students[3],
                requested_finalizer_student=cls.students[2],
                date_created=next(datetime_iterator),
            )
        )

        # 8: initiator, free change, subjects[0], same as 0), chronologically before (test priority of student-initiated
        #    exchanges, which override free changes, should never be finalised
        cls.exchanges.append(
            Exchange.objects.create(
                allocation_from=get_current_student_subject_allocation(
                    cls.timetable, cls.students[0], cls.subjects[0], lv
                ),
                allocation_to=None,
                initiator_student=None,
                requested_finalizer_student=None,
                date_created=cls.exchanges[0].date_created - timedelta(days=1),
            )
        )

        # 9: initiator, free change, subjects[1], should match 10), does not create an inverse free change (no room)
        cls.exchanges.append(
            Exchange.objects.create(
                allocation_from=cls._get_student_subject_allocation_inverse(
                    cls.timetable, cls.students[4], cls.subjects[1], lv, skip=0
                ),
                allocation_to=None,
                initiator_student=None,
                requested_finalizer_student=None,
                date_created=next(datetime_iterator),
            )
        )

        # 10: finalizer, by students[4], subjects[1], matches 9)
        cls.exchanges.append(
            Exchange.objects.create(
                allocation_from=get_current_student_subject_allocation(
                    cls.timetable, cls.students[4], cls.subjects[1], lv
                ),
                allocation_to=cls._get_student_subject_allocation_inverse(
                    cls.timetable, cls.students[4], cls.subjects[1], lv, skip=0
                ),
                initiator_student=cls.students[4],
                requested_finalizer_student=None,
                date_created=next(datetime_iterator),
            )
        )

        # 11: initiator, free change, subjects[0], should match 12), from an exchange other than that of students[0]
        #     for this subject (so we don't collide with above), should create an inverse free change
        cls.exchanges.append(
            Exchange.objects.create(
                allocation_from=cls._get_student_subject_allocation_inverse(
                    cls.timetable, cls.students[0], cls.subjects[0], lv, skip=0
                ),
                allocation_to=None,
                initiator_student=None,
                requested_finalizer_student=None,
                date_created=next(datetime_iterator),
            )
        )

        # 12: finalizer, by students[1], subjects[0], matches 11), to an exchange other than that of students[0]
        #     for this subject (so we don't collide with above)
        cls.exchanges.append(
            Exchange.objects.create(
                allocation_from=get_current_student_subject_allocation(
                    cls.timetable, cls.students[1], cls.subjects[0], lv
                ),
                allocation_to=cls._get_student_subject_allocation_inverse(
                    cls.timetable, cls.students[0], cls.subjects[0], lv, skip=0
                ),
                initiator_student=cls.students[1],
                requested_finalizer_student=None,
                date_created=next(datetime_iterator),
            )
        )

        helper_student_13_14 = (
            Student.objects.filter(
                groups__in=list(
                    get_current_student_subject_allocation(
                        cls.timetable, cls.students[3], cls.subjects[2], lv
                    ).groups.all()
                )
            )
            .exclude(id__in=[s.id for s in cls.students])
            .first()
        )

        # 13: initiator, teacher offer, subjects[2], intentionally does not match 14), to a different student
        #     but one that attends the same allocation as students[3]
        cls.exchanges.append(
            Exchange.objects.create(
                allocation_from=cls._get_student_subject_allocation_inverse(
                    cls.timetable, helper_student_13_14, cls.subjects[2], lv
                ),
                allocation_to=get_current_student_subject_allocation(
                    cls.timetable, cls.students[3], cls.subjects[2], lv
                ),
                initiator_student=None,
                requested_finalizer_student=helper_student_13_14,
                date_created=next(datetime_iterator),
            )
        )

        # 14: finalizer, by students[3], subjects[2], does not match 13)
        cls.exchanges.append(
            Exchange.objects.create(
                allocation_from=get_current_student_subject_allocation(
                    cls.timetable, cls.students[3], cls.subjects[2], lv
                ),
                allocation_to=cls._get_student_subject_allocation_inverse(
                    cls.timetable, helper_student_13_14, cls.subjects[2], lv
                ),
                initiator_student=cls.students[3],
                requested_finalizer_student=None,
                date_created=next(datetime_iterator),
            )
        )

    def setUp(self):
        super().setUp()
        # the database state isn't cached between tests, but the objects are
        # we reload all objects just in case to maintain the correct state in cases where a test changed the object
        for e in self.exchanges:
            e.refresh_from_db()

    def tearDown(self):
        super().tearDown()
        # general post-conditions

        # priority of student-initiated exchanges, which override free changes, should never be finalised
        self.assertFalse(self.exchanges[8].is_finalized())

    @classmethod
    def _get_student_subject_allocation_inverse(
        cls, timetable, student, subject, activity_types, skip=0
    ):
        """Helper: Get an allocation other than the student's current allocation. The ordering is deterministic.

        Args:
            timetable (Timetable): The requested timetable scope.
            student (Student): The student to get the allocation for.
            subject (Subject): The subject of which to get the allocation for.
            activity_types (list[str]): Limit the types of activities (e.g. labs, lectures).
            skip (int): The number of allocations to skip (useful for selecting multiple non-matching allocations).

        Returns:
            (Allocation): An allocation different from the student's current allocation.
        """
        allocations = get_student_subject_other_allocations(
            timetable, student, subject, activity_types
        )
        return list(allocations.order_by("id"))[skip]

    def _finalized_exchange_pair_checks(self, exchange_left, exchange_right):
        """Perform common checks for the consistency of two completed exchanges."""
        exchange_left.refresh_from_db()
        exchange_right.refresh_from_db()

        self.assertTrue(exchange_left.is_finalized())
        self.assertTrue(exchange_right.is_finalized())
        self.assertEqual(exchange_left.finalizer_exchange, exchange_right)
        self.assertEqual(exchange_right.finalized_exchange, exchange_left)
        self.assertIsNone(exchange_left.get_match())
        self.assertIsNone(exchange_right.get_match())

        # check if student allocations have been exchanged as requested
        # but only when we actually have student objects available (not for FREE_CHANGE, TEACHER_OFFER)
        if exchange_left.initiator_student is not None:
            self.assertEqual(
                exchange_right.allocation_from,
                get_current_student_subject_allocation(
                    self.timetable,
                    exchange_left.initiator_student,
                    Activity.from_timetable_activity(
                        exchange_right.allocation_from.activityRealization.activity
                    ).subject,
                    activity_types=["LAB", "LV", "AV"],
                ),
            )

        if exchange_right.initiator_student is not None:
            self.assertEqual(
                exchange_left.allocation_from,
                get_current_student_subject_allocation(
                    self.timetable,
                    exchange_right.initiator_student,
                    Activity.from_timetable_activity(
                        exchange_left.allocation_from.activityRealization.activity
                    ).subject,
                    activity_types=["LAB", "LV", "AV"],
                ),
            )

    def _perform_exchange_pair_success_test(
        self, exchange_left, exchange_right, exchange_left_type, exchange_right_type
    ):
        """Perform an exchange and the verification procedures for two exchanges that match and process successfully."""
        match = exchange_right.get_match()
        self.assertEqual(exchange_left, match)

        self.assertTrue(exchange_right.matches(match))
        self.assertTrue(match.matches(exchange_right))

        if exchange_left.initiator_student:
            self.assertTrue(
                is_exchange_acceptable(exchange_right, exchange_left.initiator_student)
            )
        if exchange_right.initiator_student:
            self.assertTrue(
                is_exchange_acceptable(exchange_left, exchange_right.initiator_student)
            )

        # pre-check types
        self.assertEqual(exchange_left.get_type(), exchange_left_type)
        self.assertEqual(exchange_right.get_type(), exchange_right_type)

        globally_processed_exchanges_before = sum(
            1 for e in Exchange.objects.all() if e.is_finalized()
        )

        process_exchange_request_matches(match, exchange_right)
        self._finalized_exchange_pair_checks(exchange_left, exchange_right)

        # post-check types
        self.assertEqual(exchange_left.get_type(), exchange_left_type)
        self.assertEqual(exchange_right.get_type(), exchange_right_type)

        globally_processed_exchanges_after = sum(
            1 for e in Exchange.objects.all() if e.is_finalized()
        )
        self.assertEqual(
            globally_processed_exchanges_before + 2, globally_processed_exchanges_after
        )

    def _perform_exchange_pair_success_test_endtoend(
        self,
        exchange_left,
        exchange_right,
        exchange_left_type,
        exchange_right_type,
        additional_processed_exchanges=0,
    ):
        """Same as the other one, but uses process_process_new_exchange_request for end-to-end testing."""
        globally_processed_exchanges_before = sum(
            1 for e in Exchange.objects.all() if e.is_finalized()
        )

        if exchange_left.initiator_student:
            self.assertTrue(
                is_exchange_acceptable(exchange_right, exchange_left.initiator_student)
            )
        if exchange_right.initiator_student:
            self.assertTrue(
                is_exchange_acceptable(exchange_left, exchange_right.initiator_student)
            )

        params = self._cancel_exchange_get_params(exchange_right)
        any_processed = process_new_exchange_request(**params)
        self.assertTrue(any_processed)

        # pre-check types
        self.assertEqual(exchange_left.get_type(), exchange_left_type)

        new_exchange = Exchange.objects.filter(
            allocation_from=exchange_right.allocation_from,
            allocation_to=exchange_right.allocation_to,
            initiator_student=exchange_right.initiator_student,
            date_finalized__isnull=False,
        ).first()

        self._finalized_exchange_pair_checks(exchange_left, new_exchange)

        # post-check types
        self.assertEqual(exchange_left.get_type(), exchange_left_type)
        self.assertEqual(new_exchange.get_type(), exchange_right_type)

        globally_processed_exchanges_after = sum(
            1 for e in Exchange.objects.all() if e.is_finalized()
        )
        self.assertEqual(
            globally_processed_exchanges_before + 2 + additional_processed_exchanges,
            globally_processed_exchanges_after,
        )

    def _perform_no_matches_endtoend_test(self, exchange, exchange_type):
        self.assertEqual(exchange.get_type(), exchange_type)

        exchanges_before = Exchange.objects.count()
        globally_processed_exchanges_before = sum(
            1 for e in Exchange.objects.all() if e.is_finalized()
        )

        params = self._cancel_exchange_get_params(exchange)
        any_processed = process_new_exchange_request(**params)
        self.assertFalse(any_processed)

        exchanges_after = Exchange.objects.count()
        globally_processed_exchanges_after = sum(
            1 for e in Exchange.objects.all() if e.is_finalized()
        )
        self.assertEqual(
            globally_processed_exchanges_before, globally_processed_exchanges_after
        )
        self.assertEqual(exchanges_before + 1, exchanges_after)

    def _cancel_exchange_get_params(self, exchange: Exchange):
        """Cancel an exchange object and return its parameters for end-to-end testing."""
        result = dict(
            timetable=self.timetable,
            source_person=exchange.initiator_student,
            requested_student=exchange.requested_finalizer_student,
            subject_transfer_to_map={
                Activity.from_timetable_activity(
                    exchange.allocation_from.activityRealization.activity
                ).subject.id: exchange.allocation_to
            },
            force_allocation_from=exchange.allocation_from
            if exchange.initiator_student is None
            else None,
        )
        exchange.date_cancelled = datetime.utcnow()
        exchange.save()
        return result

    def test_get_available_exchanges(self):
        exchanges = get_available_exchanges(self.timetable, self.students[0])
        self.assertEqual(len(exchanges), 10)
        for e in exchanges:
            self.assertIn(
                Activity.from_timetable_activity(
                    e.allocation_from.activityRealization.activity
                ).subject,
                self.subjects,
            )

    def test_get_student_exchanges(self):
        student = self.students[0]
        exchanges = get_student_exchanges(self.timetable, student)
        self.assertEqual(len(exchanges), 4)
        for e in exchanges:
            self.assertTrue(
                e.initiator_student == student
                or e.requested_finalizer_student == student
            )

    def test_get_student_exchanges_null_timetable(self):
        with self.assertRaises(ValueError):
            get_student_exchanges(None, self.students[0])

    def test_get_student_exchanges_null_student(self):
        with self.assertRaises(ValueError):
            get_student_exchanges(self.timetable, None)

    def test_get_subject_exchanges(self):
        exchanges = get_subject_exchanges(self.timetable, self.subjects[0])

        self.assertIn(self.exchanges[0], exchanges)
        self.assertIn(self.exchanges[1], exchanges)
        self.assertIn(self.exchanges[8], exchanges)
        self.assertIn(self.exchanges[11], exchanges)
        self.assertIn(self.exchanges[12], exchanges)
        self.assertEqual(5, len(exchanges))

    def test_get_subject_exchanges_null_timetable(self):
        with self.assertRaises(ValueError):
            get_subject_exchanges(None, self.subjects[0])

    def test_get_subject_exchanges_null_subject(self):
        with self.assertRaises(ValueError):
            get_subject_exchanges(self.timetable, None)

    def test_is_exchange_acceptable_null_exchange(self):
        with self.assertRaises(ValueError):
            is_exchange_acceptable(None, self.students[0])

    def test_is_exchange_acceptable_null_student(self):
        with self.assertRaises(ValueError):
            is_exchange_acceptable(self.exchanges[0], None)

    def test_no_self_matches(self):
        for ex in self.exchanges:
            self.assertFalse(ex.matches(ex))

    def test_request_offer_regular(self):
        self._perform_exchange_pair_success_test(
            self.exchanges[0],
            self.exchanges[1],
            ExchangeType.REQUEST_OFFER,
            ExchangeType.REQUEST_OFFER,
        )

    def test_request_offer_regular_inverse(self):
        self._perform_exchange_pair_success_test(
            self.exchanges[1],
            self.exchanges[0],
            ExchangeType.REQUEST_OFFER,
            ExchangeType.REQUEST_OFFER,
        )

    def test_request_offer_regular_endtoend(self):
        self._perform_exchange_pair_success_test_endtoend(
            self.exchanges[0],
            self.exchanges[1],
            ExchangeType.REQUEST_OFFER,
            ExchangeType.REQUEST_OFFER,
        )

    def test_request_offer_regular_endtoend_inverse(self):
        self._perform_exchange_pair_success_test_endtoend(
            self.exchanges[1],
            self.exchanges[0],
            ExchangeType.REQUEST_OFFER,
            ExchangeType.REQUEST_OFFER,
        )

    def test_request_offer_no_matches(self):
        self.assertEqual(self.exchanges[2].get_type(), ExchangeType.REQUEST_OFFER)
        match = self.exchanges[2].get_match()
        self.assertIsNone(match)

    def test_request_offer_no_matches_endtoend(self):
        self._perform_no_matches_endtoend_test(
            self.exchanges[2], ExchangeType.REQUEST_OFFER
        )

    def test_request_offer_with_teacher_offer(self):
        self._perform_exchange_pair_success_test(
            self.exchanges[3],
            self.exchanges[4],
            ExchangeType.REQUEST_OFFER,
            ExchangeType.TEACHER_OFFER,
        )

    def test_request_offer_with_teacher_offer_inverse(self):
        self._perform_exchange_pair_success_test(
            self.exchanges[4],
            self.exchanges[3],
            ExchangeType.TEACHER_OFFER,
            ExchangeType.REQUEST_OFFER,
        )

    def test_request_offer_with_teacher_offer_endtoend(self):
        self._perform_exchange_pair_success_test_endtoend(
            self.exchanges[3],
            self.exchanges[4],
            ExchangeType.REQUEST_OFFER,
            ExchangeType.TEACHER_OFFER,
        )

    def test_request_offer_with_teacher_offer_endtoend_inverse(self):
        self._perform_exchange_pair_success_test_endtoend(
            self.exchanges[4],
            self.exchanges[3],
            ExchangeType.TEACHER_OFFER,
            ExchangeType.REQUEST_OFFER,
        )

    def test_specified_student(self):
        self._perform_exchange_pair_success_test(
            self.exchanges[6],
            self.exchanges[7],
            ExchangeType.SPECIFIC_STUDENT,
            ExchangeType.SPECIFIC_STUDENT,
        )

    def test_specified_student_inverse(self):
        self._perform_exchange_pair_success_test(
            self.exchanges[7],
            self.exchanges[6],
            ExchangeType.SPECIFIC_STUDENT,
            ExchangeType.SPECIFIC_STUDENT,
        )

    def test_specified_student_endtoend(self):
        self._perform_exchange_pair_success_test_endtoend(
            self.exchanges[6],
            self.exchanges[7],
            ExchangeType.SPECIFIC_STUDENT,
            ExchangeType.SPECIFIC_STUDENT,
        )

    def test_specified_student_endtoend_inverse(self):
        self._perform_exchange_pair_success_test_endtoend(
            self.exchanges[7],
            self.exchanges[6],
            ExchangeType.SPECIFIC_STUDENT,
            ExchangeType.SPECIFIC_STUDENT,
        )

    def test_free_change_no_create(self):
        exchanges_before = Exchange.objects.count()
        self._perform_exchange_pair_success_test(
            self.exchanges[9],
            self.exchanges[10],
            ExchangeType.FREE_CHANGE,
            ExchangeType.REQUEST_OFFER,
        )
        exchanges_after = Exchange.objects.count()
        self.assertEqual(exchanges_before, exchanges_after)

    def test_free_change_no_create_inverse(self):
        exchanges_before = Exchange.objects.count()
        self._perform_exchange_pair_success_test(
            self.exchanges[10],
            self.exchanges[9],
            ExchangeType.REQUEST_OFFER,
            ExchangeType.FREE_CHANGE,
        )
        exchanges_after = Exchange.objects.count()
        self.assertEqual(exchanges_before, exchanges_after)

    def test_free_change_no_create_endtoend(self):
        exchanges_before = Exchange.objects.count()
        self._perform_exchange_pair_success_test_endtoend(
            self.exchanges[9],
            self.exchanges[10],
            ExchangeType.FREE_CHANGE,
            ExchangeType.REQUEST_OFFER,
        )
        exchanges_after = Exchange.objects.count()
        self.assertEqual(exchanges_before + 1, exchanges_after)

    def test_free_change_no_create_endtoend_inverse(self):
        exchanges_before = Exchange.objects.count()
        self._perform_exchange_pair_success_test_endtoend(
            self.exchanges[10],
            self.exchanges[9],
            ExchangeType.REQUEST_OFFER,
            ExchangeType.FREE_CHANGE,
        )
        exchanges_after = Exchange.objects.count()
        self.assertEqual(exchanges_before + 1, exchanges_after)

    def test_free_change_yes_create_chain_process(self):
        exchanges_before = Exchange.objects.count()
        self._perform_exchange_pair_success_test(
            self.exchanges[11],
            self.exchanges[12],
            ExchangeType.FREE_CHANGE,
            ExchangeType.REQUEST_OFFER,
        )
        exchanges_after = Exchange.objects.count()

        # creation only and chaining in end-to-end mode
        self.assertEqual(exchanges_before, exchanges_after)

    def test_free_change_yes_create_chain_process_inverse(self):
        exchanges_before = Exchange.objects.count()
        self._perform_exchange_pair_success_test(
            self.exchanges[12],
            self.exchanges[11],
            ExchangeType.REQUEST_OFFER,
            ExchangeType.FREE_CHANGE,
        )
        exchanges_after = Exchange.objects.count()

        # creation and chaining only in end-to-end mode
        self.assertEqual(exchanges_before, exchanges_after)

    def test_free_change_yes_create_chain_process_endtoend(self):
        exchanges_before = Exchange.objects.count()
        self._perform_exchange_pair_success_test_endtoend(
            self.exchanges[11],
            self.exchanges[12],
            ExchangeType.FREE_CHANGE,
            ExchangeType.REQUEST_OFFER,
            additional_processed_exchanges=2,
        )
        exchanges_after = Exchange.objects.count()
        self.assertEqual(exchanges_before + 2, exchanges_after)

    def test_free_change_yes_create_chain_process_endtoend_inverse(self):
        exchanges_before = Exchange.objects.count()
        self._perform_exchange_pair_success_test_endtoend(
            self.exchanges[12],
            self.exchanges[11],
            ExchangeType.REQUEST_OFFER,
            ExchangeType.FREE_CHANGE,
            additional_processed_exchanges=2,
        )
        exchanges_after = Exchange.objects.count()
        self.assertEqual(exchanges_before + 2, exchanges_after)

    def test_disallow_exchange_for_subject_hard(self):
        preference, preference_created = SubjectPreference.objects.get_or_create(
            subject=self.subjects[0]
        )
        preference.exchange_allowed = False
        preference.save()

        with self.assertRaises(FormProcessingError) as ex:
            self._perform_exchange_pair_success_test_endtoend(
                self.exchanges[0],
                self.exchanges[1],
                ExchangeType.REQUEST_OFFER,
                ExchangeType.REQUEST_OFFER,
            )
        self.assertIn("not allowed", ex.exception.header)
        self.assertIn("disabled", ex.exception.message)

    def test_disallow_exchange_for_subject_deadline(self):
        preference, preference_created = SubjectPreference.objects.get_or_create(
            subject=self.subjects[0]
        )
        preference.exchange_deadline = (datetime.utcnow() - timedelta(days=5)).date()
        preference.save()

        with self.assertRaises(FormProcessingError) as ex:
            self._perform_exchange_pair_success_test_endtoend(
                self.exchanges[0],
                self.exchanges[1],
                ExchangeType.REQUEST_OFFER,
                ExchangeType.REQUEST_OFFER,
            )
        self.assertIn("not allowed", ex.exception.header)
        self.assertIn("deadline", ex.exception.message)

    def test_cancellation_is_effective(self):
        ce = self.exchanges[6]
        counterpart = self.exchanges[7]
        ce.date_cancelled = datetime.utcnow()
        ce.save()
        match = counterpart.get_match()
        self.assertIsNone(match)

    def test_cancellation_is_effective_inverse(self):
        ce = self.exchanges[6]
        counterpart = self.exchanges[7]
        ce.date_cancelled = datetime.utcnow()
        ce.save()
        match = ce.get_match()
        self.assertNotEqual(match, counterpart)
        self.assertIsNone(match)

    def test_teacher_offer_for_other_student_no_matches(self):
        self.assertEqual(self.exchanges[13].get_type(), ExchangeType.TEACHER_OFFER)
        match = self.exchanges[13].get_match()
        self.assertIsNone(match)

    def test_teacher_offer_for_other_student_no_matches_inverse(self):
        self.assertEqual(self.exchanges[14].get_type(), ExchangeType.REQUEST_OFFER)
        match = self.exchanges[14].get_match()
        self.assertIsNone(match)

    def test_teacher_offer_for_other_student_no_matches_endtoend(self):
        self._perform_no_matches_endtoend_test(
            self.exchanges[13], ExchangeType.TEACHER_OFFER
        )

    def test_teacher_offer_for_other_student_no_matches_endtoend_inverse(self):
        self._perform_no_matches_endtoend_test(
            self.exchanges[14], ExchangeType.REQUEST_OFFER
        )
