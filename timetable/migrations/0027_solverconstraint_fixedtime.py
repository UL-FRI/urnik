from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("timetable", "0026_solverconstraint_span_and_same_room")]

    operations = [
        migrations.AlterField(
            model_name="solverconstraint",
            name="constraint_type",
            field=models.CharField(
                choices=[
                    ("NOOVERLAP", "Realizations must not overlap"), ("GROUPED", "Realizations must start together"),
                    ("CONSECUTIVE", "Realizations must be consecutive"), ("SAMEDAY", "Realizations must be on the same day"),
                    ("SAMESTARTINGTIME", "Realizations must start at the same time"), ("SAMEROOM", "Realizations must use the same room"),
                    ("ENDSSTUDENTSDAY", "Realization ends the students' day"), ("MAXROOMSREALIZATIONS", "Maximum different rooms across realizations"),
                    ("MAXDAYSWEEK", "Maximum active days per week"), ("MINDAYSWEEK", "Minimum active days per week"),
                    ("MAXHOURSDAY", "Maximum hours per day"), ("MAXHOURSCONT", "Maximum continuous hours"),
                    ("MAXSPANDAY", "Maximum daily span"), ("MINCHANGEGAP", "Minimum gap between building changes"),
                    ("MAXLECTUREHOURSDAY", "Maximum lecture hours per day for a top-level group"),
                    ("FIXEDROOM", "Fixed room for activities or realizations"),
                    ("FIXEDPLACEMENT", "Fixed weekday, time, and room for a realization"),
                    ("FIXEDTIME", "Fixed weekday and time for a realization"),
                ],
                max_length=32,
            ),
        ),
    ]
