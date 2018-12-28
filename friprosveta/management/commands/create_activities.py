import logging
from collections import defaultdict

from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand
from django.db import transaction

from friprosveta.models import Teacher, Activity, Subject, LectureType
from friprosveta.studis import Sifranti, Studij, Najave
from timetable.models import PreferenceSet, Location
from timetable.models import Timetable, ActivitySet

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    args = 'create_activities timetable_slug year semester'
    help = '''Create activities in the given timetable according to najave in studis.
Usage: create_activities  timetable_slug year semester force
Semester can be 1 (zimski), 2(poletni), 3(celoletni) or 4(blocni).
When force option is enabled and no such timetable exists it will be created.
Beware: all existing activities (and all its children) WILL BE DELETED.
'''

    def add_arguments(self, parser):
        parser.add_argument('timetable_slug', nargs=1, type=str)
        parser.add_argument('year', nargs=1, type=str)
        parser.add_argument('semester_id', nargs=1, type=str)

        parser.add_argument(
            '--force',
            action='store_true',
            help='Create timetable if it does not exists.'),

        parser.add_argument(
            '--subject_code', nargs=1,
            dest='subject_code',
            default=None,
            help='Update activities only for the subject with given code.'),

        parser.add_argument(
            '--location', nargs=1,
            default='Večna pot FRI',
            help='Location of the activities. Defaults to "Večna pot FRI".'),

    def get_semester(self, year, semester_id):
        sifranti = Sifranti()
        semestri = sifranti.get_semestri(year)
        semester = filter(lambda semester: semester['id'] == semester_id,
                        semestri)
        return list(semester)[0]

    @transaction.atomic
    def handle(self, *args, **options):
        logger.info("Entering handle")
        if options['force']:
            logger.debug("Force is True")
            tt = Timetable.objects.filter(slug=options["timetable_slug"][0])
            assert len(tt) <= 1, "Timetable slug ({0}) should be unique.".format(args[0])
            if len(tt) == 1:
                tt = tt[0]
            else:
                tt = Timetable(name=args[0], slug=args[0])
                logger.debug("No timetable '{0}' found, creating one.".format(args[0]))
                aset, created = ActivitySet.objects.get_or_create(name=args[0])
                if created:
                    logger.debug("No activityset '{0}' found, creating.".format(args[0]))
                    aset.save()
                tt.activityset = aset
                pset, created = PreferenceSet.objects.get_or_create(name=args[0])
                if created:
                    logger.debug("No preferenceset '{0}' found, creating.".format(args[0]))
                    pset.save()
                tt.preferenceset = pset
                tt.save()

        else:
            tt = Timetable.objects.get(slug=options["timetable_slug"][0])
        location = Location.objects.get(name=options['location'])
        subject = None
        if options['subject_code'] is not None:
            subject = options['subject_code'][0]

        year = int(options["year"][0])
        semester_id = int(options["semester_id"][0])
        semester = self.get_semester(year, semester_id)
        logger.debug("Gor semester {}".format(semester))
        self.sync_activities_with_fri_najave(tt, semester, year, location, subject)
        logger.info("Exiting handle")

    @transaction.atomic
    def sync_activities_with_fri_najave(self, timetable, semester, year, location, update_subject):
        """
        Sinhronizira učitelje v najavah z učitelji v aktivnostih.
        Če je potrebno, ustvari nove aktivnosti.
        Starih aktivnosti, ki jih ni v najavah, ne pobriše.
        Ce dodamo kodo predmeta, se posodobijo aktivnosti samo pri tem predmetu.
        Ce je koda predmeta None, potem se posodobijo vse aktivnosti.
        """
        logger.info("Entering syncActivitiesWithFRINajave")

        def activity_name(subject, lecture_type):
            name = "{0}({1})_{2}".format(subject.name, subject.code, lecture_type.short_name)
            logger.debug("Generated name {}".format(name))
            return name

        def activity_short_name(subject, lecture_type):
            name = "{0}_{1}".format(subject.short_name, lecture_type.short_name)
            logger.debug("Generated sname {}".format(name))
            return name

        def get_teacher_codes(cikel, lecture_type_id):
            logger.debug("Processing {}".format(cikel))
            codes = set()
            mapping_urnik_studis = {1: [1, 7], 2: [3], 3: [2], 4: [8], 6: [4]}
            for izvajalec in cikel['izvajalci']:
                if izvajalec['tip_izvajanja']['id'] in mapping_urnik_studis[lecture_type_id]:
                    codes.add(izvajalec['delavec_sifra'])
            logger.debug("Got codes for {}: {}".format(lecture_type_id, codes))
            return codes

        def subject_lecture_types(cikel):
            # id from studis to our system
            # Studis:
            # [{u'id': 1, 'title': {u'en': None, 'sl': 'Predavanja'}},
            # {u'id': 2, 'title': {u'en': None, 'sl': 'Avditorne vaje'}},
            # {u'id': 3, 'title': {u'en': None, 'sl': 'Laboratorijske vaje'}},
            # {u'id': 4, 'title': {u'en': None, 'sl': 'Seminar'}},
            # {u'id': 5, 'title': {u'en': None, 'sl': 'Poobla\u0161\u010denec'}},
            # {u'id': 6, 'title': {u'en': None, 'sl': 'Koordinator'}},
            # {u'id': 7, 'title': {u'en': None, 'sl': 'Nosilec'}},
            # {u'id': 8, 'title': {u'en': None, 'sl': 'Laborant'}}]
            mapping_studis_urnik = {1: 1, 2: 3, 3: 2, 4: 6, 5: None, 6: None, 7: 1, 8: 2}
            lecture_types_ids = set(mapping_studis_urnik[t['tip_izvajanja']['id']] for t in cikel['izvajalci'])
            lecture_types_ids.discard(None)
            return lecture_types_ids

        def get_duration(lecture_type_id, izvajanje):
            """
            Get subject duration. The duration of subject depends on subject and lecture type.
            It is read from Studis database.
            """
            mapping_urnik_studis = {1: 'st_ur_predavanj', 2: 'st_ur_lab_vaj', 3: 'st_ur_avd_vaj',
                                    6: 'st_ur_seminarja', 8: 'st_ur_lab_vaj',
                                    }
            if izvajanje[mapping_urnik_studis[lecture_type_id]] is None:
                return None

            add_duration = 0
            # Weird fix: sometimes hours are attributed to seminar
            if izvajanje['st_ur_seminarja'] is not None and lecture_type_id != 6:
                add_duration = izvajanje['st_ur_seminarja']
            total_duration = add_duration + izvajanje[mapping_urnik_studis[lecture_type_id]]
            return total_duration / 15

        semester_id = semester['id']
        studij = Studij(year)
        sifranti = Sifranti()
        najave = Najave(year)
        # Only process this semester izvajanja
        izvajanja = [i for i in studij.get_izvajanja() if i["semester"] == semester_id]

        izvajanja_subject_ids = defaultdict(list)
        for izvajanje in izvajanja:
            if not izvajanje['izvaja_partnerska_institucija']:
                izvajanja_subject_ids[izvajanje['idpredmet']].append(izvajanje)

        for cikel in najave.get_predmeti_cikli():            
            subject_code = cikel['predmet_sifra']
            # Skip subjects we should no update
            if update_subject is not None and update_subject != subject_code:
                continue

            found = False
            izvajanja = izvajanja_subject_ids[cikel['predmet_id']]
            for izvajanje in izvajanja:
                izvajanje_id = izvajanje["id"].split("-")[1].strip()
                cikel_izvajanje_id = str(cikel["izvajanje_id"]) 
                if cikel_izvajanje_id == izvajanje_id:
                    found = True
            if not found:
                logger.info("No matching izvajanje for cikel {0}, skipping".format(cikel).encode("utf-8"))
                continue

            izvajanje = izvajanja[0]
            logger.info("Looking for subject code {0}".format(subject_code).encode("utf-8"))
            try:
                subject = Subject.objects.get(code=subject_code)
            except Exception:
                logger.Exception()
                continue
            logger.debug("Processing subject {}".format(subject))
            lecture_types = subject_lecture_types(cikel)
            logger.debug("Got lecture types: {}".format(lecture_types))

            for lecture_type_id in lecture_types:
                logger.debug("Processing lt {}".format(lecture_type_id))
                lecture_type = LectureType.objects.get(pk=lecture_type_id)
                logger.debug("lt {}".format(lecture_type))
                activities = subject.activities.filter(lecture_type=lecture_type,
                                                       activityset=timetable.activityset)
                logger.debug("Got activities {}".format(activities))
                teacher_codes = get_teacher_codes(cikel, lecture_type_id)
                logger.debug("Got teacher codes {}".format(teacher_codes))
                duration = get_duration(lecture_type_id, izvajanje)
                logger.debug("Got duration {}".format(duration))

                teachers = []
                for code in teacher_codes:
                    try:
                        teacher = Teacher.objects.get(code=code)
                        teachers.append(teacher)
                    except ObjectDoesNotExist as e:
                        logger.exception(
                            "Teacher with code {0} on subject {1} does not exist".format(code, subject.code))

                if activities.count() == 0:
                    logger.debug("Activity of type {0} for {1} not found. Creating one.".format(lecture_type, subject))
                    if duration is None:
                        logger.debug('Duration for type {0} is 0, skipping.'.format(lecture_type))
                        continue
                    activity = Activity(
                        subject=subject, lecture_type=lecture_type,
                        activityset=timetable.activityset, duration=duration,
                        name=activity_name(subject, lecture_type),
                        short_name=activity_short_name(subject, lecture_type),
                        type=lecture_type.short_name
                    )
                    activity.save()
                    activity.locations.add(location)
                    logger.debug("Created activity {0}.".format(activity))
                    activities = [activity]
                for activity in activities:
                    activity.name = activity_name(subject, lecture_type)
                    activity.short_name = activity_short_name(subject, lecture_type)
                    print("Name, shortname")
                    print(activity.name, activity.short_name)
                    activity.save()
                    activity.teachers.clear()
                    activity.teachers.add(*teachers)
        logger.info("Exiting syncActivitiesWithFRINajave")
