from django.core.management.base import BaseCommand

from friprosveta.models import StudentEnrollment, Timetable, Study, Student
from friprosveta.models import Subject
from friprosveta.studis import Sifranti, Studij, Studenti, Najave


def get_parents(studijsko_drevo, entry_id, type_=5):
    """
    The method get on dict class is used for a reason:
    if the given key does not exist, it returns None
    instead of raising an Exception.
    """
    entries = dict()
    entry = studijsko_drevo.get((entry_id, type_))
    while entry:
        entries[entry["type"]] = entry
        type_ -= 1
        entry = studijsko_drevo.get((entry.get("parent"), type_))
    return entries


def get_study_classyear(studijsko_drevo, entry_id):
    if (entry_id, 5) not in studijsko_drevo:
        print("Entry not in studijsko drevo, returning PAD")
        return "PAD", 8
    study_mapper = {"Upravna informatika": "BUN-UI", "Izmenjave": "IZMENJAVE"}
    classyear_mapper = {"B": 8, "D": 4}
    entries = get_parents(studijsko_drevo, entry_id)
    classyear = int(
        classyear_mapper.get(entries[5]["short_title"], entries[5]["short_title"])
    )

    entry2_short = study_mapper.get(
        entries[2]["short_title"].strip(), entries[2]["short_title"].strip()
    )
    try:
        print("Constructing study")
        study = "{}-{}".format(entries[1]["short_title"].strip(), entry2_short)
        print(f"Got {study}.")
        # Če imamo podatek dodaj smer
        if entries[3]["short_title"] is not None:
            study += f"-{entries[3]['short_title']}"
            print(f"Adding 'smer': {study}.")

    except Exception:
        study = "{}".format(entry2_short)
        print(f"Got exception, setting study to {study}.")

    study = study_mapper.get(study, study)
    print(f"Returning {study}, {classyear}")
    return (study, classyear)


class Command(BaseCommand):
    """
    Get StudentEnrollments from Studis
    """

    args = "import_studis_students timetable_slug year date"
    help = """Enroll students to subjects from studis using
enrollment data on the given date.
Date must be in format YYYY-MM-DD.
Year is the first part in current studijsko leto 2014/2015 -> 2014."""

    def add_arguments(self, parser):
        parser.add_argument("timetable_slug", nargs=1, type=str)
        parser.add_argument("year", nargs=1, type=str)
        parser.add_argument("date", nargs=1, type=str)
        # Unconfirmed enrollments
        parser.add_argument(
            "--unconfirmed",
            action="store_true",
            dest="unconfirmed",
            help="Process unconfirmed enrollments",
        )
        # Unfinished enrollments
        parser.add_argument(
            "--unfinished",
            action="store_true",
            dest="unfinished",
            help="Process unfinished enrollments",
        )
        # Unconfirmed enrollments
        parser.add_argument(
            "--preenrolment",
            action="store_true",
            dest="preenrolment",
            help="Process preenrollments",
        )

    def handle(self, *args, **options):
        timetable = Timetable.objects.get(slug=options["timetable_slug"][0])
        year = options["year"][0]
        date = options["date"][0]
        self.year = year
        self.stdout.write("Loading data")
        sifranti = Sifranti()
        studij = Studij(year)
        self.studij = studij
        self.najave = Najave(year)
        studenti = Studenti()

        studijsko_drevo = studij.get_studijsko_drevo()
        self.students = studenti.get_student_enrollments(
            date,
            unfinished=options["unfinished"],
            unconfirmed=options["unconfirmed"],
            preenrolment=options["preenrolment"],
        )

        self.stdout.write("got {} student enrollments".format(len(self.students)))

        import pickle

        with open("students_data.pickle", "wb") as f:
            pickle.dump(self.students, f)

        self.enrollment_types = sifranti.get_tipi_vpisa()
        self.izredni_studij_id = sifranti.get_nacini_studija_izredni_studij_id
        subjects = studij.get_predmeti()
        self.stdout.write("got {} subjects".format(len(subjects)))
        self.studis_activities = studij.get_izvajanja()
        self.stdout.write("Data loaded")
        self.subjects = {subject["id"]: subject for subject in subjects}
        self.studijsko_drevo = {(e["id"], e["type"]): e for e in studijsko_drevo}
        # self.stderr.write("{}".format(self.studijsko_drevo))
        self.padstudy = Study.objects.get(short_name="PAD")
        self.enrol_students(timetable)
        # regular_studies_subjects = self.getRegularSubjects(timetable)
        # Commented out by Gregor, not needed on UniTime
        # crossections.fixRegularSubjectsEnrollments(
        #     timetable, regular_studies_subjects, padstudy
        # )

    def enrol_students(
        self, current_timetable, enrollment_types=[1, 4, 26, 41, 42, 43, 47]
    ):
        """
        Enroll students to subjects for current timetable.
        """
        regular_enrollments = [4, 26]
        # Remove current enrollments
        groupset = current_timetable.groupset
        StudentEnrollment.objects.filter(groupset=groupset).delete()
        subjects_not_found = []
        fallback_study = Study.objects.get(short_name="PAD")

        for student in self.students:
            # json.dump(student, self.stderr)
            study_short_name, classyear = get_study_classyear(
                self.studijsko_drevo, student["id_izvajanje_studija"]
            )
            izredni = student["id_nacin_studija"] == self.izredni_studij_id
            try:
                study = Study.objects.get(short_name=study_short_name)
            except:
                self.stderr.write(
                    "student {} - study {} not found:".format(
                        student["vpisna_stevilka"], study_short_name
                    )
                )
                study = fallback_study

            studis_enrollment_type_id = student["id_tip_vpisa"]
            student_id = student["vpisna_stevilka"].strip()
            student_name = student["ime"]
            student_surname = student["priimek"]
            source = student.get("source", None)
            database_student = Student.objects.get_or_create(studentId=student_id)[0]
            # Update name and surname if changed
            if (
                database_student.name != student_name
                or database_student.surname != student_surname
            ):
                database_student.name = student_name
                database_student.surname = student_surname
                database_student.save()
            subjects_to_enroll = []
            for entry in student["predmetnik"]:
                if (not entry["opravlja_vaje"]) and (not entry["opravlja_predavanja"]):
                    if (
                        entry["opravlja_vaje"] is not None
                        and entry["opravlja_predavanja"] is not None
                    ):
                        continue
                studis_subject = self.subjects.get(entry["id_predmet"], None)
                if studis_subject is None:
                    self.stdout.write(
                        "Skiping subject with id {0}".format(entry["id_predmet"])
                    )
                    continue
                assert studis_subject["sifra"] == entry["sifra_predmeta"]

                subject = Subject.objects.filter(code=studis_subject["sifra"])
                assert (
                    len(subject) <= 1
                ), "More than one subject\
with code {0} in database.".format(
                    subject.code
                )
                if len(subject) == 0:
                    self.stderr.write(
                        "Student {} - missing subject {}".format(
                            student_id, studis_subject["sifra"]
                        )
                    )
                    if subject not in subjects_not_found:
                        subjects_not_found.append(subject)
                    continue
                subject = subject[0]
                subjects_to_enroll.append(subject)
                # subjects = currentTimetable.subjects.filter(code=subject.code)
                # if subjects.count() == 0:
                #    self.stdout.write("Subject with code {0} missing from the current timetable".format(subject))
                #    continue
            StudentEnrollment.objects.filter(
                groupset=groupset, student=database_student
            ).delete()
            for subject in subjects_to_enroll:
                classyear = int(classyear)
                study_short_name = study.short_name
                studis_studies = subject.get_studis_studies(
                    self.year, self.najave, self.studij
                )
                student_study = (classyear, study_short_name)
                if (
                    student_study not in studis_studies
                    or studis_enrollment_type_id not in regular_enrollments
                ):
                    study = self.padstudy
                    classyear = 8

                se = StudentEnrollment(
                    groupset=groupset,
                    student=database_student,
                    subject=subject,
                    source=source,
                    enrollment_type=studis_enrollment_type_id,
                    study=study,
                    classyear=int(classyear),
                    regular_enrollment=not izredni,
                )

                se.save()
