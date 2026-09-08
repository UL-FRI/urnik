from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("friprosveta", "0014_teacherschedulingwindow_unavailable"),
        ("timetable", "0029_classroom_minimum_realization_size"),
    ]

    operations = [
        migrations.CreateModel(
            name="ManualActivity",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(blank=True, max_length=200)),
                ("duration", models.PositiveSmallIntegerField()),
                ("enabled", models.BooleanField(default=True)),
                ("fixed_day", models.CharField(blank=True, choices=[("MON", "ponedeljek"), ("TUE", "torek"), ("WED", "sreda"), ("THU", "četrtek"), ("FRI", "petek")], max_length=3)),
                ("fixed_start", models.CharField(blank=True, choices=[("07:00", "07:00"), ("08:00", "08:00"), ("09:00", "09:00"), ("10:00", "10:00"), ("11:00", "11:00"), ("12:00", "12:00"), ("13:00", "13:00"), ("14:00", "14:00"), ("15:00", "15:00"), ("16:00", "16:00"), ("17:00", "17:00"), ("18:00", "18:00"), ("19:00", "19:00"), ("20:00", "20:00"), ("21:00", "21:00")], max_length=5)),
                ("fixed_room", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="manual_activity_placements", to="timetable.classroom")),
                ("groups", models.ManyToManyField(blank=True, to="timetable.group")),
                ("lecture_type", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="friprosveta.lecturetype")),
                ("locations", models.ManyToManyField(to="timetable.location")),
                ("requirements", models.ManyToManyField(blank=True, to="timetable.resource")),
                ("required_rooms", models.ManyToManyField(blank=True, to="timetable.classroom")),
                ("subject", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="friprosveta.subject")),
                ("solver_constraint", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="manual_activity", to="timetable.solverconstraint")),
                ("teachers", models.ManyToManyField(blank=True, to="timetable.teacher")),
                ("timetable", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="manual_activities", to="timetable.timetable")),
            ],
            options={"ordering": ("subject__code", "lecture_type__short_name")},
        ),
        migrations.AddConstraint(
            model_name="manualactivity",
            constraint=models.UniqueConstraint(fields=("timetable", "subject", "lecture_type"), name="unique_manual_activity_per_timetable_subject_type"),
        ),
    ]
