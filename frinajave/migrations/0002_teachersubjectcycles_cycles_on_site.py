from django.db import migrations, models


def default_existing_cycles_on_site(apps, schema_editor):
    TeacherSubjectCycles = apps.get_model("frinajave", "TeacherSubjectCycles")
    for entry in TeacherSubjectCycles.objects.filter(cycles_on_site__isnull=True).iterator():
        entry.cycles_on_site = entry.cycles
        entry.save(update_fields=("cycles_on_site",))


class Migration(migrations.Migration):
    dependencies = [
        ("frinajave", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="teachersubjectcycles",
            name="cycles_on_site",
            field=models.DecimalField(
                blank=True,
                decimal_places=3,
                help_text="Cycles this teacher performs physically on site.",
                max_digits=18,
                null=True,
            ),
        ),
        migrations.RunPython(default_existing_cycles_on_site, migrations.RunPython.noop),
    ]
