from django.db import transaction

import friprosveta.models
import timetable.models


def split_activity(tt, activity, splits):
    if activity.duration != sum(splits):
        raise Exception(
            "Activity {0} with duration {1} cannot be split into {2}".format(
                activity, activity.duration, splits
            )
        )

    if len(splits) == 1:
        return [activity]

    with transaction.atomic():
        activity.duration = splits[0]
        activity.lecture_split = ""
        activity.save()
        original_activity = activity
        all_activities = [original_activity]
        for index, split in enumerate(splits[1:], start=2):
            short_name = "{}-{}".format(original_activity.short_name, index)[:32]
            new_activity = friprosveta.models.Activity(
                name=original_activity.name,
                short_name=short_name,
                type=original_activity.type,
                duration=split,
                subject=original_activity.subject,
                activityset=original_activity.activityset,
                lecture_type=original_activity.lecture_type,
                cycles_on_site=original_activity.cycles_on_site,
                ready_to_schedule=original_activity.ready_to_schedule,
                lecture_split="",
            )
            new_activity.save()
            new_activity.locations.add(*original_activity.locations.all())
            new_activity.requirements.add(*original_activity.requirements.all())
            new_activity.groups.add(*original_activity.groups.all())
            new_activity.mustNotOverlap.add(*original_activity.mustNotOverlap.all())
            new_activity.before.add(*original_activity.before.all())
            new_activity.required_rooms.add(*original_activity.required_rooms.all())
            new_activity.tags.add(*original_activity.tags.all())
            new_activity.teachers.add(*original_activity.teachers.all())
            for requirement in timetable.models.NRequirementsPerStudent.objects.filter(
                activity=original_activity
            ):
                timetable.models.NRequirementsPerStudent.objects.create(
                    activity=new_activity,
                    resource=requirement.resource,
                    n=requirement.n,
                )

            for realization in original_activity.realizations.all():
                new_realization = timetable.models.ActivityRealization(
                    activity=new_activity,
                    intended_size=realization.intended_size,
                )
                new_realization.save()
                new_realization.groups.add(*realization.groups.all())
                new_realization.teachers.add(*realization.teachers.all())
            all_activities.append(new_activity)

        tag = timetable.models.Tag.objects.create(
            name="12 ur med {0}".format(original_activity.subject.short_name)
        )
        tag.activities.add(*all_activities)
        timetable.models.TagValuePreference.objects.create(
            tag=tag,
            value=13,
            weight=1.0,
            level="WANT",
            name="MINACTIVITYGAP",
            preferenceset=tt.preferenceset,
        )
        return all_activities
