from datetime import date, datetime

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase

from friprosveta.models import (
    ActivityRealizationSchedulingWindow,
    ActivityTypeSchedulingRestriction,
    ActivityTypeSchedulingWindow,
    TeacherSchedulingWindow,
)
from timetable.models import (
    Activity,
    ActivityRealization,
    ActivitySet,
    Classroom,
    ClassroomSet,
    Group,
    GroupSet,
    Location,
    PreferenceSet,
    Teacher,
    TeacherTimePreference,
    Timetable,
    WEEKDAYS,
    WORKHOURS,
)


class ActivityRealizationSchedulingWindowModelTest(TestCase):
    def setUp(self):
        self.activityset = ActivitySet.objects.create(
            slug="realization-window-activities",
            name="Realization Window Activities",
        )
        self.other_activityset = ActivitySet.objects.create(
            slug="other-realization-window-activities",
            name="Other Realization Window Activities",
        )
        self.timetable = Timetable.objects.create(
            slug="realization-window-tt",
            name="Realization Window Timetable",
            activityset=self.activityset,
        )
        self.realization = self._create_realization(
            self.activityset, "REALIZATION_WINDOW"
        )
        self.other_realization = self._create_realization(
            self.other_activityset, "OTHER_REALIZATION_WINDOW"
        )

    def _create_realization(self, activityset, short_name):
        activity = Activity.objects.create(
            name=short_name,
            short_name=short_name,
            activityset=activityset,
            type="P",
            duration=1,
        )
        return ActivityRealization.objects.create(activity=activity)

    def test_unrestricted_override_accepts_no_bounds(self):
        # Given a realization-level override that opts out of day restrictions.
        override = ActivityRealizationSchedulingWindow(
            timetable=self.timetable,
            realization=self.realization,
            day="MON",
            unrestricted=True,
        )

        # When the override is validated.
        override.full_clean()

        # Then an unrestricted weekday needs no bounded interval.

    def test_unrestricted_override_rejects_bounded_interval(self):
        # Given an unrestricted override with an accidental bounded interval.
        override = ActivityRealizationSchedulingWindow(
            timetable=self.timetable,
            realization=self.realization,
            day="MON",
            start="08:00",
            end="10:00",
            unrestricted=True,
        )

        # When the override is validated.
        with self.assertRaises(ValidationError):
            override.full_clean()

        # Then the contradictory configuration is rejected.

    def test_bounded_override_rejects_empty_interval(self):
        # Given a bounded override whose end equals its start.
        override = ActivityRealizationSchedulingWindow(
            timetable=self.timetable,
            realization=self.realization,
            day="MON",
            start="08:00",
            end="08:00",
        )

        # When the override is validated.
        with self.assertRaises(ValidationError):
            override.full_clean()

        # Then the invalid half-open interval is rejected.

    def test_override_rejects_realization_from_another_activityset(self):
        # Given a realization that does not belong to the timetable activity set.
        override = ActivityRealizationSchedulingWindow(
            timetable=self.timetable,
            realization=self.other_realization,
            day="MON",
            start="08:00",
            end="10:00",
        )

        # When the override is validated.
        with self.assertRaises(ValidationError):
            override.full_clean()

        # Then the timetable-scoping invariant rejects it.

    def test_teacher_override_rejects_teacher_from_another_activityset(self):
        teacher = Teacher.objects.create(
            user=User.objects.create_user("other-window-teacher"), code="other-window-teacher"
        )
        other_activity = Activity.objects.create(
            name="OTHER_TEACHER_WINDOW",
            short_name="OTHER_TEACHER_WINDOW",
            activityset=self.other_activityset,
            type="P",
            duration=1,
        )
        other_activity.teachers.add(teacher)
        override = TeacherSchedulingWindow(
            timetable=self.timetable,
            teacher=teacher,
            day="MON",
            start="08:00",
            end="10:00",
        )

        with self.assertRaises(ValidationError):
            override.full_clean()


class RealizationSchedulingWindowSolverTest(TestCase):
    def setUp(self):
        self.preferenceset = PreferenceSet.objects.create(
            slug="realization-window-prefs",
            name="Realization Window Preferences",
        )
        self.activityset = ActivitySet.objects.create(
            slug="realization-window-solver-activities",
            name="Realization Window Solver Activities",
        )
        self.groupset = GroupSet.objects.create(
            slug="realization-window-groups",
            name="Realization Window Groups",
            created=datetime.now(),
        )
        self.classroomset = ClassroomSet.objects.create(
            slug="realization-window-rooms",
            name="Realization Window Rooms",
            created=date.today(),
        )
        self.location = Location.objects.create(name="Ljubljana")
        self.timetable = Timetable.objects.create(
            slug="realization-window-solver-tt",
            name="Realization Window Solver Timetable",
            activityset=self.activityset,
            preferenceset=self.preferenceset,
            groupset=self.groupset,
            classroomset=self.classroomset,
        )
        room = Classroom.objects.create(
            name="Realization Window Room",
            short_name="RWR",
            capacity=30,
            location=self.location,
        )
        self.classroomset.classrooms.add(room)

    def _create_realization(self, short_name):
        teacher = Teacher.objects.create(
            user=User.objects.create_user(short_name.lower()),
            code=short_name.lower(),
        )
        group = Group.objects.create(
            name=short_name,
            short_name=short_name,
            size=10,
            groupset=self.groupset,
        )
        activity = Activity.objects.create(
            name=short_name,
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
        return realization, teacher

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

    def _run_solver(self):
        call_command("ortools_generate", self.timetable.slug, time_limit=10)

    def _allocation_for(self, realization):
        return self.timetable.allocations.get(activityRealization=realization)

    def test_bounded_realization_override_precedes_global_window(self):
        # Given conflicting global and realization Monday windows.
        realization, teacher = self._create_realization("BOUNDED_OVERRIDE")
        ActivityTypeSchedulingWindow.objects.create(
            timetable=self.timetable,
            activity_type="P",
            day="MON",
            start="07:00",
            end="08:00",
        )
        ActivityRealizationSchedulingWindow.objects.create(
            timetable=self.timetable,
            realization=realization,
            day="MON",
            start="09:00",
            end="10:00",
        )
        self._block_teacher_except(teacher, {("MON", "09:00")})

        # When the solver generates an allocation.
        self._run_solver()

        # Then the realization-specific bounded window wins.
        allocation = self._allocation_for(realization)
        self.assertEqual((allocation.day, allocation.start), ("MON", "09:00"))

    def test_unrestricted_realization_override_precedes_global_window(self):
        # Given a global Monday window and an unrestricted realization override.
        realization, teacher = self._create_realization("UNRESTRICTED_OVERRIDE")
        ActivityTypeSchedulingWindow.objects.create(
            timetable=self.timetable,
            activity_type="P",
            day="MON",
            start="07:00",
            end="08:00",
        )
        ActivityRealizationSchedulingWindow.objects.create(
            timetable=self.timetable,
            realization=realization,
            day="MON",
            unrestricted=True,
        )
        self._block_teacher_except(teacher, {("MON", "21:00")})

        # When the solver generates an allocation.
        self._run_solver()

        # Then the unrestricted realization receives the full-day candidate.
        allocation = self._allocation_for(realization)
        self.assertEqual((allocation.day, allocation.start), ("MON", "21:00"))

    def test_teacher_override_precedes_global_window(self):
        realization, teacher = self._create_realization("TEACHER_OVERRIDE")
        ActivityTypeSchedulingWindow.objects.create(
            timetable=self.timetable,
            activity_type="P",
            day="MON",
            start="07:00",
            end="08:00",
        )
        TeacherSchedulingWindow.objects.create(
            timetable=self.timetable,
            teacher=teacher,
            day="MON",
            start="09:00",
            end="10:00",
        )
        self._block_teacher_except(teacher, {("MON", "09:00")})

        self._run_solver()

        allocation = self._allocation_for(realization)
        self.assertEqual((allocation.day, allocation.start), ("MON", "09:00"))

    def test_window_does_not_block_only_feasible_placement(self):
        realization, teacher = self._create_realization("SOFT_WINDOW")
        ActivityTypeSchedulingWindow.objects.create(
            timetable=self.timetable,
            activity_type="P",
            day="MON",
            start="07:00",
            end="08:00",
        )
        self._block_teacher_except(teacher, {("MON", "21:00")})

        self._run_solver()

        allocation = self._allocation_for(realization)
        self.assertEqual((allocation.day, allocation.start), ("MON", "21:00"))

    def test_hard_activity_type_restriction_overrides_teacher_window(self):
        realization, teacher = self._create_realization("HARD_TYPE_RESTRICTION")
        ActivityTypeSchedulingRestriction.objects.create(
            timetable=self.timetable,
            activity_type="P",
            day="MON",
            start="17:00",
            weight=100,
        )
        TeacherSchedulingWindow.objects.create(
            timetable=self.timetable,
            teacher=teacher,
            day="MON",
            start="16:00",
            end="18:00",
        )
        TeacherTimePreference.objects.create(
            preferenceset=self.preferenceset,
            teacher=teacher,
            level="WANT",
            day="MON",
            start="17:00",
            duration=1,
            weight=100,
        )
        self._block_teacher_except(teacher, {("MON", "16:00"), ("MON", "17:00")})

        self._run_solver()

        allocation = self._allocation_for(realization)
        self.assertEqual((allocation.day, allocation.start), ("MON", "16:00"))
