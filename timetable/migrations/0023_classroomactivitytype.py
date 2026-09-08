from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("timetable", "0022_classroom_is_virtual"),
    ]

    operations = [
        migrations.CreateModel(
            name="ClassroomActivityType",
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
                    "classroom",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="supported_activity_types",
                        to="timetable.classroom",
                    ),
                ),
            ],
            options={
                "unique_together": {("classroom", "activity_type")},
            },
        ),
    ]
