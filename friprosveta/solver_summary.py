from friprosveta.models import ActivityTypeSchedulingRestriction
from timetable.models import (
    Activity,
    GroupTimePreference,
    GroupValuePreference,
    TagDescriptivePreference,
    TagTimePreference,
    TagValuePreference,
    TeacherTimePreference,
    TeacherValuePreference,
)


def active_rule_sources(timetable):
    preferenceset = timetable.preferenceset
    activities = Activity.objects.filter(activityset=timetable.activityset)
    relation_count = sum(
        activity.mustNotOverlap.count() + activity.before.count()
        for activity in activities
    )
    time_preference_count = (
        TeacherTimePreference.objects.filter(preferenceset=preferenceset).count()
        + GroupTimePreference.objects.filter(preferenceset=preferenceset).count()
        + TagTimePreference.objects.filter(preferenceset=preferenceset).count()
    )
    workload_preference_count = (
        TeacherValuePreference.objects.filter(preferenceset=preferenceset).count()
        + GroupValuePreference.objects.filter(preferenceset=preferenceset).count()
        + TagValuePreference.objects.filter(preferenceset=preferenceset).count()
    )
    tag_relation_count = TagDescriptivePreference.objects.filter(
        preferenceset=preferenceset
    ).exclude(typename="COMMENT").count()
    scheduling_window_count = ActivityTypeSchedulingRestriction.objects.filter(
        timetable=timetable
    ).count()
    return (
        ("Core placement and resource protection", 1, "Always enforced for scheduled realizations."),
        ("Activity relationships", relation_count, "must-not-overlap and before relations."),
        ("Tag relationship rules", tag_relation_count, "Tag descriptive preferences."),
        ("Time preferences", time_preference_count, "Teacher, group, and tag time preferences."),
        ("Workload and room rules", workload_preference_count, "Teacher, group, and tag value preferences."),
        ("Respected timetable locks", timetable.respects.count(), "Resources blocked by respected timetables."),
        ("Activity type scheduling windows", scheduling_window_count, "Per-slot unavailable-time weights; 100 is hard."),
    )
