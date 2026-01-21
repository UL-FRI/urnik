import logging

from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

from friprosveta.management.commands.add_user import create_single_user
from friprosveta.management.commands.change_teacher_code import change_teacher_code
from friprosveta.models import Teacher
from friprosveta.studis import Osebe

User = get_user_model()


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument(
            "--teacher_code",
            nargs=1,
            action="store",
            dest="teacher_code",
            help="Only sync teacher with the given code.",
        ),

    def sync_all_teachers(self):
        logger = logging.getLogger(__name__)
        logger.info("Starting sync")
        osebe = Osebe()
        logger.debug("Created Osebe instance")
        people = osebe.get_osebe(aktiven=True)
        logger.debug("Got people")
        for person in people:
            teacher_code = person.sifra_predavatelja
            if not teacher_code or not person.upn:
                continue
            logger.info(
                "Processing {0} {1}; {2}".format(
                    person.ime, person.priimek, teacher_code
                )
            )
            try:
                logger.debug("Try to get user")
                user = User.objects.get(username__iexact=person.upn)
                logger.debug("Found user %s for upn %s", user.id, person.upn)
                if hasattr(user, "teacher") and user.teacher.code != teacher_code:
                    logger.debug("Changing teacher code from {0} to {1}")
                    change_teacher_code(user.teacher.code, teacher_code)
                elif not hasattr(user, "teacher"):
                    logger.debug("User %s has no teacher record; creating one", user.id)
                    try:
                        teacher, _ = Teacher.objects.get_or_create(code=teacher_code)
                        teacher.user = user
                        teacher.save()
                    except Exception:
                        logger.exception("Exception while creating teacher for user %s", user.id)

            except ObjectDoesNotExist:
                logger.info(
                    "User with upn {0} not found "
                    "in system".format(person.upn)
                )
                try:
                    create_single_user(
                        first_name=person.ime,
                        last_name=person.priimek,
                        uid=person.upn,
                        teacher_code=teacher_code,
                        write_to_db=True,
                    )
                except Exception as e:
                    logger.exception("Exception while creating user")
        logger.info("Completed sync")

    def sync_single_teacher(self, teacher_code):
        logger = logging.getLogger(__name__)
        logger.info("Starting sync for teacher with code {}".format(teacher_code))
        osebe = Osebe()
        logger.debug("Created Osebe instance")
        teachers = osebe.get_teachers()
        logger.debug("Got teachers")
        teacher = [t for t in teachers if t.sifra_predavatelja == teacher_code]
        assert len(teacher) == 1, "No teacher with code found in Studij"
        teacher = teacher[0]
        logger.info(
            "Processing {0} {1}; {2}".format(
                teacher.ime, teacher.priimek, teacher_code
            )
        )
        try:
            logger.debug("Try to get user")
            user = User.objects.get(username__iexact=teacher.upn)
            logger.debug("Found user %s for upn %s", user.id, teacher.upn)
            if hasattr(user, "teacher"):
                if user.teacher.code != teacher_code:
                    logger.debug("Changing teacher code from {0} to {1}")
                    change_teacher_code(user.teacher.code, teacher_code)
            else:
                logger.debug("User %s has no teacher record; creating one", user.id)
                try:
                    teacher_obj, _ = Teacher.objects.get_or_create(code=teacher_code)
                    teacher_obj.user = user
                    teacher_obj.save()
                except Exception:
                    logger.exception("Exception while creating teacher for user %s", user.id)

        except ObjectDoesNotExist:
            logger.info(
                "User with upn {0} not found " "in system".format(teacher.upn)
            )
            try:
                create_single_user(
                    first_name=teacher.ime,
                    last_name=teacher.priimek,
                    uid=teacher.upn,
                    teacher_code=teacher_code,
                    write_to_db=True,
                )
            except Exception as e:
                logger.exception("Exception while creating user")
        logger.info("Completed sync")

    def handle(self, *args, **options):
        logger = logging.getLogger(__name__)
        if options["teacher_code"] is not None:
            self.sync_single_teacher(options["teacher_code"][0])
        else:
            self.sync_all_teachers()
