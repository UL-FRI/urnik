'''
Created on 10. jan. 2013

@author: gregor
'''
from frinajave.models import TeacherSubjectCycles
import friprosveta
import logging


from django.core.management.base import BaseCommand
from django.db import transaction


@transaction.atomic
def change_teacher_code(old_code, new_code):
    '''
    Change teacher code.
    Returns True on success, False on failure (no techer with given old_code found).
    '''
    logger = logging.getLogger(__name__)
    logger.info("Changing teacher code")
    logger.debug("Old: {0}, new: {1}".format(old_code, new_code))
    try:
        teacher = friprosveta.models.Teacher.objects.get(code=old_code)
        logger.debug("Got teacher")
        teacher.code = new_code
        teacher.save()
        logger.debug("Teacher code on teacher object changed")
        for entry in TeacherSubjectCycles.objects.filter(teacher_code=old_code):
            entry.teacher_code = new_code
            entry.save()
        logger.debug("Teacher code in najave changed")
        logger.info("Changed teacher code")
        return True
    except Exception:
        logger.exception("Exception while changing code")
        return False

class Command(BaseCommand):
    '''
    Enrol students into a given timetable.
    '''

    args = 'change_teacher_code old_code new_code'
    help = 'Change teacher code.'

    def handle(self, *args, **options):
        if len(args) != 2:
            print("See help")
            return

        change_teacher_code(args[0], args[1])


