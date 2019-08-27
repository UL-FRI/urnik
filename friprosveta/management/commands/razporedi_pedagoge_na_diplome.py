from django.core.management.base import BaseCommand

from friprosveta.models import Teacher, Activity
from friprosveta.studis import Osebe
from timetable.models import Allocation


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('ids', nargs='+', type=int, help="durations of splits")

    def handle(self, *args, **options):
        #        if len(args) < 2:
        #            print("Razporedi pedagoge na diplome. Sprejme id-je realizacij.")
        #            print("./manage.py razporedi_pedagoge_na_diplome #id_realization_1 ...")
        #            print("Za te realizacije morajo biti ustvarjene alokacije, "
        #                  "vse realizacije morajo imeti isto aktivnost.")
        #            print("Primer uporabe: razporedi_pedagoge_na_diplome "
        #                  "1234 5678 9874 ...")
        #            return

        realizacije_ids = options['ids']
        print(realizacije_ids)
        osebe = Osebe()
        titles = osebe.get_nazivi()
        teachers = osebe.get_teachers()
        teachers = [teacher for teacher in teachers
                    if (teacher['sifra_predavatelja'] is not None and
                        teacher['sifra_predavatelja'].startswith('630'))]

        teacher_titles = ['docent', 'izredni profesor', 'predavatelj', 'redni profesor',
                          'višji predavatelj']
        teacher_titles_ids = [title['id'] for title in titles
                              if title['full_title']['sl'] in teacher_titles]
        teacher_codes = [teacher['sifra_predavatelja']
                         for teacher in teachers
                         if len(set(teacher['habilitacija']) & set(teacher_titles_ids)) > 0 and
                         teacher['status_kadrovska'] == 2]

        fri_teachers = Teacher.objects.filter(code__in=teacher_codes)
        allocations = Allocation.objects.filter(activityRealization__id__in=realizacije_ids)
        self.razporedi(fri_teachers, allocations)
        activity = Activity.objects.filter(realizations__id__in=realizacije_ids).distinct().get()
        for teacher in fri_teachers:
            activity.teachers.add(teacher)

    def razporedi(self, teachers, allocations):
        def je_prost(ucitelj, alokacija, proste_ure):
            for zahtevana_ura in alokacija.hours:
                if zahtevana_ura not in proste_ure[ucitelj][alokacija.day]:
                    return False
            return True

        def teacher_compare(t1, t2):
            ucitelji_mozne_alokacije[t1].count

        tt = allocations[0].timetable
        proste_ure = {ucitelj: ucitelj.free_hours(tt, 0.5) for ucitelj in teachers}

        alokacije_mozni_ucitelji = {alokacija: [ucitelj for ucitelj in teachers
                                                if je_prost(ucitelj, alokacija, proste_ure)]
                                    for alokacija in allocations}
        ucitelji_mozne_alokacije = {ucitelj: [alokacija for alokacija in allocations
                                              if ucitelj in alokacije_mozni_ucitelji[alokacija]]
                                    for ucitelj in teachers}

        teachers = sorted(teachers, key=lambda ucitelj: len(ucitelji_mozne_alokacije[ucitelj]))
        # Filter out teachers that can not take place at any exam
        teachers = [teacher for teacher in teachers if len(ucitelji_mozne_alokacije[teacher]) > 0]

        for t in teachers:
            print(len(ucitelji_mozne_alokacije[t]))

        allocations = sorted(allocations, key=lambda alokacija:
        len(alokacije_mozni_ucitelji[alokacija]))
        alokacija_ucitelj = {alokacija: [] for alokacija in allocations}

        naeno = len(teachers) / len(allocations)

        for alokacija in allocations:
            print(alokacija)
            while len(alokacija_ucitelj[alokacija]) < naeno and teachers:
                print(alokacija_ucitelj[alokacija])
                print(alokacija)
                print('Prosti', teachers)
                najden = False
                for ucitelj in teachers:
                    if (ucitelj in alokacije_mozni_ucitelji[alokacija] and
                            ucitelj not in alokacija_ucitelj[alokacija]):
                        alokacija_ucitelj[alokacija].append(ucitelj)
                        najden = True
                        break
                if najden:
                    teachers.remove(ucitelj)

        for alokacija in alokacija_ucitelj:
            user = ucitelj.user
            print(alokacija, ",".join(["{0} {1}".format(user.first_name, user.last_name)
                                        for ucitelj in alokacija_ucitelj[alokacija]]))
            alokacija.teachers.clear()
            for ucitelj in alokacija_ucitelj[alokacija]:
                alokacija.teachers.add(ucitelj)
