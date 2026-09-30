from django.db import migrations, models
import django.db.models.deletion


def ensure_activity_parent_unique(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != "postgresql":
        return

    Activity = apps.get_model("friprosveta", "Activity")
    with connection.cursor() as cursor:
        constraints = connection.introspection.get_constraints(
            cursor, Activity._meta.db_table
        )
    if any(
        constraint["columns"] == [Activity._meta.pk.column]
        and (constraint["primary_key"] or constraint["unique"])
        for constraint in constraints.values()
    ):
        return

    # Existing deployments can have a separate id primary key and only a
    # non-unique index on activity_ptr_id. Keep id and make the parent link
    # a valid foreign-key target before adding ManualActivity.activity.
    schema_editor.add_constraint(
        Activity,
        models.UniqueConstraint(
            fields=(Activity._meta.pk.name,),
            name="friprosveta_activity_activity_ptr_id_unique",
        ),
    )


def link_existing_manual_activities(apps, schema_editor):
    ManualActivity = apps.get_model("friprosveta", "ManualActivity")
    Activity = apps.get_model("friprosveta", "Activity")
    database = schema_editor.connection.alias

    for entry in ManualActivity.objects.using(database).select_related(
        "subject", "lecture_type", "timetable"
    ):
        activity = Activity.objects.using(database).filter(
            activityset_id=entry.timetable.activityset_id,
            short_name="MANUAL_{}".format(entry.pk),
        ).first()
        if activity is None:
            continue
        entry.activity_id = activity.pk
        entry.save(update_fields=("activity",))
        activity.short_name = "{}_{}".format(
            entry.subject.short_name or entry.subject.code,
            entry.lecture_type.short_name,
        )[:32]
        activity.save(update_fields=("short_name",))


def unlink_manual_activities(apps, schema_editor):
    ManualActivity = apps.get_model("friprosveta", "ManualActivity")
    Activity = apps.get_model("friprosveta", "Activity")
    database = schema_editor.connection.alias

    for entry in ManualActivity.objects.using(database).exclude(activity_id=None):
        activity = Activity.objects.using(database).filter(
            pk=entry.activity_id, activityset_id=entry.timetable.activityset_id
        ).first()
        if activity is not None:
            activity.short_name = "MANUAL_{}".format(entry.pk)
            activity.save(update_fields=("short_name",))


class Migration(migrations.Migration):
    dependencies = [("friprosveta", "0015_manualactivity")]

    operations = [
        migrations.RunPython(ensure_activity_parent_unique, migrations.RunPython.noop),
        migrations.AddField(
            model_name="manualactivity",
            name="activity",
            field=models.OneToOneField(
                to="friprosveta.activity",
                null=True,
                blank=True,
                related_name="manual_definition",
                on_delete=django.db.models.deletion.SET_NULL,
            ),
        ),
        migrations.RunPython(link_existing_manual_activities, unlink_manual_activities),
    ]
