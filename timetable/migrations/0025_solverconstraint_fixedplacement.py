from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("timetable", "0024_studymodule"),
    ]

    operations = [
        migrations.AddField(
            model_name="solverconstraint",
            name="day",
            field=models.CharField(
                blank=True,
                choices=[
                    ("MON", "ponedeljek"), ("TUE", "torek"), ("WED", "sreda"),
                    ("THU", "četrtek"), ("FRI", "petek"),
                ],
                max_length=3,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="solverconstraint",
            name="start",
            field=models.CharField(
                blank=True,
                choices=[
                    ("07:00", "07:00"), ("08:00", "08:00"), ("09:00", "09:00"),
                    ("10:00", "10:00"), ("11:00", "11:00"), ("12:00", "12:00"),
                    ("13:00", "13:00"), ("14:00", "14:00"), ("15:00", "15:00"),
                    ("16:00", "16:00"), ("17:00", "17:00"), ("18:00", "18:00"),
                    ("19:00", "19:00"), ("20:00", "20:00"), ("21:00", "21:00"),
                ],
                max_length=5,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="solverconstraint",
            name="constraint_type",
            field=models.CharField(
                choices=[
                    ("NOOVERLAP", "Realizations must not overlap"), ("GROUPED", "Realizations must start together"),
                    ("CONSECUTIVE", "Realizations must be consecutive"), ("SAMEDAY", "Realizations must be on the same day"),
                    ("SAMESTARTINGTIME", "Realizations must start at the same time"), ("ENDSSTUDENTSDAY", "Realization ends the students' day"),
                    ("MAXROOMSREALIZATIONS", "Maximum different rooms across realizations"), ("MAXDAYSWEEK", "Maximum active days per week"),
                    ("MINDAYSWEEK", "Minimum active days per week"), ("MAXHOURSDAY", "Maximum hours per day"),
                    ("MAXHOURSCONT", "Maximum continuous hours"), ("MINCHANGEGAP", "Minimum gap between building changes"),
                    ("MAXLECTUREHOURSDAY", "Maximum lecture hours per day for a top-level group"),
                    ("FIXEDROOM", "Fixed room for activities or realizations"),
                    ("FIXEDPLACEMENT", "Fixed weekday, time, and room for a realization"),
                ],
                max_length=32,
            ),
        ),
    ]
