from timetable.models import Activity


def missing_realization_groups(timetable, activity_ids=None):
    activities = Activity.objects.filter(activityset=timetable.activityset)
    if activity_ids is not None:
        activities = activities.filter(id__in=activity_ids)
    activities = activities.prefetch_related("groups", "realizations__groups")

    missing = []
    for activity in activities:
        assigned_group_ids = {
            group.id
            for realization in activity.realizations.all()
            for group in realization.groups.all()
        }
        activity_missing = [
            group
            for group in activity.groups.all()
            if group.groupset_id == timetable.groupset_id
            and (group.size or 0) > 0
            and group.study != "PAD"
            and group.id not in assigned_group_ids
        ]
        if activity_missing:
            missing.append((activity, activity_missing))
    return missing


def missing_realization_group_messages(timetable, activity_ids=None):
    missing = missing_realization_groups(timetable, activity_ids)
    if not missing:
        return []

    group_count = sum(len(groups) for _activity, groups in missing)
    planned_size = sum(group.size for _activity, groups in missing for group in groups)
    messages = [
        "Warning: {0} positive-size non-PAD group(s), with a total planned size "
        "of {1}, are not assigned to any realization.".format(
            group_count, planned_size
        )
    ]
    for activity, groups in missing:
        messages.append(
            "Activity {0} ({1}): {2}".format(
                activity.short_name,
                activity.type,
                ", ".join(group.short_name for group in groups),
            )
        )
    return messages
