from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("timetable", "0023_classroomactivitytype"),
    ]

    operations = [
        migrations.CreateModel(
            name="StudyModule",
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
                ("name", models.CharField(max_length=128)),
                ("active", models.BooleanField(default=True)),
                (
                    "activities",
                    models.ManyToManyField(blank=True, to="timetable.activity"),
                ),
                (
                    "timetable",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="study_modules",
                        to="timetable.timetable",
                    ),
                ),
                (
                    "non_overlapping_with",
                    models.ManyToManyField(blank=True, to="timetable.studymodule"),
                ),
            ],
            options={
                "ordering": ("name",),
                "unique_together": {("timetable", "name")},
            },
        ),
    ]
