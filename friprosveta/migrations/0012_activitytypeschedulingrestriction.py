from django.db import migrations, models
import django.db.models.deletion
from django.core.validators import MaxValueValidator, MinValueValidator


def migrate_windows_to_restrictions(apps, schema_editor):
    Window = apps.get_model("friprosveta", "ActivityTypeSchedulingWindow")
    Restriction = apps.get_model("friprosveta", "ActivityTypeSchedulingRestriction")
    work_hours = [f"{hour:02}:00" for hour in range(7, 22)]
    restrictions = []
    for window in Window.objects.filter(active=True):
        for hour in work_hours:
            if not window.start <= hour < window.end:
                restrictions.append(
                    Restriction(
                        timetable_id=window.timetable_id,
                        activity_type=window.activity_type,
                        day=window.day,
                        start=hour,
                        weight=window.weight,
                    )
                )
    Restriction.objects.bulk_create(restrictions)


class Migration(migrations.Migration):

    dependencies = [
        ("friprosveta", "0011_schedulingwindow_weight"),
        ("timetable", "0019_solverconstraint"),
    ]

    operations = [
        migrations.CreateModel(
            name="ActivityTypeSchedulingRestriction",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "activity_type",
                    models.CharField(
                        choices=[
                            ("LAB", "Laborant vaje"),
                            ("LV", "Laboratorijske vaje"),
                            ("AV", "Avditorne vaje"),
                            ("P", "Predavanja"),
                            ("TUT", "Tutorstvo"),
                            ("REP", "Repetitorij"),
                        ],
                        max_length=4,
                    ),
                ),
                (
                    "day",
                    models.CharField(
                        choices=[
                            ("MON", "ponedeljek"),
                            ("TUE", "torek"),
                            ("WED", "sreda"),
                            ("THU", "četrtek"),
                            ("FRI", "petek"),
                        ],
                        max_length=3,
                    ),
                ),
                (
                    "start",
                    models.CharField(
                        choices=[(f"{hour:02}:00", f"{hour:02}:00") for hour in range(7, 22)],
                        max_length=5,
                    ),
                ),
                (
                    "weight",
                    models.PositiveSmallIntegerField(
                        help_text="0 is available, 1-99 is soft unavailability, and 100 is hard.",
                        validators=[MinValueValidator(0), MaxValueValidator(100)],
                    ),
                ),
                (
                    "timetable",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="activity_type_scheduling_restrictions",
                        to="timetable.timetable",
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=("timetable", "activity_type", "day", "start"),
                        name="activity_type_scheduling_restriction_unique_slot",
                    ),
                ],
            },
        ),
        migrations.RunPython(migrate_windows_to_restrictions, migrations.RunPython.noop),
    ]
