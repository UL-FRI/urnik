from datetime import date, datetime

from django.contrib.auth.models import User
from django.test import Client, TestCase

from friprosveta.models import LectureType, ManualActivity, Subject
from friprosveta.services.manual_activities import apply_manual_activities
from timetable.models import (
    ActivitySet,
    Classroom,
    ClassroomNResources,
    ClassroomSet,
    Group,
    GroupSet,
    Location,
    PreferenceSet,
    Resource,
    Teacher,
    Timetable,
)


class ManualActivityTest(TestCase):
    def setUp(self):
        self.location = Location.objects.create(name="FRI")
        classroom_set = ClassroomSet.objects.create(
            slug="manual-rooms", name="Manual rooms", created=date.today()
        )
        self.room = Classroom.objects.create(
            name="Computer room", short_name="PR11", capacity=40, location=self.location
        )
        classroom_set.classrooms.add(self.room)
        self.timetable = Timetable.objects.create(
            slug="manual-tt",
            name="Manual timetable",
            activityset=ActivitySet.objects.create(
                slug="manual-activities", name="Manual activities"
            ),
            groupset=GroupSet.objects.create(
                slug="manual-groups", name="Manual groups", created=datetime.now()
            ),
            preferenceset=PreferenceSet.objects.create(
                slug="manual-prefs", name="Manual preferences"
            ),
            classroomset=classroom_set,
        )
        self.subject = Subject.objects.create(
            code="90066", name="ALUO", short_name="ALUO"
        )
        self.lecture_type = LectureType.objects.create(
            name="Predavanja", short_name="P", duration=3
        )
        self.teacher = Teacher.objects.create(
            user=User.objects.create_user("manual-teacher"), code="MANUAL"
        )
        self.group = Group.objects.create(
            name="Manual group",
            short_name="1_MANUAL",
            size=20,
            groupset=self.timetable.groupset,
        )
        self.computer = Resource.objects.create(name="Računalnik")
        ClassroomNResources.objects.create(
            classroom=self.room, resource=self.computer, n=40
        )

    def create_entry(self, **kwargs):
        entry = ManualActivity.objects.create(
            timetable=self.timetable,
            subject=self.subject,
            lecture_type=self.lecture_type,
            duration=3,
            **kwargs,
        )
        entry.teachers.add(self.teacher)
        entry.groups.add(self.group)
        entry.locations.add(self.location)
        entry.requirements.add(self.computer)
        return entry

    def test_apply_creates_and_reapplies_manual_activity_and_fixed_allocation(self):
        entry = self.create_entry(fixed_day="TUE", fixed_start="17:00", fixed_room=self.room)

        apply_manual_activities(self.timetable)
        apply_manual_activities(self.timetable)

        activity = self.subject.activities.get(
            activityset=self.timetable.activityset, lecture_type=self.lecture_type
        )
        realization = activity.realizations.get()
        allocation = realization.allocations.get(timetable=self.timetable)
        self.assertEqual(activity.duration, 3)
        self.assertEqual(list(activity.teachers.all()), [self.teacher])
        self.assertEqual(list(activity.requirements.all()), [self.computer])
        self.assertEqual(allocation.day, "TUE")
        self.assertEqual(allocation.start, "17:00")
        self.assertEqual(allocation.classroom, self.room)
        entry.refresh_from_db()
        self.assertEqual(entry.solver_constraint.constraint_type, "FIXEDPLACEMENT")
        self.assertEqual(list(entry.solver_constraint.realizations.all()), [realization])
        self.assertEqual(activity.realizations.count(), 1)

    def test_disabled_entry_is_not_applied(self):
        self.create_entry(enabled=False)

        apply_manual_activities(self.timetable)

        self.assertFalse(
            self.subject.activities.filter(activityset=self.timetable.activityset).exists()
        )

    def test_manual_activity_ui_requires_superuser_and_saves_entry(self):
        client = Client()
        url = "/solver/{}/manual-activities/new/".format(self.timetable.slug)
        self.assertEqual(client.get(url).status_code, 302)

        client.force_login(User.objects.create_user("operator", is_superuser=True))
        response = client.post(
            url,
            {
                "subject": self.subject.pk,
                "lecture_type": self.lecture_type.pk,
                "duration": 3,
                "enabled": "on",
                "teachers": [self.teacher.pk],
                "groups": [self.group.pk],
                "locations": [self.location.pk],
                "requirements": [self.computer.pk],
                "required_rooms": [self.room.pk],
                "fixed_day": "TUE",
                "fixed_start": "17:00",
                "fixed_room": self.room.pk,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(ManualActivity.objects.count(), 1)
        self.assertTrue(
            self.subject.activities.filter(activityset=self.timetable.activityset).exists()
        )

    def test_removing_entry_also_removes_generated_solver_constraint(self):
        entry = self.create_entry(
            fixed_day="TUE", fixed_start="17:00", fixed_room=self.room
        )
        apply_manual_activities(self.timetable)
        entry.refresh_from_db()
        constraint_id = entry.solver_constraint_id
        client = Client()
        client.force_login(
            User.objects.create_user("removing-operator", is_superuser=True)
        )

        response = client.post(
            "/solver/{}/manual-activities/".format(self.timetable.slug),
            {"entry": entry.pk},
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(ManualActivity.objects.filter(pk=entry.pk).exists())
        self.assertFalse(
            self.timetable.solver_constraints.filter(pk=constraint_id).exists()
        )
