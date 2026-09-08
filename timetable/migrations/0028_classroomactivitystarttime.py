from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("timetable", "0027_solverconstraint_fixedtime")]

    operations = [
        migrations.CreateModel(
            name="ClassroomActivityStartTime",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "activity_type",
                    models.CharField(
                        choices=[
                            ("LAB", "Laborant vaje"), ("LV", "Laboratorijske vaje"),
                            ("AV", "Avditorne vaje"), ("P", "Predavanja"),
                            ("TUT", "Tutorstvo"), ("REP", "Repetitorij"),
                        ],
                        max_length=4,
                    ),
                ),
                (
                    "start",
                    models.CharField(
                        choices=[
                            ("07:00", "07:00"), ("08:00", "08:00"), ("09:00", "09:00"),
                            ("10:00", "10:00"), ("11:00", "11:00"), ("12:00", "12:00"),
                            ("13:00", "13:00"), ("14:00", "14:00"), ("15:00", "15:00"),
                            ("16:00", "16:00"), ("17:00", "17:00"), ("18:00", "18:00"),
                            ("19:00", "19:00"), ("20:00", "20:00"), ("21:00", "21:00"),
                        ],
                        max_length=5,
                    ),
                ),
                (
                    "classroom",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="activity_start_times",
                        to="timetable.classroom",
                    ),
                ),
            ],
            options={"unique_together": {("classroom", "activity_type", "start")}},
        ),
    ]
