from datetime import datetime, timedelta

from django.test import TestCase
from django.contrib.sites.models import Site
from django.test import Client
from django.test.client import RequestFactory

from friprosveta.studis import Studij
from friprosveta.management.commands.import_studis_students import get_parents
from friprosveta.management.commands.fill_groups import Command as fgc
from friprosveta.models import GroupSizeHint

from timetable.models import default_timetable

from model_mommy import mommy
import friprosveta


# class Test(TestCase):
#     def test_import_studis_students_get_parents(self):
#         studij = Studij(2018)
#         studijsko_drevo = {e['id']: e for e in studij.get_studijsko_drevo()}
#         entries = [16286, 16266, 16289, 834352532528]
#         results = [set(e['id'] for e in get_parents(studijsko_drevo, entry_id).values())
#                    for entry_id in entries]
#         expected_output = [set([16286, 1228, 2366, 1063, 35]),
#                            set([16266, 1281, 2481, 1141, 36]),
#                            set([16289, 1321, 2541, 1201]),
#                            set()]
#         self.assertEqual(results, expected_output, "Parent from studijsko drevo are wrong")


class FillGroupsTest(TestCase):
    def setUp(self):
        TestCase.setUp(self)
        self.c = fgc()
        self.study = mommy.make('friprosveta.Study', short_name='BUN-RI')
        self.groupset = mommy.make('timetable.GroupSet')
        self.aset = mommy.make('timetable.ActivitySet')
        self.tt = mommy.make('timetable.Timetable', groupset=self.groupset,
                             activityset=self.aset)
        self.a = mommy.make('friprosveta.Activity', type='LV',
                            activityset=self.aset)
        self.subject = self.a.subject
        self.g1 = mommy.make('timetable.Group', size=18,
                             short_name='1_BUN-RI_LV_01', groupset=self.groupset)
        self.g2 = mommy.make('timetable.Group', size=18,
                             short_name='1_BUN-RI_LV_02', groupset=self.groupset)
        self.a.groups.add(self.g1)
        self.a.groups.add(self.g2)
        self.students = mommy.make('friprosveta.Student', _quantity=17)
        for student in self.students:
            mommy.make('friprosveta.StudentEnrollment',
                       groupset=self.groupset,
                       student=student,
                       subject=self.subject,
                       study=self.study,
                       enrollment_type=4,
                       classyear=1)

    def tearDown(self):
        self.a.activityset.timetable_set.first().delete()
        friprosveta.models.Student.objects.all().delete()

    def test_simple_enrollment(self):
        self.c.fill_groups_by_size(
            tt=self.tt,
            subjects=friprosveta.models.Subject.objects.all(),
            write_to_db=True,
        )
        self.assertEqual(self.g1.students.count(), 17, "All students should be enrolled")

    def test_enrollment_no_change(self):
        self.c.fill_groups_by_size(
            tt=self.tt,
            subjects=friprosveta.models.Subject.objects.all(),
            write_to_db=True,
        )
        original_g1_students = set(self.g1.students.all())
        new_students = mommy.make('friprosveta.Student', _quantity=17)
        for student in new_students:
            mommy.make('friprosveta.StudentEnrollment',
                       groupset=self.groupset,
                       student=student,
                       subject=self.subject,
                       study=self.study,
                       enrollment_type=4,
                       classyear=1)
        self.c.fill_groups_by_size(
            tt=self.tt,
            subjects=friprosveta.models.Subject.objects.all(),
            write_to_db=True,
        )
        self.assertEqual(self.g1.students.count(), 18, "Group g1 must be filled first")
        self.assertEqual(self.g2.students.count(), 16, "Group must be filled up to available students")
        self.assertEqual(len(set(self.g1.students.all()).intersection(original_g1_students)), 17,
                         "Students from g1 should not be moved")


class MultiSiteTest(TestCase):
    def setUp(self):
        TestCase.setUp(self)
        self.request_factory = RequestFactory()
        self.server_name = "urnik.fri.uni-lj.si"

    def test_default_timetable_no_site(self):
        request = self.request_factory.get("/", SERVER_NAME="koala.lumpur.si")
        with self.assertRaises(Site.DoesNotExist):
            default_timetable(request)

    def test_default_timetable_no_timetable_site(self):
        site = mommy.make(Site, domain=self.server_name)
        request = self.request_factory.get("/", SERVER_NAME=self.server_name)
        with self.assertRaises(IndexError):
            default_timetable(request)
        site.delete()

    def test_default_timetable_no_default_timetable_site(self):
        site = mommy.make(Site, domain=self.server_name)
        timetable = mommy.make('timetable.Timetable', public=True)
        timetable_site = mommy.make('timetable.TimetableSite', default=False, timetable=timetable, site=site)
        request = self.request_factory.get("/", SERVER_NAME=self.server_name)
        with self.assertRaises(IndexError):
            default_timetable(request)
        site.delete()

    def test_default_timetable_no_public_timetable(self):
        site = mommy.make(Site, domain=self.server_name)
        timetable = mommy.make('timetable.Timetable', public=False)
        timetable_site = mommy.make('timetable.TimetableSite', default=True, timetable=timetable, site=site)
        request = self.request_factory.get("/", SERVER_NAME=self.server_name)
        with self.assertRaises(IndexError):
            default_timetable(request)
        site.delete()

    def test_default_timetable_normal(self):
        site = mommy.make(Site, domain=self.server_name)
        timetable = mommy.make('timetable.Timetable', public=True)
        timetable_site = mommy.make('timetable.TimetableSite', default=True, timetable=timetable, site=site)
        request = self.request_factory.get("/", SERVER_NAME=self.server_name)
        self.assertEqual(default_timetable(request), timetable,
                         "The default timetable is not the right one")
        site.delete()

    def test_default_timetable_multiple(self):
        # Get the one that starts later
        site = mommy.make(Site, domain=self.server_name)
        timetable1 = mommy.make('timetable.Timetable', public=True, start=datetime.now())
        timetable2 = mommy.make('timetable.Timetable', public=True, start=datetime.now() + timedelta(123456))
        timetable_site = mommy.make('timetable.TimetableSite', default=True, timetable=timetable1, site=site)
        timetable_site = mommy.make('timetable.TimetableSite', default=True, timetable=timetable2, site=site)
        request = self.request_factory.get("/", SERVER_NAME=self.server_name)
        self.assertEqual(default_timetable(request), timetable2,
                         "The default timetable is not the right one")
        site.delete()


class GroupSizeHintTest(TestCase):

    def setUp(self):
        TestCase.setUp(self)
        # Create group and some hints for it
        self.g1, self.g2 = mommy.make('timetable.Group', size=20), mommy.make('timetable.Group', size=5)
        methods1 = [('1', 0), ('2', 10), ('3', 12)]
        methods2 = [('1', 0), ('2', 0), ('3', 0)]
        for method_name, size in methods1:
            mommy.make('friprosveta.GroupSizeHint', group=self.g1, size=size, method=method_name)
        for method_name, size in methods2:
            mommy.make('friprosveta.GroupSizeHint', group=self.g2, size=size, method=method_name)

    def test_group_size_hint_incorrect_strategy(self):
        with self.assertRaises(KeyError):
            GroupSizeHint.strategy(self.g1, ["unknown"], 'Weird strategy name')

    def test_group_size_hint_first(self):
        strategy = 'first'

        methods = ['1', '2']
        expected = 0
        val = GroupSizeHint.strategy(self.g1, methods, strategy)
        self.assertEqual(val, expected,
                         "Strategy '{}' for {} and methods {} should return {}".format(strategy, self.g1,
                                                                                       methods, expected))

        methods = ['2', '3']
        expected = 10
        val = GroupSizeHint.strategy(self.g1, methods, strategy)
        self.assertEqual(val, expected,
                         "Strategy '{}' for {} and methods {} should return {}".format(strategy, self.g1,
                                                                                       methods, expected))

        val = GroupSizeHint.strategy(self.g1, ['non', 'existing'], strategy)
        self.assertIsNone(val, "If no hints are available None should be returned")

    def test_group_size_hint_first_not_zero(self):
        strategy = 'first-non-zero'

        methods = ['1', '2', '3']
        expected = 10
        val = GroupSizeHint.strategy(self.g1, methods, strategy)
        self.assertEqual(val, expected,
                         "Strategy '{}' for {} and methods {} should return {}".format(strategy, self.g1, methods,
                                                                                       expected))

        methods = ['1', '2', '3']
        val = GroupSizeHint.strategy(self.g2, methods, strategy)
        self.assertIsNone(val, "If no hints are available None should be returned")

    def test_group_size_hint_max(self):
        strategy = 'max'

        methods = ['1', '2', '3']
        expected = 12
        val = GroupSizeHint.strategy(self.g1, methods, strategy)
        self.assertEqual(val, expected,
                         "Strategy '{}' for {} and methods {} should return {}".format(strategy, self.g1, methods,
                                                                                       expected))

        val = GroupSizeHint.strategy(self.g1, ['non', 'existing'], strategy)
        self.assertIsNone(val, "If no hints are available None should be returned")

        methods = ['1', '2', '3']
        expected = 0
        val = GroupSizeHint.strategy(self.g2, methods, strategy)
        self.assertEqual(val, expected,
                         "Strategy '{}' for {} and methods {} should return {}".format(strategy, self.g2,
                                                                                       methods, expected,))

    def test_group_size_hint_max_not_zero(self):
        strategy = 'max-non-zero'

        methods = ['1', '2', '3']
        expected = 12
        val = GroupSizeHint.strategy(self.g1, methods, strategy)
        self.assertEqual(val, expected,
                         "Strategy '{}' for {} and methods {} should return {}".format(strategy, self.g1, methods,
                                                                                       expected))

        methods = ['1', '2', '3']
        val = GroupSizeHint.strategy(self.g2, methods, strategy)
        self.assertIsNone(val, "If no hints are available None should be returned")

    def test_group_size_hint_max_group(self):
        strategy = 'max-group'

        methods = ['1', '2', '3']
        expected = 20
        val = GroupSizeHint.strategy(self.g1, methods, strategy)
        self.assertEqual(val, expected,
                         "Strategy '{}' for {} and methods {} should return {}".format(strategy, self.g1, methods,
                                                                                       expected))

        val = GroupSizeHint.strategy(self.g1, ['non', 'existing'], strategy)
        self.assertIsNone(val, "If no hints are available None should be returned")

        methods = ['1', '2', '3']
        expected = max(0, self.g2.size)
        val = GroupSizeHint.strategy(self.g2, methods, strategy)
        self.assertEqual(val, expected,
                         "Strategy '{}' for {} and methods {} should return {}".format(strategy, self.g2, methods,
                                                                                       expected))
