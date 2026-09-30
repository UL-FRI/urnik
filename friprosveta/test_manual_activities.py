from datetime import date, datetime
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth.models import User
from django.db import connection
from django.test import Client, TestCase

from friprosveta.management.commands.create_activities import (
    Command as CreateActivitiesCommand,
)
from friprosveta.models import Activity as FriActivity
from friprosveta.models import LectureType, ManualActivity, Subject
from friprosveta.services.manual_activities import apply_manual_activities
from timetable.models import (
    ActivityRealization,
    Allocation,
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
        self.assertEqual(activity.short_name, "ALUO_P")
        self.assertEqual(list(activity.teachers.all()), [self.teacher])
        self.assertEqual(list(activity.requirements.all()), [self.computer])
        self.assertEqual(allocation.day, "TUE")
        self.assertEqual(allocation.start, "17:00")
        self.assertEqual(allocation.classroom, self.room)
        entry.refresh_from_db()
        self.assertEqual(entry.activity_id, activity.pk)
        self.assertEqual(entry.solver_constraint.constraint_type, "FIXEDPLACEMENT")
        self.assertEqual(list(entry.solver_constraint.realizations.all()), [realization])
        self.assertEqual(activity.realizations.count(), 1)

    def test_short_name_uses_subject_code_when_abbreviation_is_empty(self):
        self.subject.short_name = ""
        self.subject.save(update_fields=("short_name",))
        self.create_entry(fixed_day="TUE", fixed_start="17:00", fixed_room=self.room)

        apply_manual_activities(self.timetable)

        self.assertEqual(
            self.subject.activities.get(activityset=self.timetable.activityset).short_name,
            "90066_P",
        )

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

    def test_post_generation_placement_does_not_change_existing_activity(self):
        generated = FriActivity.objects.create(
            activityset=self.timetable.activityset,
            subject=self.subject,
            lecture_type=self.lecture_type,
            name="Generated lecture",
            short_name="ALUO_P",
            type="P",
            duration=3,
        )
        realization = ActivityRealization.objects.create(activity=generated)
        previous = Allocation.objects.create(
            timetable=self.timetable,
            activityRealization=realization,
            classroom=self.room,
            day="MON",
            start="08:00",
        )
        client = Client()
        client.force_login(
            User.objects.create_user("post-generation-operator", is_superuser=True)
        )

        response = client.post(
            "/solver/{}/manual-activities/new/".format(self.timetable.slug),
            {
                "subject": self.subject.pk,
                "lecture_type": self.lecture_type.pk,
                "name": "Post-generation exception",
                "duration": 2,
                "enabled": "on",
                "teachers": [self.teacher.pk],
                "groups": [self.group.pk],
                "locations": [self.location.pk],
                "requirements": [self.computer.pk],
                "fixed_day": "TUE",
                "fixed_start": "17:00",
                "fixed_room": self.room.pk,
            },
        )

        self.assertEqual(response.status_code, 302)
        generated.refresh_from_db()
        previous.refresh_from_db()
        self.assertEqual((generated.name, generated.duration), ("Generated lecture", 3))
        self.assertEqual((previous.day, previous.start), ("MON", "08:00"))
        manual = FriActivity.objects.exclude(pk=generated.pk).get(
            activityset=self.timetable.activityset,
            subject=self.subject,
            lecture_type=self.lecture_type,
        )
        self.assertEqual(
            manual.realizations.get().allocations.get(timetable=self.timetable).day,
            "TUE",
        )
        self.assertEqual(manual.short_name, "ALUO_P")
        self.assertEqual(ManualActivity.objects.get(timetable=self.timetable).activity_id, manual.pk)

        response = client.post(
            "/solver/{}/manual-activities/".format(self.timetable.slug),
            {"entry": ManualActivity.objects.get(timetable=self.timetable).pk},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(FriActivity.objects.filter(pk=manual.pk).exists())
        previous.refresh_from_db()
        self.assertEqual((previous.day, previous.start), ("MON", "08:00"))

    def test_edit_and_remove_post_generation_manual_allocation(self):
        entry = self.create_entry(
            fixed_day="TUE", fixed_start="17:00", fixed_room=self.room
        )
        apply_manual_activities(self.timetable)
        activity = FriActivity.objects.get(
            activityset=self.timetable.activityset,
            subject=self.subject,
            lecture_type=self.lecture_type,
        )
        client = Client()
        client.force_login(
            User.objects.create_user("post-edit-operator", is_superuser=True)
        )

        response = client.post(
            "/solver/{}/manual-activities/{}/edit/".format(self.timetable.slug, entry.pk),
            {
                "subject": self.subject.pk,
                "lecture_type": self.lecture_type.pk,
                "duration": 3,
                "enabled": "on",
                "teachers": [self.teacher.pk],
                "groups": [self.group.pk],
                "locations": [self.location.pk],
                "fixed_day": "FRI",
                "fixed_start": "08:00",
                "fixed_room": self.room.pk,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            activity.realizations.get().allocations.get(timetable=self.timetable).day,
            "FRI",
        )
        response = client.post(
            "/solver/{}/manual-activities/".format(self.timetable.slug),
            {"entry": entry.pk},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(FriActivity.objects.filter(pk=activity.pk).exists())
        self.assertFalse(Allocation.objects.filter(timetable=self.timetable).exists())

    def test_disabling_and_clearing_fixed_placement_remove_only_manual_allocation(self):
        entry = self.create_entry(
            fixed_day="TUE", fixed_start="17:00", fixed_room=self.room
        )
        apply_manual_activities(self.timetable)
        entry.refresh_from_db()
        constraint = entry.solver_constraint

        entry.fixed_day = ""
        entry.fixed_start = ""
        entry.fixed_room = None
        entry.save(update_fields=("fixed_day", "fixed_start", "fixed_room"))
        apply_manual_activities(self.timetable)

        self.assertFalse(Allocation.objects.filter(timetable=self.timetable).exists())
        constraint.refresh_from_db()
        self.assertFalse(constraint.active)
        self.assertEqual(
            FriActivity.objects.filter(activityset=self.timetable.activityset).count(), 1
        )

        entry.enabled = False
        entry.save(update_fields=("enabled",))
        apply_manual_activities(self.timetable)

        self.assertFalse(
            FriActivity.objects.filter(activityset=self.timetable.activityset).exists()
        )
        entry.refresh_from_db()
        self.assertIsNone(entry.activity_id)

    def test_reapplying_unplaced_entry_preserves_solver_allocation(self):
        entry = self.create_entry()
        apply_manual_activities(self.timetable)
        activity = FriActivity.objects.get(
            activityset=self.timetable.activityset,
            subject=self.subject,
            lecture_type=self.lecture_type,
        )
        allocation = Allocation.objects.create(
            timetable=self.timetable,
            activityRealization=activity.realizations.get(),
            classroom=self.room,
            day="MON",
            start="08:00",
        )

        apply_manual_activities(self.timetable)

        self.assertTrue(Allocation.objects.filter(pk=allocation.pk).exists())
        self.assertIsNone(entry.solver_constraint_id)

    @patch("friprosveta.management.commands.create_activities.Studij")
    @patch("friprosveta.management.commands.create_activities.Najave")
    def test_studis_sync_does_not_replace_manual_activity(self, najave, studij):
        entry = self.create_entry(
            fixed_day="TUE", fixed_start="17:00", fixed_room=self.room
        )
        apply_manual_activities(self.timetable)
        manual = self.subject.activities.get(activityset=self.timetable.activityset)
        najave.return_value.get_predmeti_cikli.return_value = [
            {
                "predmet_sifra": self.subject.code,
                "predmet_id": 123,
                "izvajanje_id": 456,
                "izvajalci": [
                    {"tip_izvajanja": {"id": 1}, "delavec_sifra": self.teacher.code}
                ],
            }
        ]
        studij.return_value.get_izvajanja.return_value = [
            {
                "semester": 1,
                "idpredmet": 123,
                "id": "subject-456",
                "izvaja_partnerska_institucija": False,
                "st_ur_predavanj": 45,
                "st_ur_seminarja": None,
            }
        ]

        with patch(
            "friprosveta.management.commands.create_activities.LectureType.objects.get",
            return_value=self.lecture_type,
        ):
            CreateActivitiesCommand().sync_activities_with_fri_najave(
                self.timetable, {"id": 1}, 2026, self.location, None
            )

        manual.refresh_from_db()
        self.assertEqual(manual.short_name, "ALUO_P")
        self.assertEqual(ManualActivity.objects.get(pk=entry.pk).activity_id, manual.pk)
        self.assertEqual(
            manual.realizations.get().allocations.get(timetable=self.timetable).day,
            "TUE",
        )
        self.assertEqual(
            self.subject.activities.filter(activityset=self.timetable.activityset).count(),
            2,
        )

    def test_existing_manual_marker_is_migrated_without_moving_allocation(self):
        entry = self.create_entry(fixed_day="TUE", fixed_start="17:00", fixed_room=self.room)
        legacy = FriActivity.objects.create(
            activityset=self.timetable.activityset,
            subject=self.subject,
            lecture_type=self.lecture_type,
            name=self.subject.name,
            short_name="MANUAL_{}".format(entry.pk),
            type="P",
            duration=3,
        )
        realization = ActivityRealization.objects.create(activity=legacy)
        allocation = Allocation.objects.create(
            timetable=self.timetable,
            activityRealization=realization,
            classroom=self.room,
            day="TUE",
            start="17:00",
        )

        migration = import_module("friprosveta.migrations.0016_manualactivity_activity")
        migration.link_existing_manual_activities(
            apps, SimpleNamespace(connection=connection)
        )

        entry.refresh_from_db()
        legacy.refresh_from_db()
        allocation.refresh_from_db()
        self.assertEqual(entry.activity_id, legacy.pk)
        self.assertEqual(legacy.short_name, "ALUO_P")
        self.assertEqual((allocation.day, allocation.start), ("TUE", "17:00"))

        apply_manual_activities(self.timetable)
        self.assertEqual(
            self.subject.activities.filter(activityset=self.timetable.activityset).count(),
            1,
        )
        self.assertTrue(Allocation.objects.filter(pk=allocation.pk).exists())
