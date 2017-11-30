from django.conf import settings
from urllib.request import Request, urlopen
import json
from timetable.models import Group


def get_group_name(predmetnik_id, predmetnik):
    """Return the group name for given predmetnik entry.
    Predmetnik is retrieved from studis api on URL
    ~/api/studijapi/studijskodrevo by get_predmetnik.
    """
    if predmetnik_id not in predmetnik:
        return None
    entry = predmetnik[predmetnik_id]
    assert entry['type'] == 5
    class_year = entry['short_title']
    entry1 = predmetnik[entry['parent']]
    entry2 = predmetnik[entry1['parent']]
    entry3 = predmetnik[entry2['parent']]
    # entry4 = predmetnik[entry3['parent']]
    study_short_name = entry3['short_title']
    study_name = entry3['title']['sl']
    group_name = u'{0}. letnik, {1}'.format(class_year, study_name)
    group_short_name = u'{0}_{1}'.format(class_year, study_short_name)
    return (group_name, group_short_name)


def subject_groups(subject_code, izvajanja, predmetnik, tt):
    """Return groups attending a subject with a given code.
    Izvajanja are retrieved from studis api on URL
    ~/api/studijapi/izvajanjepredmeta .
    Predmeti are retrieved from studis api on URL
    ~/api/studijapi/predmet
    Predmetnik is retrieved from studis api on URL
    ~/api/studijapi/studijskodrevo
    """
    subject_code = str(subject_code)
    if subject_code not in izvajanja:
        return []
    izvajanja = izvajanja[subject_code]
    groups = []
    for izvajanje in izvajanja:
        predmetnik_entry = izvajanje['predmetnik']
        if predmetnik_entry not in predmetnik:
            continue
        names = get_group_name(predmetnik_entry, predmetnik)
        if names is None:
            continue
        name, short_name = names
        group, _ = Group.objects.get_or_create(
                    name=name,
                    short_name=short_name,
                    size=0,
                    parent=None,
                    groupset=tt.groupset)
        groups.append(group)
    return groups


def assign_groups(izvajanja, predmetnik, tt):
    """Assign groups to all subjects in the timetable"""
    for subject in tt.subjects.all():
        groups = subject_groups(subject.code,
                                izvajanja,
                                predmetnik,
                                tt)
        for activity in tt.activities.filter(subject=subject):
            activity.groups.add(*groups)
            for realization in activity.realizations.all():
                realization.groups.add(*groups)


def get_predmetnik(year):
    token = settings.STUDIS_API_TOKEN
    base_url = settings.STUDIS_API_BASE_URL
    auth = {'Content-Type': 'application/json',
            'AUTHENTICATION_TOKEN': token}
    url = '{0}/studijapi/{1}/studijskodrevo'.format(base_url, year)
    req = Request(url, None, auth)
    response = urlopen(req)
    drevo = json.loads(response.read().decode('utf-8'))
    return {e['id']: e for e in drevo}


def get_predmeti(year):
    token = settings.STUDIS_API_TOKEN
    base_url = settings.STUDIS_API_BASE_URL
    auth = {'Content-Type': 'application/json',
            'AUTHENTICATION_TOKEN': token}

    url = '{0}/studijapi/{1}/predmet'.format(base_url, year)
    req = Request(url, None, auth)
    response = urlopen(req)
    predmeti = json.loads(response.read().decode('utf-8'))
    return {p['sifra']: p for p in predmeti}


def get_izvajanja(year):
    token = settings.STUDIS_API_TOKEN
    base_url = settings.STUDIS_API_BASE_URL
    auth = {'Content-Type': 'application/json',
            'AUTHENTICATION_TOKEN': token}

    url = '{0}/studijapi/{1}/izvajanjepredmeta'.format(base_url, year)
    req = Request(url, None, auth)
    response = urlopen(req)
    izvajanja = json.loads(response.read().decode('utf-8'))
    ret = dict()
    for izvajanje in izvajanja:
        subject_code = izvajanje['sifra_predmeta']
        if subject_code not in ret:
            ret[subject_code] = []
        ret[subject_code].append(izvajanje)
    return ret


def print_entry(key, ddict):
    e = ddict[key]
    if e['parent'] is not None:
        print_entry(e['parent'], ddict)                                                                                                                                                                    
    print(e)
    