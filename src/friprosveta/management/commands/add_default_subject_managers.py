import maroltnajave
from django.core.management.base import BaseCommand

import friprosveta


class Command(BaseCommand):
    def add_catedra_heads_and_deputies(self, obdobja, clear_managers):
        for s in friprosveta.models.Subject.objects.all():
            if clear_managers:
                s.managers.clear()
            # print s
            dpt = maroltnajave.models.Delavecpredmett.objects.filter(
                subject__sifra=s.code, type=1, valid=True, obdobje__in=obdobja
            )
            # ce ne znamo najti katedre, med managerje dodamo nosilca
            mgrs = set()
            if len(dpt) == 0:
                for t in friprosveta.models.Teacher.objects.filter(
                    activities__activity__subject=s, activities__type="P"
                ).distinct():
                    #                    print "ako je prazno ", t, type(t)
                    mgrs.add(t)
            for d in dpt:
                try:
                    c = friprosveta.models.Cathedra.objects.get(
                        name=d.teacher.katedra.naziv
                    )
                    headt = c.heads.all()[0]
                    mgrs.add(friprosveta.models.Teacher.objects.get(id=headt.id))
                    # print("glava ", headt, type(headt), friprosveta.models.Teacher.objects.get(id = headt.id))
                    if len(c.najave_deputies.all()) == 0:
                        print(" na ", s, " dodajam izvajalce:")
                        for t in friprosveta.models.Teacher.objects.filter(
                            activities__activity__subject=s, activities__type="P"
                        ).distinct():
                            #                            print "z aktivnosti ", t, type(t)
                            print("    ", t)
                            mgrs.add(t)
                    for tn in c.najave_deputies.all():
                        t = friprosveta.models.Teacher.objects.get(user__username=tn)
                        #                        print "deputies ", t, type(t)
                        mgrs.add(t)
                except Exception as e:
                    print(e)
                    print("XXXX", d.teacher)
            #            print "    ", mgrs
            for m in mgrs:
                print("dodaj ", m, type(m))
                try:
                    s.managers.add(m)
                except Exception as e:
                    print(e)

    def add_staff(self):
        managers = friprosveta.models.Teacher.objects.filter(user__is_staff=True)
        for m in managers.all():
            for s in friprosveta.models.Subject.objects.all():
                #    print "    " + str(s)
                s.managers.add(m)

    def handle(self, *args, **options):
        # parser = argparse.ArgumentParser(description='Enroll students into subjects for a given timetable.', epilog="Copyright polz")
        # parser.add_argument('--timetable', )
        if len(args) != 1:
            print("Usage: add_default_managers timetable_slug")
            return

        timetable = friprosveta.models.Timetable.objects.get(slug=args[0])
        obdobja = maroltnajave.models.Obdobjet.by_dates(timetable.start, timetable.end)[
            0
        ]
        self.add_catedra_heads_and_deputies(obdobja, True)
        self.add_staff()
