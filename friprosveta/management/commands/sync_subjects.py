import logging

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.utils import IntegrityError

from friprosveta.models import Subject
from friprosveta.studis import Studij


class Command(BaseCommand):
    """
    Create all subjects from studis database not in ours and sync their names.
    """

    def add_arguments(self, parser):
        parser.add_argument('ok', nargs=1, type=str, help="must be 'True' to proceed")

    @transaction.atomic
    def sync_subjects(self):
        """
        Copy all subjects from studis to our database.
        Only subject name and code are copied.
        """
        logger = logging.getLogger(__name__)
        logger.info("Entering sync_subjects")

        studij = Studij(2018)
        subjects = studij.get_predmeti()
        subjects_added = dict()
        for subject in subjects:
            logger.debug("Processing subject with code {0}".format(subject["sifra"]))
            fri_subjects_count = Subject.objects.filter(
                code=subject['sifra']
            ).count()
            logger.debug("{0} matching subjects found in our database".format(fri_subjects_count))
            assert fri_subjects_count <= 1, "More than one subject \
with code {0} in our database.".format(subject['sifra'])
            if fri_subjects_count == 0:
                logger.debug("Subject not in our database, creating new one")
                subject_name = subject['naslov']['sl']
                logger.info("Created subject {1} ({0})".format(
                    subject['sifra'], subject_name))
                if subject['sifra'] in subjects_added:
                    logger.error(f"Duplicated subject code {subject['sifra']}")
                subjects_added[subject['sifra']] = Subject(code=subject['sifra'], name=subject_name)
            else:
                logger.debug("Updating subject")
                urnik_subject = Subject.objects.get(code=subject['sifra'])
                if urnik_subject.name != subject['naslov']['sl']:
                    urnik_subject.name = subject['naslov']['sl']
                    urnik_subject.save()
                    logger.debug("Updated subject {1} ({0})".format(
                        subject['sifra'], urnik_subject.name)
                    )
        for subject in subjects_added.values():
            try:
                subject.save()
            except IntegrityError:
                logger.exception(f"Error saving subject {subject}")
        logger.info("Added {0} subjects.".format(len(subjects_added)))
        return len(subjects_added)

    def handle(self, *args, **options):
        logger = logging.getLogger(__name__)
        logger.info("Starting subject sync")
        confirm = options['ok'][0]
        if confirm == "True":
            self.sync_subjects()
        else:
            print("Second argument must be 'True' to proceed")
        logger.info("Finished subjects sync")
