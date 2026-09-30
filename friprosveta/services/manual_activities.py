"""Apply operator-managed activities to generated timetable data."""

from django.db import transaction

from friprosveta.models import Activity, ActivityRealization, ManualActivity
from timetable.models import Allocation, SolverConstraint


def _managed_activity(timetable, entry):
    if entry.activity_id:
        if entry.activity.activityset_id != timetable.activityset_id:
            raise ValueError("Manual activity belongs to another activity set.")
        return entry.activity

    # Entries created before the activity link existed used an internal short name.
    activity = Activity.objects.filter(
        activityset=timetable.activityset, short_name="MANUAL_{}".format(entry.pk)
    ).first()
    if activity is not None:
        entry.activity = activity
        entry.save(update_fields=("activity",))
    return activity


@transaction.atomic
def remove_manual_activity(timetable, entry):
    constraint = entry.solver_constraint
    activity = _managed_activity(timetable, entry)
    if activity is not None:
        activity.delete()
    entry.delete()
    if constraint is not None:
        constraint.delete()


@transaction.atomic
def apply_manual_activities(timetable):
    """Create or update enabled manual activities and their optional placements."""
    entries = (
        ManualActivity.objects.filter(timetable=timetable)
        .select_related("activity", "subject", "lecture_type", "fixed_room", "solver_constraint")
        .prefetch_related("teachers", "groups", "locations", "requirements", "required_rooms")
    )
    for entry in entries:
        activity = _managed_activity(timetable, entry)
        if not entry.enabled:
            if entry.solver_constraint_id:
                entry.solver_constraint.active = False
                entry.solver_constraint.save(update_fields=("active",))
            if activity is not None:
                activity.delete()
                entry.activity = None
                entry.save(update_fields=("activity",))
            continue
        short_name = "{}_{}".format(
            entry.subject.short_name or entry.subject.code,
            entry.lecture_type.short_name,
        )[:32]
        if activity is None:
            activity = Activity.objects.create(
                activityset=timetable.activityset,
                subject=entry.subject,
                lecture_type=entry.lecture_type,
                name=entry.name or entry.subject.name,
                short_name=short_name,
                type=entry.lecture_type.short_name,
                duration=entry.duration,
            )
            entry.activity = activity
            entry.save(update_fields=("activity",))
        activity.subject = entry.subject
        activity.lecture_type = entry.lecture_type
        activity.name = entry.name or entry.subject.name
        activity.short_name = short_name
        activity.type = entry.lecture_type.short_name
        activity.duration = entry.duration
        activity.save(
            update_fields=("subject", "lecture_type", "name", "short_name", "type", "duration")
        )
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
            if entry.solver_constraint.active:
                Allocation.objects.filter(
                    timetable=timetable, activityRealization=realization
                ).delete()
                entry.solver_constraint.active = False
                entry.solver_constraint.save(update_fields=("active",))
