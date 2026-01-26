import logging
import re

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

    def _sync_person(self, person, logger):
        teacher_code = person.sifra_predavatelja
        studis_id = person.id
        if not teacher_code:
            return

        teacher = Teacher.objects.filter(studis_id=studis_id).first()
        if teacher is not None:
            if teacher.code != teacher_code:
                logger.debug("Changing teacher code from {0} to {1}")
                change_teacher_code(teacher.code, teacher_code)
            return

        teacher = Teacher.objects.filter(code=teacher_code).first()
        if teacher is not None:
            if teacher.studis_id != studis_id:
                teacher.studis_id = studis_id
                teacher.save(update_fields=["studis_id"])
            return

        if person.upn:
            try:
                user = User.objects.get(username__iexact=person.upn)
                logger.debug("Found user %s for upn %s", user.id, person.upn)
                if hasattr(user, "teacher"):
                    if user.teacher.code != teacher_code:
                        logger.debug("Changing teacher code from {0} to {1}")
                        change_teacher_code(user.teacher.code, teacher_code)
                    if user.teacher.studis_id != studis_id:
                        user.teacher.studis_id = studis_id
                        user.teacher.save(update_fields=["studis_id"])
                else:
                    logger.debug(
                        "User %s has no teacher record; creating one", user.id
                    )
                    teacher = Teacher.objects.create(
                        code=teacher_code, studis_id=studis_id, user=user
                    )
            except ObjectDoesNotExist:
                logger.info(
                    "User with upn {0} not found in system".format(person.upn)
                )
                create_single_user(
                    first_name=person.ime,
                    last_name=person.priimek,
                    uid=person.upn,
                    teacher_code=teacher_code,
                    write_to_db=True,
                )
            return

        external_code = teacher_code
        first = (person.ime or "").strip().lower()
        last = (person.priimek or "").strip().lower()
        local_part = re.sub(r"[^a-z0-9]+", "_", f"{first}_{last}").strip("_")
        username = f"{local_part}@fri1.uni-lj.si" if local_part else external_code
        logger.info(
            "Creating external teacher for {0} {1}; {2}".format(
                person.ime, person.priimek, external_code
            )
        )
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "first_name": person.ime,
                "last_name": person.priimek,
                "is_active": False,
            },
        )
        if not created and hasattr(user, "teacher") and user.teacher.code != external_code:
            change_teacher_code(user.teacher.code, external_code)
        teacher, _ = Teacher.objects.get_or_create(code=external_code)
        if teacher.studis_id != studis_id:
            teacher.studis_id = studis_id
            teacher.save(update_fields=["studis_id"])
        if teacher.user is None and not hasattr(user, "teacher"):
            teacher.user = user
            teacher.save(update_fields=["user"])

    def sync_all_teachers(self):
        logger = logging.getLogger(__name__)
        logger.info("Starting sync")
        osebe = Osebe()
        logger.debug("Created Osebe instance")
        people = osebe.get_osebe(aktiven=True)
        logger.debug("Got people")
        for person in people:
            try:
                self._sync_person(person, logger)
            except Exception:
                logger.exception("Exception while syncing teacher")
        logger.info("Completed sync")

    def sync_single_teacher(self, teacher_code):
        logger = logging.getLogger(__name__)
        logger.info("Starting sync for teacher with code {}".format(teacher_code))
        osebe = Osebe()
        logger.debug("Created Osebe instance")
        people = osebe.get_osebe(aktiven=True)
        logger.debug("Got people")
        person = [p for p in people if p.sifra_predavatelja == teacher_code]
        assert len(person) == 1, "No teacher with code found in Studij"
        try:
            self._sync_person(person[0], logger)
        except Exception:
            logger.exception("Exception while syncing teacher")
        logger.info("Completed sync")

    def handle(self, *args, **options):
        logger = logging.getLogger(__name__)
        if options["teacher_code"] is not None:
            self.sync_single_teacher(options["teacher_code"][0])
        else:
            self.sync_all_teachers()
