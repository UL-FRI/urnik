import logging

from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand

from friprosveta.management.commands.add_user import create_single_user
from friprosveta.management.commands.change_teacher_code import change_teacher_code
from friprosveta.studis import Osebe
from timetable.models import User


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument(
            '--teacher_code', nargs=1,
            action='store',
            dest='teacher_code',
            help='Only sync teacher with the given code.'),

    def sync_all_teachers(self):
        logger = logging.getLogger(__name__)
        logger.info("Starting sync")
        osebe = Osebe()
        logger.debug("Created Osebe instance")
        teachers = osebe.get_teachers()
        logger.debug("Got teachers")
        # logger.debug("{0}".format(teachers))
        teacher_codes = osebe.get_teacher_codes()
        # logger.debug("Got teacher codes")
        logger.debug("{0}".format(teacher_codes))
        for teacher in teachers:
            teacher_code = teacher['sifra_predavatelja']
            if teacher_code in teacher_codes:
                logger.info("Processing {0} {1}; {2}".format(teacher['ime'], teacher['priimek'], teacher_code))
                try:
                    logger.debug("Try to get user")
                    user = User.objects.get(
                        username__iexact=teacher['upn']
                    )
                    if user.teacher.code != teacher_code:
                        logger.debug("Changing teacher code from {0} to {1}")
                        change_teacher_code(user.teacher.code,
                                            teacher_code)

                except ObjectDoesNotExist:
                    logger.info("User with upn {0} not found "
                                "in system".format(teacher['upn']))
                    try:
                        create_single_user(first_name=teacher['ime'],
                                           last_name=teacher['priimek'],
                                           uid=teacher['upn'],
                                           teacher_code=teacher_code,
                                           write_to_db=True)
                    except Exception as e:
                        logger.exception("Exception while creating user")
            else:
                logger.error("Teacher with code {0} not found in teacher_codes".format(teacher_code))
        logger.info("Completed sync")

    def sync_single_teacher(self, teacher_code):
        logger = logging.getLogger(__name__)
        logger.info("Starting sync for teacher with code {}".format(teacher_code))
        osebe = Osebe()
        logger.debug("Created Osebe instance")
        teachers = osebe.get_teachers()
        logger.debug("Got teachers")
        teacher = [t for t in teachers if t['sifra_predavatelja'] == teacher_code]
        assert len(teacher) == 1, "No teacher with code found in Studij"
        teacher = teacher[0]
        logger.info("Processing {0} {1}; {2}".format(teacher['ime'], teacher['priimek'], teacher_code))
        try:
            logger.debug("Try to get user")
            user = User.objects.get(
                username__iexact=teacher['upn']
            )
            if user.teacher.code != teacher_code:
                logger.debug("Changing teacher code from {0} to {1}")
                change_teacher_code(user.teacher.code,
                                    teacher_code)

        except ObjectDoesNotExist:
            logger.info("User with upn {0} not found "
                        "in system".format(teacher['upn']))
            try:
                create_single_user(first_name=teacher['ime'],
                                   last_name=teacher['priimek'],
                                   uid=teacher['upn'],
                                   teacher_code=teacher_code,
                                   write_to_db=True)
            except Exception as e:
                logger.exception("Exception while creating user")
        logger.info("Completed sync")

    def handle(self, *args, **options):
        logger = logging.getLogger(__name__)
        if options['teacher_code'] is not None:
            self.sync_single_teacher(options['teacher_code'][0])
        else:
            self.sync_all_teachers()
