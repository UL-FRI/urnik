"""Apply operator-managed activities to generated timetable data."""

from django.db import transaction

from friprosveta.models import Activity, ActivityRealization, ManualActivity
from timetable.models import Allocation, SolverConstraint


@transaction.atomic
def apply_manual_activities(timetable):
    """Create or update enabled manual activities and their optional placements."""
    entries = (
        ManualActivity.objects.filter(timetable=timetable)
        .select_related("subject", "lecture_type", "fixed_room", "solver_constraint")
        .prefetch_related("teachers", "groups", "locations", "requirements", "required_rooms")
    )
    for entry in entries:
        if not entry.enabled:
            if entry.solver_constraint_id:
                entry.solver_constraint.active = False
                entry.solver_constraint.save(update_fields=("active",))
            continue
        activity, _ = Activity.objects.get_or_create(
            activityset=timetable.activityset,
            subject=entry.subject,
            lecture_type=entry.lecture_type,
            defaults={
                "name": entry.name or entry.subject.name,
                "short_name": "{}_{}".format(
                    entry.subject.short_name, entry.lecture_type.short_name
                ),
                "type": entry.lecture_type.short_name,
                "duration": entry.duration,
            },
        )
        activity.name = entry.name or entry.subject.name
        activity.short_name = "{}_{}".format(
            entry.subject.short_name, entry.lecture_type.short_name
        )
        activity.type = entry.lecture_type.short_name
        activity.duration = entry.duration
        activity.save(update_fields=("name", "short_name", "type", "duration"))
        activity.teachers.set(entry.teachers.all())
        activity.groups.set(entry.groups.all())
        activity.locations.set(entry.locations.all())
        activity.requirements.set(entry.requirements.all())
        activity.required_rooms.set(entry.required_rooms.all())

        realization = activity.realizations.order_by("pk").first()
        if realization is None:
            realization = ActivityRealization.objects.create(activity=activity)
        realization.teachers.set(entry.teachers.all())
        realization.groups.set(entry.groups.all())

        if entry.fixed_day and entry.fixed_start and entry.fixed_room_id:
            allocation = Allocation.objects.filter(
                timetable=timetable, activityRealization=realization
            ).order_by("pk").first()
            if allocation is None:
                Allocation.objects.create(
                    timetable=timetable,
                    activityRealization=realization,
                    classroom=entry.fixed_room,
                    day=entry.fixed_day,
                    start=entry.fixed_start,
                )
            else:
                allocation.classroom = entry.fixed_room
                allocation.day = entry.fixed_day
                allocation.start = entry.fixed_start
                allocation.save(update_fields=("classroom", "day", "start"))
            constraint = entry.solver_constraint
            if constraint is None:
                constraint = SolverConstraint.objects.create(
                    timetable=timetable,
                    name="Manual placement {} {}".format(
                        entry.subject.code, entry.lecture_type.short_name
                    ),
                    constraint_type="FIXEDPLACEMENT",
                    day=entry.fixed_day,
                    start=entry.fixed_start,
                )
                entry.solver_constraint = constraint
                entry.save(update_fields=("solver_constraint",))
            else:
                constraint.name = "Manual placement {} {}".format(
                    entry.subject.code, entry.lecture_type.short_name
                )
                constraint.constraint_type = "FIXEDPLACEMENT"
                constraint.day = entry.fixed_day
                constraint.start = entry.fixed_start
                constraint.active = True
                constraint.save(
                    update_fields=("name", "constraint_type", "day", "start", "active")
                )
            constraint.realizations.set((realization,))
            constraint.classrooms.set((entry.fixed_room,))
        elif entry.solver_constraint_id:
            entry.solver_constraint.active = False
            entry.solver_constraint.save(update_fields=("active",))
