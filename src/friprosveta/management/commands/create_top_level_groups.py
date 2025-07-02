from django.core.management.base import BaseCommand

from friprosveta.models import Subject, Timetable
from friprosveta.studis import Najave, Studij
from timetable.models import Group


class Command(BaseCommand):
    """
    Create top level groups from Studis izvajanja for the given timetable.
    """

    args = "create_top_level_groups timetable_slug year semester_id"
    help = (
        "Usage:\n"
        "create_top_level_groups timetable_slug year semester_id\n"
        "\n"
        "Year is the first part in the study year:\n"
        "2015/2016 -> 2015\n"
        "\n"
        "Semester can be 1 (zimski), 2(poletni), 3(celoletni) or 4(blocni).\n"
    )

    def add_arguments(self, parser):
        parser.add_argument("timetable_slug", nargs=1, type=str)
        parser.add_argument("year", nargs=1, type=str)
        parser.add_argument("semester_id", nargs=1, type=str)

    def handle(self, *args, **options):
        timetable = Timetable.objects.get(slug=options["timetable_slug"][0])
        year = options["year"][0]
        semester_id = options["semester_id"][0]

        studis_najave = Najave(year)
        studij = Studij(year)
        studijsko_drevo = studij.get_studijsko_drevo()
        izvajanja = studis_najave.get_izvajanja()
        create_regular_groups(
            izvajanja, [semester_id], studijsko_drevo, timetable.groupset, studis_najave
        )


def group_name(self, predmetnik):
    """Generate tuple (name, short_name) from Studis predmetnik entry."""
    assert len(predmetnik) == 5, "Predmetnik not complete " + str(predmetnik)
    short_name = "{0}_{1}-{2}".format(
        predmetnik[5]["short_title"],
        predmetnik[1]["short_title"],
        predmetnik[2]["short_title"],
    )
    name = "{0}, {1}, {2}".format(
        predmetnik[5]["title"]["sl"],
        predmetnik[2]["title"]["sl"],
        predmetnik[1]["title"]["sl"],
    )
    return short_name, name


def create_regular_groups(izvajanja, semestri, studijsko_drevo, groupset, najave):
    regular_izvajanja = [
        e for e in izvajanja if e["obvezen"] and e["semester"] in semestri
    ]
    problems = []
    for e in regular_izvajanja:
        try:
            predmetnik = najave.get_predmetnik(e, studijsko_drevo)
            subject = Subject.objects.get(code=e["sifra_predmeta"])
        except Exception as ex:
            print("Problems for izvajanje", e["sifra_predmeta"])
            problems.append(e)
            continue
        sname, name = najave.group_name(predmetnik)
        g = Group.objects.get_or_create(
            name=name, short_name=sname, parent=None, groupset=groupset, size=0
        )
