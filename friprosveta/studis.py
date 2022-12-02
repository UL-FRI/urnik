import codecs
import json
from contextlib import suppress
from urllib.request import Request, urlopen, quote
from typing import Union

from django.conf import settings


def default_if_none(value, default):
    return default if value is None else value


class Studis:
    def __init__(self, cached=True):
        token = settings.STUDIS_API_TOKEN
        self.base_url = settings.STUDIS_API_BASE_URL
        self.auth = {"Content-Type": "application/json", "AUTHENTICATION_TOKEN": token}
        self.cached = cached
        self.cached_data = dict()

    def data(self, url):
        if self.cached and url in self.cached_data:
            return self.cached_data[url]
        reader = codecs.getreader("utf-8")
        req_url = self.base_url + "/" + url
        # Encode url (replace spaces with %20 etc...)
        req_url = quote(req_url, safe="/:=&?#+!$,;'@()*[]")
        request = Request(req_url, None, self.auth)
        response = urlopen(request)
        data = json.load(reader(response))
        if self.cached:
            self.cached_data[url] = data
        return data


class Sifranti(Studis):
    def get_tipi_vpisa(self):
        return self.data("/sifrantiapi/tipivpisa")

    def get_nacini_studija(self):
        study_types = self.data("/sifrantiapi/nacinistudija")
        # Vrnjeno v obliki tabele, vsak vnos ima id in title.
        # Preoblikuj v slovar.
        d = {e["id"]: e["title"] for e in study_types}
        return d

    def get_tipi_izvajanja_predmeta(self):
        return self.data("sifrantiapi/tipiizvajanjapredmeta")

    @property
    def get_nacini_studija_izredni_studij_id(self):
        nacini = self.get_nacini_studija()
        assert 22 in nacini, "ID 22 should be in sifrant (izredni)"
        assert nacini[22]["en"] == "part-time", "Critical sifrant changed!!!"
        return 22

    def get_semestri(self, year):
        return self.data("/sifrantiapi/{0}/semestri".format(year))


class Studij(Studis):
    def __init__(self, year, cached=True):
        super().__init__(cached)
        self.year = year

    def get_studijsko_drevo(self):
        drevo_url = "/studijapi/{0}/studijskodrevo".format(self.year)
        return self.data(drevo_url)

    def get_predmeti(self):
        subjects_url = "/studijapi/{0}/predmet".format(self.year)
        return self.data(subjects_url)

    def get_izvajanja(self):
        url = "/studijapi/{0}/izvajanjepredmeta".format(self.year)
        return self.data(url)


class Studenti(Studis):
    source_urls = {
        "studis_preenrolment": ("/studentiapi/" "studentpredvpis" "?date={0}"),
        "studis_unconfirmed": ("/studentiapi/" "studentcakapotrditev" "?date={0}"),
        "studis_unconfirmed_unfinished": (
            "/studentiapi/" "studentcakapotrditev" "?date={0}&tudi_neopravljeni=true"
        ),
        "studis_confirmed": ("/studentiapi/" "student" "?date={0}"),
        "studis_confirmed_unfinished": (
            "/studentiapi/" "student" "?date={0}&tudi_neopravljeni=true"
        ),
    }

    def get_pre_enrollments(self, date):
        return self.data(self.source_urls["studis_preenrolment"].format(date))

    def get_confirmed_enrollments(self, date, unfinished=True):
        if unfinished:
            return self.data(
                self.source_urls["studis_confirmed_unfinished"].format(date)
            )
        return self.data(self.source_urls["studis_confirmed"].format(date))

    def get_unconfirmed_enrollments(self, date, unfinished=True):
        if unfinished:
            return self.data(
                self.source_urls["studis_unconfirmed_unfinished"].format(date)
            )
        return self.data(self.source_urls["studis_unconfirmed"].format(date))

    def get_student_enrollments(
        self, date, unconfirmed=True, unfinished=True, preenrolment=True
    ):
        """
        Get information about student enrollments.

        When unconfirmed parameter is set to True (default), then also
        uncorfirmed and pre enrollments are considered.
        """
        chosen_sources = [
            ("studis_preenrolment", False, False, True),
            ("studis_unconfirmed", True, False, False),
            ("studis_unconfirmed_unfinished", True, True, False),
            ("studis_confirmed_unfinished", False, True, False),
            ("studis_confirmed", False, False, False),
        ]
        results = []
        for (
            source,
            only_unconfirmed,
            only_unfinished,
            only_preenrolment,
        ) in chosen_sources:
            if (
                (not unconfirmed and only_unconfirmed)
                or (not unfinished and only_unfinished)
                or (not preenrolment and only_preenrolment)
            ):
                continue

            data = self.data(self.source_urls[source].format(date))
            for enrolment in data:
                enrolment["source"] = source
                results.append(enrolment)
        return results


class Najave(Studis):
    def __init__(self, year, cached=True):
        super().__init__(cached)
        self.year = year

    def get_predmeti_cikli(self):
        url = "/najaveapi/{0}/cikli".format(self.year)
        return self.data(url)

    def get_izvajanja(self):
        url = "/studijapi/{0}/izvajanjepredmeta".format(self.year)
        return self.data(url)

    def get_rawclassyear(self, predmetnik) -> Union[str, int]:
        """Get the raw classyear from the predmetnik."""
        return predmetnik[5]["short_title"]

    def get_classyear(self, predmetnik, fallback: int = 8) -> int:
        """Get the classyear from predmetnik.

        When classyear can not be determined returnt 8.
        """
        classyear = fallback  # Fallback year when no year is set.
        with suppress(Exception):
            classyear = int(self.get_rawclassyear(predmetnik))
        return classyear

    def get_study_short_name(self, predmetnik):
        """
        Get short name from predmetnik. A predmetnik entry consists of 5 parts, the first one
        may not be present. The stages are:
        1: study name (BMA, BUN). May be missing in special cases.
        2: "smer" of the stury (RI, Izmenjave...)
        3: "podsmer"
        4: Human readable naziv.
        5: Classyear.

        {5: {'id': 16645,
        'sifra': None,
        'sifra_paul': None,
        'sifra_evs': None,
        'title': {'sl': 'Brez letnika', 'en': 'No year'},
        'short_title': 'B',
        'parent': 1321,
        'type': 5},
        4: {'id': 1321,
        'sifra': '0000',
        'sifra_paul': None,
        'sifra_evs': None,
        'title': {'sl': 'Ljubljana', 'en': 'Ljubljana'},
        'short_title': 'Courses for exchange students LJ',
        'parent': 2541,
        'type': 4},
        3: {'id': 2541,
        'sifra': None,
        'sifra_paul': None,
        'sifra_evs': None,
        'title': {'sl': 'Predmetnik za tuje študente na izmenjavi', 'en': None},
        'short_title': None,
        'parent': 1201,
        'type': 3},
        2: {'id': 1201,
        'sifra': 'Izmenjave',
        'sifra_paul': None,
        'sifra_evs': None,
        'title': {'sl': 'Predmetnik za tuje študente na izmenjavi',
        'en': 'Courses for exchange students'},
        'short_title': 'Izmenjave',
        'parent': None,
        'type': 2}}


        {5: {'id': 16573,
        'sifra': None,
        'sifra_paul': None,
        'sifra_evs': None,
        'title': {'sl': '1. letnik', 'en': '1st year'},
        'short_title': '1',
        'parent': 1401,
        'type': 5},
        4: {'id': 1401,
        'sifra': 'L102?',
        'sifra_paul': '7003024',
        'sifra_evs': '0022841',
        'title': {'sl': 'Ljubljana redni študij', 'en': 'Ljubljana full-time'},
        'short_title': 'BMA-RI-DS LJ FU',
        'parent': 2621,
        'type': 4},
        3: {'id': 2621,
        'sifra': None,
        'sifra_paul': None,
        'sifra_evs': None,
        'title': {'sl': 'Podatkovne vede', 'en': 'Data Science'},
        'short_title': 'PV',
        'parent': 1071,
        'type': 3},
        2: {'id': 1071,
        'sifra': 'L1',
        'sifra_paul': '1000471',
        'sifra_evs': '0000920',
        'title': {'sl': 'Računalništvo in informatika',
        'en': 'MASTER STUDY PROGRAM COMPUTER AND INFORMATION SCIENCE, LEVEL 2'},
        'short_title': 'RI',
        'parent': 37,
        'type': 2},
        1: {'id': 37,
        'sifra': 'L',
        'sifra_paul': None,
        'sifra_evs': None,
        'title': {'sl': 'druga stopnja: magistrski', 'en': None},
        'short_title': 'BMA',
        'parent': None,
        'type': 1}}


        """
        study_mapper = {"Upravna informatika": "BUN-UI", "Izmenjave": "IZMENJAVE"}
        fallback_study = "PAD"

        if predmetnik[2]["short_title"] in study_mapper:
            return study_mapper[predmetnik[2]["short_title"]]

        try:
            study = "{}-{}".format(
                predmetnik[1]["short_title"].strip(), predmetnik[2]["short_title"]
            )
            # Če imamo podatek dodaj smer
            if predmetnik[3]["short_title"] is not None:
                study += f"-{predmetnik[3]['short_title']}"
        except Exception:
            study = fallback_study
        return study

    def get_predmetnik(self, izvajanje, studijsko_drevo):
        """Return entire predmetnik for given izvajanje."""
        ret = dict()
        e = self.get_studijsko_drevo_entry(izvajanje["predmetnik"], 5, studijsko_drevo)
        while e["parent"] is not None:
            ret[e["type"]] = e
            e = self.get_studijsko_drevo_entry(
                e["parent"], e["type"] - 1, studijsko_drevo
            )
        ret[e["type"]] = e
        return ret

    def get_studijsko_drevo_entry(self, predmetnik_id, level, studijsko_drevo):
        """
        Return entry in studijsko drevo from predmetnik (in izvajanja).
        :param predmetnik_id:
        :param level: entry named "type" in studijsko drevo. Initial entry has type 5.
        :param studijsko_drevo:
        :return: entry in studijsko drevo with the given id. Exception is thrown
        if entry is not found.
        """
        entry = [
            e
            for e in studijsko_drevo
            if str(e["id"]) == str(predmetnik_id) and e["type"] == level
        ]
        assert len(entry) == 1, "No entries found"
        return entry[0]

    def get_izvajanja_ids(self):
        izvajanja_ids = set()
        for izvajanje in self.get_izvajanja():
            izvajanja_ids.add(izvajanje["id"].split("-")[1].strip())
        return izvajanja_ids

    def check_izvajanje(self, izvajanje, tt):
        """
        Check whether izvajanje for given subject is in sync with studis data.
        We check whether:
        - right types of activites for the subject are present
        - the duration is OK
        :param izvajanje: one studis izvajanje
        :param tt:
        :return:
        """

        def none_or_zero(value):
            return value is None or value == 0

        subject_code = izvajanje["sifra_predmeta"]
        subject = tt.subjects.get(code=subject_code)
        types = dict()
        if not none_or_zero(izvajanje["st_ur_avd_vaj"]):
            duration = int(izvajanje["st_ur_avd_vaj"])
            assert (
                duration % 15 == 0
            ), "Error processing AV for subject {} ({}), izvajanje {}".format(
                izvajanje, subject, subject.code
            )
            types["AV"] = duration / 15
        if not none_or_zero(izvajanje["st_ur_lab_vaj"]):
            duration = int(izvajanje["st_ur_lab_vaj"])
            if not none_or_zero(izvajanje["st_ur_seminarja"]):
                duration += int(izvajanje["st_ur_seminarja"])
            assert (
                duration % 15 == 0
            ), "Error processing LV for subject {} ({}), izvajanje {}".format(
                izvajanje, subject, subject.code
            )
            types["LV"] = duration / 15
        if not none_or_zero(izvajanje["st_ur_predavanj"]):
            duration = int(izvajanje["st_ur_predavanj"])
            assert (
                duration % 15 == 0
            ), "Error processing P for subject {} ({}), izvajanje {}".format(
                izvajanje, subject, subject.code
            )
            types["P"] = duration / 15
        for studis_lecture_type, studis_duration in types.items():
            activities = tt.activities.filter(subject=subject, type=studis_lecture_type)
            assert activities.count() > 0, "No activity of type {} for {}(){}".format(
                studis_lecture_type, subject, subject.code
            )
            duration = sum(a.duration for a in activities)
            assert duration == studis_duration, "Durations from studis and tt differ"
        return True


class Oseba:
    def __init__(self, data, osebe):
        """
        Construct instance of class Oseba with data from dictionary.
        Beware: not every string is a valid variable name, use with caution.
        """
        self.osebe = osebe
        self.__dict__.update(data)

    @property
    def is_teacher(self):
        return self.osebe.is_teacher(self)


class Osebe(Studis):
    def __init__(self):
        super().__init__()
        teacher_titles = [
            "asistent",
            "asistent-raziskovalec",
            "izredni profesor",
            "docent",
            "predavatelj",
            "redni profesor",
            "strokovni sodelavec",
            "višji predavatelj",
        ]
        self.teacher_titles_ids = set(
            [
                title["id"]
                for title in self.get_nazivi()
                if title["full_title"]["sl"] in teacher_titles
            ]
        )

    def get_nazivi(self):
        return self.data("/sifrantiapi/nazivdelavca")

    def get_osebe(self, aktiven=False):
        """
        Return info about all persons in studis.
        If parameter aktiven is True it returns only persons with aktiven status set to True,
        otherwise it returns all persons.
        """
        url = "/osebeapi/oseba"
        if not aktiven:
            url += "?aktiven=false"
        return [Oseba(person_data, self) for person_data in self.data(url)]

    def is_teacher(self, oseba):
        """
        Is given person a teacher? (ali ima veljavno habilitacijo)
        """
        return len(set(oseba.habilitacija) & self.teacher_titles_ids) > 0

    def get_teachers(self):
        """
        Return all persons with valid habilitation.
        """
        return [
            teacher
            for teacher in self.get_osebe()
            if teacher.status_prikazan and teacher.is_teacher
        ]

    def get_teacher_details(self, teacher_code):
        """
        Return data for a teacher with the given code. Only data for the given teacher is fetched from Studis.
        :param teacher_code: code of the teacher.
        :return: class Oseba when teacher exists or None.
        """
        url = "/osebeapi/oseba?$filter=sifra_predavatelja eq '{}'".format(teacher_code)
        teacher = [Oseba(person_data) for person_data in self.data(url)]
        assert (
            len(teacher) <= 1
        ), "At most one teacher with code {} should exist in Studij".format(
            teacher_code
        )
        return teacher[0] if teacher else None

    def get_teacher_codes(self):
        return [teacher.sifra_predavatelja for teacher in self.get_teachers()]
