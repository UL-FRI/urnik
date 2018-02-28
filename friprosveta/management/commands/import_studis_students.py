import sys
from _collections import defaultdict
from django.core.management.base import BaseCommand
import json
from friprosveta.models import StudentEnrollment, Timetable, Study, Student
from friprosveta.models import Subject
from friprosveta.studis import Sifranti, Studij, Studenti


def get_study_classyear(studijsko_drevo, entry_id):
    if entry_id not in studijsko_drevo:
        return ('PAD', 8)
    study_mapper = {'Upravna informatika': 'BUN-UI', 'Izmenjave': 'IZMENJAVE', 'BUN-ML': 'BUN-MM'}
    classyear_mapper = {'B': 8, 'D': 4}
    entry5 = studijsko_drevo[entry_id]
    assert entry5['type'] == 5
    classyear = int(classyear_mapper.get(entry5['short_title'],
                                         entry5['short_title']))
    entry4 = studijsko_drevo[entry5['parent']]
    assert entry4['type'] == 4
    entry3 = studijsko_drevo[entry4['parent']]
    assert (entry3['type'] == 3) and (entry3['short_title'] is None)
    entry2 = studijsko_drevo[entry3['parent']]
    assert (entry2['type'] == 2)
    try: 
        entry1 = studijsko_drevo[entry2['parent']]
        assert (entry1['type'] == 1)
        entry2_short = study_mapper.get(entry2['short_title'].strip(),
                                 entry2['short_title'].strip())
        study = "{}-{}".format(entry1['short_title'].strip(), entry2_short)
    except:
        study = "{}".format(study_mapper.get(entry2['short_title'].strip(), entry2['short_title'].strip()))
    study = study_mapper.get(study, study)
    return (study, classyear)


class Command(BaseCommand):
    '''
    Get StudentEnrollments from Studis
    '''
    args = 'enroll_students timetable_slug year date'
    help = '''Enroll students to subjects from studis using
enrollment data on the given date.
Date must be in format YYYY-MM-DD.
Year is the first part in current studijsko leto 2014/2015 -> 2014.'''

    def add_arguments(self, parser):
        parser.add_argument('timetable_slug', nargs=1, type=str)
        parser.add_argument('year', nargs=1, type=str)
        parser.add_argument('date', nargs=1, type=str)
        # Unconfirmed enrollments
        parser.add_argument(
            '--unconfirmed',
            action='store_true',
            dest='unconfirmed',
            help='Process unconfirmed enrollments',
        )
        # Unfinished enrollments
        parser.add_argument(
            '--unfinished',
            action='store_true',
            dest='unfinished',
            help='Process unfinished enrollments',
        )
        # Unconfirmed enrollments
        parser.add_argument(
            '--preenrolment',
            action='store_true',
            dest='preenrolment',
            help='Process preenrollments',
        )

 

    def handle(self, *args, **options):
        timetable = Timetable.objects.get(slug=options['timetable_slug'][0])
        year = options['year'][0]
        date = options['date'][0]

        self.stdout.write("Loading data")
        sifranti = Sifranti()
        studij = Studij(year)
        studenti = Studenti()

        studijsko_drevo = studij.get_studijsko_drevo()
        self.students = studenti.get_student_enrollments(date, unfinished=options['unfinished'], unconfirmed=options['unconfirmed'], preenrolment=options['preenrolment'])
        self.stdout.write("got {} student enrollments".format(len(self.students)))
        self.enrollment_types = sifranti.get_tipi_vpisa()
        self.izredni_studij_id = sifranti.get_nacini_studija_izredni_studij_id
        subjects = studij.get_predmeti()
        self.stdout.write("got {} subjects".format(len(subjects)))
        self.studis_activities = studij.get_izvajanja()
        self.stdout.write("Data loaded")
        self.subjects = {subject['id']: subject for subject in subjects}
        self.studijsko_drevo = {e['id']: e for e in studijsko_drevo}
        # self.stderr.write("{}".format(self.studijsko_drevo))
        self.enrolStudents(timetable)
        # regular_studies_subjects = self.getRegularSubjects(timetable)
        # Commented out by Gregor, not needed on UniTime
        #$ padstudy = Study.objects.get(short_name="PAD")
        # crossections.fixRegularSubjectsEnrollments(
        #     timetable, regular_studies_subjects, padstudy
        # )

    def enrolStudents(self, currentTimetable,
                      enrollment_types=[1, 4, 26, 41, 42, 43, 47]):
        """
        Enroll students to subjects for current timetable.
        """
        # Remove current enrollments
        groupset = currentTimetable.groupset
        StudentEnrollment.objects.filter(groupset=groupset).delete()
        subjects_not_found = []

        for student in self.students:
            # json.dump(student, self.stderr)
            study_short_name, classyear = get_study_classyear(
                self.studijsko_drevo, student['id_izvajanje_studija']
            )
            izredni = student['id_nacin_studija'] == self.izredni_studij_id
            try:
                study = Study.objects.get(short_name=study_short_name)
            except:
                self.stderr.write('student {} - study {} not found:'.format(
                    student['vpisna_stevilka'], study_short_name))
                study = Study.objects.get(short_name='PAD')

            studis_enrollment_type_id = student['id_tip_vpisa']
            student_id = student['vpisna_stevilka'].strip()
            student_name = student['ime']
            student_surname = student['priimek']
            source = student.get('source', None)
            databaseStudent = Student.objects.get_or_create(studentId=student_id)[0]
            # Update name and surname if changed
            if (databaseStudent.name != student_name or
                    databaseStudent.surname != student_surname):
                databaseStudent.name = student_name
                databaseStudent.surname = student_surname
                databaseStudent.save()
            subjects_to_enroll = []
            for entry in student['predmetnik']:
                if (not entry['opravlja_vaje']) and (not entry['opravlja_predavanja']):
                    continue
                studis_subject = self.subjects.get(entry['id_predmet'], None)
                if studis_subject is None:
                    self.stdout.write('Skiping subject with id {0}'.format(entry['id_predmet']))
                    continue
                assert studis_subject['sifra'] == entry['sifra_predmeta']


                subject = Subject.objects.filter(code=studis_subject['sifra'])
                assert len(subject) <= 1, u"More than one subject\
with code {0} in database.".format(subject.code)
                if len(subject) == 0:
                    self.stderr.write("Student {} - missing subject {}".format(
                        student_id, studis_subject['sifra']))
                    if subject not in subjects_not_found:
                        subjects_not_found.append(subject)
                    continue
                subject = subject[0]
                subjects_to_enroll.append(subject)
                #subjects = currentTimetable.subjects.filter(code=subject.code)
                #if subjects.count() == 0:
                #    self.stdout.write("Subject with code {0} missing from the current timetable".format(subject))
                #    continue
            StudentEnrollment.objects.filter(groupset=groupset,
                                     student=databaseStudent).delete()
            if student_id == '63160433':
                print("here i am")
            for subject in subjects_to_enroll:
                se = StudentEnrollment(groupset=groupset,
                                  student=databaseStudent,
                                  subject=subject,
                                  source=source,
                                  enrollment_type=studis_enrollment_type_id,
                                  study=study,
                                  classyear=int(classyear),
                                  regular_enrollment=not izredni)
                                  
                se.save()
                #self.stderr.write("enroll {} on {}({}) under {}_{} -> {}".format(
                #    student_id, subject.short_name, subject.code, classyear, study, se.id))
                if student_id == '63160433':
                    print (se)
