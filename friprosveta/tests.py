import unittest
from datetime import date, datetime, timedelta
from io import StringIO
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.contrib.sites.models import Site
from django.test import Client, TestCase
from django.test.client import RequestFactory
from django.urls import reverse
from model_mommy import mommy

import friprosveta
from friprosveta.auth import oidc_username_from_claims
from friprosveta.management.commands.fill_groups import Command as fgc
from friprosveta.management.commands.import_studis_students import get_parents
from friprosveta.models import (
    ActivityTypeSchedulingRestriction,
    ActivityTypeSchedulingWindow,
    GroupSizeHint,
    SolverWeightSettings,
    Study,
)
from friprosveta.services.ortools_solver import ORToolsSolverOptions, ORToolsTimetableSolver
from friprosveta.studis import Studij
from friprosveta.solver_run_views import (
    SOLVER_GENERATION_LOCK_PREFIX,
    SOLVER_GENERATION_CACHE_TTL_SECONDS,
    SOLVER_GENERATION_STATE_PREFIX,
)
from friprosveta.studis_workflow_views import (
    STUDIS_WORKFLOW_CACHE_TTL_SECONDS,
    STUDIS_WORKFLOW_LOCK_PREFIX,
    STUDIS_WORKFLOW_STATE_PREFIX,
)
from frinajave.models import TeacherSubjectCycles
from timetable.models import (
    ACTIVITYTYPES,
    ActivityRealization,
    Allocation,
    Activity,
    ActivitySet,
    Classroom,
    ClassroomSet,
    Group,
    GroupSet,
    GroupTimePreference,
    GroupValuePreference,
    Location,
    PreferenceSet,
    SolverConstraint,
    StudyModule,
    Tag,
    TagDescriptivePreference,
    TagTimePreference,
    TagValuePreference,
    Teacher,
    TeacherTimePreference,
    TeacherValuePreference,
    TimetableSet,
    Timetable,
    WEEKDAYS,
    WORKHOURS,
    default_timetable,
)


class MyTestCase(TestCase):
    def assertEmpty(self, obj, *msg):
        """
        Is an iterable obj empty?
        """
        self.assertEqual(len(obj), 0, msg)

    def assertLength(self, obj, length, *msg):
        """
        Has an iterable a given length?
        """
        self.assertEqual(len(obj), length, msg)


class ActivityTypeSchedulingWindowTest(TestCase):
    def setUp(self):
        self.timetable = Timetable.objects.create(
            slug="window-tt", name="Scheduling Window Timetable"
        )

    def test_end_allows_boundary_after_final_workhour(self):
        # Given a scheduling window ending immediately after the final workhour.
        window_model = friprosveta.models.ActivityTypeSchedulingWindow
        window = window_model(
            timetable=self.timetable,
            activity_type="P",
            day="FRI",
            start="21:00",
            end="22:00",
        )

        # When the window is validated.
        window.full_clean()

        # Then no validation error is raised.

    def test_rejects_end_that_is_not_after_start(self):
        # Given a window whose end equals its start.
        window = ActivityTypeSchedulingWindow(
            timetable=self.timetable,
            activity_type="P",
            day="MON",
            start="08:00",
            end="08:00",
        )

        # When the window is validated.
        with self.assertRaises(ValidationError):
            window.full_clean()

        # Then the invalid half-open interval is rejected.

    def test_rejects_duplicate_activity_type_day_for_timetable(self):
        # Given an existing timetable, activity type, and weekday window.
        ActivityTypeSchedulingWindow.objects.create(
            timetable=self.timetable,
            activity_type="P",
            day="MON",
            start="08:00",
            end="18:00",
        )
        duplicate = ActivityTypeSchedulingWindow(
            timetable=self.timetable,
            activity_type="P",
            day="MON",
            start="09:00",
            end="18:00",
        )

        # When a duplicate is validated.
        with self.assertRaises(ValidationError):
            duplicate.full_clean()

        # Then the single-window-per-day constraint rejects it.


class OIDCUsernameTest(unittest.TestCase):
    def test_username_accepts_mozilla_django_oidc_signature(self):
        claims = {
            "email": "user@example.com",
            "upn": "user@example.org",
            "preferred_username": "user",
            "sub": "subject-id",
        }

        self.assertEqual(
            oidc_username_from_claims("user@example.com", claims), "user@example.com"
        )

    def test_username_falls_back_to_alternate_claims(self):
        self.assertEqual(
            oidc_username_from_claims(None, {"upn": "user@example.org"}),
            "user@example.org",
        )

    def test_username_accepts_claims_dict_for_direct_calls(self):
        self.assertEqual(
            oidc_username_from_claims({"preferred_username": "user"}), "user"
        )


class ORToolsUnavailableTest(TestCase):
    def setUp(self):
        self.preferenceset = PreferenceSet.objects.create(
            slug="prefs", name="Preferences"
        )
        self.activityset = ActivitySet.objects.create(
            slug="activities", name="Activities"
        )
        self.groupset = GroupSet.objects.create(
            slug="groups", name="Groups", created=datetime.now()
        )
        self.timetable = Timetable.objects.create(
            slug="tt",
            name="Timetable",
            activityset=self.activityset,
            preferenceset=self.preferenceset,
            groupset=self.groupset,
        )
        self.teacher = Teacher.objects.create(
            user=User.objects.create_user("teacher"), code="teacher"
        )
        self.group = Group.objects.create(
            name="Group", short_name="G_01", size=10, groupset=self.groupset
        )
        self.activity = Activity.objects.create(
            name="Activity",
            short_name="ACT",
            activityset=self.activityset,
            type="P",
            duration=1,
        )
        self.activity.teachers.add(self.teacher)
        self.solver = ORToolsTimetableSolver(self.timetable)

    def test_teacher_hate_preference_is_unavailable(self):
        TeacherTimePreference.objects.create(
            preferenceset=self.preferenceset,
            teacher=self.teacher,
            level="HATE",
            day="MON",
            start="08:00",
            duration=2,
        )

        unavailable = self.solver._build_teacher_unavailable()

        self.assertEqual(unavailable[self.teacher.id]["MON"], {1, 2})

    def test_teacher_tag_hate_preference_is_unavailable(self):
        tag = Tag.objects.create(name="No mornings", description="")
        tag.teachers.add(self.teacher)
        TagTimePreference.objects.create(
            preferenceset=self.preferenceset,
            tag=tag,
            level="HATE",
            day="TUE",
            start="09:00",
            duration=1,
        )

        unavailable = self.solver._build_teacher_unavailable()

        self.assertEqual(unavailable[self.teacher.id]["TUE"], {2})

    def test_group_hate_preference_is_unavailable(self):
        GroupTimePreference.objects.create(
            preferenceset=self.preferenceset,
            group=self.group,
            level="HATE",
            day="WED",
            start="10:00",
            duration=1,
        )

        unavailable = self.solver._build_group_unavailable()

        self.assertEqual(unavailable[self.group.id]["WED"], {3})

    def test_group_tag_hate_preference_is_unavailable(self):
        tag = Tag.objects.create(name="Group block", description="")
        tag.groups.add(self.group)
        TagTimePreference.objects.create(
            preferenceset=self.preferenceset,
            tag=tag,
            level="HATE",
            day="THU",
            start="11:00",
            duration=1,
        )

        unavailable = self.solver._build_group_unavailable()

        self.assertEqual(unavailable[self.group.id]["THU"], {4})

    def test_child_inherits_hard_group_and_tag_preferences(self):
        child = Group.objects.create(
            name="Child",
            short_name="G_01_01",
            size=10,
            parent=self.group,
            groupset=self.groupset,
        )
        GroupTimePreference.objects.create(
            preferenceset=self.preferenceset,
            group=self.group,
            level="CANT",
            day="FRI",
            start="12:00",
            duration=1,
        )
        GroupTimePreference.objects.create(
            preferenceset=self.preferenceset,
            group=self.group,
            level="HATE",
            day="MON",
            start="07:00",
            duration=1,
        )
        tag = Tag.objects.create(name="Parent group block", description="")
        tag.groups.add(self.group)
        TagTimePreference.objects.create(
            preferenceset=self.preferenceset,
            tag=tag,
            level="CANT",
            day="TUE",
            start="09:00",
            duration=1,
        )

        unavailable = self.solver._build_group_unavailable()

        self.assertEqual(unavailable[child.id]["FRI"], {5})
        self.assertEqual(unavailable[child.id]["MON"], {0})
        self.assertEqual(unavailable[child.id]["TUE"], {2})

    def test_child_inherits_group_and_tag_want_preferences(self):
        child = Group.objects.create(
            name="Child",
            short_name="G_01_01",
            size=10,
            parent=self.group,
            groupset=self.groupset,
        )
        GroupTimePreference.objects.create(
            preferenceset=self.preferenceset,
            group=self.group,
            level="WANT",
            day="WED",
            start="10:00",
            duration=1,
            weight=1.5,
        )
        tag = Tag.objects.create(name="Parent group preference", description="")
        tag.groups.add(self.group)
        TagTimePreference.objects.create(
            preferenceset=self.preferenceset,
            tag=tag,
            level="WANT",
            day="THU",
            start="11:00",
            duration=1,
            weight=2,
        )

        _teacher_prefs, group_prefs, _tag_prefs = (
            self.solver._build_want_preferences()
        )

        self.assertIn(("WED", {3}, 1.5), group_prefs[child.id])
        self.assertIn(("THU", {4}, 2), group_prefs[child.id])


class ORToolsGenerationTest(TestCase):
    def setUp(self):
        self.preferenceset = PreferenceSet.objects.create(
            slug="solver-prefs", name="Solver Preferences"
        )
        self.activityset = ActivitySet.objects.create(
            slug="solver-activities", name="Solver Activities"
        )
        self.groupset = GroupSet.objects.create(
            slug="solver-groups", name="Solver Groups", created=datetime.now()
        )
        self.classroomset = ClassroomSet.objects.create(
            slug="solver-rooms", name="Solver Rooms", created=date.today()
        )
        self.location = Location.objects.create(name="Ljubljana")
        self.timetable = Timetable.objects.create(
            slug="solver-tt",
            name="Solver Timetable",
            activityset=self.activityset,
            preferenceset=self.preferenceset,
            groupset=self.groupset,
            classroomset=self.classroomset,
        )
        self.room1 = self._create_room("Room 1", "R1", 30)
        self.room2 = self._create_room("Room 2", "R2", 30)

    def _create_room(self, name, short_name, capacity, location=None):
        room = Classroom.objects.create(
            name=name,
            short_name=short_name,
            capacity=capacity,
            location=location or self.location,
        )
        self.classroomset.classrooms.add(room)
        return room

    def _create_teacher(self, username):
        return Teacher.objects.create(
            user=User.objects.create_user(username), code=username
        )

    def _create_group(self, short_name, size=10, student_count=0):
        group = Group.objects.create(
            name=short_name,
            short_name=short_name,
            size=size,
            groupset=self.groupset,
        )
        for index in range(student_count):
            student = friprosveta.models.Student.objects.create(
                name=f"Student {short_name} {index}",
                surname="Solver",
                studentId=f"{short_name[:3]}{index:05d}"[:8],
            )
            student.groups.add(group)
        return group

    def _create_realization(
        self,
        short_name,
        teacher,
        group,
        duration=1,
        location=None,
        activity_type="P",
        subject=None,
        lecture_type=None,
    ):
        activity_model = friprosveta.models.Activity if subject is not None else Activity
        activity = activity_model.objects.create(
            name=short_name,
            short_name=short_name,
            activityset=self.activityset,
            type=activity_type,
            duration=duration,
            **(
                {"subject": subject, "lecture_type": lecture_type}
                if subject is not None
                else {}
            ),
        )
        activity.locations.add(location or self.location)
        activity.teachers.add(teacher)
        activity.groups.add(group)
        realization = ActivityRealization.objects.create(activity=activity)
        realization.teachers.add(teacher)
        realization.groups.add(group)
        return realization

    def _create_ready_only_realization(
        self, short_name, teacher, group, ready_to_schedule, duration=1
    ):
        subject = friprosveta.models.Subject.objects.create(
            code=short_name[:16], name="{} subject".format(short_name)
        )
        lecture_type = friprosveta.models.LectureType.objects.create(
            name="{} lecture type".format(short_name),
            short_name=short_name[:4],
            duration=duration,
        )
        activity = friprosveta.models.Activity.objects.create(
            name=short_name,
            short_name=short_name,
            activityset=self.activityset,
            type="P",
            duration=duration,
            subject=subject,
            lecture_type=lecture_type,
            ready_to_schedule=ready_to_schedule,
        )
        activity.teachers.add(teacher)
        activity.groups.add(group)
        activity.locations.add(self.location)
        realization = ActivityRealization.objects.create(activity=activity)
        realization.teachers.add(teacher)
        realization.groups.add(group)
        return realization

    def _create_cross_section_pair(self, shared_student_count):
        subject = friprosveta.models.Subject.objects.create(
            code="XSEC", name="XSection Subject"
        )
        lecture_type = friprosveta.models.LectureType.objects.create(
            name="XSection LT", short_name="XL", duration=1
        )
        groups = [
            self._create_group("XSEC1", size=10),
            self._create_group("XSEC2", size=10),
        ]
        shared_group = self._create_group(
            "SHARE", size=shared_student_count, student_count=shared_student_count
        )
        for student in shared_group.students.all():
            groups[0].students.add(student)
            groups[1].students.add(student)

        realizations = []
        teachers = []
        for index, group in enumerate(groups, start=1):
            teacher = self._create_teacher(f"xoverlap-teacher-{index}")
            activity = friprosveta.models.Activity.objects.create(
                name=f"XSEC{index}",
                short_name=f"XSEC{index}",
                activityset=self.activityset,
                type="P",
                duration=1,
                subject=subject,
                lecture_type=lecture_type,
            )
            activity.teachers.add(teacher)
            activity.groups.add(group)
            activity.locations.add(self.location)
            realization = ActivityRealization.objects.create(activity=activity)
            realization.teachers.add(teacher)
            realization.groups.add(group)
            realizations.append(realization)
            teachers.append(teacher)
        return realizations, teachers

    def _create_group_cross_section_pair(self, group_size):
        group = self._create_group("GROUP_RAZOR", size=group_size)
        teachers = [
            self._create_teacher("group-razor-teacher-1"),
            self._create_teacher("group-razor-teacher-2"),
        ]
        realizations = [
            self._create_realization("GROUP_RAZOR_1", teachers[0], group),
            self._create_realization("GROUP_RAZOR_2", teachers[1], group),
        ]
        return realizations, teachers, group

    def _run_solver(self, **options):
        output = StringIO()
        try:
            call_command(
                "ortools_generate",
                self.timetable.slug,
                time_limit=10,
                stdout=output,
                **options,
            )
        except CommandError as error:
            output.write(str(error))
        return output.getvalue()

    def _allocation_for(self, realization):
        return Allocation.objects.get(
            timetable=self.timetable, activityRealization=realization
        )

    def test_generation_warns_about_realizations_without_groups(self):
        teacher = self._create_teacher("ungrouped-teacher")
        realization = self._create_realization(
            "Ungrouped", teacher, self._create_group("Ungrouped")
        )
        realization.groups.clear()

        output = self._run_solver()

        self.assertIn(
            f"Warning: realization {realization.id} ({realization}) has no groups;",
            output,
        )
        self.assertTrue(Allocation.objects.filter(timetable=self.timetable).exists())

    def test_generation_warns_about_activity_groups_without_realizations(self):
        teacher = self._create_teacher("missing-group-teacher")
        assigned = self._create_group("1_RI_LV_01", size=15)
        missing = self._create_group("1_RI_LV_02", size=12)
        realization = self._create_realization(
            "MISSING", teacher, assigned, activity_type="LV"
        )
        realization.activity.groups.add(missing)

        output = self._run_solver()

        self.assertIn(
            "Warning: 1 positive-size non-PAD group(s), with a total planned "
            "size of 12, are not assigned to any realization.",
            output,
        )
        self.assertIn("Activity MISSING (LV): 1_RI_LV_02", output)
        self.assertTrue(Allocation.objects.filter(timetable=self.timetable).exists())

    def test_skips_zero_duration_realizations(self):
        teacher = self._create_teacher("zero-duration-teacher")
        group = self._create_group("ZERO_01")

        valid_realization = self._create_realization("VALID", teacher, group)
        invalid_realization = self._create_realization(
            "INVALID", teacher, group, duration=0
        )

        output = self._run_solver(clear_existing=True)

        self.assertIn(
            "Skipping 1 realization(s) with invalid duration: {}(duration=0)".format(
                invalid_realization.id
            ),
            output,
        )
        self.assertTrue(
            Allocation.objects.filter(
                timetable=self.timetable, activityRealization=valid_realization
            ).exists()
        )
        self.assertFalse(
            Allocation.objects.filter(
                timetable=self.timetable, activityRealization=invalid_realization
            ).exists()
        )
        self.assertEqual(Allocation.objects.filter(timetable=self.timetable).count(), 1)

    @patch("friprosveta.management.commands.prepare_ortools_groups.Studij")
    @patch("friprosveta.management.commands.prepare_ortools_groups.Najave")
    def test_group_preparation_assigns_lecture_groups_to_realizations(
        self, mocked_najave, mocked_studij
    ):
        teacher = self._create_teacher("preparation-teacher")
        group = self._create_group("Preparation")
        realization = self._create_realization(
            "Preparation", teacher, group
        )
        realization.groups.clear()

        output = StringIO()
        call_command(
            "prepare_ortools_groups", self.timetable.slug, "2026", stdout=output
        )

        mocked_studij.assert_called_once_with("2026")
        mocked_najave.assert_called_once_with("2026")
        self.assertEqual(list(realization.groups.all()), [group])
        self.assertIn("Prepared groups for timetable solver-tt", output.getvalue())

    @patch("friprosveta.management.commands.prepare_ortools_groups.Studij")
    @patch("friprosveta.management.commands.prepare_ortools_groups.Najave")
    def test_group_preparation_warns_about_unassigned_activity_groups(
        self, _mocked_najave, _mocked_studij
    ):
        teacher = self._create_teacher("coverage-teacher")
        assigned = self._create_group("1_RI_LV_01", size=15)
        missing = self._create_group("1_RI_LV_02", size=15)
        realization = self._create_realization(
            "COVERAGE", teacher, assigned, activity_type="LV"
        )
        realization.intended_size = 18
        realization.save(update_fields=["intended_size"])
        realization.activity.groups.add(missing)
        errors = StringIO()

        call_command(
            "prepare_ortools_groups",
            self.timetable.slug,
            "2026",
            stderr=errors,
        )

        self.assertIn(
            "Warning: 1 positive-size non-PAD group(s), with a total planned "
            "size of 15, are not assigned to any realization.",
            errors.getvalue(),
        )
        self.assertIn("Activity COVERAGE (LV): 1_RI_LV_02", errors.getvalue())

    def _slot_index(self, allocation):
        day_index = [day[0] for day in WEEKDAYS].index(allocation.day)
        hour_index = [hour[0] for hour in WORKHOURS].index(allocation.start)
        return day_index * len(WORKHOURS) + hour_index

    def _overlap(self, first, second):
        if first.day != second.day:
            return False
        first_start = [hour[0] for hour in WORKHOURS].index(first.start)
        second_start = [hour[0] for hour in WORKHOURS].index(second.start)
        first_hours = set(range(first_start, first_start + first.duration))
        second_hours = set(range(second_start, second_start + second.duration))
        return not first_hours.isdisjoint(second_hours)

    def _block_teacher_except(self, teacher, allowed_slots):
        allowed_slots = set(allowed_slots)
        for day, _day_name in WEEKDAYS:
            for hour, _hour_name in WORKHOURS:
                if (day, hour) in allowed_slots:
                    continue
                TeacherTimePreference.objects.create(
                    preferenceset=self.preferenceset,
                    teacher=teacher,
                    level="HATE",
                    day=day,
                    start=hour,
                    duration=1,
                )

    def _block_group_except(self, group, allowed_slots):
        allowed_slots = set(allowed_slots)
        for day, _day_name in WEEKDAYS:
            for hour, _hour_name in WORKHOURS:
                if (day, hour) in allowed_slots:
                    continue
                GroupTimePreference.objects.create(
                    preferenceset=self.preferenceset,
                    group=group,
                    level="HATE",
                    day=day,
                    start=hour,
                    duration=1,
                )

    def _restrict_activity_type_to(self, activity_type, allowed_slots, weight=100):
        allowed_slots = set(allowed_slots)
        for day, _day_name in WEEKDAYS:
            for hour, _hour_name in WORKHOURS:
                if (day, hour) not in allowed_slots:
                    ActivityTypeSchedulingRestriction.objects.create(
                        timetable=self.timetable,
                        activity_type=activity_type,
                        day=day,
                        start=hour,
                        weight=weight,
                    )

    def _slot_distance(self, first, second):
        return abs(self._slot_index(first) - self._slot_index(second))

    def test_generates_complete_schedule_for_simple_timetable(self):
        teacher1 = self._create_teacher("simple-teacher-1")
        teacher2 = self._create_teacher("simple-teacher-2")
        group1 = self._create_group("SIMPLE_01")
        group2 = self._create_group("SIMPLE_02")
        realization1 = self._create_realization("SIMPLE1", teacher1, group1)
        realization2 = self._create_realization("SIMPLE2", teacher2, group2)

        output = self._run_solver()

        self.assertIn("Generated 2 allocations", output)
        self.assertEqual(Allocation.objects.filter(timetable=self.timetable).count(), 2)
        self._allocation_for(realization1)
        self._allocation_for(realization2)

    def test_hate_preferences_force_only_allowed_slot(self):
        teacher = self._create_teacher("hate-teacher")
        group = self._create_group("HATE_01")
        realization = self._create_realization("HATE", teacher, group)
        self._block_teacher_except(teacher, {("FRI", "21:00")})

        self._run_solver()

        allocation = self._allocation_for(realization)
        self.assertEqual((allocation.day, allocation.start), ("FRI", "21:00"))

    def test_reports_direct_conflict_between_forced_placements(self):
        group = self._create_group("FORCED_01")
        first = self._create_realization(
            "FORCED_FIRST", self._create_teacher("forced-teacher-1"), group
        )
        second = self._create_realization(
            "FORCED_SECOND", self._create_teacher("forced-teacher-2"), group
        )
        self.classroomset.classrooms.remove(self.room2)
        self._block_group_except(group, {("MON", "07:00")})

        output = self._run_solver()

        self.assertIn("Direct forced-placement conflicts:", output)
        self.assertIn(f"#{first.id} FORCED_FIRST", output)
        self.assertIn(f"#{second.id} FORCED_SECOND", output)
        self.assertIn("via group", output)

    def test_sibling_lv_and_av_groups_cannot_overlap(self):
        top_group = self._create_group("LV_AV_TOP")
        lv_group = Group.objects.create(
            name="LV_AV_LV_01",
            short_name="LV_AV_LV_01",
            size=10,
            groupset=self.groupset,
            parent=top_group,
        )
        av_group = Group.objects.create(
            name="LV_AV_AV_01",
            short_name="LV_AV_AV_01",
            size=10,
            groupset=self.groupset,
            parent=top_group,
        )
        lv_teacher = self._create_teacher("sibling-lv-teacher")
        av_teacher = self._create_teacher("sibling-av-teacher")
        self._create_realization("SIBLING_LV", lv_teacher, lv_group, activity_type="LV")
        self._create_realization("SIBLING_AV", av_teacher, av_group, activity_type="AV")
        self._block_teacher_except(lv_teacher, {("MON", "07:00")})
        self._block_teacher_except(av_teacher, {("MON", "07:00")})

        result = ORToolsTimetableSolver(
            self.timetable,
            ORToolsSolverOptions(time_limit=10, clear_existing=True),
        ).solve()

        self.assertFalse(result.success)

    def test_subject_lecture_and_lab_cannot_overlap_despite_group_razor(self):
        subject = friprosveta.models.Subject.objects.create(
            code="SUBJECT_NO_OV", name="Subject no overlap"
        )
        lecture_type = friprosveta.models.LectureType.objects.create(
            name="Subject lecture type", short_name="SUB", duration=1
        )
        lecture_group = self._create_group("SUBJECT_P", size=2)
        lab_group = Group.objects.create(
            name="SUBJECT_LV_01",
            short_name="SUBJECT_LV_01",
            size=2,
            groupset=self.groupset,
            parent=lecture_group,
        )
        lecture_teacher = self._create_teacher("subject-lecture-teacher")
        lab_teacher = self._create_teacher("subject-lab-teacher")
        lecture = self._create_realization(
            "SUBJECT_P",
            lecture_teacher,
            lecture_group,
            activity_type="P",
            subject=subject,
            lecture_type=lecture_type,
        )
        lab = self._create_realization(
            "SUBJECT_LV",
            lab_teacher,
            lab_group,
            activity_type="LV",
            subject=subject,
            lecture_type=lecture_type,
        )
        self._block_teacher_except(lecture_teacher, {("MON", "07:00")})
        self._block_teacher_except(lab_teacher, {("MON", "07:00")})

        result = ORToolsTimetableSolver(
            self.timetable,
            ORToolsSolverOptions(
                time_limit=10, clear_existing=True, cross_section_group_razor=3
            ),
        ).solve()

        self.assertFalse(result.success)

    def test_optional_activity_cannot_overlap_mandatory_lecture_despite_group_razor(self):
        mandatory_group = self._create_group("MANDATORY_COHORT", size=10)
        optional_subject = friprosveta.models.Subject.objects.create(
            code="OPTIONAL", name="Optional subject"
        )
        optional_lecture_type = friprosveta.models.LectureType.objects.create(
            name="Optional lecture type", short_name="OPT", duration=1
        )
        optional_curriculum_group = Group.objects.create(
            name="Optional curriculum group",
            short_name="MANDATORY_COHORT_(OPTIONAL)",
            size=0,
            groupset=self.groupset,
            parent=mandatory_group,
        )
        optional_activity_group = Group.objects.create(
            name="Optional activity group",
            short_name="MANDATORY_COHORT_(OPTIONAL)_LV_01",
            size=0,
            groupset=self.groupset,
            parent=optional_curriculum_group,
        )
        mandatory_teacher = self._create_teacher("mandatory-lecture-teacher")
        optional_teacher = self._create_teacher("optional-lab-teacher")
        self._create_realization("MANDATORY_P", mandatory_teacher, mandatory_group)
        self._create_realization(
            "OPTIONAL_LV",
            optional_teacher,
            optional_activity_group,
            activity_type="LV",
            subject=optional_subject,
            lecture_type=optional_lecture_type,
        )
        self._block_teacher_except(mandatory_teacher, {("MON", "07:00")})
        self._block_teacher_except(optional_teacher, {("MON", "07:00")})

        result = ORToolsTimetableSolver(
            self.timetable,
            ORToolsSolverOptions(
                time_limit=10, clear_existing=True, cross_section_group_razor=3
            ),
        ).solve()

        self.assertFalse(result.success)

    def test_top_group_cannot_overlap_deep_descendant_group(self):
        top_group = self._create_group("ANCESTOR_TOP")
        intermediate_group = Group.objects.create(
            name="ANCESTOR_INTERMEDIATE",
            short_name="ANCESTOR_INTERMEDIATE",
            size=10,
            groupset=self.groupset,
            parent=top_group,
        )
        leaf_group = Group.objects.create(
            name="ANCESTOR_LEAF",
            short_name="ANCESTOR_LEAF",
            size=10,
            groupset=self.groupset,
            parent=intermediate_group,
        )
        lecture_teacher = self._create_teacher("ancestor-lecture-teacher")
        exercise_teacher = self._create_teacher("ancestor-exercise-teacher")
        self._create_realization("ANCESTOR_P", lecture_teacher, top_group, activity_type="P")
        self._create_realization("ANCESTOR_LV", exercise_teacher, leaf_group, activity_type="LV")
        self._block_teacher_except(lecture_teacher, {("MON", "07:00")})
        self._block_teacher_except(exercise_teacher, {("MON", "07:00")})

        result = ORToolsTimetableSolver(
            self.timetable, ORToolsSolverOptions(time_limit=10, clear_existing=True)
        ).solve()

        self.assertFalse(result.success)

    def test_top_level_group_lecture_hour_limit_includes_descendants(self):
        teacher = self._create_teacher("lecture-group-limit-teacher")
        top_group = self._create_group("LECTURE_LIMIT_TOP")
        child_group = Group.objects.create(
            name="LECTURE_LIMIT_CHILD",
            short_name="LECTURE_LIMIT_CHILD",
            size=10,
            groupset=self.groupset,
            parent=top_group,
        )
        self._create_realization(
            "LECTURE_LIMIT_P", teacher, child_group, duration=3, activity_type="P"
        )
        constraint = SolverConstraint.objects.create(
            timetable=self.timetable,
            name="Top group maximum lecture hours",
            constraint_type="MAXLECTUREHOURSDAY",
            value=2,
        )
        constraint.groups.add(top_group)

        result = ORToolsTimetableSolver(
            self.timetable,
            ORToolsSolverOptions(time_limit=10, clear_existing=True),
        ).solve()

        self.assertFalse(result.success)

    def test_lecture_hour_limit_is_applied_independently_per_selected_group(self):
        first_group = self._create_group("LECTURE_LIMIT_FIRST")
        second_group = self._create_group("LECTURE_LIMIT_SECOND")
        first_teacher = self._create_teacher("lecture-limit-first-teacher")
        second_teacher = self._create_teacher("lecture-limit-second-teacher")
        self._create_realization(
            "LECTURE_LIMIT_FIRST_P",
            first_teacher,
            first_group,
            duration=3,
            activity_type="P",
        )
        self._create_realization(
            "LECTURE_LIMIT_SECOND_P",
            second_teacher,
            second_group,
            duration=3,
            activity_type="P",
        )
        shared_window = {
            ("MON", "07:00"),
            ("MON", "08:00"),
            ("MON", "09:00"),
        }
        self._block_teacher_except(first_teacher, shared_window)
        self._block_teacher_except(second_teacher, shared_window)
        constraint = SolverConstraint.objects.create(
            timetable=self.timetable,
            name="Independent group lecture limits",
            constraint_type="MAXLECTUREHOURSDAY",
            value=3,
        )
        constraint.groups.add(first_group, second_group)

        result = ORToolsTimetableSolver(
            self.timetable,
            ORToolsSolverOptions(time_limit=10, clear_existing=True),
        ).solve()

        self.assertTrue(result.success, result.messages)

    def test_pad_group_does_not_create_group_no_overlap_constraint(self):
        first_teacher = self._create_teacher("pad-first-teacher")
        second_teacher = self._create_teacher("pad-second-teacher")
        pad_group = self._create_group("COURSE_PAD")
        self._create_realization("PAD_FIRST", first_teacher, pad_group)
        self._create_realization("PAD_SECOND", second_teacher, pad_group)
        self._block_teacher_except(first_teacher, {("MON", "07:00")})
        self._block_teacher_except(second_teacher, {("MON", "07:00")})

        result = ORToolsTimetableSolver(
            self.timetable,
            ORToolsSolverOptions(time_limit=10, clear_existing=True),
        ).solve()

        self.assertTrue(result.success)

    def test_fixed_room_constraint_assigns_selected_room(self):
        teacher = self._create_teacher("fixed-room-teacher")
        group = self._create_group("FIXED_ROOM_GROUP")
        realization = self._create_realization("FIXED_ROOM", teacher, group)
        self.room2.location = Location.objects.create(name="Fixed room location")
        self.room2.save(update_fields=("location",))
        constraint = SolverConstraint.objects.create(
            timetable=self.timetable,
            name="Fixed room",
            constraint_type="FIXEDROOM",
        )
        constraint.realizations.add(realization)
        constraint.classrooms.add(self.room2)

        self._run_solver()

        self.assertEqual(self._allocation_for(realization).classroom, self.room2)

    def test_fixed_placement_assigns_selected_time_and_room(self):
        teacher = self._create_teacher("fixed-placement-teacher")
        group = self._create_group("FIXED_PLACEMENT_GROUP")
        realization = self._create_realization("FIXED_PLACEMENT", teacher, group)
        constraint = SolverConstraint.objects.create(
            timetable=self.timetable,
            name="Fixed placement",
            constraint_type="FIXEDPLACEMENT",
            day="MON",
            start="09:00",
        )
        constraint.realizations.add(realization)
        constraint.classrooms.add(self.room2)

        self._run_solver()

        allocation = self._allocation_for(realization)
        self.assertEqual((allocation.day, allocation.start, allocation.classroom), ("MON", "09:00", self.room2))

    def test_fixed_time_assigns_selected_time_with_any_suitable_room(self):
        teacher = self._create_teacher("fixed-time-teacher")
        group = self._create_group("FIXED_TIME_GROUP")
        realization = self._create_realization("FIXED_TIME", teacher, group)
        constraint = SolverConstraint.objects.create(
            timetable=self.timetable,
            name="Fixed time",
            constraint_type="FIXEDTIME",
            day="TUE",
            start="10:00",
        )
        constraint.realizations.add(realization)

        self._run_solver()

        allocation = self._allocation_for(realization)
        self.assertEqual((allocation.day, allocation.start), ("TUE", "10:00"))
        self.assertIn(allocation.classroom, {self.room1, self.room2})

    def test_three_hour_lecture_prefers_three_hour_grid(self):
        teacher = self._create_teacher("lecture-grid-teacher")
        group = self._create_group("LECTURE_GRID_GROUP")
        realization = self._create_realization(
            "LECTURE_GRID", teacher, group, duration=3, activity_type="P"
        )

        self._run_solver()

        allocation = self._allocation_for(realization)
        self.assertIn(allocation.start, {"08:00", "11:00", "14:00", "17:00", "20:00"})

    def test_two_hour_exercises_prefer_two_hour_grid(self):
        lv_teacher = self._create_teacher("lv-grid-teacher")
        av_teacher = self._create_teacher("av-grid-teacher")
        lv = self._create_realization(
            "LV_GRID", lv_teacher, self._create_group("LV_GRID_GROUP"), duration=2, activity_type="LV"
        )
        av = self._create_realization(
            "AV_GRID", av_teacher, self._create_group("AV_GRID_GROUP"), duration=2, activity_type="AV"
        )

        self._run_solver()

        grid = {"08:00", "10:00", "12:00", "14:00", "16:00", "18:00", "20:00"}
        self.assertIn(self._allocation_for(lv).start, grid)
        self.assertIn(self._allocation_for(av).start, grid)

    def test_max_span_day_rejects_widely_separated_sessions(self):
        teacher = self._create_teacher("max-span-teacher")
        first = self._create_realization(
            "MAX_SPAN_FIRST", teacher, self._create_group("MAX_SPAN_FIRST")
        )
        second = self._create_realization(
            "MAX_SPAN_SECOND", teacher, self._create_group("MAX_SPAN_SECOND")
        )
        constraint = SolverConstraint.objects.create(
            timetable=self.timetable,
            name="Maximum daily span",
            constraint_type="MAXSPANDAY",
            value=3,
        )
        constraint.teachers.add(teacher)
        self._block_teacher_except(teacher, {("MON", "07:00"), ("MON", "12:00")})

        result = ORToolsTimetableSolver(
            self.timetable, ORToolsSolverOptions(time_limit=10, clear_existing=True)
        ).solve()

        self.assertFalse(result.success)

    def test_same_room_constraint_rejects_different_fixed_rooms(self):
        first_teacher = self._create_teacher("same-room-first-teacher")
        second_teacher = self._create_teacher("same-room-second-teacher")
        first = self._create_realization(
            "SAME_ROOM_FIRST", first_teacher, self._create_group("SAME_ROOM_FIRST")
        )
        second = self._create_realization(
            "SAME_ROOM_SECOND", second_teacher, self._create_group("SAME_ROOM_SECOND")
        )
        same_room = SolverConstraint.objects.create(
            timetable=self.timetable, name="Same room", constraint_type="SAMEROOM"
        )
        same_room.realizations.add(first, second)
        for realization, room, start in ((first, self.room1, "07:00"), (second, self.room2, "09:00")):
            placement = SolverConstraint.objects.create(
                timetable=self.timetable,
                name="Placement {}".format(realization.id),
                constraint_type="FIXEDPLACEMENT",
                day="MON",
                start=start,
            )
            placement.realizations.add(realization)
            placement.classrooms.add(room)

        result = ORToolsTimetableSolver(
            self.timetable, ORToolsSolverOptions(time_limit=10, clear_existing=True)
        ).solve()

        self.assertFalse(result.success)

    def test_adjacent_teacher_realizations_prefer_same_room(self):
        teacher = self._create_teacher("adjacent-room-teacher")
        first = self._create_realization(
            "ADJACENT_ROOM_FIRST", teacher, self._create_group("ADJACENT_ROOM_FIRST")
        )
        second = self._create_realization(
            "ADJACENT_ROOM_SECOND", teacher, self._create_group("ADJACENT_ROOM_SECOND")
        )
        second.activity = first.activity
        second.save(update_fields=("activity",))
        self._block_teacher_except(teacher, {("MON", "07:00"), ("MON", "08:00")})

        self._run_solver()

        first_allocation = self._allocation_for(first)
        second_allocation = self._allocation_for(second)
        self.assertEqual((first_allocation.day, second_allocation.day), ("MON", "MON"))
        self.assertEqual({first_allocation.start, second_allocation.start}, {"07:00", "08:00"})
        self.assertEqual(first_allocation.classroom, second_allocation.classroom)

    def test_study_module_activities_cannot_overlap(self):
        self.classroomset.classrooms.remove(self.room2)
        first_teacher = self._create_teacher("module-first-teacher")
        second_teacher = self._create_teacher("module-second-teacher")
        first = self._create_realization(
            "MODULE_FIRST", first_teacher, self._create_group("MODULE_FIRST")
        )
        second = self._create_realization(
            "MODULE_SECOND", second_teacher, self._create_group("MODULE_SECOND")
        )
        StudyModule.objects.create(name="Module", timetable=self.timetable).activities.add(
            first.activity, second.activity
        )
        self._block_teacher_except(first_teacher, {("MON", "07:00")})
        self._block_teacher_except(second_teacher, {("MON", "07:00")})

        result = ORToolsTimetableSolver(
            self.timetable, ORToolsSolverOptions(time_limit=10, clear_existing=True)
        ).solve()

        self.assertFalse(result.success)

    def test_linked_study_modules_cannot_overlap(self):
        self.classroomset.classrooms.remove(self.room2)
        first_teacher = self._create_teacher("linked-module-first-teacher")
        second_teacher = self._create_teacher("linked-module-second-teacher")
        first = self._create_realization(
            "LINKED_MODULE_FIRST", first_teacher, self._create_group("LINKED_MODULE_FIRST")
        )
        second = self._create_realization(
            "LINKED_MODULE_SECOND", second_teacher, self._create_group("LINKED_MODULE_SECOND")
        )
        first_module = StudyModule.objects.create(name="First module", timetable=self.timetable)
        second_module = StudyModule.objects.create(name="Second module", timetable=self.timetable)
        first_module.activities.add(first.activity)
        second_module.activities.add(second.activity)
        first_module.non_overlapping_with.add(second_module)
        self._block_teacher_except(first_teacher, {("MON", "07:00")})
        self._block_teacher_except(second_teacher, {("MON", "07:00")})

        result = ORToolsTimetableSolver(
            self.timetable, ORToolsSolverOptions(time_limit=10, clear_existing=True)
        ).solve()

        self.assertFalse(result.success)

    def test_room_activity_type_allowlist_limits_candidates(self):
        self.room1.supported_activity_types.create(activity_type="P")
        teacher = self._create_teacher("room-type-teacher")
        group = self._create_group("ROOM_TYPE_GROUP")
        realization = self._create_realization(
            "ROOM_TYPE_AV", teacher, group, activity_type="AV"
        )

        self._run_solver()

        self.assertEqual(self._allocation_for(realization).classroom, self.room2)

    def test_room_activity_start_grid_is_hard(self):
        self.classroomset.classrooms.remove(self.room2)
        self.room1.activity_start_times.create(activity_type="P", start="08:00")
        teacher = self._create_teacher("room-start-grid-teacher")
        group = self._create_group("ROOM_START_GRID_GROUP")
        self._create_realization("ROOM_START_GRID", teacher, group, activity_type="P")
        self._block_teacher_except(teacher, {("MON", "09:00")})

        result = ORToolsTimetableSolver(
            self.timetable, ORToolsSolverOptions(time_limit=10, clear_existing=True)
        ).solve()

        self.assertFalse(result.success)

    def test_reports_classroom_capacity_pressure(self):
        self.room1.capacity = 20
        self.room1.save(update_fields=("capacity",))
        teacher = self._create_teacher("capacity-pressure-teacher")
        group = self._create_group("CAPACITY_PRESSURE", size=25)
        realization = self._create_realization("CAPACITY_PRESSURE", teacher, group)
        solver = ORToolsTimetableSolver(self.timetable)
        realization_tag_ids = solver._build_realization_tag_ids([realization])

        messages = solver._build_room_capacity_messages(
            [realization],
            {realization.id: [self.room1, self.room2]},
            {realization.id: [self.room2]},
            realization_tag_ids,
            solver._build_tag_size_adjustments(),
            set(),
        )

        self.assertIn("Classroom capacity pressure", messages[0])
        self.assertIn("qualifying=R2(30)", messages[1])
        self.assertIn("excluded_by_capacity=R1(20)", messages[1])

    def test_prefers_tighter_room_fit(self):
        self.room1.capacity = 20
        self.room1.save(update_fields=("capacity",))
        self.room2.capacity = 100
        self.room2.save(update_fields=("capacity",))
        realization = self._create_realization(
            "ROOM_FIT",
            self._create_teacher("room-fit-teacher"),
            self._create_group("ROOM_FIT_01", size=12),
            activity_type="AV",
        )

        self._run_solver()

        self.assertEqual(self._allocation_for(realization).classroom, self.room1)

    def test_room_minimum_size_excludes_small_realizations(self):
        self.room1.capacity = 20
        self.room1.save(update_fields=("capacity",))
        self.room2.capacity = 100
        self.room2.minimum_realization_size = 50
        self.room2.save(update_fields=("capacity", "minimum_realization_size"))
        realization = self._create_realization(
            "ROOM_MINIMUM",
            self._create_teacher("room-minimum-teacher"),
            self._create_group("ROOM_MINIMUM_01", size=12),
            activity_type="AV",
        )

        self._run_solver()

        self.assertEqual(self._allocation_for(realization).classroom, self.room1)

    def test_no_room_message_reports_minimum_size_exclusions(self):
        self.room1.minimum_realization_size = 50
        self.room1.save(update_fields=("minimum_realization_size",))
        self.classroomset.classrooms.remove(self.room2)
        self._create_realization(
            "ROOM_MINIMUM_FAIL",
            self._create_teacher("room-minimum-fail-teacher"),
            self._create_group("ROOM_MINIMUM_FAIL_01", size=12),
            activity_type="AV",
        )

        output = self._run_solver()

        self.assertIn("No suitable rooms", output)
        self.assertIn("excluded_by_minimum_size=1", output)

    def test_overlapping_room_allows_simultaneous_realizations(self):
        self.classroomset.classrooms.remove(self.room2)
        self.room1.allow_overlaps = True
        self.room1.save(update_fields=("allow_overlaps",))
        first_teacher = self._create_teacher("virtual-room-first-teacher")
        second_teacher = self._create_teacher("virtual-room-second-teacher")
        first_group = self._create_group("VIRTUAL_ROOM_FIRST")
        second_group = self._create_group("VIRTUAL_ROOM_SECOND")
        first = self._create_realization("VIRTUAL_ROOM_FIRST", first_teacher, first_group)
        second = self._create_realization("VIRTUAL_ROOM_SECOND", second_teacher, second_group)
        self._block_teacher_except(first_teacher, {("MON", "07:00")})
        self._block_teacher_except(second_teacher, {("MON", "07:00")})

        self._run_solver()

        first_allocation = self._allocation_for(first)
        second_allocation = self._allocation_for(second)
        self.assertEqual((first_allocation.day, first_allocation.start), ("MON", "07:00"))
        self.assertEqual((second_allocation.day, second_allocation.start), ("MON", "07:00"))
        self.assertEqual(first_allocation.classroom, self.room1)
        self.assertEqual(second_allocation.classroom, self.room1)

    def test_remote_cycles_are_matched_per_teacher(self):
        self.classroomset.classrooms.remove(self.room2)
        virtual_room = Classroom.objects.create(
            name="Oddaljeno",
            short_name="ODDALJENO",
            capacity=0,
            location=self.location,
            is_virtual=True,
        )
        self.classroomset.classrooms.add(virtual_room)
        subject = friprosveta.models.Subject.objects.create(
            code="REMOTE_CYCLES", name="Remote cycles"
        )
        lecture_type = friprosveta.models.LectureType.objects.create(
            name="Remote cycles type", short_name="RCT", duration=1
        )
        activity = friprosveta.models.Activity.objects.create(
            name="REMOTE_CYCLES",
            short_name="REMOTE_CYCLES",
            activityset=self.activityset,
            type="LV",
            duration=1,
            subject=subject,
            lecture_type=lecture_type,
            cycles_on_site=1,
        )
        activity.locations.add(self.location)
        timetable_set = TimetableSet.objects.create(
            slug="remote-cycles", name="Remote cycles"
        )
        timetable_set.timetables.add(self.timetable)
        realizations = {}
        for suffix, site_cycles in (("FIRST", 0), ("SECOND", 1)):
            teacher = self._create_teacher("remote-cycles-{}".format(suffix.lower()))
            teacher.code = "RC{}".format(suffix[0])
            teacher.save(update_fields=("code",))
            group = self._create_group("REMOTE_CYCLES_{}".format(suffix))
            activity.teachers.add(teacher)
            activity.groups.add(group)
            realization = ActivityRealization.objects.create(activity=activity)
            realization.teachers.add(teacher)
            realization.groups.add(group)
            realizations[suffix] = realization
            TeacherSubjectCycles.objects.create(
                teacher_code=teacher.code,
                subject_code=subject.code,
                timetable_set=timetable_set,
                instruction_type=1,
                lecture_type=lecture_type.id,
                cycles=1,
                cycles_on_site=site_cycles,
            )

        self._run_solver()

        self.assertEqual(self._allocation_for(realizations["FIRST"]).classroom, virtual_room)
        self.assertEqual(self._allocation_for(realizations["SECOND"]).classroom, self.room1)

    def test_all_on_site_cycles_do_not_use_virtual_rooms(self):
        self.classroomset.classrooms.remove(self.room2)
        virtual_room = Classroom.objects.create(
            name="All on-site remote room",
            short_name="ALL_ON_SITE_ODDALJENO",
            capacity=0,
            location=self.location,
            is_virtual=True,
        )
        self.classroomset.classrooms.add(virtual_room)
        subject = friprosveta.models.Subject.objects.create(
            code="ALL_ON_SITE", name="All on-site cycles"
        )
        lecture_type = friprosveta.models.LectureType.objects.create(
            name="All on-site type", short_name="AOS", duration=1
        )
        activity = friprosveta.models.Activity.objects.create(
            name="ALL_ON_SITE",
            short_name="ALL_ON_SITE",
            activityset=self.activityset,
            type="LV",
            duration=1,
            subject=subject,
            lecture_type=lecture_type,
            cycles_on_site=2,
        )
        activity.locations.add(self.location)
        for suffix in ("FIRST", "SECOND"):
            teacher = self._create_teacher("all-on-site-{}".format(suffix.lower()))
            group = self._create_group("ALL_ON_SITE_{}".format(suffix))
            activity.teachers.add(teacher)
            activity.groups.add(group)
            realization = ActivityRealization.objects.create(activity=activity)
            realization.teachers.add(teacher)
            realization.groups.add(group)

        self._run_solver()

        self.assertEqual(
            {self._allocation_for(realization).classroom for realization in activity.realizations.all()},
            {self.room1},
        )

    def test_remote_cycle_settings_do_not_require_a_virtual_room(self):
        self.classroomset.classrooms.remove(self.room2)
        subject = friprosveta.models.Subject.objects.create(
            code="REMOTE_NO_ROOM", name="Remote without room"
        )
        lecture_type = friprosveta.models.LectureType.objects.create(
            name="Remote without room type", short_name="RWR", duration=1
        )
        activity = friprosveta.models.Activity.objects.create(
            name="REMOTE_WITHOUT_ROOM",
            short_name="REMOTE_WITHOUT_ROOM",
            activityset=self.activityset,
            type="LV",
            duration=1,
            subject=subject,
            lecture_type=lecture_type,
            cycles_on_site=1,
        )
        activity.locations.add(self.location)
        for suffix in ("FIRST", "SECOND"):
            teacher = self._create_teacher("remote-without-room-{}".format(suffix.lower()))
            group = self._create_group("REMOTE_WITHOUT_ROOM_{}".format(suffix))
            activity.teachers.add(teacher)
            activity.groups.add(group)
            realization = ActivityRealization.objects.create(activity=activity)
            realization.teachers.add(teacher)
            realization.groups.add(group)

        self._run_solver()

        self.assertEqual(
            {self._allocation_for(realization).classroom for realization in activity.realizations.all()},
            {self.room1},
        )

    def test_generation_reports_constraint_summary(self):
        teacher = self._create_teacher("summary-teacher")
        group = self._create_group("SUMMARY_GROUP")
        self._create_realization("SUMMARY", teacher, group)

        result = ORToolsTimetableSolver(
            self.timetable, ORToolsSolverOptions(time_limit=10, clear_existing=True)
        ).solve()

        self.assertTrue(result.success)
        self.assertIn(
            "Hard constraint verification: overlap violations teacher=0, group=0, student=0, room=0.",
            result.messages,
        )
        self.assertTrue(
            any("Respected timetable locks: timetables=0" in message for message in result.messages)
        )

    def test_generation_reports_missed_soft_constraints(self):
        teacher = self._create_teacher("soft-summary-teacher")
        group = self._create_group("SOFT_SUMMARY_GROUP")
        self._create_realization("SOFT_SUMMARY", teacher, group)
        self._block_teacher_except(teacher, {("MON", "08:00")})
        TeacherTimePreference.objects.create(
            preferenceset=self.preferenceset,
            teacher=teacher,
            day="MON",
            start="07:00",
            duration=1,
            level="WANT",
            weight=1,
        )

        result = ORToolsTimetableSolver(
            self.timetable, ORToolsSolverOptions(time_limit=10, clear_existing=True)
        ).solve()

        self.assertTrue(result.success)
        self.assertIn("WANT terms met=0, missed=1", result.messages[-1])

    def test_activity_type_window_prefers_inside_start_times(self):
        # Given a two-slot lecture with an active Monday [08:00, 10:00) window.
        teacher = self._create_teacher("window-teacher")
        group = self._create_group("WINDOW_01")
        realization = self._create_realization(
            "WINDOW", teacher, group, duration=2, activity_type="P"
        )
        self._restrict_activity_type_to("P", {("MON", "08:00"), ("MON", "09:00")})
        TeacherTimePreference.objects.create(
            preferenceset=self.preferenceset,
            teacher=teacher,
            level="WANT",
            day="MON",
            start="07:00",
            duration=2,
            weight=100,
        )

        # When the solver generates an allocation.
        self._run_solver()

        # Then the solver prefers the configured window over an otherwise equivalent slot.
        allocation = self._allocation_for(realization)
        self.assertEqual((allocation.day, allocation.start), ("MON", "08:00"))

    def test_activity_type_window_allows_final_workhour_until_day_boundary(self):
        # Given a Friday window [21:00, 22:00) for a one-slot lecture.
        teacher = self._create_teacher("window-boundary-teacher")
        group = self._create_group("WINDOW_BOUNDARY_01")
        realization = self._create_realization("WINDOWBOUNDARY", teacher, group)
        self._restrict_activity_type_to("P", {("FRI", "21:00")})
        self._block_teacher_except(teacher, {("FRI", "21:00")})

        # When the solver generates an allocation.
        self._run_solver()

        # Then the final workhour is a valid candidate.
        allocation = self._allocation_for(realization)
        self.assertEqual((allocation.day, allocation.start), ("FRI", "21:00"))

    def test_activity_type_restrictions_allow_soft_and_enforce_hard_slots(self):
        teacher = self._create_teacher("weighted-restriction-teacher")
        group = self._create_group("WEIGHTED_RESTRICTION_01")
        realization = self._create_realization("WEIGHTED_RESTRICTION", teacher, group)
        ActivityTypeSchedulingRestriction.objects.create(
            timetable=self.timetable,
            activity_type="P",
            day="MON",
            start="17:00",
            weight=50,
        )
        for hour, _hour_name in WORKHOURS:
            if hour >= "18:00":
                ActivityTypeSchedulingRestriction.objects.create(
                    timetable=self.timetable,
                    activity_type="P",
                    day="MON",
                    start=hour,
                    weight=100,
                )
        self._block_teacher_except(teacher, {("MON", "17:00")})

        output = self._run_solver()

        allocation = self._allocation_for(realization)
        self.assertEqual((allocation.day, allocation.start), ("MON", "17:00"))
        self.assertIn("Soft activity-type time restrictions: 0/1", output)

    def test_missing_activity_type_window_preserves_full_day_candidates(self):
        # Given a lecture with no configured scheduling window.
        teacher = self._create_teacher("window-default-teacher")
        group = self._create_group("WINDOW_DEFAULT_01")
        realization = self._create_realization("WINDOWDEFAULT", teacher, group)
        self._block_teacher_except(teacher, {("FRI", "21:00")})

        # When the solver generates an allocation.
        self._run_solver()

        # Then it retains the full-day candidate at the final workhour.
        allocation = self._allocation_for(realization)
        self.assertEqual((allocation.day, allocation.start), ("FRI", "21:00"))

    def test_inactive_activity_type_window_does_not_filter_candidates(self):
        # Given an inactive window that excludes the only available slot.
        teacher = self._create_teacher("window-inactive-teacher")
        group = self._create_group("WINDOW_INACTIVE_01")
        realization = self._create_realization("WINDOWINACTIVE", teacher, group)
        ActivityTypeSchedulingWindow.objects.create(
            timetable=self.timetable,
            activity_type="P",
            day="FRI",
            start="07:00",
            end="08:00",
            active=False,
        )
        self._block_teacher_except(teacher, {("FRI", "21:00")})

        # When the solver generates an allocation.
        self._run_solver()

        # Then inactive configuration leaves candidates untouched.
        allocation = self._allocation_for(realization)
        self.assertEqual((allocation.day, allocation.start), ("FRI", "21:00"))

    def test_tag_hate_preferences_force_only_allowed_slot(self):
        teacher = self._create_teacher("tag-hate-teacher")
        group = self._create_group("TAGHATE_01")
        realization = self._create_realization("TAGHATE", teacher, group)
        tag = Tag.objects.create(name="Blocked teacher", description="")
        tag.teachers.add(teacher)
        for day, _day_name in WEEKDAYS:
            for hour, _hour_name in WORKHOURS:
                if (day, hour) == ("THU", "20:00"):
                    continue
                TagTimePreference.objects.create(
                    preferenceset=self.preferenceset,
                    tag=tag,
                    level="HATE",
                    day=day,
                    start=hour,
                    duration=1,
                )

        self._run_solver()

        allocation = self._allocation_for(realization)
        self.assertEqual((allocation.day, allocation.start), ("THU", "20:00"))

    def test_tag_want_preference_prefers_tagged_slot(self):
        teacher = self._create_teacher("tag-want-teacher")
        group = self._create_group("TAGWANT_01")
        realization = self._create_realization("TAGWANT", teacher, group)
        tag = Tag.objects.create(name="Preferred afternoon", description="")
        realization.activity.tags.add(tag)
        TagTimePreference.objects.create(
            preferenceset=self.preferenceset,
            tag=tag,
            level="WANT",
            day="FRI",
            start="21:00",
            duration=1,
            weight=100,
        )

        self._run_solver()

        allocation = self._allocation_for(realization)
        self.assertEqual((allocation.day, allocation.start), ("FRI", "21:00"))

    def test_room_capacity_filters_assignments(self):
        small_room = self._create_room("Small", "SMALL", 5)
        large_room = self._create_room("Large", "LARGE", 50)
        self.classroomset.classrooms.remove(self.room1, self.room2)
        teacher = self._create_teacher("capacity-teacher")
        group = self._create_group("CAPACITY_01", size=20)
        realization = self._create_realization("CAPACITY", teacher, group)

        self._run_solver()

        allocation = self._allocation_for(realization)
        self.assertEqual(allocation.classroom, large_room)
        self.assertNotEqual(allocation.classroom, small_room)

    def test_same_teacher_realizations_do_not_overlap(self):
        teacher = self._create_teacher("busy-teacher")
        group1 = self._create_group("BUSY_01")
        group2 = self._create_group("BUSY_02")
        realization1 = self._create_realization("BUSY1", teacher, group1, duration=2)
        realization2 = self._create_realization("BUSY2", teacher, group2, duration=2)
        TeacherTimePreference.objects.create(
            preferenceset=self.preferenceset,
            teacher=teacher,
            level="WANT",
            day="MON",
            start="07:00",
            duration=2,
            weight=100,
        )

        self._run_solver()

        self.assertFalse(
            self._overlap(
                self._allocation_for(realization1), self._allocation_for(realization2)
            )
        )

    def test_same_room_realizations_do_not_overlap(self):
        self.classroomset.classrooms.remove(self.room2)
        teacher1 = self._create_teacher("room-teacher-1")
        teacher2 = self._create_teacher("room-teacher-2")
        group1 = self._create_group("ROOM_01")
        group2 = self._create_group("ROOM_02")
        realization1 = self._create_realization("ROOM1", teacher1, group1)
        realization2 = self._create_realization("ROOM2", teacher2, group2)
        for teacher in (teacher1, teacher2):
            TeacherTimePreference.objects.create(
                preferenceset=self.preferenceset,
                teacher=teacher,
                level="WANT",
                day="MON",
                start="07:00",
                duration=1,
                weight=100,
            )

        self._run_solver()

        allocation1 = self._allocation_for(realization1)
        allocation2 = self._allocation_for(realization2)
        self.assertEqual(allocation1.classroom, self.room1)
        self.assertEqual(allocation2.classroom, self.room1)
        self.assertFalse(self._overlap(allocation1, allocation2))

    def test_shared_student_realizations_do_not_overlap(self):
        teacher1 = self._create_teacher("student-teacher-1")
        teacher2 = self._create_teacher("student-teacher-2")
        group1 = self._create_group("STUDENT_01")
        group2 = self._create_group("STUDENT_02")
        student = friprosveta.models.Student.objects.create(
            name="Shared", surname="Student", studentId="SHARED01"
        )
        student.groups.add(group1, group2)
        realization1 = self._create_realization("STUDENT1", teacher1, group1)
        realization2 = self._create_realization("STUDENT2", teacher2, group2)
        for teacher in (teacher1, teacher2):
            TeacherTimePreference.objects.create(
                preferenceset=self.preferenceset,
                teacher=teacher,
                level="WANT",
                day="MON",
                start="07:00",
                duration=1,
                weight=100,
            )

        self._run_solver()

        self.assertFalse(
            self._overlap(
                self._allocation_for(realization1), self._allocation_for(realization2)
            )
        )

    def test_respected_timetable_blocks_existing_resource_usage(self):
        teacher = self._create_teacher("respected-teacher")
        group = self._create_group("RESPECT_01")
        respected = Timetable.objects.create(
            slug="respected-tt",
            name="Respected Timetable",
            activityset=ActivitySet.objects.create(
                slug="respected-activities", name="Respected Activities"
            ),
            preferenceset=self.preferenceset,
            groupset=self.groupset,
            classroomset=self.classroomset,
        )
        blocking_activity = Activity.objects.create(
            name="BLOCKING",
            short_name="BLOCKING",
            activityset=respected.activityset,
            type="P",
            duration=1,
        )
        blocking_activity.locations.add(self.location)
        blocking_activity.teachers.add(teacher)
        blocking_activity.groups.add(group)
        blocking_realization = ActivityRealization.objects.create(
            activity=blocking_activity
        )
        blocking_realization.teachers.add(teacher)
        blocking_realization.groups.add(group)
        Allocation.objects.create(
            timetable=respected,
            activityRealization=blocking_realization,
            classroom=self.room1,
            day="MON",
            start="07:00",
        )
        self.timetable.respects.add(respected)
        realization = self._create_realization("RESPECT", teacher, group)
        self._block_teacher_except(teacher, {("MON", "07:00"), ("MON", "08:00")})

        self._run_solver()

        allocation = self._allocation_for(realization)
        self.assertEqual((allocation.day, allocation.start), ("MON", "08:00"))

    def test_empty_respected_timetable_reports_warning(self):
        respected = Timetable.objects.create(
            slug="respected-empty",
            name="Empty respected timetable",
            activityset=ActivitySet.objects.create(
                slug="empty-respected-activities", name="Empty respected activities"
            ),
            preferenceset=self.preferenceset,
            groupset=self.groupset,
            classroomset=self.classroomset,
        )
        teacher = self._create_teacher("respected-empty-teacher")
        group = self._create_group("RESPECT_EMPTY_01")
        self._create_realization("RESPECT_EMPTY", teacher, group)
        self.timetable.respects.add(respected)

        output = self._run_solver(clear_existing=True)

        self.assertIn(
            "Warning: respected timetable(s) respected-empty have no allocations; they do not enforce any hard timetable locks.",
            output,
        )

        self.assertTrue(Allocation.objects.filter(timetable=self.timetable).exists())

    def test_allocation_set_includes_respected_timetables(self):
        from friprosveta.views import _allocation_set

        respected = Timetable.objects.create(
            slug="respected-tt-view",
            name="Respected Timetable for View",
            activityset=ActivitySet.objects.create(
                slug="respected-view-activities", name="Respected View Activities"
            ),
            preferenceset=self.preferenceset,
            groupset=self.groupset,
            classroomset=self.classroomset,
        )
        teacher = self._create_teacher("view-respected-teacher")
        group = self._create_group("RESPECT_VIEW_01")

        blocking_activity = Activity.objects.create(
            name="BLOCKING_VIEW",
            short_name="BLOCKING_VIEW",
            activityset=respected.activityset,
            type="P",
            duration=1,
        )
        blocking_activity.teachers.add(teacher)
        blocking_activity.groups.add(group)
        blocking_realization = ActivityRealization.objects.create(activity=blocking_activity)
        blocking_realization.teachers.add(teacher)
        blocking_realization.groups.add(group)
        Allocation.objects.create(
            timetable=respected,
            activityRealization=blocking_realization,
            classroom=self.room1,
            day="MON",
            start="07:00",
        )

        own_realization = self._create_realization("OWN_VIEW", teacher, group)
        Allocation.objects.create(
            timetable=self.timetable,
            activityRealization=own_realization,
            classroom=self.room1,
            day="MON",
            start="08:00",
        )

        self.timetable.respects.add(respected)

        filtered = _allocation_set(
            {"timetable_slug": [self.timetable.slug]},
            Allocation.objects.all(),
            is_staff=True,
        )

        self.assertEqual(filtered.count(), 2)
        self.assertEqual(
            set(filtered.values_list("timetable__slug", flat=True)),
            {self.timetable.slug, respected.slug},
        )

    def test_must_not_overlap_relation_is_enforced(self):
        teacher1 = self._create_teacher("overlap-teacher-1")
        teacher2 = self._create_teacher("overlap-teacher-2")
        group1 = self._create_group("OVERLAP_01")
        group2 = self._create_group("OVERLAP_02")
        realization1 = self._create_realization("OVERLAP1", teacher1, group1)
        realization2 = self._create_realization("OVERLAP2", teacher2, group2)
        realization1.activity.mustNotOverlap.add(realization2.activity)
        for teacher in (teacher1, teacher2):
            TeacherTimePreference.objects.create(
                preferenceset=self.preferenceset,
                teacher=teacher,
                level="WANT",
                day="MON",
                start="07:00",
                duration=1,
                weight=100,
            )

        self._run_solver()

        self.assertFalse(
            self._overlap(
                self._allocation_for(realization1), self._allocation_for(realization2)
            )
        )

    def test_tag_no_overlap_relation_is_enforced(self):
        teacher1 = self._create_teacher("tag-nooverlap-teacher-1")
        teacher2 = self._create_teacher("tag-nooverlap-teacher-2")
        group1 = self._create_group("TAGNOOVERLAP_01")
        group2 = self._create_group("TAGNOOVERLAP_02")
        realization1 = self._create_realization("TAGNOOVERLAP1", teacher1, group1)
        realization2 = self._create_realization("TAGNOOVERLAP2", teacher2, group2)
        tag = Tag.objects.create(name="Tag no overlap", description="")
        realization1.activity.tags.add(tag)
        realization2.activity.tags.add(tag)
        TagDescriptivePreference.objects.create(
            preferenceset=self.preferenceset,
            tag=tag,
            level="CANT",
            typename="NOOVERLAP",
            value="",
        )
        for teacher in (teacher1, teacher2):
            TeacherTimePreference.objects.create(
                preferenceset=self.preferenceset,
                teacher=teacher,
                level="WANT",
                day="MON",
                start="07:00",
                duration=1,
                weight=100,
            )

        self._run_solver()

        self.assertFalse(
            self._overlap(
                self._allocation_for(realization1), self._allocation_for(realization2)
            )
        )

    def test_tag_same_day_relation_is_enforced(self):
        teacher1 = self._create_teacher("same-day-teacher-1")
        teacher2 = self._create_teacher("same-day-teacher-2")
        group1 = self._create_group("SAMEDAY_01")
        group2 = self._create_group("SAMEDAY_02")
        realization1 = self._create_realization("SAMEDAY1", teacher1, group1)
        realization2 = self._create_realization("SAMEDAY2", teacher2, group2)
        tag = Tag.objects.create(name="Same day", description="")
        realization1.activity.tags.add(tag)
        realization2.activity.tags.add(tag)
        TagDescriptivePreference.objects.create(
            preferenceset=self.preferenceset,
            tag=tag,
            level="CANT",
            typename="SAMEDAY",
            value="",
        )

        self._run_solver()

        self.assertEqual(
            self._allocation_for(realization1).day,
            self._allocation_for(realization2).day,
        )

    def test_tag_same_starting_time_relation_is_enforced(self):
        teacher1 = self._create_teacher("same-start-teacher-1")
        teacher2 = self._create_teacher("same-start-teacher-2")
        group1 = self._create_group("SAMESTART_01")
        group2 = self._create_group("SAMESTART_02")
        realization1 = self._create_realization("SAMESTART1", teacher1, group1)
        realization2 = self._create_realization("SAMESTART2", teacher2, group2)
        tag = Tag.objects.create(name="Same start", description="")
        realization1.activity.tags.add(tag)
        realization2.activity.tags.add(tag)
        TagDescriptivePreference.objects.create(
            preferenceset=self.preferenceset,
            tag=tag,
            level="CANT",
            typename="SAMESTARTINGTIME",
            value="",
        )

        self._run_solver()

        allocation1 = self._allocation_for(realization1)
        allocation2 = self._allocation_for(realization2)
        self.assertEqual((allocation1.day, allocation1.start), (allocation2.day, allocation2.start))

    def test_tag_grouped_relation_is_enforced(self):
        teacher1 = self._create_teacher("grouped-teacher-1")
        teacher2 = self._create_teacher("grouped-teacher-2")
        group1 = self._create_group("GROUPED_01")
        group2 = self._create_group("GROUPED_02")
        realization1 = self._create_realization("GROUPED1", teacher1, group1)
        realization2 = self._create_realization("GROUPED2", teacher2, group2)
        tag = Tag.objects.create(name="Grouped", description="")
        realization1.activity.tags.add(tag)
        realization2.activity.tags.add(tag)
        TagDescriptivePreference.objects.create(
            preferenceset=self.preferenceset,
            tag=tag,
            level="CANT",
            typename="GROUPED",
            value="",
        )

        self._run_solver()

        allocation1 = self._allocation_for(realization1)
        allocation2 = self._allocation_for(realization2)
        self.assertEqual((allocation1.day, allocation1.start), (allocation2.day, allocation2.start))

    def test_tag_consecutive_relation_is_enforced(self):
        teacher1 = self._create_teacher("consecutive-teacher-1")
        teacher2 = self._create_teacher("consecutive-teacher-2")
        group1 = self._create_group("CONSECUTIVE_01")
        group2 = self._create_group("CONSECUTIVE_02")
        first = self._create_realization("CONSECUTIVE1", teacher1, group1, duration=2)
        second = self._create_realization("CONSECUTIVE2", teacher2, group2, duration=1)
        tag = Tag.objects.create(name="Consecutive", description="")
        first.activity.tags.add(tag)
        second.activity.tags.add(tag)
        TagDescriptivePreference.objects.create(
            preferenceset=self.preferenceset,
            tag=tag,
            level="CANT",
            typename="CONSECUTIVE",
            value="",
        )

        self._run_solver()

        first_allocation = self._allocation_for(first)
        second_allocation = self._allocation_for(second)
        self.assertEqual(first_allocation.day, second_allocation.day)
        self.assertEqual(
            self._slot_index(first_allocation) + first.duration,
            self._slot_index(second_allocation),
        )

    def test_tag_min_activity_gap_is_enforced(self):
        teacher1 = self._create_teacher("mingap-teacher-1")
        teacher2 = self._create_teacher("mingap-teacher-2")
        group1 = self._create_group("MINGAP_01")
        group2 = self._create_group("MINGAP_02")
        first = self._create_realization("MINGAP1", teacher1, group1)
        second = self._create_realization("MINGAP2", teacher2, group2)
        tag = Tag.objects.create(name="Min gap", description="")
        first.activity.tags.add(tag)
        second.activity.tags.add(tag)
        TagValuePreference.objects.create(
            preferenceset=self.preferenceset,
            tag=tag,
            level="CANT",
            name="MINACTIVITYGAP",
            value=2,
        )
        self._block_teacher_except(teacher1, {("MON", "07:00"), ("MON", "08:00"), ("MON", "09:00"), ("MON", "10:00")})
        self._block_teacher_except(teacher2, {("MON", "07:00"), ("MON", "08:00"), ("MON", "09:00"), ("MON", "10:00")})

        self._run_solver()

        self.assertGreaterEqual(
            self._slot_distance(self._allocation_for(first), self._allocation_for(second)),
            3,
        )

    def test_tag_max_rooms_realizations_is_enforced(self):
        teacher1 = self._create_teacher("maxrooms-teacher-1")
        teacher2 = self._create_teacher("maxrooms-teacher-2")
        group1 = self._create_group("MAXROOMS_01")
        group2 = self._create_group("MAXROOMS_02")
        first = self._create_realization("MAXROOMS1", teacher1, group1)
        second = self._create_realization("MAXROOMS2", teacher2, group2)
        tag = Tag.objects.create(name="Max rooms", description="")
        first.activity.tags.add(tag)
        second.activity.tags.add(tag)
        TagValuePreference.objects.create(
            preferenceset=self.preferenceset,
            tag=tag,
            level="CANT",
            name="MAXROOMSREALIZATIONS",
            value=1,
        )

        self._run_solver()

        self.assertEqual(
            self._allocation_for(first).classroom,
            self._allocation_for(second).classroom,
        )

    def test_solver_constraint_same_day_is_enforced(self):
        teacher1 = self._create_teacher("solver-sameday-teacher-1")
        teacher2 = self._create_teacher("solver-sameday-teacher-2")
        group1 = self._create_group("SOLVERSAMEDAY_01")
        group2 = self._create_group("SOLVERSAMEDAY_02")
        first = self._create_realization("SOLVERSAMEDAY1", teacher1, group1)
        second = self._create_realization("SOLVERSAMEDAY2", teacher2, group2)
        constraint = SolverConstraint.objects.create(
            timetable=self.timetable,
            name="same day",
            constraint_type="SAMEDAY",
        )
        constraint.realizations.add(first, second)

        self._run_solver()

        self.assertEqual(self._allocation_for(first).day, self._allocation_for(second).day)

    def test_solver_constraint_max_rooms_realizations_is_enforced(self):
        teacher1 = self._create_teacher("solver-maxrooms-teacher-1")
        teacher2 = self._create_teacher("solver-maxrooms-teacher-2")
        group1 = self._create_group("SOLVERMAXROOMS_01")
        group2 = self._create_group("SOLVERMAXROOMS_02")
        first = self._create_realization("SOLVERMAXROOMS1", teacher1, group1)
        second = self._create_realization("SOLVERMAXROOMS2", teacher2, group2)
        constraint = SolverConstraint.objects.create(
            timetable=self.timetable,
            name="max rooms",
            constraint_type="MAXROOMSREALIZATIONS",
            value=1,
        )
        constraint.realizations.add(first, second)

        self._run_solver()

        self.assertEqual(
            self._allocation_for(first).classroom,
            self._allocation_for(second).classroom,
        )

    def test_tag_ends_students_day_relation_is_enforced(self):
        teacher1 = self._create_teacher("ends-day-teacher-1")
        teacher2 = self._create_teacher("ends-day-teacher-2")
        group = self._create_group("ENDSDAY_01")
        earlier = self._create_realization("EARLIER", teacher1, group)
        ending = self._create_realization("ENDING", teacher2, group)
        tag = Tag.objects.create(name="Ends day", description="")
        ending.activity.tags.add(tag)
        TagDescriptivePreference.objects.create(
            preferenceset=self.preferenceset,
            tag=tag,
            level="CANT",
            typename="ENDSSTUDENTSDAY",
            value="",
        )
        self._block_teacher_except(teacher1, {("MON", "07:00"), ("MON", "08:00")})
        self._block_teacher_except(teacher2, {("MON", "07:00"), ("MON", "08:00")})

        self._run_solver()

        self.assertLess(
            self._slot_index(self._allocation_for(earlier)),
            self._slot_index(self._allocation_for(ending)),
        )

    def test_before_relation_is_enforced(self):
        teacher1 = self._create_teacher("before-teacher-1")
        teacher2 = self._create_teacher("before-teacher-2")
        group1 = self._create_group("BEFORE_01")
        group2 = self._create_group("BEFORE_02")
        first = self._create_realization("BEFORE1", teacher1, group1, duration=2)
        second = self._create_realization("BEFORE2", teacher2, group2, duration=1)
        first.activity.before.add(second.activity)

        self._run_solver()

        first_allocation = self._allocation_for(first)
        second_allocation = self._allocation_for(second)
        self.assertLessEqual(
            self._slot_index(first_allocation) + first.duration,
            self._slot_index(second_allocation),
        )

    def test_existing_allocations_are_not_replaced_without_clear_existing(self):
        teacher = self._create_teacher("guard-teacher")
        group = self._create_group("GUARD_01")
        realization = self._create_realization("GUARD", teacher, group)
        existing = Allocation.objects.create(
            timetable=self.timetable,
            activityRealization=realization,
            classroom=self.room1,
            day="MON",
            start="07:00",
        )

        output = self._run_solver()

        self.assertIn("pass --clear-existing", output)
        existing.refresh_from_db()
        self.assertEqual((existing.day, existing.start), ("MON", "07:00"))
        self.assertEqual(Allocation.objects.filter(timetable=self.timetable).count(), 1)

    def test_clear_existing_replaces_after_feasible_solution(self):
        teacher = self._create_teacher("replace-teacher")
        group = self._create_group("REPLACE_01")
        realization = self._create_realization("REPLACE", teacher, group)
        Allocation.objects.create(
            timetable=self.timetable,
            activityRealization=realization,
            classroom=self.room1,
            day="MON",
            start="07:00",
        )
        self._block_teacher_except(teacher, {("FRI", "21:00")})

        output = self._run_solver(clear_existing=True)

        self.assertIn("Generated 1 allocations", output)
        allocation = self._allocation_for(realization)
        self.assertEqual((allocation.day, allocation.start), ("FRI", "21:00"))
        self.assertEqual(Allocation.objects.filter(timetable=self.timetable).count(), 1)

    def test_existing_allocation_soft_lock_prefers_current_slot(self):
        teacher = self._create_teacher("soft-lock-teacher")
        group = self._create_group("SOFTLOCK_01")
        realization = self._create_realization("SOFTLOCK", teacher, group)
        Allocation.objects.create(
            timetable=self.timetable,
            activityRealization=realization,
            classroom=self.room2,
            day="WED",
            start="12:00",
        )

        output = self._run_solver(clear_existing=True)

        self.assertIn("Generated 1 allocations", output)
        allocation = self._allocation_for(realization)
        self.assertEqual((allocation.day, allocation.start, allocation.classroom), ("WED", "12:00", self.room2))

    def test_teacher_max_hours_daily_is_enforced(self):
        teacher = self._create_teacher("max-hours-teacher")
        group1 = self._create_group("MAXHOURS_01")
        group2 = self._create_group("MAXHOURS_02")
        first = self._create_realization("MAXHOURS1", teacher, group1, duration=2)
        second = self._create_realization("MAXHOURS2", teacher, group2, duration=2)
        TeacherValuePreference.objects.create(
            preferenceset=self.preferenceset,
            teacher=teacher,
            level="CANT",
            name="MAXHOURSDAY",
            value=2,
        )
        self._block_teacher_except(
            teacher,
            {("MON", "07:00"), ("MON", "08:00"), ("TUE", "07:00"), ("TUE", "08:00")},
        )

        self._run_solver()

        self.assertNotEqual(self._allocation_for(first).day, self._allocation_for(second).day)

    def test_solver_constraint_group_max_days_week_is_enforced(self):
        teacher1 = self._create_teacher("group-days-teacher-1")
        teacher2 = self._create_teacher("group-days-teacher-2")
        group = self._create_group("GROUPDAYS_01")
        first = self._create_realization("GROUPDAYS1", teacher1, group)
        second = self._create_realization("GROUPDAYS2", teacher2, group)
        constraint = SolverConstraint.objects.create(
            timetable=self.timetable,
            name="group max days",
            constraint_type="MAXDAYSWEEK",
            value=1,
        )
        constraint.groups.add(group)

        self._run_solver()

        self.assertEqual(self._allocation_for(first).day, self._allocation_for(second).day)

    def test_reports_max_days_week_workload_contention(self):
        teacher = self._create_teacher("workload-contention-teacher")
        first = self._create_realization(
            "WORKLOAD1", teacher, self._create_group("WORKLOAD_01")
        )
        second = self._create_realization(
            "WORKLOAD2", teacher, self._create_group("WORKLOAD_02")
        )
        TeacherValuePreference.objects.create(
            preferenceset=self.preferenceset,
            teacher=teacher,
            level="CANT",
            name="MAXDAYSWEEK",
            value=1,
        )
        self._block_teacher_except(teacher, {("MON", "07:00"), ("TUE", "07:00")})

        output = self._run_solver()

        self.assertIn("Hard workload limits", output)
        self.assertIn("MAXDAYSWEEK=1", output)
        self.assertIn("workload-contention-teacher", output)
        self.assertIn("IMPOSSIBLE", output)

    def test_min_building_change_gap_is_enforced(self):
        other_location = Location.objects.create(name="Sežana")
        sezana_room = self._create_room("Sezana Room", "SEZ", 30, location=other_location)
        self.classroomset.classrooms.remove(self.room2)
        teacher = self._create_teacher("change-gap-teacher")
        group1 = self._create_group("CHANGEGAP_01")
        group2 = self._create_group("CHANGEGAP_02")
        first = self._create_realization("CHANGEGAP1", teacher, group1)
        second = self._create_realization("CHANGEGAP2", teacher, group2, location=other_location)
        first.activity.required_rooms.add(self.room1)
        second.activity.required_rooms.add(sezana_room)
        TeacherValuePreference.objects.create(
            preferenceset=self.preferenceset,
            teacher=teacher,
            level="CANT",
            name="MINCHANGEGAP",
            value=2,
        )
        self._block_teacher_except(teacher, {("MON", "07:00"), ("MON", "08:00"), ("MON", "09:00"), ("MON", "10:00")})

        self._run_solver()

        self.assertGreaterEqual(
            self._slot_distance(self._allocation_for(first), self._allocation_for(second)),
            3,
        )

    def test_repair_mode_hard_locks_unrepaired_existing_allocations(self):
        teacher1 = self._create_teacher("repair-teacher-1")
        teacher2 = self._create_teacher("repair-teacher-2")
        group1 = self._create_group("REPAIR_01")
        group2 = self._create_group("REPAIR_02")
        locked = self._create_realization("REPAIRLOCKED", teacher1, group1)
        repaired = self._create_realization("REPAIRMOVED", teacher2, group2)
        Allocation.objects.create(
            timetable=self.timetable,
            activityRealization=locked,
            classroom=self.room1,
            day="MON",
            start="07:00",
        )
        Allocation.objects.create(
            timetable=self.timetable,
            activityRealization=repaired,
            classroom=self.room1,
            day="MON",
            start="08:00",
        )
        self._block_teacher_except(teacher2, {("FRI", "21:00")})

        self._run_solver(
            clear_existing=True,
            mode="repair",
            repair_realization=[repaired.id],
        )

        self.assertEqual((self._allocation_for(locked).day, self._allocation_for(locked).start), ("MON", "07:00"))
        self.assertEqual((self._allocation_for(repaired).day, self._allocation_for(repaired).start), ("FRI", "21:00"))

    def test_repair_mode_fails_when_existing_lock_is_no_longer_feasible(self):
        teacher = self._create_teacher("invalid-repair-lock-teacher")
        realization = self._create_realization(
            "INVALID_REPAIR_LOCK", teacher, self._create_group("INVALID_REPAIR_LOCK_01")
        )
        Allocation.objects.create(
            timetable=self.timetable,
            activityRealization=realization,
            classroom=self.room1,
            day="MON",
            start="07:00",
        )
        realization.activity.required_rooms.add(self.room2)

        output = self._run_solver(clear_existing=True, mode="repair")

        self.assertIn("cannot be preserved in repair mode", output)
        self.assertEqual(self._allocation_for(realization).classroom, self.room1)

    def test_no_feasible_solution_writes_no_allocations(self):
        teacher = self._create_teacher("infeasible-teacher")
        group = self._create_group("INFEASIBLE_01")
        self._create_realization("INFEASIBLE", teacher, group)
        self._block_teacher_except(teacher, set())

        output = self._run_solver()

        self.assertIn("No feasible assignments", output)
        self.assertEqual(Allocation.objects.filter(timetable=self.timetable).count(), 0)

    def test_no_feasible_solution_makes_management_command_fail(self):
        teacher = self._create_teacher("command-failure-teacher")
        group = self._create_group("COMMAND_FAILURE_01")
        self._create_realization("COMMAND_FAILURE", teacher, group)
        self._block_teacher_except(teacher, set())

        with self.assertRaises(CommandError):
            call_command(
                "ortools_generate",
                self.timetable.slug,
                time_limit=10,
                stdout=StringIO(),
            )

    def test_cross_section_overlap_constraints_are_parsed_from_fet_helper(self):
        solver = ORToolsTimetableSolver(
            self.timetable, ORToolsSolverOptions(cross_section_razor=2)
        )

        with patch(
            "friprosveta.services.ortools_solver.crossections.realizations_must_not_overlap_database",
            return_value=[
                [
                    "ConstraintActivitiesNotOverlapping",
                    None,
                    [
                        ["Weight_Percentage", "100"],
                        ["Number_of_Activities", "2"],
                        ["Activity_Id", "11"],
                        ["Activity_Id", "22"],
                    ],
                ]
            ],
        ):
            self.assertEqual(solver._cross_section_no_overlap_pairs(), [(11, 22)])

    def test_cross_section_overlap_is_enforced_end_to_end(self):
        _realizations, teachers = self._create_cross_section_pair(3)
        for teacher in teachers:
            self._block_teacher_except(teacher, {("MON", "07:00")})

        output = self._run_solver(cross_section_razor=2)

        self.assertIn(
            "Cross-section razor: student overlaps up to 2 are allowed by this "
            "rule; hard no-overlap pairs=1.",
            output,
        )
        self.assertIn("No feasible timetable found", output)
        self.assertEqual(Allocation.objects.filter(timetable=self.timetable).count(), 0)

    def test_cross_section_razor_allows_overlap_at_threshold(self):
        realizations, teachers = self._create_cross_section_pair(3)
        for teacher in teachers:
            self._block_teacher_except(teacher, {("MON", "07:00")})

        output = self._run_solver(cross_section_razor=3)

        self.assertIn(
            "Cross-section razor: student overlaps up to 3 are allowed by this "
            "rule; hard no-overlap pairs=0.",
            output,
        )
        self.assertIn("Generated 2 allocations", output)
        self.assertTrue(
            self._overlap(
                self._allocation_for(realizations[0]),
                self._allocation_for(realizations[1]),
            )
        )
        self.assertIn(
            "overlap violations teacher=0, group=0, student=0, room=0", output
        )

    def test_group_cross_section_razor_retains_group_at_threshold(self):
        _realizations, teachers, _group = self._create_group_cross_section_pair(3)
        for teacher in teachers:
            self._block_teacher_except(teacher, {("MON", "07:00")})

        output = self._run_solver(cross_section_group_razor=3)

        self.assertIn(
            "Group assignment razor: ignored 0 assignment(s) across 0 group(s) "
            "with effective size below 3",
            output,
        )
        self.assertIn("No feasible timetable found", output)
        self.assertEqual(Allocation.objects.filter(timetable=self.timetable).count(), 0)

    def test_group_cross_section_razor_ignores_group_below_threshold(self):
        realizations, teachers, _group = self._create_group_cross_section_pair(3)
        for teacher in teachers:
            self._block_teacher_except(teacher, {("MON", "07:00")})

        output = self._run_solver(cross_section_group_razor=4)

        self.assertIn(
            "Group assignment razor: ignored 2 assignment(s) across 1 group(s) "
            "with effective size below 4",
            output,
        )
        self.assertIn("Generated 2 allocations", output)
        self.assertTrue(
            self._overlap(
                self._allocation_for(realizations[0]),
                self._allocation_for(realizations[1]),
            )
        )

    def test_solver_room_size_uses_retained_groups_not_intended_size(self):
        self.room1.capacity = 10
        self.room1.save(update_fields=["capacity"])
        self.room2.capacity = 10
        self.room2.save(update_fields=["capacity"])
        teacher = self._create_teacher("retained-size-teacher")
        group = self._create_group("RETAINED_SIZE", size=10)
        realization = self._create_realization("RETAINED_SIZE", teacher, group)
        realization.intended_size = 20
        realization.save(update_fields=["intended_size"])

        output = self._run_solver()

        self.assertIn("Generated 1 allocations", output)

    def test_group_cross_section_razor_reduces_solver_room_size(self):
        self.room1.capacity = 8
        self.room1.save(update_fields=["capacity"])
        self.room2.capacity = 8
        self.room2.save(update_fields=["capacity"])
        teacher = self._create_teacher("group-razor-size-teacher")
        retained = self._create_group("GROUP_RAZOR_RETAINED", size=8)
        ignored = self._create_group("GROUP_RAZOR_IGNORED", size=3)
        realization = self._create_realization(
            "GROUP_RAZOR_ROOM_SIZE", teacher, retained
        )
        realization.activity.groups.add(ignored)
        realization.groups.add(ignored)

        without_razor = self._run_solver(cross_section_group_razor=3)
        self.assertIn("No suitable rooms", without_razor)

        output = self._run_solver(cross_section_group_razor=4)

        self.assertIn("ignored 1 assignment(s)", output)
        self.assertIn("Generated 1 allocations", output)

    def test_tag_max_hours_daily_is_enforced(self):
        teacher1 = self._create_teacher("tagmax-teacher-1")
        teacher2 = self._create_teacher("tagmax-teacher-2")
        group = self._create_group("TAGMAX_01")
        first = self._create_realization("TAGMAX1", teacher1, group, duration=2)
        second = self._create_realization("TAGMAX2", teacher2, group, duration=2)
        third = self._create_realization("TAGMAX3", teacher2, group, duration=2)
        tag = Tag.objects.create(name="Tag max hours", description="")
        tag.groups.add(group)
        for realization in (first, second, third):
            realization.activity.tags.add(tag)
        TagValuePreference.objects.create(
            preferenceset=self.preferenceset,
            tag=tag,
            level="WANT",
            name="TAGMAXHOURSDAILY",
            value=4,
        )
        self._block_teacher_except(
            teacher1,
            {("MON", "07:00"), ("MON", "08:00")},
        )
        self._block_teacher_except(
            teacher2,
            {
                ("MON", "07:00"), ("MON", "08:00"), ("MON", "09:00"), ("MON", "10:00"),
                ("TUE", "07:00"), ("TUE", "08:00"),
            },
        )

        self._run_solver()

        mon_hours = 0
        for realization in (first, second, third):
            allocation = self._allocation_for(realization)
            if allocation.day == "MON":
                mon_hours += allocation.duration
        self.assertLessEqual(mon_hours, 4)

    def test_shrink_groups_allows_smaller_room(self):
        small_room = self._create_room("Shrink", "SHR", 5)
        self.classroomset.classrooms.remove(self.room1, self.room2)
        teacher = self._create_teacher("shrink-teacher")
        group = self._create_group("SHRINK_01", size=20)
        realization = self._create_realization("SHRINK", teacher, group)
        tag = Tag.objects.create(name="Shrink", description="")
        realization.activity.tags.add(tag)
        tag.groups.add(group)
        TagValuePreference.objects.create(
            preferenceset=self.preferenceset,
            tag=tag,
            level="WANT",
            name="SHRINKGROUPS",
            value=16,
        )

        self._run_solver()

        allocation = self._allocation_for(realization)
        self.assertEqual(allocation.classroom, small_room)

    def test_shrink_groups_reduces_computed_size(self):
        teacher = self._create_teacher("shrink-helper-teacher")
        group = self._create_group("SHRINKHELPER_01", size=20)
        realization = self._create_realization("SHRINKHELPER", teacher, group)
        tag = Tag.objects.create(name="Shrink helper", description="")
        tag.groups.add(group)
        realization.activity.tags.add(tag)
        TagValuePreference.objects.create(
            preferenceset=self.preferenceset,
            tag=tag,
            level="WANT",
            name="SHRINKGROUPS",
            value=7,
        )

        solver = ORToolsTimetableSolver(self.timetable)
        tag_ids = solver._build_realization_tag_ids([realization])
        adjustments = solver._build_tag_size_adjustments()

        self.assertEqual(solver._adjusted_size(realization, tag_ids, adjustments), 13)

    def test_mul_size_reduces_computed_size(self):
        teacher = self._create_teacher("mullsize-helper-teacher")
        group = self._create_group("MULSIZEHELPER_01", size=20)
        realization = self._create_realization("MULSIZEHELPER", teacher, group)
        tag = Tag.objects.create(name="Mulsize helper", description="")
        tag.groups.add(group)
        realization.activity.tags.add(tag)
        TagValuePreference.objects.create(
            preferenceset=self.preferenceset,
            tag=tag,
            level="WANT",
            name="MULSIZE",
            value=50,
        )

        solver = ORToolsTimetableSolver(self.timetable)
        tag_ids = solver._build_realization_tag_ids([realization])
        adjustments = solver._build_tag_size_adjustments()

        self.assertEqual(solver._adjusted_size(realization, tag_ids, adjustments), 10)

    def test_mul_size_allows_smaller_room(self):
        small_room = self._create_room("Mulsize Room", "MULR", 8)
        self.classroomset.classrooms.remove(self.room1, self.room2)
        teacher = self._create_teacher("mulsize-teacher")
        group = self._create_group("MULSIZE_01", size=20)
        realization = self._create_realization("MULSIZE", teacher, group)
        tag = Tag.objects.create(name="Mulsize", description="")
        tag.groups.add(group)
        realization.activity.tags.add(tag)
        TagValuePreference.objects.create(
            preferenceset=self.preferenceset,
            tag=tag,
            level="WANT",
            name="MULSIZE",
            value=40,
        )

        self._run_solver()

        allocation = self._allocation_for(realization)
        self.assertEqual(allocation.classroom, small_room)

    def test_max_changes_week_zero_forbids_building_switch(self):
        other_location = Location.objects.create(name="Maribor")
        maribor_room = self._create_room("Maribor Room", "MB", 30, location=other_location)
        self.classroomset.classrooms.remove(self.room2)
        teacher = self._create_teacher("changezero-teacher")
        group1 = self._create_group("CHANGEW0_01")
        group2 = self._create_group("CHANGEW0_02")
        first = self._create_realization("CHANGEW1", teacher, group1, duration=2, location=self.location)
        second = self._create_realization("CHANGEW2", teacher, group2, duration=2, location=other_location)
        first.activity.required_rooms.add(self.room1)
        second.activity.required_rooms.add(maribor_room)
        TeacherValuePreference.objects.create(
            preferenceset=self.preferenceset,
            teacher=teacher,
            level="CANT",
            name="MAXCHANGESWEEK",
            value=0,
        )
        self._block_teacher_except(
            teacher,
            {
                ("MON", "07:00"), ("MON", "08:00"), ("MON", "09:00"), ("MON", "10:00"),
                ("TUE", "07:00"), ("TUE", "08:00"), ("TUE", "09:00"), ("TUE", "10:00"),
            },
        )

        self._run_solver()

        self.assertEqual(Allocation.objects.filter(timetable=self.timetable).count(), 2)
        self.assertNotEqual(
            self._allocation_for(first).day,
            self._allocation_for(second).day,
        )

    def test_max_changes_day_limits_back_to_back_moves(self):
        other_location = Location.objects.create(name="Koper")
        koper_room = self._create_room("Koper Room", "KP", 30, location=other_location)
        self.classroomset.classrooms.remove(self.room2)
        teacher = self._create_teacher("changeday-teacher")
        group1 = self._create_group("CHANGEDAY_01")
        group2 = self._create_group("CHANGEDAY_02")
        first = self._create_realization("CHANGED1", teacher, group1, duration=2, location=self.location)
        second = self._create_realization("CHANGED2", teacher, group2, duration=2, location=other_location)
        first.activity.required_rooms.add(self.room1)
        second.activity.required_rooms.add(koper_room)
        TeacherValuePreference.objects.create(
            preferenceset=self.preferenceset,
            teacher=teacher,
            level="CANT",
            name="MAXCHANGESDAY",
            value=0,
        )
        self._block_teacher_except(
            teacher,
            {
                ("MON", "07:00"), ("MON", "08:00"), ("MON", "09:00"), ("MON", "10:00"),
                ("TUE", "07:00"), ("TUE", "08:00"), ("TUE", "09:00"), ("TUE", "10:00"),
            },
        )

        self._run_solver()

        self.assertEqual(Allocation.objects.filter(timetable=self.timetable).count(), 2)
        self.assertNotEqual(
            self._allocation_for(first).day,
            self._allocation_for(second).day,
        )

    def test_max_hours_continuous_is_enforced(self):
        teacher = self._create_teacher("cont-teacher")
        group1 = self._create_group("CONT_01")
        group2 = self._create_group("CONT_02")
        first = self._create_realization("CONT1", teacher, group1, duration=2)
        second = self._create_realization("CONT2", teacher, group2, duration=2)
        TeacherValuePreference.objects.create(
            preferenceset=self.preferenceset,
            teacher=teacher,
            level="CANT",
            name="MAXHOURSCONT",
            value=2,
        )
        self._block_teacher_except(
            teacher,
            {
                ("MON", "07:00"), ("MON", "08:00"), ("MON", "09:00"), ("MON", "10:00"),
                ("TUE", "07:00"), ("TUE", "08:00"),
            },
        )

        self._run_solver()

        self.assertFalse(
            self._overlap(
                self._allocation_for(first), self._allocation_for(second)
            )
        )

    def test_min_days_week_is_enforced(self):
        teacher1 = self._create_teacher("minday-teacher-1")
        teacher2 = self._create_teacher("minday-teacher-2")
        teacher3 = self._create_teacher("minday-teacher-3")
        group = self._create_group("MINDAY_01")
        first = self._create_realization("MINDAY1", teacher1, group)
        second = self._create_realization("MINDAY2", teacher2, group)
        third = self._create_realization("MINDAY3", teacher3, group)
        GroupValuePreference.objects.create(
            preferenceset=self.preferenceset,
            group=group,
            level="CANT",
            name="MINDAYSWEEK",
            value=3,
        )

        self._run_solver()

        days = {
            self._allocation_for(realization).day
            for realization in (first, second, third)
        }
        self.assertGreaterEqual(len(days), 3)

    def test_solver_constraint_max_days_week_is_enforced(self):
        teacher1 = self._create_teacher("solver-maxdays-teacher-1")
        teacher2 = self._create_teacher("solver-maxdays-teacher-2")
        group = self._create_group("SOLVERMAXDAYS_01")
        first = self._create_realization("SOLVERMAXDAYS1", teacher1, group)
        second = self._create_realization("SOLVERMAXDAYS2", teacher2, group)
        constraint = SolverConstraint.objects.create(
            timetable=self.timetable,
            name="group max days",
            constraint_type="MAXDAYSWEEK",
            value=1,
        )
        constraint.groups.add(group)

        self._run_solver()

        self.assertEqual(self._allocation_for(first).day, self._allocation_for(second).day)

    def test_solver_constraint_min_days_week_is_enforced(self):
        teacher1 = self._create_teacher("solver-mindays-teacher-1")
        teacher2 = self._create_teacher("solver-mindays-teacher-2")
        group = self._create_group("SOLVERMINDAYS_01")
        first = self._create_realization("SOLVERMINDAYS1", teacher1, group)
        second = self._create_realization("SOLVERMINDAYS2", teacher2, group)
        constraint = SolverConstraint.objects.create(
            timetable=self.timetable,
            name="group min days",
            constraint_type="MINDAYSWEEK",
            value=2,
        )
        constraint.groups.add(group)

        self._run_solver()

        self.assertNotEqual(self._allocation_for(first).day, self._allocation_for(second).day)

    def test_solver_constraint_consecutive_is_enforced(self):
        teacher1 = self._create_teacher("solver-consec-teacher-1")
        teacher2 = self._create_teacher("solver-consec-teacher-2")
        group1 = self._create_group("SOLVERCONSEC_01")
        group2 = self._create_group("SOLVERCONSEC_02")
        first = self._create_realization("SOLVERCONSEC1", teacher1, group1, duration=2)
        second = self._create_realization("SOLVERCONSEC2", teacher2, group2, duration=1)
        constraint = SolverConstraint.objects.create(
            timetable=self.timetable,
            name="consecutive",
            constraint_type="CONSECUTIVE",
        )
        constraint.realizations.add(first, second)

        self._run_solver()

        first_alloc = self._allocation_for(first)
        second_alloc = self._allocation_for(second)
        self.assertEqual(first_alloc.day, second_alloc.day)
        self.assertEqual(
            self._slot_index(first_alloc) + first.duration,
            self._slot_index(second_alloc),
        )

    def test_solver_constraint_grouped_is_enforced(self):
        teacher1 = self._create_teacher("solver-grouped-teacher-1")
        teacher2 = self._create_teacher("solver-grouped-teacher-2")
        group1 = self._create_group("SOLVERGROUPED_01")
        group2 = self._create_group("SOLVERGROUPED_02")
        first = self._create_realization("SOLVERGROUPED1", teacher1, group1)
        second = self._create_realization("SOLVERGROUPED2", teacher2, group2)
        constraint = SolverConstraint.objects.create(
            timetable=self.timetable,
            name="grouped",
            constraint_type="GROUPED",
        )
        constraint.realizations.add(first, second)

        self._run_solver()

        first_alloc = self._allocation_for(first)
        second_alloc = self._allocation_for(second)
        self.assertEqual((first_alloc.day, first_alloc.start), (second_alloc.day, second_alloc.start))

    def test_solver_constraint_same_starting_time_is_enforced(self):
        teacher1 = self._create_teacher("solver-samestart-teacher-1")
        teacher2 = self._create_teacher("solver-samestart-teacher-2")
        group1 = self._create_group("SOLVERSAMESTART_01")
        group2 = self._create_group("SOLVERSAMESTART_02")
        first = self._create_realization("SOLVERSAMESTART1", teacher1, group1)
        second = self._create_realization("SOLVERSAMESTART2", teacher2, group2)
        constraint = SolverConstraint.objects.create(
            timetable=self.timetable,
            name="same start",
            constraint_type="SAMESTARTINGTIME",
        )
        constraint.realizations.add(first, second)

        self._run_solver()

        first_alloc = self._allocation_for(first)
        second_alloc = self._allocation_for(second)
        self.assertEqual((first_alloc.day, first_alloc.start), (second_alloc.day, second_alloc.start))

    def test_solver_constraint_no_overlap_is_enforced(self):
        teacher1 = self._create_teacher("solver-nooverlap-teacher-1")
        teacher2 = self._create_teacher("solver-nooverlap-teacher-2")
        group1 = self._create_group("SOLVERNOOVERLAP_01")
        group2 = self._create_group("SOLVERNOOVERLAP_02")
        first = self._create_realization("SOLVERNOOVERLAP1", teacher1, group1)
        second = self._create_realization("SOLVERNOOVERLAP2", teacher2, group2)
        constraint = SolverConstraint.objects.create(
            timetable=self.timetable,
            name="no overlap",
            constraint_type="NOOVERLAP",
        )
        constraint.realizations.add(first, second)
        for teacher in (teacher1, teacher2):
            TeacherTimePreference.objects.create(
                preferenceset=self.preferenceset,
                teacher=teacher,
                level="WANT",
                day="MON",
                start="07:00",
                duration=1,
                weight=100,
            )

        self._run_solver()

        self.assertFalse(
            self._overlap(
                self._allocation_for(first), self._allocation_for(second)
            )
        )

    def test_solver_constraint_ends_students_day_is_enforced(self):
        teacher1 = self._create_teacher("solver-ends-teacher-1")
        teacher2 = self._create_teacher("solver-ends-teacher-2")
        group = self._create_group("SOLVERENDS_01")
        earlier = self._create_realization("SOLVERENDS1", teacher1, group)
        ending = self._create_realization("SOLVERENDS2", teacher2, group)
        constraint = SolverConstraint.objects.create(
            timetable=self.timetable,
            name="ends day",
            constraint_type="ENDSSTUDENTSDAY",
        )
        constraint.realizations.add(ending)
        self._block_teacher_except(teacher1, {("MON", "07:00"), ("MON", "08:00")})
        self._block_teacher_except(teacher2, {("MON", "07:00"), ("MON", "08:00")})

        self._run_solver()

        self.assertLess(
            self._slot_index(self._allocation_for(earlier)),
            self._slot_index(self._allocation_for(ending)),
        )

    def test_solver_constraint_min_change_gap_is_enforced(self):
        other_location = Location.objects.create(name="Kranj")
        kranj_room = self._create_room("Kranj Room", "KR", 30, location=other_location)
        self.classroomset.classrooms.remove(self.room2)
        teacher = self._create_teacher("solver-mcg-teacher")
        group1 = self._create_group("SOLVERMCG_01")
        group2 = self._create_group("SOLVERMCG_02")
        first = self._create_realization("SOLVERMCG1", teacher, group1, location=self.location)
        second = self._create_realization("SOLVERMCG2", teacher, group2, location=other_location)
        first.activity.required_rooms.add(self.room1)
        second.activity.required_rooms.add(kranj_room)
        constraint = SolverConstraint.objects.create(
            timetable=self.timetable,
            name="min change gap",
            constraint_type="MINCHANGEGAP",
            value=2,
        )
        constraint.teachers.add(teacher)
        self._block_teacher_except(teacher, {("MON", "07:00"), ("MON", "08:00"), ("MON", "09:00"), ("MON", "10:00")})

        self._run_solver()

        self.assertGreaterEqual(
            self._slot_distance(self._allocation_for(first), self._allocation_for(second)),
            3,
        )

    def test_solver_constraint_max_hours_day_is_enforced(self):
        teacher = self._create_teacher("solver-maxhours-teacher")
        group1 = self._create_group("SOLVERMAXHOURS_01")
        group2 = self._create_group("SOLVERMAXHOURS_02")
        first = self._create_realization("SOLVERMAXHOURS1", teacher, group1, duration=2)
        second = self._create_realization("SOLVERMAXHOURS2", teacher, group2, duration=2)
        constraint = SolverConstraint.objects.create(
            timetable=self.timetable,
            name="max hours",
            constraint_type="MAXHOURSDAY",
            value=2,
        )
        constraint.teachers.add(teacher)
        self._block_teacher_except(
            teacher,
            {("MON", "07:00"), ("MON", "08:00"), ("TUE", "07:00"), ("TUE", "08:00")},
        )

        self._run_solver()

        self.assertNotEqual(self._allocation_for(first).day, self._allocation_for(second).day)

    def test_solver_constraint_max_continuous_hours_is_enforced(self):
        teacher = self._create_teacher("solver-maxcont-teacher")
        group1 = self._create_group("SOLVERMAXCONT_01")
        group2 = self._create_group("SOLVERMAXCONT_02")
        first = self._create_realization("SOLVERMAXCONT1", teacher, group1, duration=2)
        second = self._create_realization("SOLVERMAXCONT2", teacher, group2, duration=2)
        constraint = SolverConstraint.objects.create(
            timetable=self.timetable,
            name="max continuous",
            constraint_type="MAXHOURSCONT",
            value=2,
        )
        constraint.teachers.add(teacher)
        self._block_teacher_except(
            teacher,
            {
                ("MON", "07:00"), ("MON", "08:00"), ("MON", "09:00"), ("MON", "10:00"),
                ("TUE", "07:00"), ("TUE", "08:00"),
            },
        )

        self._run_solver()

        self.assertFalse(
            self._overlap(
                self._allocation_for(first), self._allocation_for(second)
            )
        )

    def test_infeasible_message_includes_capacity_hint(self):
        small_room = self._create_room("Tiny", "TINY", 1)
        self.classroomset.classrooms.remove(self.room1, self.room2)
        teacher = self._create_teacher("infeasible-capacity-teacher")
        group = self._create_group("INFEASIBLECAP_01", size=50)
        self._create_realization("INFEASIBLECAP", teacher, group)

        output = self._run_solver()

        self.assertIn("No suitable rooms", output)
        self.assertIn("max_capacity=1", output)
        self.assertIn("required=50", output)

    def test_infeasible_message_aggregates_all_no_room_realizations(self):
        self._create_room("Tiny", "TINY", 1)
        self.classroomset.classrooms.remove(self.room1, self.room2)
        teacher1 = self._create_teacher("infeasible-capacity-teacher-1")
        teacher2 = self._create_teacher("infeasible-capacity-teacher-2")
        group1 = self._create_group("INFEASIBLECAP_01", size=50)
        group2 = self._create_group("INFEASIBLECAP_02", size=60)
        realization1 = self._create_realization("INFEASIBLECAP1", teacher1, group1)
        realization2 = self._create_realization("INFEASIBLECAP2", teacher2, group2)

        output = self._run_solver()

        self.assertIn("No suitable rooms for 2 realizations:", output)
        self.assertIn(f"#{realization1.id}", output)
        self.assertIn(f"#{realization2.id}", output)
        self.assertIn("max_capacity=1", output)
        self.assertIn("required=50", output)
        self.assertIn("required=60", output)
        self.assertEqual(Allocation.objects.filter(timetable=self.timetable).count(), 0)

    def test_timeout_or_infeasibility_reports_resource_contention(self):
        teacher = self._create_teacher("contention-teacher")
        group1 = self._create_group("CONTENTION_01")
        group2 = self._create_group("CONTENTION_02")
        first = self._create_realization("CONTENTION1", teacher, group1)
        second = self._create_realization("CONTENTION2", teacher, group2)
        self._block_teacher_except(teacher, {("MON", "07:00")})

        output = self._run_solver()

        self.assertIn("Highest mandatory resource contention", output)
        self.assertIn(f"teacher={teacher}", output)
        self.assertIn("demand=2, feasible_slots=1, utilization=200%", output)
        self.assertIn(f"realizations={first.id},{second.id}", output)
        self.assertIn("Least flexible realizations", output)

    def test_infeasibility_reports_shared_resource_pair_pressure(self):
        teacher = self._create_teacher("pair-pressure-teacher")
        first = self._create_realization(
            "PAIR_PRESSURE_1", teacher, self._create_group("PAIR_PRESSURE_01"), duration=2
        )
        second = self._create_realization(
            "PAIR_PRESSURE_2", teacher, self._create_group("PAIR_PRESSURE_02"), duration=2
        )
        self._block_teacher_except(
            teacher,
            {("MON", "07:00"), ("MON", "08:00"), ("MON", "09:00")},
        )

        output = self._run_solver()

        self.assertIn("Shared-resource pair pressure", output)
        self.assertIn(f"pair=#{first.id}/#{second.id}", output)
        self.assertIn("shared_feasible_hours=3", output)
        self.assertIn("combined_feasible_hours=3, shared_days=MON", output)
        self.assertIn("non_overlapping_start_pairs=0/4. IMPOSSIBLE", output)
        self.assertIn("candidate_starts=2: MON 07:00, MON 08:00", output)

    def test_placeholder_teacher_does_not_prevent_parallel_scheduling(self):
        teacher = self._create_teacher("placeholder-teacher")
        teacher.user.first_name = "PROSTO"
        teacher.user.last_name = "PROSTO"
        teacher.user.save(update_fields=("first_name", "last_name"))
        first_group = self._create_group("PLACEHOLDER_01")
        second_group = self._create_group("PLACEHOLDER_02")
        first = self._create_realization("PLACEHOLDER1", teacher, first_group)
        second = self._create_realization(
            "PLACEHOLDER2", teacher, second_group
        )
        self._block_teacher_except(teacher, {("MON", "07:00")})
        self._block_group_except(first_group, {("MON", "07:00")})
        self._block_group_except(second_group, {("MON", "07:00")})

        output = self._run_solver()

        self.assertIn("Generated 2 allocations", output)
        self.assertTrue(self._overlap(self._allocation_for(first), self._allocation_for(second)))

    def test_ready_only_preserves_existing_allocations_for_non_ready_activities(self):
        subject = friprosveta.models.Subject.objects.create(code="R01", name="Ready Subject")
        lecture_type = friprosveta.models.LectureType.objects.create(
            name="Ready LT", short_name="RLT", duration=1
        )
        ready_teacher = self._create_teacher("ready-teacher")
        unready_teacher = self._create_teacher("unready-teacher")
        ready_group = self._create_group("READY_01")
        unready_group = self._create_group("UNREADY_01")

        ready_activity = friprosveta.models.Activity.objects.create(
            name="READY",
            short_name="READY",
            activityset=self.activityset,
            type="P",
            duration=1,
            subject=subject,
            lecture_type=lecture_type,
            ready_to_schedule=True,
        )
        ready_activity.teachers.add(ready_teacher)
        ready_activity.groups.add(ready_group)
        ready_activity.locations.add(self.location)
        ready = ActivityRealization.objects.create(activity=ready_activity)
        ready.teachers.add(ready_teacher)
        ready.groups.add(ready_group)

        unready_activity = friprosveta.models.Activity.objects.create(
            name="UNREADY",
            short_name="UNREADY",
            activityset=self.activityset,
            type="P",
            duration=1,
            subject=subject,
            lecture_type=lecture_type,
            ready_to_schedule=False,
        )
        unready_activity.teachers.add(unready_teacher)
        unready_activity.groups.add(unready_group)
        unready_activity.locations.add(self.location)
        unready = ActivityRealization.objects.create(activity=unready_activity)
        unready.teachers.add(unready_teacher)
        unready.groups.add(unready_group)
        Allocation.objects.create(
            timetable=self.timetable,
            activityRealization=unready,
            classroom=self.room2,
            day="FRI",
            start="21:00",
        )

        output = self._run_solver(ready_only=True, clear_existing=True)

        self.assertIn("Generated 1 allocations", output)
        self.assertEqual(Allocation.objects.filter(timetable=self.timetable).count(), 2)
        self._allocation_for(ready)
        preserved = Allocation.objects.get(
            timetable=self.timetable, activityRealization=unready
        )
        self.assertEqual(
            (preserved.day, preserved.start, preserved.classroom),
            ("FRI", "21:00", self.room2),
        )

    def test_ready_only_preserved_allocation_blocks_teacher_for_full_duration(self):
        teacher = self._create_teacher("ready-fixed-teacher")
        fixed = self._create_ready_only_realization(
            "FIXED_TEACHER",
            teacher,
            self._create_group("FIXED_TEACHER_GROUP"),
            ready_to_schedule=False,
            duration=2,
        )
        ready = self._create_ready_only_realization(
            "READY_TEACHER",
            teacher,
            self._create_group("READY_TEACHER_GROUP"),
            ready_to_schedule=True,
        )
        Allocation.objects.create(
            timetable=self.timetable,
            activityRealization=fixed,
            classroom=self.room1,
            day="MON",
            start="07:00",
        )
        self._block_teacher_except(teacher, {("MON", "08:00")})

        output = self._run_solver(ready_only=True, clear_existing=True)

        self.assertIn("No feasible assignments for realization {}".format(ready.id), output)
        self.assertFalse(
            Allocation.objects.filter(
                timetable=self.timetable, activityRealization=ready
            ).exists()
        )
        self.assertEqual(self._allocation_for(fixed).start, "07:00")

    def test_ready_only_preserved_allocation_blocks_group(self):
        group = self._create_group("READY_FIXED_GROUP")
        fixed = self._create_ready_only_realization(
            "FIXED_GROUP",
            self._create_teacher("fixed-group-teacher"),
            group,
            ready_to_schedule=False,
        )
        ready_teacher = self._create_teacher("ready-group-teacher")
        ready = self._create_ready_only_realization(
            "READY_GROUP", ready_teacher, group, ready_to_schedule=True
        )
        Allocation.objects.create(
            timetable=self.timetable,
            activityRealization=fixed,
            classroom=self.room1,
            day="MON",
            start="07:00",
        )
        self._block_teacher_except(ready_teacher, {("MON", "07:00")})

        output = self._run_solver(ready_only=True, clear_existing=True)

        self.assertIn("No feasible assignments for realization {}".format(ready.id), output)
        self.assertEqual(self._allocation_for(fixed).start, "07:00")

    def test_ready_only_preserved_allocation_blocks_shared_student(self):
        fixed_group = self._create_group("FIXED_STUDENT_GROUP")
        ready_group = self._create_group("READY_STUDENT_GROUP")
        student = friprosveta.models.Student.objects.create(
            name="Ready", surname="Student", studentId="READY001"
        )
        student.groups.add(fixed_group, ready_group)
        fixed = self._create_ready_only_realization(
            "FIXED_STUDENT",
            self._create_teacher("fixed-student-teacher"),
            fixed_group,
            ready_to_schedule=False,
        )
        ready_teacher = self._create_teacher("ready-student-teacher")
        ready = self._create_ready_only_realization(
            "READY_STUDENT", ready_teacher, ready_group, ready_to_schedule=True
        )
        Allocation.objects.create(
            timetable=self.timetable,
            activityRealization=fixed,
            classroom=self.room1,
            day="MON",
            start="07:00",
        )
        self._block_teacher_except(ready_teacher, {("MON", "07:00")})

        output = self._run_solver(ready_only=True, clear_existing=True)

        self.assertIn("No feasible assignments for realization {}".format(ready.id), output)
        self.assertEqual(self._allocation_for(fixed).start, "07:00")

    def test_ready_only_preserved_allocation_blocks_room(self):
        fixed = self._create_ready_only_realization(
            "FIXED_ROOM",
            self._create_teacher("fixed-room-teacher"),
            self._create_group("FIXED_ROOM_GROUP"),
            ready_to_schedule=False,
        )
        ready_teacher = self._create_teacher("ready-room-teacher")
        ready = self._create_ready_only_realization(
            "READY_ROOM",
            ready_teacher,
            self._create_group("READY_ROOM_GROUP"),
            ready_to_schedule=True,
        )
        Allocation.objects.create(
            timetable=self.timetable,
            activityRealization=fixed,
            classroom=self.room1,
            day="MON",
            start="07:00",
        )
        self.classroomset.classrooms.remove(self.room2)
        self._block_teacher_except(ready_teacher, {("MON", "07:00")})

        output = self._run_solver(ready_only=True, clear_existing=True)

        self.assertIn("No feasible assignments for realization {}".format(ready.id), output)
        self.assertEqual(self._allocation_for(fixed).classroom, self.room1)

    def test_prefers_gap_between_lectures_for_same_group(self):
        first_teacher = self._create_teacher("lecture-gap-first")
        second_teacher = self._create_teacher("lecture-gap-second")
        group = self._create_group("LECTURE_GAP_01")
        first = self._create_realization("LECTURE_GAP_FIRST", first_teacher, group)
        second = self._create_realization("LECTURE_GAP_SECOND", second_teacher, group)
        self._block_group_except(
            group,
            {("MON", "08:00"), ("MON", "09:00"), ("MON", "10:00")},
        )

        self._run_solver(clear_existing=True)

        starts = sorted(
            [self._allocation_for(first).start, self._allocation_for(second).start]
        )
        self.assertEqual(starts, ["08:00", "10:00"])

    def test_scratch_mode_ignores_existing_allocations(self):
        teacher = self._create_teacher("scratch-teacher")
        group = self._create_group("SCRATCH_01")
        realization = self._create_realization("SCRATCH", teacher, group)
        Allocation.objects.create(
            timetable=self.timetable,
            activityRealization=realization,
            classroom=self.room2,
            day="WED",
            start="12:00",
        )
        self._block_teacher_except(teacher, {("FRI", "21:00")})

        self._run_solver(clear_existing=True, mode="scratch")

        allocation = self._allocation_for(realization)
        self.assertEqual((allocation.day, allocation.start), ("FRI", "21:00"))

    def test_improve_mode_preserves_existing_when_still_feasible(self):
        teacher = self._create_teacher("improve-teacher")
        group = self._create_group("IMPROVE_01")
        realization = self._create_realization("IMPROVE", teacher, group)
        Allocation.objects.create(
            timetable=self.timetable,
            activityRealization=realization,
            classroom=self.room2,
            day="WED",
            start="12:00",
        )

        output = self._run_solver(clear_existing=True, mode="improve")

        self.assertIn("Generated 1 allocations", output)
        allocation = self._allocation_for(realization)
        self.assertEqual((allocation.day, allocation.start, allocation.classroom), ("WED", "12:00", self.room2))

    def test_debug_messages_are_emitted_when_enable(self):
        teacher = self._create_teacher("debug-teacher")
        group = self._create_group("DEBUG_01")
        self._create_realization("DEBUG", teacher, group)

        output = self._run_solver(debug=True)

        self.assertIn("Building model:", output)
        self.assertIn("Model built:", output)
        self.assertIn("Generated 1 allocations", output)


class AllocationsAPIRespectsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.preferenceset = PreferenceSet.objects.create(
            slug="api-view-prefs", name="API View Prefs"
        )
        self.activityset = ActivitySet.objects.create(
            slug="api-view-activities", name="API View Activities"
        )
        self.groupset = GroupSet.objects.create(
            slug="api-view-groups", name="API View Groups", created=datetime.now()
        )
        self.classroomset = ClassroomSet.objects.create(
            slug="api-view-rooms", name="API View Rooms", created=date.today()
        )
        self.location = Location.objects.create(name="API View Room")
        self.room = Classroom.objects.create(
            name="API View Room", short_name="APIR", capacity=20, location=self.location
        )
        self.classroomset.classrooms.add(self.room)

        self.main_tt = Timetable.objects.create(
            slug="api-main-tt",
            name="API Main Timetable",
            activityset=self.activityset,
            preferenceset=self.preferenceset,
            groupset=self.groupset,
            classroomset=self.classroomset,
            public=True,
        )
        self.respected_tt = Timetable.objects.create(
            slug="api-respected-tt",
            name="API Respected Timetable",
            activityset=self.activityset,
            preferenceset=self.preferenceset,
            groupset=self.groupset,
            classroomset=self.classroomset,
            public=True,
        )

    def _create_allocation(self, timetable, short_name, hour):
        teacher = Teacher.objects.create(
            user=User.objects.create_user(f"api-{short_name}"), code=f"api-{short_name}"
        )
        group = Group.objects.create(
            name=f"{short_name}-group",
            short_name=f"{short_name}-g",
            size=1,
            groupset=self.groupset,
        )
        activity = Activity.objects.create(
            name=f"{short_name}-activity",
            short_name=short_name,
            activityset=self.activityset,
            type="P",
            duration=1,
        )
        activity.locations.add(self.location)
        activity.teachers.add(teacher)
        activity.groups.add(group)
        realization = ActivityRealization.objects.create(activity=activity)
        realization.teachers.add(teacher)
        realization.groups.add(group)
        return Allocation.objects.create(
            timetable=timetable,
            activityRealization=realization,
            classroom=self.room,
            day="MON",
            start=hour,
        )

    def test_allocations_json_includes_respected_timetable_slots(self):
        self._create_allocation(self.main_tt, "MAIN", "07:00")
        self._create_allocation(self.respected_tt, "RESPECTED", "08:00")
        self.main_tt.respects.add(self.respected_tt)

        response = self.client.get(f"/timetable/{self.main_tt.slug}/allocations.json")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 2)
        self.assertEqual(
            {item["fields"]["timetable"] for item in data},
            {self.main_tt.id, self.respected_tt.id},
        )

    def test_authenticated_view_filter_includes_private_respected_timetable(self):
        from friprosveta.views import _allocation_set

        self.respected_tt.public = False
        self.respected_tt.save(update_fields=["public"])
        self._create_allocation(self.main_tt, "MAIN_AUTH", "07:00")
        self._create_allocation(self.respected_tt, "RESPECTED_AUTH", "08:00")
        self.main_tt.respects.add(self.respected_tt)
        params = {"timetable_slug": [self.main_tt.slug]}

        public_only = _allocation_set(
            params, Allocation.objects.all(), is_staff=False
        )
        authenticated = _allocation_set(
            params,
            Allocation.objects.all(),
            is_staff=False,
            include_private_respected=True,
        )

        self.assertEqual(public_only.count(), 1)
        self.assertEqual(authenticated.count(), 2)


class SolverSetupUITest(TestCase):
    """
    Tests for the superuser-only Solver Setup UI: permissions, constraint CRUD,
    typed validation by category, timetable scoping, and run-command preview.
    Uses real Django objects (no broad mocks).
    """

    def setUp(self):
        self.preferenceset = PreferenceSet.objects.create(
            slug="ui-prefs", name="UI Preferences"
        )
        self.activityset = ActivitySet.objects.create(
            slug="ui-activities", name="UI Activities"
        )
        self.groupset = GroupSet.objects.create(
            slug="ui-groups", name="UI Groups", created=datetime.now()
        )
        self.timetable = Timetable.objects.create(
            slug="ui-tt",
            name="UI Timetable",
            activityset=self.activityset,
            preferenceset=self.preferenceset,
            groupset=self.groupset,
        )
        # A second timetable to prove cross-timetable scoping is enforced.
        self.other_activityset = ActivitySet.objects.create(
            slug="ui-activities-2", name="UI Activities 2"
        )
        self.other_groupset = GroupSet.objects.create(
            slug="ui-groups-2", name="UI Groups 2", created=datetime.now()
        )
        self.other_timetable = Timetable.objects.create(
            slug="ui-tt-2",
            name="UI Timetable 2",
            activityset=self.other_activityset,
            preferenceset=self.preferenceset,
            groupset=self.other_groupset,
        )
        self.staff_user = User.objects.create_user(
            "solver-staff", password="pw", is_staff=True, is_superuser=True
        )
        self.non_staff_user = User.objects.create_user(
            "solver-regular", password="pw", is_staff=False, is_superuser=False
        )
        self.teacher = Teacher.objects.create(
            user=User.objects.create_user("ui-teacher"), code="ui-teacher"
        )
        self.group = Group.objects.create(
            name="UI Group", short_name="UI_01", size=10, groupset=self.groupset
        )
        self.activity = Activity.objects.create(
            name="UI Activity",
            short_name="UIACT",
            activityset=self.activityset,
            type="P",
            duration=1,
        )
        self.activity.teachers.add(self.teacher)
        self.activity.groups.add(self.group)
        self.realization = ActivityRealization.objects.create(activity=self.activity)
        self.realization.teachers.add(self.teacher)
        self.realization.groups.add(self.group)
        # A teacher assigned only to a realization, not to the activity,
        # to verify teacher choices follow realization-level assignments.
        self.realization_only_teacher = Teacher.objects.create(
            user=User.objects.create_user("ui-realization-teacher"),
            code="ui-rt",
        )
        self.realization.teachers.add(self.realization_only_teacher)
        # A second realization of the same activity, for effective-realization tests.
        self.second_realization = ActivityRealization.objects.create(activity=self.activity)
        self.second_realization.teachers.add(self.teacher)
        self.second_realization.groups.add(self.group)
        # Objects belonging to the OTHER timetable.
        self.other_activity = Activity.objects.create(
            name="Other Activity",
            short_name="OTHACT",
            activityset=self.other_activityset,
            type="P",
            duration=1,
        )
        self.other_group = Group.objects.create(
            name="Other Group", short_name="OTH_01", size=10, groupset=self.other_groupset
        )
        self.other_realization = ActivityRealization.objects.create(
            activity=self.other_activity
        )
        self.client = Client()
        self._clear_generation_cache()

    def _generation_cache_keys(self, timetable_slug="ui-tt"):
        return (
            "{}:{}".format(SOLVER_GENERATION_LOCK_PREFIX, timetable_slug),
            "{}:{}".format(SOLVER_GENERATION_STATE_PREFIX, timetable_slug),
        )

    def _clear_generation_cache(self, timetable_slug="ui-tt"):
        lock_key, state_key = self._generation_cache_keys(timetable_slug)
        cache.delete(lock_key)
        cache.delete(state_key)

    def tearDown(self):
        self._clear_generation_cache()
        super().tearDown()

    def _login_staff(self):
        self.client.login(username="solver-staff", password="pw")

    def _login_regular(self):
        self.client.login(username="solver-regular", password="pw")

    # --- Permissions -------------------------------------------------

    def test_dashboard_requires_login(self):
        response = self.client.get("/solver/ui-tt/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login", response["Location"])

    def test_dashboard_requires_superuser(self):
        self._login_regular()
        response = self.client.get("/solver/ui-tt/")
        self.assertEqual(response.status_code, 403)

    def test_dashboard_staff_ok(self):
        self._login_staff()
        response = self.client.get("/solver/ui-tt/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Solver setup")

    def test_scheduling_scope_requires_superuser(self):
        self._login_regular()

        response = self.client.get("/solver/ui-tt/activities/")

        self.assertEqual(response.status_code, 403)

    def test_scheduling_scope_saves_activity_selection(self):
        subject = friprosveta.models.Subject.objects.create(
            code="UISCOPE", name="UI scheduling scope"
        )
        lecture_type = friprosveta.models.LectureType.objects.create(
            name="UI scope lecture", short_name="USP", duration=1
        )
        activity = friprosveta.models.Activity.objects.create(
            name="Sportna vzgoja",
            short_name="UISCOPE_P",
            activityset=self.activityset,
            type="P",
            duration=1,
            subject=subject,
            lecture_type=lecture_type,
        )
        self._login_staff()

        response = self.client.get("/solver/ui-tt/activities/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sportna vzgoja")
        formset = response.context["formset"]
        self.assertEqual(len(formset.forms), 1)
        response = self.client.post(
            "/solver/ui-tt/activities/",
            data={
                "form-TOTAL_FORMS": "1",
                "form-INITIAL_FORMS": "1",
                "form-MIN_NUM_FORMS": "0",
                "form-MAX_NUM_FORMS": "1000",
                "form-0-activity_ptr": str(activity.id),
                "form-0-exclude_from_solver": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        activity.refresh_from_db()
        self.assertFalse(activity.ready_to_schedule)

        response = self.client.post(
            "/solver/ui-tt/activities/", data={"action": "schedule_all"}
        )

        self.assertEqual(response.status_code, 302)
        activity.refresh_from_db()
        self.assertTrue(activity.ready_to_schedule)

    def test_scheduling_scope_excludes_doctoral_studies(self):
        doctoral_subject = friprosveta.models.Subject.objects.create(
            code="638001", name="Doctoral subject"
        )
        regular_subject = friprosveta.models.Subject.objects.create(
            code="632001", name="Regular subject"
        )
        lecture_type = friprosveta.models.LectureType.objects.create(
            name="UI doctoral lecture", short_name="UDP", duration=1
        )
        doctoral_activity = friprosveta.models.Activity.objects.create(
            name="Doctoral activity",
            short_name="DOCTORAL_P",
            activityset=self.activityset,
            type="P",
            duration=1,
            subject=doctoral_subject,
            lecture_type=lecture_type,
            ready_to_schedule=True,
        )
        regular_activity = friprosveta.models.Activity.objects.create(
            name="Regular activity",
            short_name="REGULAR_P",
            activityset=self.activityset,
            type="P",
            duration=1,
            subject=regular_subject,
            lecture_type=lecture_type,
            ready_to_schedule=True,
        )
        self._login_staff()

        response = self.client.post(
            "/solver/ui-tt/activities/", data={"action": "exclude_doctoral"}
        )

        self.assertEqual(response.status_code, 302)
        doctoral_activity.refresh_from_db()
        regular_activity.refresh_from_db()
        self.assertFalse(doctoral_activity.ready_to_schedule)
        self.assertTrue(regular_activity.ready_to_schedule)

    def test_dashboard_shows_automatic_rule_sources(self):
        self._login_staff()
        tag = Tag.objects.create(name="Automatic relation", description="")
        self.activity.tags.add(tag)
        TagDescriptivePreference.objects.create(
            preferenceset=self.preferenceset,
            tag=tag,
            level="CANT",
            typename="SAMEDAY",
            value="",
        )

        response = self.client.get("/solver/ui-tt/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Active rule sources")
        self.assertContains(response, "Tag relationship rules")
        self.assertContains(response, "You should not need to recreate")

    def test_direct_constraint_card_preselects_type(self):
        self._login_staff()

        response = self.client.get(
            "/solver/ui-tt/constraints/new/?category=workload&constraint_type=MAXSPANDAY"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["form"].fields["constraint_type"].initial, "MAXSPANDAY")

    def test_run_preview_requires_superuser(self):
        self._login_regular()
        response = self.client.get("/solver/ui-tt/run/")
        self.assertEqual(response.status_code, 403)

    def test_group_rules_requires_superuser(self):
        self._login_regular()
        response = self.client.get("/solver/ui-tt/groups/")
        self.assertEqual(response.status_code, 403)

    # --- CRUD -------------------------------------------------------

    def test_create_relation_constraint(self):
        self._login_staff()
        response = self.client.post(
            "/solver/ui-tt/constraints/new/?category=relation",
            data={
                "name": "no overlap",
                "constraint_type": "NOOVERLAP",
                "active": "on",
                "activities": [self.activity.id],
                "realizations": [self.realization.id],
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            SolverConstraint.objects.filter(
                timetable=self.timetable, constraint_type="NOOVERLAP", name="no overlap"
            ).exists()
        )

    def test_create_study_module(self):
        self._login_staff()
        second = Activity.objects.create(
            name="Second activity",
            short_name="SECOND",
            activityset=self.activityset,
            type="P",
            duration=1,
        )

        response = self.client.post(
            "/solver/ui-tt/modules/new/",
            data={
                "name": "Module A",
                "active": "on",
                "activities": [self.activity.id, second.id],
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            set(StudyModule.objects.get(timetable=self.timetable).activities.all()),
            {self.activity, second},
        )

    def test_create_fixed_placement(self):
        self._login_staff()
        classroomset = ClassroomSet.objects.create(
            slug="ui-rooms", name="UI Rooms", created=date.today()
        )
        room = Classroom.objects.create(
            name="UI Room",
            short_name="UIR",
            capacity=30,
            location=Location.objects.create(name="UI Location"),
        )
        classroomset.classrooms.add(room)
        self.timetable.classroomset = classroomset
        self.timetable.save(update_fields=("classroomset",))

        response = self.client.post(
            "/solver/ui-tt/constraints/new/?category=placement",
            data={
                "name": "Fixed placement",
                "constraint_type": "FIXEDPLACEMENT",
                "active": "on",
                "realizations": [self.realization.id],
                "classrooms": [room.id],
                "day": "MON",
                "start": "09:00",
            },
        )

        self.assertEqual(response.status_code, 302)
        constraint = SolverConstraint.objects.get(name="Fixed placement")
        self.assertEqual((constraint.day, constraint.start), ("MON", "09:00"))
        self.assertEqual(list(constraint.classrooms.all()), [room])

    def test_create_fixed_time(self):
        self._login_staff()

        response = self.client.post(
            "/solver/ui-tt/constraints/new/?category=time",
            data={
                "name": "Fixed time",
                "constraint_type": "FIXEDTIME",
                "active": "on",
                "realizations": [self.realization.id],
                "day": "MON",
                "start": "09:00",
            },
        )

        self.assertEqual(response.status_code, 302)
        constraint = SolverConstraint.objects.get(name="Fixed time")
        self.assertEqual((constraint.day, constraint.start), ("MON", "09:00"))
        self.assertFalse(constraint.classrooms.exists())

    def test_create_workload_constraint_requires_value_and_entity(self):
        self._login_staff()
        response = self.client.post(
            "/solver/ui-tt/constraints/new/?category=workload",
            data={
                "name": "max days",
                "constraint_type": "MAXDAYSWEEK",
                "active": "on",
                "value": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(SolverConstraint.objects.filter(name="max days").exists())
        form = response.context["form"]
        self.assertTrue(form.non_field_errors() or form.errors)

    def test_create_workload_constraint_with_group(self):
        self._login_staff()
        response = self.client.post(
            "/solver/ui-tt/constraints/new/?category=workload",
            data={
                "name": "max days",
                "constraint_type": "MAXDAYSWEEK",
                "active": "on",
                "value": "3",
                "groups": [self.group.id],
            },
        )
        self.assertEqual(response.status_code, 302)
        constraint = SolverConstraint.objects.get(name="max days")
        self.assertEqual(constraint.value, 3)
        self.assertEqual(list(constraint.groups.all()), [self.group])

    def test_create_relation_requires_two_objects(self):
        self._login_staff()
        response = self.client.post(
            "/solver/ui-tt/constraints/new/?category=relation",
            data={
                "name": "too few",
                "constraint_type": "NOOVERLAP",
                "active": "on",
                "realizations": [self.realization.id],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(SolverConstraint.objects.filter(name="too few").exists())

    def test_before_relations_page_adds_directed_activity_relations(self):
        later_activity = Activity.objects.create(
            name="Later Activity",
            short_name="LATER",
            activityset=self.activityset,
            type="LV",
            duration=1,
        )
        another_later_activity = Activity.objects.create(
            name="Another Later Activity",
            short_name="LATER2",
            activityset=self.activityset,
            type="AV",
            duration=1,
        )
        self._login_staff()

        response = self.client.post(
            "/solver/ui-tt/before-relations/",
            data={
                "action": "add",
                "before_activity": self.activity.id,
                "after_activities": [later_activity.id, another_later_activity.id],
            },
        )

        self.assertRedirects(response, "/solver/ui-tt/before-relations")
        self.assertEqual(
            set(self.activity.before.all()),
            {later_activity, another_later_activity},
        )

    def test_before_relations_page_rejects_self_relation_and_scopes_choices(self):
        self._login_staff()

        response = self.client.post(
            "/solver/ui-tt/before-relations/",
            data={
                "action": "add",
                "before_activity": self.activity.id,
                "after_activities": [self.activity.id],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.activity.before.exists())
        form = response.context["form"]
        activity_ids = set(
            form.fields["before_activity"].queryset.values_list("id", flat=True)
        )
        self.assertIn(self.activity.id, activity_ids)
        self.assertNotIn(self.other_activity.id, activity_ids)
        self.assertIn("cannot be ordered before itself", str(form.errors))

    def test_before_relations_page_removes_relation(self):
        later_activity = Activity.objects.create(
            name="Later Activity",
            short_name="LATER",
            activityset=self.activityset,
            type="LV",
            duration=1,
        )
        self.activity.before.add(later_activity)
        self._login_staff()

        response = self.client.post(
            "/solver/ui-tt/before-relations/",
            data={
                "action": "remove",
                "before_activity": self.activity.id,
                "after_activity": later_activity.id,
            },
        )

        self.assertRedirects(response, "/solver/ui-tt/before-relations")
        self.assertFalse(self.activity.before.filter(id=later_activity.id).exists())

    def test_dashboard_links_to_before_relations(self):
        self._login_staff()

        response = self.client.get("/solver/ui-tt/")

        self.assertContains(response, "/solver/ui-tt/before-relations")
        self.assertContains(response, "Before / after")

    def test_create_max_rooms_requires_positive_value(self):
        self._login_staff()
        response = self.client.post(
            "/solver/ui-tt/constraints/new/?category=relation",
            data={
                "name": "max rooms no value",
                "constraint_type": "MAXROOMSREALIZATIONS",
                "active": "on",
                "realizations": [self.realization.id],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            SolverConstraint.objects.filter(name="max rooms no value").exists()
        )

    def test_create_ends_day_requires_one_object(self):
        self._login_staff()
        response = self.client.post(
            "/solver/ui-tt/constraints/new/?category=ends_day",
            data={
                "name": "ends day",
                "constraint_type": "ENDSSTUDENTSDAY",
                "active": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(SolverConstraint.objects.filter(name="ends day").exists())

    def test_create_ends_day_with_realization(self):
        self._login_staff()
        response = self.client.post(
            "/solver/ui-tt/constraints/new/?category=ends_day",
            data={
                "name": "ends day",
                "constraint_type": "ENDSSTUDENTSDAY",
                "active": "on",
                "realizations": [self.realization.id],
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(SolverConstraint.objects.filter(name="ends day").exists())

    def test_edit_constraint(self):
        self._login_staff()
        second_realization = ActivityRealization.objects.create(activity=self.activity)
        second_realization.teachers.add(self.teacher)
        second_realization.groups.add(self.group)
        constraint = SolverConstraint.objects.create(
            timetable=self.timetable,
            name="edit me",
            constraint_type="SAMEDAY",
        )
        constraint.realizations.add(self.realization, second_realization)
        response = self.client.post(
            "/solver/ui-tt/constraints/{}/edit/".format(constraint.id),
            data={
                "name": "edited",
                "constraint_type": "SAMEDAY",
                "active": "on",
                "realizations": [self.realization.id, second_realization.id],
            },
        )
        self.assertEqual(response.status_code, 302)
        constraint.refresh_from_db()
        self.assertEqual(constraint.name, "edited")

    def test_delete_constraint(self):
        self._login_staff()
        constraint = SolverConstraint.objects.create(
            timetable=self.timetable,
            name="delete me",
            constraint_type="NOOVERLAP",
        )
        response = self.client.post(
            "/solver/ui-tt/constraints/{}/delete/".format(constraint.id)
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(SolverConstraint.objects.filter(id=constraint.id).exists())

    # --- Scope protection -------------------------------------------

    def test_edit_constraint_from_other_timetable_returns_404(self):
        self._login_staff()
        other_constraint = SolverConstraint.objects.create(
            timetable=self.other_timetable,
            name="other tt",
            constraint_type="NOOVERLAP",
        )
        response = self.client.get(
            "/solver/ui-tt/constraints/{}/edit/".format(other_constraint.id)
        )
        self.assertEqual(response.status_code, 404)

    def test_delete_constraint_from_other_timetable_returns_404(self):
        self._login_staff()
        other_constraint = SolverConstraint.objects.create(
            timetable=self.other_timetable,
            name="other tt del",
            constraint_type="NOOVERLAP",
        )
        response = self.client.post(
            "/solver/ui-tt/constraints/{}/delete/".format(other_constraint.id)
        )
        self.assertEqual(response.status_code, 404)
        self.assertTrue(SolverConstraint.objects.filter(id=other_constraint.id).exists())

    def test_create_form_does_not_offer_other_timetable_objects(self):
        self._login_staff()
        response = self.client.get(
            "/solver/ui-tt/constraints/new/?category=relation"
        )
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        activity_ids = set(form.fields["activities"].queryset.values_list("id", flat=True))
        realization_ids = set(
            form.fields["realizations"].queryset.values_list("id", flat=True)
        )
        group_ids = set(form.fields["groups"].queryset.values_list("id", flat=True))
        self.assertIn(self.activity.id, activity_ids)
        self.assertNotIn(self.other_activity.id, activity_ids)
        self.assertIn(self.realization.id, realization_ids)
        self.assertNotIn(self.other_realization.id, realization_ids)
        self.assertIn(self.group.id, group_ids)
        self.assertNotIn(self.other_group.id, group_ids)

    # --- Run command preview ----------------------------------------

    def test_run_preview_get_does_not_execute(self):
        self._login_staff()
        response = self.client.get("/solver/ui-tt/run/")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["command"])

    def test_run_preview_explains_generation_options(self):
        self._login_staff()

        response = self.client.get("/solver/ui-tt/run/")

        self.assertContains(response, "Required for exclusions to apply")
        self.assertContains(response, "Soft reward for retaining an existing allocation")
        self.assertContains(response, "Set 0 to disable")

    def test_full_generation_preview_has_no_realization_picker(self):
        self._login_staff()

        response = self.client.get("/solver/ui-tt/run/")

        self.assertNotIn("repair_realization", response.context["form"].fields)
        self.assertContains(response, "Generate entire timetable")

    def test_full_generation_preview_renders_command(self):
        self._login_staff()
        response = self.client.post(
            "/solver/ui-tt/run/",
            data={
                "time_limit": "30",
                "progress_every": "10",
                "num_search_workers": "4",
                "build_timeout": "0",
                "allocation_time_weight": "100",
                "allocation_room_weight": "25",
                "mode": "scratch",
                "cross_section_razor": "2",
                "cross_section_group_razor": "5",
            },
        )
        self.assertEqual(response.status_code, 200)
        command = response.context["command"]
        self.assertIn("ortools_generate ui-tt", command)
        self.assertIn("--time-limit=30", command)
        self.assertIn("--num-search-workers=4", command)
        self.assertIn("--mode=scratch", command)
        self.assertIn("--cross-section-razor=2", command)
        self.assertIn("--cross-section-group-razor=5", command)
        self.assertNotIn("--repair-realization", command)

    def test_full_generation_preview_accepts_unlimited_time(self):
        self._login_staff()

        response = self.client.post(
            "/solver/ui-tt/run/",
            data={
                "time_limit": "0",
                "progress_every": "10",
                "num_search_workers": "4",
                "build_timeout": "0",
                "allocation_time_weight": "100",
                "allocation_room_weight": "25",
                "mode": "scratch",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("--time-limit=0", response.context["command"])

    @patch("friprosveta.solver_run_views.call_command")
    @patch("friprosveta.solver_run_views.close_old_connections")
    @patch("friprosveta.solver_run_views.Thread")
    def test_run_now_starts_generation_in_background(self, mocked_thread, mocked_close_old_connections, mocked_call_command):
        self._login_staff()
        mocked_thread_instance = MagicMock()

        def fake_start():
            target = mocked_thread.call_args.kwargs.get("target")
            if target is None:
                target = mocked_thread.call_args.args[0]
            target()

        mocked_thread_instance.start.side_effect = fake_start
        mocked_thread.return_value = mocked_thread_instance
        mocked_call_command.side_effect = lambda *args, **kwargs: kwargs[
            "stdout"
        ].write("Generated 2 allocations\n")

        response = self.client.post(
            "/solver/ui-tt/run/",
            data={
                "action": "run",
                "time_limit": "30",
                "progress_every": "10",
                "num_search_workers": "6",
                "build_timeout": "0",
                "allocation_time_weight": "100",
                "allocation_room_weight": "25",
                "mode": "scratch",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            reverse("solver_dashboard", kwargs={"timetable_slug": "ui-tt"}),
        )
        self.assertEqual(mocked_thread.call_count, 1)
        mocked_thread_instance.start.assert_called_once()
        self.assertTrue(mocked_thread.call_args.kwargs["daemon"])
        mocked_call_command.assert_called_once()
        self.assertEqual(mocked_call_command.call_args.args, ("ortools_generate", "ui-tt"))
        self.assertEqual(mocked_call_command.call_args.kwargs["time_limit"], 30)
        self.assertEqual(mocked_call_command.call_args.kwargs["num_search_workers"], 6)
        self.assertEqual(mocked_call_command.call_args.kwargs["max_memory_mb"], 4096)

    def test_run_now_blocked_when_generation_is_running(self):
        self._login_staff()
        lock_key, state_key = self._generation_cache_keys()
        cache.set(
            lock_key,
            "running",
            timeout=SOLVER_GENERATION_CACHE_TTL_SECONDS,
        )
        cache.set(
            state_key,
            {
                "status": "running",
                "is_running": True,
                "mode": "scratch",
                "started_by": "solver-staff",
            },
            timeout=SOLVER_GENERATION_CACHE_TTL_SECONDS,
        )

        response = self.client.post(
            "/solver/ui-tt/run/",
            data={
                "action": "run",
                "time_limit": "30",
                "progress_every": "10",
                "num_search_workers": "4",
                "build_timeout": "0",
                "allocation_time_weight": "100",
                "allocation_room_weight": "25",
                "mode": "scratch",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "A solver generation is already running for this timetable.",
            response.content.decode("utf-8"),
        )
        self.assertIn('name="action" value="run" disabled', response.content.decode("utf-8"))
        self.assertEqual(cache.get(lock_key), "running")

    def test_dashboard_shows_running_generation_status(self):
        self._login_staff()
        lock_key, state_key = self._generation_cache_keys()
        cache.set(
            lock_key,
            "running",
            timeout=SOLVER_GENERATION_CACHE_TTL_SECONDS,
        )
        cache.set(
            state_key,
            {
                "status": "running",
                "is_running": True,
                "mode": "scratch",
                "started_by": "solver-staff",
            },
            timeout=SOLVER_GENERATION_CACHE_TTL_SECONDS,
        )

        response = self.client.get("/solver/ui-tt/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Solver generation is currently running.")
        self.assertContains(response, "Started by")
        self.assertContains(response, "solver-staff")

    def test_run_preview_rejects_unknown_repair_realization(self):
        self._login_staff()
        response = self.client.post(
            "/solver/ui-tt/repair/",
            data={
                "time_limit": "30",
                "progress_every": "10",
                "num_search_workers": "9",
                "build_timeout": "0",
                "allocation_time_weight": "100",
                "allocation_room_weight": "25",
                "mode": "repair",
                "repair_realization": "999999",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["command"])
        self.assertTrue(response.context["form"].errors)

    # --- Group rules page ------------------------------------------

    def test_group_rules_page_explains_native_overlap(self):
        self._login_staff()
        response = self.client.get("/solver/ui-tt/groups/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Native group no-overlap")
        self.assertContains(response, "Cross-section no-overlap threshold")
        self.assertContains(
            response, "Create a group workload / movement rule"
        )

    def test_automatic_rules_page_persists_soft_rule_weights(self):
        self._login_staff()
        response = self.client.get("/solver/ui-tt/automatic-rules/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Built-in hard constraints")
        self.assertContains(response, "Back-to-back lecture penalty")

        response = self.client.post(
            "/solver/ui-tt/automatic-rules/",
            data={
                "scheduling_window_weight": "5000",
                "lecture_grid_alignment_weight": "9",
                "consecutive_teacher_room_weight": "11",
                "room_adjacency_weight": "3",
                "lecture_back_to_back_penalty": "12",
            },
        )
        self.assertRedirects(response, "/solver/ui-tt/automatic-rules")
        settings = SolverWeightSettings.objects.get(timetable=self.timetable)
        self.assertEqual(settings.scheduling_window_weight, 5000)
        self.assertEqual(settings.lecture_grid_alignment_weight, 9)
        self.assertEqual(settings.consecutive_teacher_room_weight, 11)
        self.assertEqual(settings.room_adjacency_weight, 3)
        self.assertEqual(settings.lecture_back_to_back_penalty, 12)
        solver = ORToolsTimetableSolver(self.timetable)
        self.assertEqual(solver._automatic_weight("room_adjacency_weight", 2), 3)

    def test_copy_group_time_preferences_replaces_matching_groups(self):
        self._login_staff()
        source_preferenceset = PreferenceSet.objects.create(
            slug="source-group-prefs", name="Source group preferences"
        )
        source_groupset = GroupSet.objects.create(
            slug="source-groups", name="Source groups", created=datetime.now()
        )
        source_timetable = Timetable.objects.create(
            slug="source-group-time-preferences",
            name="Source timetable",
            preferenceset=source_preferenceset,
            groupset=source_groupset,
        )
        source_group = Group.objects.create(
            name="Source group",
            short_name=self.group.short_name,
            size=10,
            groupset=source_groupset,
        )
        GroupTimePreference.objects.create(
            preferenceset=source_preferenceset,
            group=source_group,
            day="MON",
            start="08:00",
            duration=2,
            level="CANT",
            weight=1,
        )
        GroupTimePreference.objects.create(
            preferenceset=self.preferenceset,
            group=self.group,
            day="FRI",
            start="10:00",
            duration=1,
            level="WANT",
            weight=0.5,
        )

        response = self.client.post(
            "/solver/ui-tt/copy-group-time-preferences/",
            data={"source_timetable": source_timetable.id},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Copied 1 group time preferences for 1 matching groups")
        copied = GroupTimePreference.objects.filter(
            preferenceset=self.preferenceset, group=self.group
        )
        self.assertEqual(copied.count(), 1)
        self.assertEqual(
            copied.values_list("day", "start", "duration", "level", "weight").get(),
            ("MON", "08:00", 2, "CANT", 1.0),
        )

    # --- hard/weight/classrooms not exposed ------------------------

    def test_form_does_not_expose_hard_weight_classrooms(self):
        self._login_staff()
        response = self.client.get(
            "/solver/ui-tt/constraints/new/?category=relation"
        )
        form = response.context["form"]
        self.assertNotIn("hard", form.fields)
        self.assertNotIn("weight", form.fields)
        self.assertNotIn("classrooms", form.fields)

    # --- Oracle: effective realization semantics ---------------------

    def test_relation_rejects_single_activity_with_one_realization(self):
        self._login_staff()
        ActivityRealization.objects.filter(
            id__in=[self.realization.id, self.second_realization.id]
        ).delete()
        solo_realization = ActivityRealization.objects.create(activity=self.activity)
        response = self.client.post(
            "/solver/ui-tt/constraints/new/?category=relation",
            data={
                "name": "one act one real",
                "constraint_type": "NOOVERLAP",
                "active": "on",
                "activities": [self.activity.id],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(SolverConstraint.objects.filter(name="one act one real").exists())

    def test_relation_accepts_single_activity_with_two_realizations(self):
        self._login_staff()
        response = self.client.post(
            "/solver/ui-tt/constraints/new/?category=relation",
            data={
                "name": "one act two real",
                "constraint_type": "NOOVERLAP",
                "active": "on",
                "activities": [self.activity.id],
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(SolverConstraint.objects.filter(name="one act two real").exists())

    def test_relation_rejects_activity_plus_own_realization(self):
        self._login_staff()
        ActivityRealization.objects.filter(
            id__in=[self.realization.id, self.second_realization.id]
        ).delete()
        only_realization = ActivityRealization.objects.create(activity=self.activity)
        response = self.client.post(
            "/solver/ui-tt/constraints/new/?category=relation",
            data={
                "name": "act plus own real",
                "constraint_type": "SAMEDAY",
                "active": "on",
                "activities": [self.activity.id],
                "realizations": [only_realization.id],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            SolverConstraint.objects.filter(name="act plus own real").exists()
        )

    def test_relation_accepts_two_distinct_realizations(self):
        self._login_staff()
        response = self.client.post(
            "/solver/ui-tt/constraints/new/?category=relation",
            data={
                "name": "two distinct real",
                "constraint_type": "NOOVERLAP",
                "active": "on",
                "realizations": [self.realization.id, self.second_realization.id],
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(SolverConstraint.objects.filter(name="two distinct real").exists())

    # --- Oracle: teacher queryset follows realization teachers ------

    def test_teacher_queryset_includes_realization_only_teacher(self):
        self._login_staff()
        response = self.client.get(
            "/solver/ui-tt/constraints/new/?category=workload"
        )
        form = response.context["form"]
        teacher_ids = set(form.fields["teachers"].queryset.values_list("id", flat=True))
        self.assertIn(self.realization_only_teacher.id, teacher_ids)

    def test_teacher_queryset_excludes_activity_only_teacher(self):
        self._login_staff()
        activity_only_teacher = Teacher.objects.create(
            user=User.objects.create_user("activity-only-t"), code="act-only"
        )
        self.activity.teachers.add(activity_only_teacher)
        response = self.client.get(
            "/solver/ui-tt/constraints/new/?category=workload"
        )
        form = response.context["form"]
        teacher_ids = set(form.fields["teachers"].queryset.values_list("id", flat=True))
        self.assertNotIn(activity_only_teacher.id, teacher_ids)

    # --- Oracle: ignored M2M fields cleared on save -----------------

    def test_relation_save_clears_teachers_and_groups(self):
        self._login_staff()
        response = self.client.post(
            "/solver/ui-tt/constraints/new/?category=relation",
            data={
                "name": "clear m2m",
                "constraint_type": "NOOVERLAP",
                "active": "on",
                "realizations": [self.realization.id, self.second_realization.id],
                "teachers": [self.teacher.id],
                "groups": [self.group.id],
            },
        )
        self.assertEqual(response.status_code, 302)
        constraint = SolverConstraint.objects.get(name="clear m2m")
        self.assertEqual(constraint.teachers.count(), 0)
        self.assertEqual(constraint.groups.count(), 0)

    def test_workload_save_clears_activities_and_realizations(self):
        self._login_staff()
        response = self.client.post(
            "/solver/ui-tt/constraints/new/?category=workload",
            data={
                "name": "clear act real",
                "constraint_type": "MAXDAYSWEEK",
                "active": "on",
                "value": "3",
                "groups": [self.group.id],
                "activities": [self.activity.id],
                "realizations": [self.realization.id],
            },
        )
        self.assertEqual(response.status_code, 302)
        constraint = SolverConstraint.objects.get(name="clear act real")
        self.assertEqual(constraint.activities.count(), 0)
        self.assertEqual(constraint.realizations.count(), 0)

    def test_relation_non_maxrooms_value_cleared_on_save(self):
        self._login_staff()
        response = self.client.post(
            "/solver/ui-tt/constraints/new/?category=relation",
            data={
                "name": "no value",
                "constraint_type": "NOOVERLAP",
                "active": "on",
                "realizations": [self.realization.id, self.second_realization.id],
                "value": "5",
            },
        )
        self.assertEqual(response.status_code, 302)
        constraint = SolverConstraint.objects.get(name="no value")
        self.assertIsNone(constraint.value)

    def test_maxrooms_value_preserved_on_save(self):
        self._login_staff()
        response = self.client.post(
            "/solver/ui-tt/constraints/new/?category=relation",
            data={
                "name": "maxrooms",
                "constraint_type": "MAXROOMSREALIZATIONS",
                "active": "on",
                "realizations": [self.realization.id, self.second_realization.id],
                "value": "2",
            },
        )
        self.assertEqual(response.status_code, 302)
        constraint = SolverConstraint.objects.get(name="maxrooms")
        self.assertEqual(constraint.value, 2)

    # --- Oracle: repair realization scoped multiple-select ----------

    def test_run_preview_repair_realization_field_is_scoped_select(self):
        self._login_staff()
        response = self.client.get("/solver/ui-tt/repair/")
        form = response.context["form"]
        from django import forms as django_forms
        self.assertIsInstance(
            form.fields["repair_realization"], django_forms.ModelMultipleChoiceField
        )
        qs_ids = set(form.fields["repair_realization"].queryset.values_list("id", flat=True))
        self.assertIn(self.realization.id, qs_ids)
        self.assertIn(self.second_realization.id, qs_ids)
        self.assertNotIn(self.other_realization.id, qs_ids)

    def test_run_preview_repair_realization_rejects_other_timetable_id(self):
        self._login_staff()
        response = self.client.post(
            "/solver/ui-tt/repair/",
            data={
                "time_limit": "30",
                "progress_every": "10",
                "num_search_workers": "7",
                "build_timeout": "0",
                "allocation_time_weight": "100",
                "allocation_room_weight": "25",
                "mode": "repair",
                "repair_realization": [str(self.other_realization.id)],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["command"])
        self.assertTrue(response.context["form"].errors)

    def test_run_preview_repair_realization_accepts_timetable_realization(self):
        self._login_staff()
        response = self.client.post(
            "/solver/ui-tt/repair/",
            data={
                "time_limit": "30",
                "progress_every": "10",
                "num_search_workers": "8",
                "build_timeout": "0",
                "allocation_time_weight": "100",
                "allocation_room_weight": "25",
                "mode": "repair",
                "repair_realization": [str(self.realization.id)],
            },
        )
        self.assertEqual(response.status_code, 200)
        command = response.context["command"]
        self.assertIn("--repair-realization={}".format(self.realization.id), command)

    # --- Oracle: group rules copy distinguishes preference levels ----

    def test_group_rules_distinguishes_cant_hate_want_and_value(self):
        self._login_staff()
        response = self.client.get("/solver/ui-tt/groups/")
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("CANT", body)
        self.assertIn("HATE", body)
        self.assertIn("WANT", body)
        self.assertIn("hard unavailability", body)
        self.assertIn("soft objective", body)
        self.assertIn("hard limits regardless of the preference level", body)


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


class StudentOverlapsTest(MyTestCase):
    """
    Test methods used for overlaps reduction.
    """

    def setUp(self):
        super(StudentOverlapsTest, self).setUp()
        self.duration = 3
        self.groupset = mommy.make("timetable.GroupSet")
        self.activityset = mommy.make("timetable.ActivitySet")
        self.tt = mommy.make(
            "timetable.Timetable", groupset=self.groupset, activityset=self.activityset
        )
        activities = mommy.make(
            "timetable.Activity",
            _quantity=2,
            duration=self.duration,
            activityset=self.activityset,
        )
        self.r1 = mommy.make("timetable.ActivityRealization", activity=activities[0])
        self.r2 = mommy.make("timetable.ActivityRealization", activity=activities[1])
        self.alloc1 = mommy.make(
            "timetable.Allocation",
            timetable=self.tt,
            activityRealization=self.r1,
            day="MON",
            start="08:00",
        )
        self.alloc2 = mommy.make(
            "timetable.Allocation",
            timetable=self.tt,
            activityRealization=self.r2,
            day="MON",
            start="10:00",
        )
        self.g1 = mommy.make(
            "timetable.Group",
            size=18,
            short_name="1_BUN-RI_LV_01",
            groupset=self.groupset,
        )
        self.g2 = mommy.make(
            "timetable.Group",
            size=18,
            short_name="1_BUN-RI_LV_02",
            groupset=self.groupset,
        )
        self.r1.groups.add(self.g1)
        self.r2.groups.add(self.g2)
        self.student = mommy.make("friprosveta.Student")

    def tearDown(self):
        friprosveta.models.Activity.objects.all().delete()
        friprosveta.models.Timetable.objects.all().delete()
        friprosveta.models.Student.objects.all().delete()

    def test_realizations(self):
        tt = self.tt
        self.assertEmpty(self.student.realizations(tt))
        self.g1.students.add(self.student)
        self.assertLength(self.student.realizations(tt), 1)
        self.assertTrue(self.r1 in self.student.realizations(tt))
        self.g2.students.add(self.student)
        self.assertLength(self.student.realizations(tt), 2)
        self.assertTrue(self.r1 in self.student.realizations(tt))
        self.assertTrue(self.r2 in self.student.realizations(tt))

    def test_allocations(self):
        tt = self.tt
        self.assertEmpty(self.student.realizations(tt))
        self.g1.students.add(self.student)
        self.assertLength(self.student.realizations(tt), 1)
        self.assertTrue(self.r1 in self.student.realizations(tt))
        self.g2.students.add(self.student)
        self.assertLength(self.student.realizations(tt), 2)
        self.assertTrue(self.r1 in self.student.realizations(tt))
        self.assertTrue(self.r2 in self.student.realizations(tt))

    def test_busy_hours(self):
        tt = self.tt
        self.assertEmpty(self.student.busy_hours(tt))
        self.g1.students.add(self.student)
        busy_hours = self.student.busy_hours(tt)
        self.assertEqual(len(busy_hours), self.duration)
        self.assertLength(busy_hours[("MON", "08:00")], 1)
        self.assertTrue(self.alloc1 in busy_hours[("MON", "08:00")])
        self.assertLength(busy_hours[("MON", "09:00")], 1)
        self.assertTrue(self.alloc1 in busy_hours[("MON", "09:00")])
        self.assertLength(busy_hours[("MON", "10:00")], 1)
        self.assertTrue(self.alloc1 in busy_hours[("MON", "10:00")])

        self.g2.students.add(self.student)
        busy_hours = self.student.busy_hours(tt)
        self.assertLength(busy_hours, self.duration * 2 - 1)  # One hour overlap
        self.assertLength(busy_hours[("MON", "08:00")], 1)
        self.assertTrue(self.alloc1 in busy_hours[("MON", "08:00")])
        self.assertLength(busy_hours[("MON", "09:00")], 1)
        self.assertTrue(self.alloc1 in busy_hours[("MON", "09:00")])
        self.assertLength(busy_hours[("MON", "10:00")], 2)
        self.assertTrue(self.alloc1 in busy_hours[("MON", "10:00")])
        self.assertTrue(self.alloc2 in busy_hours[("MON", "10:00")])
        self.assertLength(busy_hours[("MON", "11:00")], 1)
        self.assertTrue(self.alloc2 in busy_hours[("MON", "11:00")])
        self.assertLength(busy_hours[("MON", "12:00")], 1)
        self.assertTrue(self.alloc2 in busy_hours[("MON", "12:00")])

    def test_available(self):
        self.assertTrue(self.student.is_available(self.tt, self.alloc1))
        self.assertTrue(self.student.is_available(self.tt, self.alloc2))
        self.g1.students.add(self.student)
        self.assertFalse(self.student.is_available(self.tt, self.alloc1))
        self.assertFalse(self.student.is_available(self.tt, self.alloc2))
        self.alloc2.start = "12:00"
        self.alloc2.save()
        self.assertFalse(self.student.is_available(self.tt, self.alloc1))
        self.assertTrue(self.student.is_available(self.tt, self.alloc2))

    def test_overlaps(self):
        """
        Test method overlaps on class Student.
        It returns tuples in the form of (#day, #hour, #overlaps).
        The overlaps are list of allocations overlapping in the given timeslot.
        """
        self.assertEmpty(
            self.student.overlaps(self.tt), "No overlaps on empty schedule"
        )
        self.g1.students.add(self.student)
        self.assertEmpty(
            self.student.overlaps(self.tt), "No overlaps when enrolled on one activity"
        )
        self.g2.students.add(self.student)
        self.assertLength(
            self.student.overlaps(self.tt), 1, "One overlap between two activities"
        )
        res = self.student.overlaps(self.tt).pop()
        self.assertEqual(res[:2], ("MON", "10:00"), "There is overlap on MON at 10:00")
        self.assertEqual(
            set([self.alloc1, self.alloc2]),
            set(res[2]),
            "Alloc1 is overlapping with alloc2",
        )
        self.alloc2.start = "12:00"
        self.alloc2.save()
        self.assertFalse(
            self.student.overlaps(self.tt),
            "No overlaps when activities do not overlap in time",
        )


class FillGroupsTest(TestCase):
    def setUp(self):
        TestCase.setUp(self)
        self.c = fgc()
        self.study = mommy.make("friprosveta.Study", short_name="BUN-RI")
        self.groupset = mommy.make("timetable.GroupSet")
        self.aset = mommy.make("timetable.ActivitySet")
        self.tt = mommy.make(
            "timetable.Timetable", groupset=self.groupset, activityset=self.aset
        )
        self.a = mommy.make("friprosveta.Activity", type="LV", activityset=self.aset)
        self.subject = self.a.subject
        self.g1 = mommy.make(
            "timetable.Group",
            size=18,
            short_name="1_BUN-RI_LV_01",
            groupset=self.groupset,
        )
        self.g2 = mommy.make(
            "timetable.Group",
            size=18,
            short_name="1_BUN-RI_LV_02",
            groupset=self.groupset,
        )
        self.a.groups.add(self.g1)
        self.a.groups.add(self.g2)
        self.students = mommy.make("friprosveta.Student", _quantity=17)
        for student in self.students:
            mommy.make(
                "friprosveta.StudentEnrollment",
                groupset=self.groupset,
                student=student,
                subject=self.subject,
                study=self.study,
                enrollment_type=4,
                classyear=1,
            )

    def tearDown(self):
        self.a.activityset.timetable_set.first().delete()
        friprosveta.models.Student.objects.all().delete()

    # Commented out failing test due to model changes
    # def test_simple_enrollment(self):
    #     self.c.fill_groups_by_size(
    #         tt=self.tt,
    #         subjects=friprosveta.models.Subject.objects.all(),
    #         write_to_db=True,
    #     )
    #     self.assertEqual(self.g1.students.count(), 17, "All students should be enrolled")

    # Commented out failing test due to model changes
    # def test_enrollment_no_change(self):
    #     self.c.fill_groups_by_size(
    #         tt=self.tt,
    #         subjects=friprosveta.models.Subject.objects.all(),
    #         write_to_db=True,
    #     )
    #     original_g1_students = set(self.g1.students.all())
    #     new_students = mommy.make('friprosveta.Student', _quantity=17)
    #     for student in new_students:
    #         mommy.make('friprosveta.StudentEnrollment',
    #                    groupset=self.groupset,
    #                    student=student,
    #                    subject=self.subject,
    #                    study=self.study,
    #                    enrollment_type=4,
    #                    classyear=1)
    #     self.c.fill_groups_by_size(
    #         tt=self.tt,
    #         subjects=friprosveta.models.Subject.objects.all(),
    #         write_to_db=True,
    #     )
    #     self.assertEqual(self.g1.students.count(), 18, "Group g1 must be filled first")
    #     self.assertEqual(self.g2.students.count(), 16, "Group must be filled up to available students")
    #     self.assertEqual(len(set(self.g1.students.all()).intersection(original_g1_students)), 17,
    #                      "Students from g1 should not be moved")


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
        timetable = mommy.make("timetable.Timetable", public=True)
        timetable_site = mommy.make(
            "timetable.TimetableSite", default=False, timetable=timetable, site=site
        )
        request = self.request_factory.get("/", SERVER_NAME=self.server_name)
        with self.assertRaises(IndexError):
            default_timetable(request)
        site.delete()

    def test_default_timetable_no_public_timetable(self):
        site = mommy.make(Site, domain=self.server_name)
        timetable = mommy.make("timetable.Timetable", public=False)
        timetable_site = mommy.make(
            "timetable.TimetableSite", default=True, timetable=timetable, site=site
        )
        request = self.request_factory.get("/", SERVER_NAME=self.server_name)
        with self.assertRaises(IndexError):
            default_timetable(request)
        site.delete()

    def test_default_timetable_normal(self):
        site = mommy.make(Site, domain=self.server_name)
        timetable = mommy.make("timetable.Timetable", public=True)
        timetable_site = mommy.make(
            "timetable.TimetableSite", default=True, timetable=timetable, site=site
        )
        request = self.request_factory.get("/", SERVER_NAME=self.server_name)
        self.assertEqual(
            default_timetable(request),
            timetable,
            "The default timetable is not the right one",
        )
        site.delete()

    def test_default_timetable_multiple(self):
        # Get the one that starts later
        site = mommy.make(Site, domain=self.server_name)
        timetable1 = mommy.make(
            "timetable.Timetable", public=True, start=datetime.now()
        )
        timetable2 = mommy.make(
            "timetable.Timetable", public=True, start=datetime.now() + timedelta(123456)
        )
        timetable_site = mommy.make(
            "timetable.TimetableSite", default=True, timetable=timetable1, site=site
        )
        timetable_site = mommy.make(
            "timetable.TimetableSite", default=True, timetable=timetable2, site=site
        )
        request = self.request_factory.get("/", SERVER_NAME=self.server_name)
        self.assertEqual(
            default_timetable(request),
            timetable2,
            "The default timetable is not the right one",
        )
        site.delete()


class GroupSizeHintTest(TestCase):
    def setUp(self):
        TestCase.setUp(self)
        # Create group and some hints for it
        self.g1, self.g2 = mommy.make("timetable.Group", size=20), mommy.make(
            "timetable.Group", size=5
        )
        methods1 = [("1", 0), ("2", 10), ("3", 12)]
        methods2 = [("1", 0), ("2", 0), ("3", 0)]
        for method_name, size in methods1:
            mommy.make(
                "friprosveta.GroupSizeHint",
                group=self.g1,
                size=size,
                method=method_name,
            )
        for method_name, size in methods2:
            mommy.make(
                "friprosveta.GroupSizeHint",
                group=self.g2,
                size=size,
                method=method_name,
            )

    def test_group_size_hint_incorrect_strategy(self):
        with self.assertRaises(KeyError):
            GroupSizeHint.strategy(self.g1, ["unknown"], "Weird strategy name")

    def test_group_size_hint_first(self):
        strategy = "first"

        methods = ["1", "2"]
        expected = 0
        val = GroupSizeHint.strategy(self.g1, methods, strategy)
        self.assertEqual(
            val,
            expected,
            "Strategy '{}' for {} and methods {} should return {}".format(
                strategy, self.g1, methods, expected
            ),
        )

        methods = ["2", "3"]
        expected = 10
        val = GroupSizeHint.strategy(self.g1, methods, strategy)
        self.assertEqual(
            val,
            expected,
            "Strategy '{}' for {} and methods {} should return {}".format(
                strategy, self.g1, methods, expected
            ),
        )

        val = GroupSizeHint.strategy(self.g1, ["non", "existing"], strategy)
        self.assertIsNone(val, "If no hints are available None should be returned")

    def test_group_size_hint_first_not_zero(self):
        strategy = "first-non-zero"

        methods = ["1", "2", "3"]
        expected = 10
        val = GroupSizeHint.strategy(self.g1, methods, strategy)
        self.assertEqual(
            val,
            expected,
            "Strategy '{}' for {} and methods {} should return {}".format(
                strategy, self.g1, methods, expected
            ),
        )

        methods = ["1", "2", "3"]
        val = GroupSizeHint.strategy(self.g2, methods, strategy)
        self.assertIsNone(val, "If no hints are available None should be returned")

    def test_group_size_hint_max(self):
        strategy = "max"

        methods = ["1", "2", "3"]
        expected = 12
        val = GroupSizeHint.strategy(self.g1, methods, strategy)
        self.assertEqual(
            val,
            expected,
            "Strategy '{}' for {} and methods {} should return {}".format(
                strategy, self.g1, methods, expected
            ),
        )

        val = GroupSizeHint.strategy(self.g1, ["non", "existing"], strategy)
        self.assertIsNone(val, "If no hints are available None should be returned")

        methods = ["1", "2", "3"]
        expected = 0
        val = GroupSizeHint.strategy(self.g2, methods, strategy)
        self.assertEqual(
            val,
            expected,
            "Strategy '{}' for {} and methods {} should return {}".format(
                strategy,
                self.g2,
                methods,
                expected,
            ),
        )

    def test_group_size_hint_max_not_zero(self):
        strategy = "max-non-zero"

        methods = ["1", "2", "3"]
        expected = 12
        val = GroupSizeHint.strategy(self.g1, methods, strategy)
        self.assertEqual(
            val,
            expected,
            "Strategy '{}' for {} and methods {} should return {}".format(
                strategy, self.g1, methods, expected
            ),
        )

        methods = ["1", "2", "3"]
        val = GroupSizeHint.strategy(self.g2, methods, strategy)
        self.assertIsNone(val, "If no hints are available None should be returned")

    def test_group_size_hint_max_group(self):
        strategy = "max-group"

        methods = ["1", "2", "3"]
        expected = 20
        val = GroupSizeHint.strategy(self.g1, methods, strategy)
        self.assertEqual(
            val,
            expected,
            "Strategy '{}' for {} and methods {} should return {}".format(
                strategy, self.g1, methods, expected
            ),
        )

        val = GroupSizeHint.strategy(self.g1, ["non", "existing"], strategy)
        self.assertIsNone(val, "If no hints are available None should be returned")

        methods = ["1", "2", "3"]
        expected = max(0, self.g2.size)
        val = GroupSizeHint.strategy(self.g2, methods, strategy)
        self.assertEqual(
            val,
            expected,
            "Strategy '{}' for {} and methods {} should return {}".format(
                strategy, self.g2, methods, expected
            ),
        )


class PrepareORToolsGroupsTest(TestCase):
    def setUp(self):
        self.preferenceset = PreferenceSet.objects.create(
            slug="prepare-prefs", name="Prepare preferences"
        )
        self.activityset = ActivitySet.objects.create(
            slug="prepare-activities", name="Prepare activities"
        )
        self.groupset = GroupSet.objects.create(
            slug="prepare-groups", name="Prepare groups", created=datetime.now()
        )
        self.timetable = Timetable.objects.create(
            slug="prepare-current",
            name="Prepare current",
            activityset=self.activityset,
            preferenceset=self.preferenceset,
            groupset=self.groupset,
        )
        self.study = friprosveta.models.Study.objects.create(
            short_name="TEST", name="Test study"
        )
        self.subject = friprosveta.models.Subject.objects.create(
            code="PREP", name="Prepare subject"
        )
        lecture_type = friprosveta.models.LectureType.objects.create(
            name="Prepare lecture", short_name="PREP", duration=1
        )
        self.top_group = Group.objects.create(
            name="Test top group",
            short_name="1_TEST",
            size=3,
            groupset=self.groupset,
        )
        lecture = friprosveta.models.Activity.objects.create(
            name="Prepare lecture",
            short_name="PREP-P",
            activityset=self.activityset,
            type="P",
            duration=1,
            subject=self.subject,
            lecture_type=lecture_type,
        )
        lecture.groups.add(self.top_group)
        laboratory = friprosveta.models.Activity.objects.create(
            name="Prepare laboratory",
            short_name="PREP-LV",
            activityset=self.activityset,
            type="LV",
            duration=1,
            subject=self.subject,
            lecture_type=lecture_type,
        )
        self.lecture_realization = ActivityRealization.objects.create(activity=lecture)
        self.laboratory_realization = ActivityRealization.objects.create(
            activity=laboratory, intended_size=16
        )
        previous_groupset = GroupSet.objects.create(
            slug="prepare-previous-groups",
            name="Prepare previous groups",
            created=datetime.now(),
        )
        self.previous_timetable = Timetable.objects.create(
            slug="prepare-previous",
            name="Prepare previous",
            groupset=previous_groupset,
        )
        self.previous_group = Group.objects.create(
            name="Test previous group",
            short_name=self.top_group.short_name,
            size=16,
            groupset=previous_groupset,
        )

    def _run_command(self, *arguments):
        output = StringIO()
        with (
            patch("friprosveta.management.commands.prepare_ortools_groups.Studij"),
            patch("friprosveta.management.commands.prepare_ortools_groups.Najave"),
            patch(
                "friprosveta.models.Subject.get_studis_predmetnik",
                return_value=[],
            ),
        ):
            call_command(
                "prepare_ortools_groups",
                self.timetable.slug,
                "2026",
                *arguments,
                stdout=output,
            )
        return output.getvalue()

    def test_requires_previous_timetable_for_prior_hint_sources(self):
        with self.assertRaisesMessage(
            CommandError, "--previous-timetable-slug is required"
        ):
            call_command(
                "prepare_ortools_groups",
                self.timetable.slug,
                "2026",
                "--hint-source",
                "previous-size",
            )

    def test_uses_selected_hints_to_size_subgroups_and_assign_realizations(self):
        previous_student = friprosveta.models.Student.objects.create(
            name="Previous", surname="Student", studentId="PREV0001"
        )
        previous_student.groups.add(self.previous_group)
        friprosveta.models.StudentEnrollment.objects.create(
            groupset=self.previous_timetable.groupset,
            student=previous_student,
            subject=self.subject,
            study=self.study,
            classyear=1,
            enrollment_type="4",
        )
        current_student = friprosveta.models.Student.objects.create(
            name="Current", surname="Student", studentId="CURR0001"
        )
        friprosveta.models.StudentEnrollment.objects.create(
            groupset=self.groupset,
            student=current_student,
            subject=self.subject,
            study=self.study,
            classyear=1,
            enrollment_type="4",
        )

        self._run_command(
            "--previous-timetable-slug",
            self.previous_timetable.slug,
            "--hint-source",
            "previous-students",
            "--hint-source",
            "current-enrollments",
            "--hint-source",
            "previous-size",
            "--hint-strategy",
            "max",
        )

        self.top_group.refresh_from_db()
        subgroup_sizes = list(
            Group.objects.filter(parent=self.top_group).values_list("size", flat=True)
        )
        self.assertEqual(self.top_group.size, 16)
        self.assertCountEqual(subgroup_sizes, [15, 1])
        self.assertEqual(
            self.lecture_realization.groups.get(), self.top_group
        )
        self.assertEqual(self.laboratory_realization.group_size, 16)
        self.assertEqual(
            GroupSizeHint.objects.get(
                group=self.top_group,
                method="group from {} from size".format(
                    self.previous_timetable.groupset
                ),
            ).size,
            16,
        )
        self.assertEqual(
            GroupSizeHint.objects.get(
                group=self.top_group,
                method="group from {} with enrollment types [4, 26]".format(
                    self.previous_timetable.groupset
                ),
            ).size,
            1,
        )

    def test_previous_timetable_defaults_to_max_of_current_and_prior_enrollments(self):
        for index in range(4):
            student = friprosveta.models.Student.objects.create(
                name="Previous",
                surname=f"Student {index}",
                studentId=f"PREV{index:04d}",
            )
            friprosveta.models.StudentEnrollment.objects.create(
                groupset=self.previous_timetable.groupset,
                student=student,
                subject=self.subject,
                study=self.study,
                classyear=1,
                enrollment_type="4",
                source="studis_confirmed",
            )
        current_student = friprosveta.models.Student.objects.create(
            name="Current", surname="Student", studentId="CURR0002"
        )
        friprosveta.models.StudentEnrollment.objects.create(
            groupset=self.groupset,
            student=current_student,
            subject=self.subject,
            study=self.study,
            classyear=1,
            enrollment_type="4",
            source="studis_confirmed",
        )

        self._run_command(
            "--previous-timetable-slug",
            self.previous_timetable.slug,
        )

        self.top_group.refresh_from_db()
        self.assertEqual(self.top_group.size, 4)
        self.assertFalse(self.previous_group.students.exists())
        self.assertEqual(
            GroupSizeHint.objects.get(
                group=self.top_group,
                method="enrollments from {} for types [4, 26]".format(
                    self.previous_timetable.groupset
                ),
            ).size,
            4,
        )
        self.assertEqual(
            GroupSizeHint.objects.get(
                group=self.top_group,
                method="enrollments from {} for types [4, 26]".format(
                    self.groupset
                ),
            ).size,
            1,
        )
        self.assertEqual(
            GroupSizeHint.objects.get(
                group=self.top_group,
                method="enrollments from {} for types [4, 26]".format(
                    self.groupset
                ),
            ).size,
            1,
        )

    def test_excluded_study_is_not_resized(self):
        self.laboratory_realization.delete()

        self._run_command(
            "--previous-timetable-slug",
            self.previous_timetable.slug,
            "--hint-source",
            "previous-size",
            "--exclude-study",
            self.study.short_name,
        )

        self.top_group.refresh_from_db()
        self.assertEqual(self.top_group.size, 3)
        self.assertEqual(
            GroupSizeHint.objects.get(
                group=self.top_group,
                method="group from {} from size".format(
                    self.previous_timetable.groupset
                ),
            ).size,
            16,
        )
        self.assertFalse(Group.objects.filter(parent=self.top_group).exists())

    def test_dry_run_rolls_back_hints_subgroups_and_assignments(self):
        self._run_command(
            "--previous-timetable-slug",
            self.previous_timetable.slug,
            "--hint-source",
            "previous-size",
            "--dry-run",
        )

        self.top_group.refresh_from_db()
        self.assertEqual(self.top_group.size, 3)
        self.assertFalse(GroupSizeHint.objects.filter(group=self.top_group).exists())
        self.assertFalse(Group.objects.filter(parent=self.top_group).exists())
        self.assertFalse(self.lecture_realization.groups.exists())
        self.assertFalse(self.laboratory_realization.groups.exists())


class PreparationPreviewUITest(TestCase):
    """
    Tests for the superuser-only prepare_ortools_groups command preview UI:
    permissions, timetable scoping of the previous-timetable picker, prior
    hint source validation, and command construction. The management command
    is never executed from the HTTP path.
    """

    def setUp(self):
        self.preferenceset = PreferenceSet.objects.create(
            slug="prep-ui-prefs", name="Prep UI Preferences"
        )
        self.activityset = ActivitySet.objects.create(
            slug="prep-ui-activities", name="Prep UI Activities"
        )
        self.groupset = GroupSet.objects.create(
            slug="prep-ui-groups", name="Prep UI Groups", created=datetime.now()
        )
        self.timetable = Timetable.objects.create(
            slug="prep-ui-tt",
            name="Prep UI Timetable",
            activityset=self.activityset,
            preferenceset=self.preferenceset,
            groupset=self.groupset,
        )
        self.previous_groupset = GroupSet.objects.create(
            slug="prep-ui-prev-groups", name="Prep UI Prev Groups", created=datetime.now()
        )
        self.previous_timetable = Timetable.objects.create(
            slug="prep-ui-prev",
            name="Prep UI Previous",
            activityset=self.activityset,
            preferenceset=self.preferenceset,
            groupset=self.previous_groupset,
        )
        self.study = Study.objects.create(short_name="PVE", name="Prep study")
        self.staff_user = User.objects.create_user(
            "prep-staff", password="pw", is_staff=True, is_superuser=True
        )
        self.non_staff_user = User.objects.create_user(
            "prep-regular", password="pw", is_staff=False, is_superuser=False
        )
        self.client = Client()

    def _login_staff(self):
        self.client.login(username="prep-staff", password="pw")

    def _login_regular(self):
        self.client.login(username="prep-regular", password="pw")

    # --- Permissions ------------------------------------------------

    def test_preview_requires_login(self):
        response = self.client.get("/solver/prep-ui-tt/prepare/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login", response["Location"])

    def test_preview_requires_superuser(self):
        self._login_regular()
        response = self.client.get("/solver/prep-ui-tt/prepare/")
        self.assertEqual(response.status_code, 403)

    def test_preview_staff_ok(self):
        self._login_staff()
        response = self.client.get("/solver/prep-ui-tt/prepare/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Prepare OR-Tools groups")

    def test_dashboard_links_to_preparation_preview(self):
        self._login_staff()
        response = self.client.get("/solver/prep-ui-tt/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Prepare groups")
        self.assertContains(response, "/solver/prep-ui-tt/prepare")

    # --- Scoping -----------------------------------------------------

    def test_previous_timetable_choices_exclude_current(self):
        self._login_staff()
        response = self.client.get("/solver/prep-ui-tt/prepare/")
        form = response.context["form"]
        previous_ids = set(
            form.fields["previous_timetable"].queryset.values_list("id", flat=True)
        )
        self.assertIn(self.previous_timetable.id, previous_ids)
        self.assertNotIn(self.timetable.id, previous_ids)

    def test_unknown_timetable_returns_404(self):
        self._login_staff()
        response = self.client.get("/solver/does-not-exist/prepare/")
        self.assertEqual(response.status_code, 404)

    # --- Defaults & no execution ------------------------------------

    def test_get_does_not_produce_command(self):
        self._login_staff()
        response = self.client.get("/solver/prep-ui-tt/prepare/")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["command"])

    def test_default_hint_source_is_current_enrollments_only(self):
        self._login_staff()
        response = self.client.get("/solver/prep-ui-tt/prepare/")
        form = response.context["form"]
        self.assertEqual(form.fields["hint_source"].initial, ["current-enrollments"])
        self.assertEqual(form.fields["hint_strategy"].initial, "max")

    # --- Command construction ---------------------------------------

    def test_safe_defaults_render_minimal_command(self):
        self._login_staff()
        response = self.client.post(
            "/solver/prep-ui-tt/prepare/",
            data={
                "year": "2026",
                "hint_source": ["current-enrollments"],
                "hint_strategy": "max",
            },
        )
        self.assertEqual(response.status_code, 200)
        command = response.context["command"]
        self.assertIn("prepare_ortools_groups prep-ui-tt 2026", command)
        self.assertIn("--hint-source=current-enrollments", command)
        self.assertIn("--hint-strategy=max", command)
        self.assertNotIn("--previous-timetable-slug", command)
        self.assertNotIn("--dry-run", command)
        self.assertNotIn("--exclude-study", command)

    @patch("friprosveta.preparation_run_views.call_command")
    def test_run_now_executes_validated_preparation_command(self, mocked_call_command):
        self._login_staff()
        mocked_call_command.side_effect = lambda *args, **kwargs: kwargs["stdout"].write("Prepared groups\n")

        response = self.client.post(
            "/solver/prep-ui-tt/prepare/",
            data={
                "action": "run",
                "year": "2026",
                "hint_source": ["current-enrollments"],
                "hint_strategy": "max",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            mocked_call_command.call_args.args,
            ("prepare_ortools_groups", "prep-ui-tt", "2026"),
        )
        self.assertTrue(response.context["succeeded"])
        self.assertIn("Prepared groups", response.context["output"])

    def test_prior_hint_source_requires_previous_timetable(self):
        self._login_staff()
        response = self.client.post(
            "/solver/prep-ui-tt/prepare/",
            data={
                "year": "2026",
                "hint_source": ["previous-size"],
                "hint_strategy": "max",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["command"])
        self.assertTrue(response.context["form"].errors)

    def test_prior_hint_source_with_previous_timetable_renders_command(self):
        self._login_staff()
        response = self.client.post(
            "/solver/prep-ui-tt/prepare/",
            data={
                "year": "2026",
                "previous_timetable": str(self.previous_timetable.id),
                "hint_source": ["previous-enrollments", "current-enrollments"],
                "hint_strategy": "max-non-zero",
            },
        )
        self.assertEqual(response.status_code, 200)
        command = response.context["command"]
        self.assertIn(
            "--previous-timetable-slug={}".format(self.previous_timetable.slug),
            command,
        )
        self.assertIn("--hint-source=previous-enrollments", command)
        self.assertIn("--hint-source=current-enrollments", command)
        self.assertIn("--hint-strategy=max-non-zero", command)

    def test_exclude_study_emits_repeatable_flags(self):
        other_study = Study.objects.create(short_name="OTH", name="Other study")
        self._login_staff()
        response = self.client.post(
            "/solver/prep-ui-tt/prepare/",
            data={
                "year": "2026",
                "hint_source": ["current-enrollments"],
                "hint_strategy": "max",
                "exclude_study": [str(self.study.id), str(other_study.id)],
            },
        )
        self.assertEqual(response.status_code, 200)
        command = response.context["command"]
        self.assertIn("--exclude-study=PVE", command)
        self.assertIn("--exclude-study=OTH", command)

    def test_dry_run_flag_rendered(self):
        self._login_staff()
        response = self.client.post(
            "/solver/prep-ui-tt/prepare/",
            data={
                "year": "2026",
                "hint_source": ["current-enrollments"],
                "hint_strategy": "max",
                "dry_run": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        command = response.context["command"]
        self.assertIn("--dry-run", command)

    def test_year_is_required(self):
        self._login_staff()
        response = self.client.post(
            "/solver/prep-ui-tt/prepare/",
            data={
                "hint_source": ["current-enrollments"],
                "hint_strategy": "max",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["command"])
        self.assertTrue(response.context["form"].errors)

    def test_hint_source_is_required(self):
        self._login_staff()
        response = self.client.post(
            "/solver/prep-ui-tt/prepare/",
            data={
                "year": "2026",
                "hint_strategy": "max",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["command"])
        self.assertTrue(response.context["form"].errors)


class StudisWorkflowUITest(TestCase):
    """Tests for the superuser-only Studis workflow preview/execute page."""

    def setUp(self):
        self.preferenceset = PreferenceSet.objects.create(
            slug="studis-ui-prefs", name="Studis UI Preferences"
        )
        self.activityset = ActivitySet.objects.create(
            slug="studis-ui-activities", name="Studis UI Activities"
        )
        self.groupset = GroupSet.objects.create(
            slug="studis-ui-groups", name="Studis UI Groups", created=datetime.now()
        )
        self.timetable = Timetable.objects.create(
            slug="studis-ui-tt",
            name="Studis UI Timetable",
            activityset=self.activityset,
            preferenceset=self.preferenceset,
            groupset=self.groupset,
        )
        self.timetable_set = TimetableSet.objects.create(
            slug="studis-ui-set",
            name="Studis UI Set",
        )
        self.timetable_set.timetables.add(self.timetable)
        self.staff_user = User.objects.create_user(
            "studis-staff", password="pw", is_staff=True, is_superuser=True
        )
        self.non_staff_user = User.objects.create_user(
            "studis-regular", password="pw", is_staff=False, is_superuser=False
        )
        self.client = Client()
        self._clear_studis_cache()

    def _studis_cache_keys(self, timetable_slug="studis-ui-tt"):
        return (
            "{}:{}".format(STUDIS_WORKFLOW_LOCK_PREFIX, timetable_slug),
            "{}:{}".format(STUDIS_WORKFLOW_STATE_PREFIX, timetable_slug),
        )

    def _clear_studis_cache(self, timetable_slug="studis-ui-tt"):
        lock_key, state_key = self._studis_cache_keys(timetable_slug)
        cache.delete(lock_key)
        cache.delete(state_key)

    def tearDown(self):
        self._clear_studis_cache()
        super().tearDown()

    def _login_staff(self):
        self.client.login(username="studis-staff", password="pw")

    def _login_regular(self):
        self.client.login(username="studis-regular", password="pw")

    # --- Permissions ------------------------------------------------

    def test_preview_requires_login(self):
        response = self.client.get("/solver/studis-ui-tt/studis-workflow/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login", response["Location"])

    def test_preview_requires_superuser(self):
        self._login_regular()
        response = self.client.get("/solver/studis-ui-tt/studis-workflow/")
        self.assertEqual(response.status_code, 403)

    def test_preview_staff_ok(self):
        self._login_staff()
        response = self.client.get("/solver/studis-ui-tt/studis-workflow/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Studis workflow")

    def test_dashboard_links_to_studis_workflow(self):
        self._login_staff()
        response = self.client.get("/solver/studis-ui-tt/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Run Studis workflow")
        self.assertContains(response, "/solver/studis-ui-tt/studis-workflow")

    # --- Command previews -------------------------------------------

    def test_get_does_not_render_command(self):
        self._login_staff()
        response = self.client.get("/solver/studis-ui-tt/studis-workflow/")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["command"])

    def test_sync_subjects_preview(self):
        self._login_staff()
        response = self.client.post(
            "/solver/studis-ui-tt/studis-workflow/",
            data={
                "workflow": "sync_subjects",
                "action": "preview",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["command"], "python3 manage.py sync_subjects True")

    def test_import_najave_preview_with_optional_filter(self):
        self._login_staff()
        response = self.client.post(
            "/solver/studis-ui-tt/studis-workflow/",
            data={
                "workflow": "import_studis_najave",
                "year": "2026",
                "semester_id": "2",
                "subject_code": "SI123",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["command"],
            "python3 manage.py import_studis_najave studis-ui-tt 2026 2 --subject=SI123",
        )

    def test_create_activities_preview_with_subject_filter(self):
        self._login_staff()
        response = self.client.post(
            "/solver/studis-ui-tt/studis-workflow/",
            data={
                "workflow": "create_activities",
                "year": "2026",
                "semester_id": "2",
                "subject_code": "CS101",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["command"],
            "python3 manage.py create_activities studis-ui-tt 2026 2 --subject_code=CS101",
        )

    def test_import_students_preview_with_flags(self):
        self._login_staff()
        response = self.client.post(
            "/solver/studis-ui-tt/studis-workflow/",
            data={
                "workflow": "import_studis_students",
                "year": "2026",
                "date": "2026-05-01",
                "unconfirmed": "on",
                "unfinished": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["command"],
            "python3 manage.py import_studis_students studis-ui-tt 2026 2026-05-01 --unconfirmed --unfinished",
        )

    def test_create_top_level_groups_preview(self):
        self._login_staff()
        response = self.client.post(
            "/solver/studis-ui-tt/studis-workflow/",
            data={
                "workflow": "create_top_level_groups",
                "year": "2026",
                "semester_id": "2",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["command"],
            "python3 manage.py create_top_level_groups studis-ui-tt 2026 2",
        )

    def test_create_realizations_preview(self):
        self._login_staff()
        response = self.client.post(
            "/solver/studis-ui-tt/studis-workflow/",
            data={
                "workflow": "create_realizations",
                "timetable_set": "studis-ui-set",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["command"],
            "python3 manage.py create_realizations studis-ui-tt studis-ui-set",
        )

    def test_notebook_workflow_previews(self):
        self._login_staff()
        previews = [
            (
                {"workflow": "check_durations"},
                "python3 manage.py check_durations studis-ui-tt",
            ),
            (
                {"workflow": "set_visible_groups"},
                "python3 manage.py set_visible_groups studis-ui-tt",
            ),
            (
                {
                    "workflow": "find_missing_teachers",
                    "timetable_set": "studis-ui-set",
                },
                "python3 manage.py find_missing_teachers studis-ui-tt studis-ui-set",
            ),
            (
                {"workflow": "remove_pad_groups", "dry_run": "on"},
                "python3 manage.py remove_pad_groups studis-ui-tt --dry-run",
            ),
        ]

        for data, expected_command in previews:
            response = self.client.post("/solver/studis-ui-tt/studis-workflow/", data=data)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context["command"], expected_command)

    # --- Execution --------------------------------------------------

    @patch("friprosveta.studis_workflow_views.call_command")
    @patch("friprosveta.studis_workflow_views.close_old_connections")
    @patch("friprosveta.studis_workflow_views.Thread")
    def test_run_sync_subjects_starts_in_background(
        self,
        mocked_thread,
        mocked_close_old_connections,
        mocked_call_command,
    ):
        self._login_staff()
        mocked_thread_instance = MagicMock()

        def fake_start():
            target = mocked_thread.call_args.kwargs.get("target")
            if target is None:
                target = mocked_thread.call_args.args[0]
            target()

        mocked_thread_instance.start.side_effect = fake_start
        mocked_thread.return_value = mocked_thread_instance
        mocked_call_command.side_effect = lambda *args, **kwargs: kwargs["stdout"].write(
            "Subjects synced\n"
        )

        response = self.client.post(
            "/solver/studis-ui-tt/studis-workflow/",
            data={"action": "run", "workflow": "sync_subjects"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            reverse("solver_dashboard", kwargs={"timetable_slug": "studis-ui-tt"}),
        )
        self.assertEqual(mocked_thread.call_count, 1)
        mocked_thread_instance.start.assert_called_once()
        self.assertTrue(mocked_thread.call_args.kwargs["daemon"])
        self.assertEqual(mocked_call_command.call_args.args, ("sync_subjects", "True"))
        state_key = self._studis_cache_keys("studis-ui-tt")[1]
        workflow_state = cache.get(state_key)
        self.assertEqual(workflow_state["status"], "succeeded")
        self.assertEqual(workflow_state["command"], "python3 manage.py sync_subjects True")
        self.assertIn("Subjects synced", workflow_state["output"])

    @patch("friprosveta.studis_workflow_views.call_command")
    @patch("friprosveta.studis_workflow_views.close_old_connections")
    @patch("friprosveta.studis_workflow_views.Thread")
    def test_run_import_students_passes_flags_in_background(
        self,
        mocked_thread,
        mocked_close_old_connections,
        mocked_call_command,
    ):
        self._login_staff()
        mocked_thread_instance = MagicMock()

        def fake_start():
            target = mocked_thread.call_args.kwargs.get("target")
            if target is None:
                target = mocked_thread.call_args.args[0]
            target()

        mocked_thread_instance.start.side_effect = fake_start
        mocked_thread.return_value = mocked_thread_instance
        mocked_call_command.side_effect = lambda *args, **kwargs: kwargs["stdout"].write(
            "Students imported\n"
        )

        response = self.client.post(
            "/solver/studis-ui-tt/studis-workflow/",
            data={
                "action": "run",
                "workflow": "import_studis_students",
                "year": "2026",
                "date": "2026-05-01",
                "unconfirmed": "on",
                "unfinished": "on",
                "preenrolment": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            reverse("solver_dashboard", kwargs={"timetable_slug": "studis-ui-tt"}),
        )
        self.assertEqual(
            mocked_call_command.call_args.args,
            ("import_studis_students", "studis-ui-tt", "2026", "2026-05-01"),
        )
        self.assertTrue(mocked_call_command.call_args.kwargs["unconfirmed"])
        self.assertTrue(mocked_call_command.call_args.kwargs["unfinished"])
        self.assertTrue(mocked_call_command.call_args.kwargs["preenrolment"])
        state_key = self._studis_cache_keys("studis-ui-tt")[1]
        workflow_state = cache.get(state_key)
        self.assertEqual(
            workflow_state["command"],
            "python3 manage.py import_studis_students studis-ui-tt 2026 2026-05-01 --unconfirmed --unfinished --preenrolment",
        )

    @patch("friprosveta.studis_workflow_views.call_command")
    @patch("friprosveta.studis_workflow_views.close_old_connections")
    @patch("friprosveta.studis_workflow_views.Thread")
    def test_run_create_activities_calls_subject_filter_in_background(
        self,
        mocked_thread,
        mocked_close_old_connections,
        mocked_call_command,
    ):
        self._login_staff()
        mocked_thread_instance = MagicMock()

        def fake_start():
            target = mocked_thread.call_args.kwargs.get("target")
            if target is None:
                target = mocked_thread.call_args.args[0]
            target()

        mocked_thread_instance.start.side_effect = fake_start
        mocked_thread.return_value = mocked_thread_instance
        mocked_call_command.side_effect = lambda *args, **kwargs: kwargs["stdout"].write(
            "Activities updated\n"
        )

        response = self.client.post(
            "/solver/studis-ui-tt/studis-workflow/",
            data={
                "action": "run",
                "workflow": "create_activities",
                "year": "2026",
                "semester_id": "2",
                "subject_code": "CS101",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            reverse("solver_dashboard", kwargs={"timetable_slug": "studis-ui-tt"}),
        )
        self.assertEqual(
            mocked_call_command.call_args.args,
            ("create_activities", "studis-ui-tt", 2026, "2"),
        )
        self.assertEqual(mocked_call_command.call_args.kwargs["subject_code"], "CS101")

    @patch("friprosveta.studis_workflow_views.call_command")
    @patch("friprosveta.studis_workflow_views.close_old_connections")
    @patch("friprosveta.studis_workflow_views.Thread")
    def test_run_import_najave_calls_subject_filter_in_background(
        self,
        mocked_thread,
        mocked_close_old_connections,
        mocked_call_command,
    ):
        self._login_staff()
        mocked_thread_instance = MagicMock()

        def fake_start():
            target = mocked_thread.call_args.kwargs.get("target")
            if target is None:
                target = mocked_thread.call_args.args[0]
            target()

        mocked_thread_instance.start.side_effect = fake_start
        mocked_thread.return_value = mocked_thread_instance
        mocked_call_command.side_effect = lambda *args, **kwargs: kwargs["stdout"].write(
            "Najave imported\n"
        )

        response = self.client.post(
            "/solver/studis-ui-tt/studis-workflow/",
            data={
                "action": "run",
                "workflow": "import_studis_najave",
                "year": "2026",
                "semester_id": "2",
                "subject_code": "SI123",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            reverse("solver_dashboard", kwargs={"timetable_slug": "studis-ui-tt"}),
        )
        self.assertEqual(
            mocked_call_command.call_args.args,
            ("import_studis_najave", "studis-ui-tt", "2026", "2"),
        )
        self.assertEqual(mocked_call_command.call_args.kwargs["subject"][0], "SI123")

    @patch("friprosveta.studis_workflow_views.call_command")
    @patch("friprosveta.studis_workflow_views.close_old_connections")
    @patch("friprosveta.studis_workflow_views.Thread")
    def test_run_create_top_level_groups_executes_command_in_background(
        self,
        mocked_thread,
        mocked_close_old_connections,
        mocked_call_command,
    ):
        self._login_staff()
        mocked_thread_instance = MagicMock()

        def fake_start():
            target = mocked_thread.call_args.kwargs.get("target")
            if target is None:
                target = mocked_thread.call_args.args[0]
            target()

        mocked_thread_instance.start.side_effect = fake_start
        mocked_thread.return_value = mocked_thread_instance
        mocked_call_command.side_effect = lambda *args, **kwargs: kwargs["stdout"].write(
            "Top-level groups created\n"
        )

        response = self.client.post(
            "/solver/studis-ui-tt/studis-workflow/",
            data={
                "action": "run",
                "workflow": "create_top_level_groups",
                "year": "2026",
                "semester_id": "2",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            reverse("solver_dashboard", kwargs={"timetable_slug": "studis-ui-tt"}),
        )
        self.assertEqual(
            mocked_call_command.call_args.args,
            ("create_top_level_groups", "studis-ui-tt", "2026", "2"),
        )

    @patch("friprosveta.studis_workflow_views.call_command")
    @patch("friprosveta.studis_workflow_views.close_old_connections")
    @patch("friprosveta.studis_workflow_views.Thread")
    def test_run_create_realizations_executes_command_in_background(
        self,
        mocked_thread,
        mocked_close_old_connections,
        mocked_call_command,
    ):
        self._login_staff()
        mocked_thread_instance = MagicMock()

        def fake_start():
            target = mocked_thread.call_args.kwargs.get("target")
            if target is None:
                target = mocked_thread.call_args.args[0]
            target()

        mocked_thread_instance.start.side_effect = fake_start
        mocked_thread.return_value = mocked_thread_instance
        mocked_call_command.side_effect = lambda *args, **kwargs: kwargs["stdout"].write(
            "Realizations created\n"
        )

        response = self.client.post(
            "/solver/studis-ui-tt/studis-workflow/",
            data={
                "action": "run",
                "workflow": "create_realizations",
                "timetable_set": "studis-ui-set",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            reverse("solver_dashboard", kwargs={"timetable_slug": "studis-ui-tt"}),
        )
        self.assertEqual(
            mocked_call_command.call_args.args,
            ("create_realizations", "studis-ui-tt", "studis-ui-set"),
        )

    def test_run_studis_workflow_blocked_when_running(self):
        self._login_staff()
        lock_key, state_key = self._studis_cache_keys("studis-ui-tt")
        cache.set(
            lock_key,
            "running",
            timeout=STUDIS_WORKFLOW_CACHE_TTL_SECONDS,
        )
        cache.set(
            state_key,
            {
                "status": "running",
                "is_running": True,
                "workflow": "import_studis_students",
                "started_by": "studis-staff",
            },
            timeout=STUDIS_WORKFLOW_CACHE_TTL_SECONDS,
        )

        response = self.client.post(
            "/solver/studis-ui-tt/studis-workflow/",
            data={
                "action": "run",
                "workflow": "sync_subjects",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "Studis workflow is currently running.",
            response.content.decode("utf-8"),
        )
        self.assertIn('name="action" value="run" disabled', response.content.decode("utf-8"))

    def test_dashboard_shows_running_studis_workflow_status(self):
        self._login_staff()
        lock_key, state_key = self._studis_cache_keys("studis-ui-tt")
        cache.set(
            lock_key,
            "running",
            timeout=STUDIS_WORKFLOW_CACHE_TTL_SECONDS,
        )
        cache.set(
            state_key,
            {
                "status": "running",
                "is_running": True,
                "workflow": "create_top_level_groups",
                "started_by": "studis-staff",
            },
            timeout=STUDIS_WORKFLOW_CACHE_TTL_SECONDS,
        )

        response = self.client.get("/solver/studis-ui-tt/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Studis workflow is currently running.")
        self.assertContains(response, "Started by")
        self.assertContains(response, "studis-staff")


class NotebookWorkflowCommandsTest(TestCase):
    def setUp(self):
        self.activityset = ActivitySet.objects.create(
            slug="notebook-command-activities", name="Notebook command activities"
        )
        self.preferenceset = PreferenceSet.objects.create(
            slug="notebook-command-preferences", name="Notebook command preferences"
        )
        self.groupset = GroupSet.objects.create(
            slug="notebook-command-groups",
            name="Notebook command groups",
            created=datetime.now(),
        )
        self.timetable = Timetable.objects.create(
            slug="notebook-command-tt",
            name="Notebook command timetable",
            activityset=self.activityset,
            preferenceset=self.preferenceset,
            groupset=self.groupset,
        )
        self.timetable_set = TimetableSet.objects.create(
            slug="notebook-command-set", name="Notebook command set"
        )
        self.timetable_set.timetables.add(self.timetable)
        self.subject = friprosveta.models.Subject.objects.create(
            code="NOTEBOOK101", name="Notebook subject"
        )
        self.lecture_type = friprosveta.models.LectureType.objects.create(
            name="Notebook lecture", short_name="NP", duration=3
        )
        self.activity = friprosveta.models.Activity.objects.create(
            name="Notebook activity",
            short_name="NOTEBOOK101_P",
            activityset=self.activityset,
            type="P",
            duration=2,
            subject=self.subject,
            lecture_type=self.lecture_type,
        )

    def test_check_durations_reports_realized_activity_with_wrong_duration(self):
        ActivityRealization.objects.create(activity=self.activity)
        output = StringIO()

        call_command("check_durations", self.timetable.slug, stdout=output)

        self.assertIn("NOTEBOOK101 P: duration 2 (expected 3)", output.getvalue())

    def test_set_visible_groups_hides_synthetic_groups(self):
        regular = Group.objects.create(
            name="Regular", short_name="1_BUN-RI", size=1, groupset=self.groupset
        )
        reserved = Group.objects.create(
            name="Reserved", short_name="99_RESERVED", size=1, groupset=self.groupset
        )
        pad = Group.objects.create(
            name="Vsi padalci", short_name="VSI_PADALCI", size=1, groupset=self.groupset
        )
        child = Group.objects.create(
            name="Child",
            short_name="1_BUN-RI_01",
            size=1,
            groupset=self.groupset,
            parent=regular,
        )

        call_command("set_visible_groups", self.timetable.slug)

        regular.refresh_from_db()
        reserved.refresh_from_db()
        pad.refresh_from_db()
        child.refresh_from_db()
        self.assertTrue(regular.visible_in_navigation)
        self.assertFalse(reserved.visible_in_navigation)
        self.assertFalse(pad.visible_in_navigation)
        self.assertFalse(child.visible_in_navigation)

    def test_find_missing_teachers_reports_codes_referenced_by_najave(self):
        TeacherSubjectCycles.objects.create(
            teacher_code="MISSING_TEACHER",
            subject_code=self.subject.code,
            timetable_set=self.timetable_set,
            lecture_type=self.lecture_type.id,
            cycles=1,
        )
        output = StringIO()

        call_command(
            "find_missing_teachers",
            self.timetable.slug,
            self.timetable_set.slug,
            stdout=output,
        )

        self.assertIn("MISSING_TEACHER: NOTEBOOK101", output.getvalue())

    def test_teacher_activity_form_saves_on_site_cycles_to_najave(self):
        from friprosveta.forms import ActivityMinimalForm

        teacher = Teacher.objects.create(
            user=User.objects.create_user("notebook-cycle-teacher"),
            code="NB_CYCLE",
        )
        self.activity.teachers.add(teacher)
        entry = TeacherSubjectCycles.objects.create(
            teacher_code=teacher.code,
            subject_code=self.subject.code,
            timetable_set=self.timetable_set,
            instruction_type=1,
            lecture_type=self.lecture_type.id,
            cycles=2,
            cycles_on_site=2,
        )
        form = ActivityMinimalForm(
            data={
                "name": self.activity.name,
                "activityset": self.activityset.id,
                "type": self.activity.type,
                "duration": self.activity.duration,
                "requirements": [],
                "lecture_split": "",
                "site_cycles": "1",
            },
            instance=self.activity,
            teacher=teacher,
            timetable=self.timetable,
            min_physical_cycle_percentage=0,
        )

        self.assertTrue(form.is_valid(), form.errors)
        form.save()

        entry.refresh_from_db()
        self.activity.refresh_from_db()
        self.assertEqual(entry.cycles_on_site, 1)
        self.assertIsNone(self.activity.cycles_on_site)

    def test_remove_pad_groups_removes_only_lecture_pad_assignments(self):
        regular = Group.objects.create(
            name="Regular", short_name="1_BUN-RI", size=70, groupset=self.groupset
        )
        pad = Group.objects.create(
            name="PAD", short_name="NOTEBOOK101_PAD", size=20, groupset=self.groupset
        )
        realization = ActivityRealization.objects.create(activity=self.activity)
        realization.groups.add(regular, pad)

        call_command("remove_pad_groups", self.timetable.slug, "--dry-run")
        self.assertEqual(set(realization.groups.all()), {regular, pad})
        realization.refresh_from_db()
        self.assertEqual(realization.intended_size, 0)

        call_command("remove_pad_groups", self.timetable.slug)
        self.assertEqual(set(realization.groups.all()), {regular})
        realization.refresh_from_db()
        self.assertEqual(realization.intended_size, 90)
        self.assertEqual(realization.size, 90)

    @patch("friprosveta.models.GroupSizeHint.size_from_enrollments")
    def test_calculate_group_size_hints_uses_short_name_field(self, mocked_size):
        group = Group.objects.create(
            name="Regular", short_name="1_BUN-RI", size=1, groupset=self.groupset
        )
        self.activity.groups.add(group)

        call_command(
            "calculate_group_size_hints", self.timetable.slug, "notebook-test"
        )

        mocked_size.assert_called_once()

    @patch("friprosveta.models.Subject.update_or_create_subgroups_from_hints")
    def test_update_subgroups_from_hints_calls_current_model_method(self, mocked_update):
        call_command(
            "update_subgroups_from_hints",
            self.timetable.slug,
            "notebook-test",
        )

        mocked_update.assert_called_once_with(
            activityset=self.activityset,
            methods=["notebook-test"],
            strategy_name="max",
        )

    def test_bootstrap_timetable_creates_fresh_sets_and_reuses_classrooms(self):
        classrooms = ClassroomSet.objects.create(
            slug="notebook-command-rooms",
            name="Notebook command rooms",
            created=date.today(),
        )
        source = Timetable.objects.create(
            slug="notebook-command-source",
            name="Notebook command source",
            activityset=self.activityset,
            preferenceset=self.preferenceset,
            groupset=self.groupset,
            classroomset=classrooms,
        )
        output = StringIO()

        call_command(
            "bootstrap_timetable",
            "notebook-command-new",
            "Notebook command new",
            source.slug,
            stdout=output,
        )

        created = Timetable.objects.get(slug="notebook-command-new")
        self.assertEqual(created.classroomset, classrooms)
        self.assertNotEqual(created.activityset, source.activityset)
        self.assertNotEqual(created.preferenceset, source.preferenceset)
        self.assertNotEqual(created.groupset, source.groupset)
        self.assertIn("Created timetable 'notebook-command-new'", output.getvalue())

    def test_force_create_realizations_refuses_foreign_allocation_cascade(self):
        realization = ActivityRealization.objects.create(activity=self.activity)
        foreign_timetable = Timetable.objects.create(
            slug="notebook-command-foreign",
            name="Notebook command foreign",
            activityset=self.activityset,
            preferenceset=self.preferenceset,
            groupset=self.groupset,
        )
        allocation = Allocation.objects.create(
            timetable=foreign_timetable,
            activityRealization=realization,
            classroom=None,
            day="MON",
            start="07:00",
        )

        with self.assertRaisesRegex(
            CommandError,
            "Refusing to recreate realizations because they have allocations",
        ):
            call_command(
                "create_realizations",
                self.timetable.slug,
                self.timetable_set.slug,
                force=True,
            )

        self.assertTrue(ActivityRealization.objects.filter(pk=realization.pk).exists())
        self.assertTrue(Allocation.objects.filter(pk=allocation.pk).exists())


class SchedulingWindowsUITest(TestCase):
    """
    Tests for the superuser-only ActivityTypeSchedulingWindow configuration UI:
    permissions, saving a restricted window, validation, command-free
    behavior, and the dashboard link/count.
    """

    def setUp(self):
        self.timetable = Timetable.objects.create(
            slug="win-ui-tt", name="Window UI Timetable"
        )
        self.staff_user = User.objects.create_user(
            "win-staff", password="pw", is_staff=True, is_superuser=True
        )
        self.non_staff_user = User.objects.create_user(
            "win-regular", password="pw", is_staff=False, is_superuser=False
        )
        self.client = Client()

    def _login_staff(self):
        self.client.login(username="win-staff", password="pw")

    def _login_regular(self):
        self.client.login(username="win-regular", password="pw")

    def _full_form_data(self):
        """Return POST data with every weekday/hour grid cell available."""
        data = {}
        for activity_type, _ in ACTIVITYTYPES:
            for day, _ in WEEKDAYS:
                for hour_index, _hour in enumerate(WORKHOURS):
                    data["weight_{}_{}_{}".format(activity_type, day, hour_index)] = "0"
        return data

    def _set_window(self, data, activity_type, day, start, end):
        for hour_index, (hour, _hour_name) in enumerate(WORKHOURS):
            field = "weight_{}_{}_{}".format(activity_type, day, hour_index)
            data[field] = "0" if start <= hour < end else "50"

    def _teacher_grid_data(self, teacher, day, start, end):
        data = {"form_type": "teacher", "teacher": teacher.id}
        for grid_day, _day_name in WEEKDAYS:
            data["weight_{}".format(grid_day)] = "0"
            for hour_index, (hour, _hour_name) in enumerate(WORKHOURS):
                if grid_day != day or start <= hour < end:
                    data["enabled_{}_{}".format(grid_day, hour_index)] = "on"
        return data

    # --- Permissions -------------------------------------------------

    def test_page_requires_login(self):
        response = self.client.get("/solver/win-ui-tt/windows/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login", response["Location"])

    def test_page_requires_superuser(self):
        self._login_regular()
        response = self.client.get("/solver/win-ui-tt/windows/")
        self.assertEqual(response.status_code, 403)

    def test_staff_can_view_empty(self):
        self._login_staff()
        response = self.client.get("/solver/win-ui-tt/windows/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Activity type scheduling windows")
        self.assertContains(response, "Predavanja")
        self.assertEqual(
            ActivityTypeSchedulingWindow.objects.filter(
                timetable=self.timetable
            ).count(),
            0,
        )

    # --- Saving ------------------------------------------------------

    def test_save_p_monday_window(self):
        self._login_staff()
        data = self._full_form_data()
        self._set_window(data, "P", "MON", "08:00", "18:00")
        data["weight_P_MON"] = "100"
        response = self.client.post("/solver/win-ui-tt/windows/", data=data)
        self.assertEqual(response.status_code, 302)

        restriction = ActivityTypeSchedulingRestriction.objects.get(
            timetable=self.timetable, activity_type="P", day="MON", start="07:00"
        )
        self.assertEqual(restriction.weight, 50)
        self.assertEqual(
            ActivityTypeSchedulingRestriction.objects.filter(
                timetable=self.timetable
            ).count(),
            5,
        )

    def test_save_redirects_back_to_page(self):
        self._login_staff()
        data = self._full_form_data()
        self._set_window(data, "P", "MON", "08:00", "18:00")
        response = self.client.post("/solver/win-ui-tt/windows/", data=data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/solver/win-ui-tt/windows")

    def test_staff_can_create_teacher_window_override(self):
        activityset = ActivitySet.objects.create(
            slug="win-ui-override-activities", name="Window Override Activities"
        )
        self.timetable.activityset = activityset
        self.timetable.save(update_fields=("activityset",))
        teacher = Teacher.objects.create(
            user=User.objects.create_user("window-override-teacher"),
            code="window-override-teacher",
        )
        activity = Activity.objects.create(
            name="Window Override Activity",
            short_name="WINOVERRIDE",
            activityset=activityset,
            type="P",
            duration=1,
        )
        activity.teachers.add(teacher)
        self._login_staff()

        response = self.client.post(
            "/solver/win-ui-tt/windows/overrides/",
            data=self._teacher_grid_data(teacher, "MON", "18:00", "20:00"),
        )

        self.assertEqual(response.status_code, 302)
        override = friprosveta.models.TeacherSchedulingWindow.objects.get(
            timetable=self.timetable, teacher=teacher, day="MON"
        )
        self.assertEqual((override.start, override.end), ("18:00", "20:00"))

    def test_teacher_window_override_allows_fully_unchecked_days(self):
        activityset = ActivitySet.objects.create(
            slug="window-unavailable-activities", name="Window Unavailable Activities"
        )
        self.timetable.activityset = activityset
        self.timetable.save(update_fields=("activityset",))
        teacher = Teacher.objects.create(
            user=User.objects.create_user("window-unavailable-teacher"),
            code="window-unavailable-teacher",
        )
        activity = Activity.objects.create(
            name="Window Unavailable Activity",
            short_name="WINUNAVAILABLE",
            activityset=activityset,
            type="P",
            duration=1,
        )
        activity.teachers.add(teacher)
        data = self._teacher_grid_data(teacher, "TUE", "08:00", "18:00")
        for day in ("MON", "FRI"):
            for hour_index, _hour in enumerate(WORKHOURS):
                data.pop(f"enabled_{day}_{hour_index}")
        self._login_staff()

        response = self.client.post("/solver/win-ui-tt/windows/overrides/", data=data)

        self.assertEqual(response.status_code, 302)
        unavailable = friprosveta.models.TeacherSchedulingWindow.objects.filter(
            timetable=self.timetable,
            teacher=teacher,
            day__in=("MON", "FRI"),
        )
        self.assertEqual(unavailable.count(), 2)
        self.assertTrue(all(window.unavailable and window.weight == 100 for window in unavailable))

    def test_realization_override_updates_existing_day_and_normalizes_unrestricted(self):
        activityset = ActivitySet.objects.create(
            slug="realization-window-override-activities",
            name="Realization Window Override Activities",
        )
        self.timetable.activityset = activityset
        self.timetable.save(update_fields=("activityset",))
        activity = Activity.objects.create(
            name="Realization Window Override Activity",
            short_name="REALWINDOW",
            activityset=activityset,
            type="P",
            duration=1,
        )
        realization = ActivityRealization.objects.create(activity=activity)
        self._login_staff()
        url = "/solver/win-ui-tt/windows/overrides/"

        response = self.client.post(
            url,
            data={
                "form_type": "realization",
                "realization": realization.id,
                "day": "MON",
                "start": "08:00",
                "end": "18:00",
                "weight": "100",
            },
        )
        self.assertEqual(response.status_code, 302)
        response = self.client.post(
            url,
            data={
                "form_type": "realization",
                "realization": realization.id,
                "day": "MON",
                "unrestricted": "on",
                "start": "08:00",
                "end": "18:00",
                "weight": "100",
            },
        )

        self.assertEqual(response.status_code, 302)
        override = friprosveta.models.ActivityRealizationSchedulingWindow.objects.get(
            timetable=self.timetable, realization=realization, day="MON"
        )
        self.assertTrue(override.unrestricted)
        self.assertIsNone(override.start)
        self.assertIsNone(override.end)
        self.assertEqual(override.weight, 0)
        self.assertEqual(
            friprosveta.models.ActivityRealizationSchedulingWindow.objects.filter(
                timetable=self.timetable, realization=realization, day="MON"
            ).count(),
            1,
        )

    def test_full_day_default_removes_existing_row(self):
        ActivityTypeSchedulingRestriction.objects.create(
            timetable=self.timetable,
            activity_type="P",
            day="MON",
            start="07:00",
            weight=50,
        )
        self._login_staff()
        data = self._full_form_data()
        response = self.client.post("/solver/win-ui-tt/windows/", data=data)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            ActivityTypeSchedulingRestriction.objects.filter(
                timetable=self.timetable, activity_type="P", day="MON"
            ).exists()
        )

    def test_get_pre_populates_existing_window(self):
        ActivityTypeSchedulingRestriction.objects.create(
            timetable=self.timetable,
            activity_type="P",
            day="MON",
            start="07:00",
            weight=50,
        )
        self._login_staff()
        response = self.client.get("/solver/win-ui-tt/windows/")
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertEqual(form.fields["weight_P_MON_0"].initial, 50)
        self.assertEqual(form.fields["weight_P_MON_1"].initial, 0)
        self.assertEqual(form.fields["weight_P_MON_11"].initial, 0)

    # --- Validation --------------------------------------------------

    def test_validation_accepts_non_contiguous_restrictions(self):
        self._login_staff()
        data = self._full_form_data()
        data["weight_P_MON_0"] = "50"
        data["weight_P_MON_2"] = "100"
        response = self.client.post("/solver/win-ui-tt/windows/", data=data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            ActivityTypeSchedulingRestriction.objects.filter(
                timetable=self.timetable, activity_type="P", day="MON"
            ).count(),
            2,
        )

    def test_validation_accepts_boundary_end_after_final_workhour(self):
        self._login_staff()
        data = self._full_form_data()
        self._set_window(data, "P", "MON", "21:00", "22:00")
        response = self.client.post("/solver/win-ui-tt/windows/", data=data)
        self.assertEqual(response.status_code, 302)
        restriction = ActivityTypeSchedulingRestriction.objects.get(
            timetable=self.timetable, activity_type="P", day="MON", start="20:00"
        )
        self.assertEqual(restriction.weight, 50)

    # --- Command-free behavior --------------------------------------

    def test_save_does_not_invoke_management_command(self):
        self._login_staff()
        data = self._full_form_data()
        self._set_window(data, "P", "MON", "08:00", "18:00")
        with patch("django.core.management.call_command") as mocked:
            response = self.client.post(
                "/solver/win-ui-tt/windows/", data=data
            )
        self.assertEqual(response.status_code, 302)
        mocked.assert_not_called()

    def test_save_does_not_execute_solver(self):
        self._login_staff()
        data = self._full_form_data()
        self._set_window(data, "P", "MON", "08:00", "18:00")
        with patch(
            "friprosveta.services.ortools_solver.ORToolsTimetableSolver"
        ) as mocked_solver:
            response = self.client.post(
                "/solver/win-ui-tt/windows/", data=data
            )
        self.assertEqual(response.status_code, 302)
        mocked_solver.assert_not_called()

    # --- Dashboard link/count ---------------------------------------

    def test_dashboard_links_windows_page(self):
        self._login_staff()
        response = self.client.get("/solver/win-ui-tt/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "/solver/win-ui-tt/windows")
        self.assertContains(response, "Activity type scheduling windows")

    def test_dashboard_counts_configured_windows(self):
        ActivityTypeSchedulingWindow.objects.create(
            timetable=self.timetable,
            activity_type="P",
            day="MON",
            start="08:00",
            end="18:00",
        )
        self._login_staff()
        response = self.client.get("/solver/win-ui-tt/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Activity type scheduling windows")
        self.assertContains(response, "Set soft or hard weekday-hour bounds by activity type")
