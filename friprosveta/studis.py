import codecs
import json
from urllib.request import Request, urlopen, quote

from django.conf import settings


def default_if_none(value, default):
    return default if value is None else value


class Studis:
    def __init__(self, cached=True):
        token = settings.STUDIS_API_TOKEN
        self.base_url = settings.STUDIS_API_BASE_URL
        self.auth = {'Content-Type': 'application/json',
                     'AUTHENTICATION_TOKEN': token}
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
        return self.data('/sifrantiapi/tipivpisa')

    def get_nacini_studija(self):
        study_types = self.data('/sifrantiapi/nacinistudija')
        # Vrnjeno v obliki tabele, vsak vnos ima id in title.
        # Preoblikuj v slovar.
        d = {e['id']: e['title'] for e in study_types}
        return d

    def get_tipi_izvajanja_predmeta(self):
        return self.data('sifrantiapi/tipiizvajanjapredmeta')

    @property
    def get_nacini_studija_izredni_studij_id(self):
        nacini = self.get_nacini_studija()
        assert 22 in nacini, 'ID 22 should be in sifrant (izredni)'
        assert nacini[22]['en'] == 'part-time', 'Critical sifrant changed!!!'
        return 22

    def get_semestri(self, year):
        return self.data('{0}/sifrantiapi/semestri'.format(year))


class Studij(Studis):
    def __init__(self, year, cached=True):
        super().__init__(cached)
        self.year = year

    def get_studijsko_drevo(self):
        drevo_url = '/studijapi/{0}/studijskodrevo'.format(self.year)
        return self.data(drevo_url)

    def get_predmeti(self):
        subjects_url = '/studijapi/{0}/predmet'.format(self.year)
        return self.data(subjects_url)

    def get_izvajanja(self):
        url = '/studijapi/{0}/izvajanjepredmeta'.format(self.year)
        return self.data(url)


class Studenti(Studis):
    source_urls = {
        'studis_preenrolment': (
            '/studentiapi/'
            'studentpredvpis'
            '?date={0}'),
        'studis_unconfirmed': (
            '/studentiapi/'
            'studentcakapotrditev'
            '?date={0}'),
        'studis_unconfirmed_unfinished': (
            '/studentiapi/'
            'studentcakapotrditev'
            '?date={0}&tudi_neopravljeni=true'),
        'studis_confirmed': (
            '/studentiapi/'
            'student'
            '?date={0}'),
        'studis_confirmed_unfinished': (
            '/studentiapi/'
            'student'
            '?date={0}&tudi_neopravljeni=true')
    }

    def get_pre_enrollments(self, date):
        return self.data(self.source_urls['studis_preenrolment'].format(date))

    def get_confirmed_enrollments(self, date, unfinished=True):
        if unfinished:
            return self.data(self.source_urls['studis_confirmed_unfinished'].format(date))
        return self.data(self.source_urls['studis_confirmed'].format(date))

    def get_unconfirmed_enrollments(self, date, unfinished=True):
        if unfinished:
            return self.data(self.source_urls['studis_unconfirmed_unfinished'].format(date))
        return self.data(self.source_urls['studis_unconfirmed'].format(date))

    def get_student_enrollments(self, date, unconfirmed=True, unfinished=True, preenrolment=True):
        """
        Get information about student enrollments.

        When unconfirmed parameter is set to True (default), then also
        uncorfirmed and pre enrollments are considered.
        """
        chosen_sources = [
            ('studis_preenrolment', False, False, True),
            ('studis_unconfirmed', True, False, False),
            ('studis_unconfirmed_unfinished', True, True, False),
            ('studis_confirmed_unfinished', False, True, False),
            ('studis_confirmed', False, False, False),
        ]
        results = []
        for source, only_unconfirmed, only_unfinished, only_preenrolment in chosen_sources:
            if (not unconfirmed and only_unconfirmed) or \
                    (not unfinished and only_unfinished) or \
                    (not preenrolment and only_preenrolment): continue

            data = self.data(self.source_urls[source].format(date))
            for enrolment in data:
                enrolment['source'] = source
                results.append(enrolment)
        return results


class Najave(Studis):
    def __init__(self, year, cached=True):
        super().__init__(cached)
        self.year = year

    def get_predmeti_cikli(self):
        url = '/najaveapi/{0}/cikli'.format(self.year)
        return self.data(url)

    def get_izvajanja(self):
        url = '/studijapi/{0}/izvajanjepredmeta'.format(self.year)
        return self.data(url)

    def get_classyear(self, predmetnik):
        return int(predmetnik[5]["short_title"])

    def get_study_short_name(self, predmetnik):
        short_name = "{0}-{1}".format(predmetnik[1]['short_title'], predmetnik[2]['short_title'])
        return short_name

    def get_predmetnik(self, izvajanje, studijsko_drevo):
        """Return entire predmetnik for given izvajanje."""
        ret = dict()
        print(izvajanje['predmetnik'])
        print(studijsko_drevo)
        e = self.get_studijsko_drevo_entry(izvajanje['predmetnik'], studijsko_drevo)
        while e["parent"] is not None:
            ret[e["type"]] = e
            e = self.get_studijsko_drevo_entry(e['parent'], studijsko_drevo)
        ret[e["type"]] = e
        return ret

    def get_studijsko_drevo_entry(self, predmetnik_id, studijsko_drevo):
        """
        Return entry in studijsko drevo from predmetnik (in izvajanja).
        :param predmetnik_id:
        :param studijsko_drevo:
        :return: entry in studijsko drevo with the given id. Exception is thrown
        if entry is not found.
        """
        entry = [e for e in studijsko_drevo if str(e["id"]) == str(predmetnik_id)]
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

        subject_code = izvajanje['sifra_predmeta']
        subject = tt.subjects.get(code=subject_code)
        types = dict()
        if not none_or_zero(izvajanje['st_ur_avd_vaj']):
            duration = int(izvajanje['st_ur_avd_vaj'])
            assert duration % 15 == 0, "Error processing AV for subject {} ({}), izvajanje {}".format(
                izvajanje, subject, subject.code)
            types['AV'] = duration / 15
        if not none_or_zero(izvajanje['st_ur_lab_vaj']):
            duration = int(izvajanje['st_ur_lab_vaj'])
            if not none_or_zero(izvajanje['st_ur_seminarja']):
                duration += int(izvajanje['st_ur_seminarja'])
            assert duration % 15 == 0, "Error processing LV for subject {} ({}), izvajanje {}".format(
                izvajanje, subject, subject.code)
            types['LV'] = duration / 15
        if not none_or_zero(izvajanje['st_ur_predavanj']):
            duration = int(izvajanje['st_ur_predavanj'])
            assert duration % 15 == 0, "Error processing P for subject {} ({}), izvajanje {}".format(
                izvajanje, subject, subject.code)
            types['P'] = duration / 15
        for studis_lecture_type, studis_duration in types.items():
            activities = tt.activities.filter(subject=subject, type=studis_lecture_type)
            assert activities.count() > 0, "No activity of type {} for {}(){}".format(
                studis_lecture_type, subject, subject.code
            )
            duration = sum(a.duration for a in activities)
            assert duration == studis_duration, "Durations from studis and tt differ"
        return True


class Osebe(Studis):
    def get_nazivi(self):
        return self.data('/sifrantiapi/nazivdelavca')

    def get_osebe(self):
        return self.data('/osebeapi/oseba?aktiven=false')

    def get_teachers(self):
        osebe = self.get_osebe()
        teachers = [teacher for teacher in osebe
                    if teacher['status_prikazan'] != 0]
        return teachers

    def get_teacher_details(self, teacher_code):
        """
        Return data for a teacher with the given code.
        :param teacher_code:
        :return: dictionary obtained from Studis.
        """
        url = ("/osebeapi/oseba?$filter=sifra_predavatelja eq '{}'".format(teacher_code))
        # url = "osebeapi/oseba?$filter=sifra_predavatelja%20eq%20%27000014%27"
        # print(url)
        teacher = self.data(url)
        assert len(teacher) <= 1, "At most one teacher with code {} should exist in Studij".format(teacher_code)
        return teacher

    def get_teacher_codes(self):
        teacher_titles = ['asistent', 'asistent-raziskovalec',
                          'izredni profesor', 'docent', 'predavatelj',
                          'redni profesor', 'strokovni sodelavec',
                          'višji predavatelj']

        teacher_titles_ids = set([title['id'] for title in self.get_nazivi()
                                  if title['full_title']['sl'] in teacher_titles])

        teacher_codes = [teacher['sifra_predavatelja']
                         for teacher in self.get_teachers()
                         if len(set(teacher['habilitacija']) & teacher_titles_ids) > 0]
        return teacher_codes
