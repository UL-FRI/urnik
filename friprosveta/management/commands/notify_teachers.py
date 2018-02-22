# -*- coding: utf-8 -*-

from django.core.management.base import BaseCommand
from django.core.urlresolvers import reverse
import friprosveta.models
import smtplib

from email.mime.text import MIMEText
from email.header import Header


def sendEmail(fr, to, subject, message):
    smtp = smtplib.SMTP()
    smtp.connect("fri-postar10.fri1.uni-lj.si", 2025)
    body = MIMEText(message.encode('utf-8'), 'plain', 'utf-8')
    body['From'] = fr
    body['To'] = to
    body['Subject'] = Header(subject, 'utf-8')
    # TODO: read password and username from the config file
    smtp.login("urnik", "SECRET_PASSWORD")
    return smtp.sendmail(fr, to, body.as_string())


class Command(BaseCommand):
    '''
    Notify teachers about new timetable.
    '''
    args = 'notify_teachers timetable_slug'
    help = 'Send emails to teachers assigned to activities in new timetable.'

    def handle(self, *args, **options):
        assert len(args) == 1, u"{0}".format(args)
        timetable = friprosveta.models.Timetable.objects.get(slug=args[0])
        aset = timetable.activityset
        for teacher in timetable.teachers:
            self.notify_teacher(teacher,
                                timetable)

    def notify_teacher(self, teacher, tt):
        aset = tt.activityset
        teacher_activities = teacher.activities.filter(activityset=aset)
        subjects = u"\n".join([u"{0}".format(a) for a in teacher_activities])
        kwargs = {"timetable_set_slug": tt.timetable_sets.first().slug,
                  "preference_set_slug": tt.preferenceset.slug}
        preferences_url = "https://urnik.fri.uni-lj.si" + reverse('my_preferences', kwargs=kwargs)
        email = u"""Spoštovani!

V prihajajočem urniku "{0}" učite spodaj navedene predmete.

{1}

Prosiva, da na spletnem naslovu

{2}

najkasneje do konca tedna nastavite zahteve zanje (niso predizpolnjene).

V kolikor so zgornji podatki netočni, nama prosim to čimprej sporočite preko elektronske pošte.

Lep pozdrav in vse dobro v novem letu 2016 Vam želiva
Vaša FRI Urničarja
""".format(tt.name, subjects, preferences_url)
        try: 
            sendEmail("urnik@fri.uni-lj.si",
                  teacher.user.email,
                  "Novi urnik: {0}".format(tt.name),
                  email)
        except Exception, e:
            print e
