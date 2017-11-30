from django.core.management.base import BaseCommand
from frinajave.models import TeacherSubjectCycles
from timetable.models import TimetableSet
from friprosveta.models import LectureType, Subject
from friprosveta.studis import Najave

import logging

logger = logging.getLogger(__name__)

tip_izv_map = {
    1: ('P', 'Predavanja',),
    2: ('AV', 'Avditorne vaje'),
    3: ('LV', 'Laboratorijske vaje'),
    4: ('SEM', 'Seminar'),
    5: ('POO', 'Pooblaščenec'),
    6: ('KOO', 'Koordinator'),
    7: ('P', 'Predavanja',),  # Nosilec
    8: ('lab.', 'Laborant'),
}


class Command(BaseCommand):
    '''
    Get najave from studis.
    '''
    args = 'import_studis_najave timetable_slug year semester_id'
    help = '''Usage:
import_studis_najave timetable_slug year semester_id

Year is the first part in the study year:
2015/2016 -> 2015

Semester can be 1 (zimski), 2(poletni), 3(celoletni) or 4(blocni).
'''

    def add_arguments(self, parser):
        parser.add_argument('timetable_slug', nargs=1, type=str)
        parser.add_argument('year', nargs=1, type=str)
        parser.add_argument('semester_id', nargs=1, type=str)

        parser.add_argument(
            '--subject', nargs=1,
            action='store',
            dest='subject',
            help='Only update subject with the given code.'),

    def handle(self, *args, **options):
        logger.info("Entering handle")
        logger.debug("Args: {}".format(args))
        logger.debug("Options: {}".format(options))
        timetable_set = TimetableSet.objects.get(slug=options['timetable_slug'][0])
        year = options['year'][0]
        semester_id = options['semester_id'][0]

        subject_codes = set()
        if options['subject'] is not None:
            subject_codes.add(options['subject'][0])
        else:
            #for timetable in timetable_set.timetables.all():
            #    timetable = Timetable.objects.get(id=timetable.id)
            #    subjects = timetable.subjects
            #    subject_codes.update(subject.code for subject in subjects)
            subject_codes.update(subject.code for subject in Subject.objects.all())

        studis_najave = Najave(year)
        predmeti_cikli = studis_najave.get_predmeti_cikli()
        izvajanja_ids = studis_najave.get_izvajanja_ids()

        for predmet_cikli in predmeti_cikli:
            if predmet_cikli['predmet_sifra'] not in subject_codes:
                logger.debug("Subject {} not in subject_codes".format(predmet_cikli["predmet_sifra"]))
                continue
            if str(predmet_cikli["izvajanje_id"]) not in izvajanja_ids:
                # Probably not in this semester
                logger.debug("Subject {} not in this semester".format(predmet_cikli["predmet_sifra"]))
                continue
            TeacherSubjectCycles.objects.filter(
                timetable_set=timetable_set,
                subject_code=predmet_cikli['predmet_sifra']
            ).delete()
            for cikel in predmet_cikli['izvajalci']:
                lecture_type = LectureType.objects.filter(
                    short_name=tip_izv_map[cikel['tip_izvajanja']['id']][0]
                )
                if len(lecture_type) == 0:
                    continue
                assert len(lecture_type) == 1
                lecture_type = lecture_type[0]
                instruction_type = cikel['cikli_dvojni']
                if instruction_type is not None:
                    instruction_type = instruction_type['id']
                novi = TeacherSubjectCycles(
                    timetable_set=timetable_set,
                    subject_code=predmet_cikli['predmet_sifra'],
                    teacher_code=cikel['delavec_sifra'],
                    lecture_type=lecture_type.id,
                    cycles=cikel['cikli_stevilo'],
                    instruction_type=instruction_type,
                )
                novi.save()
