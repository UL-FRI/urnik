import logging
from collections import defaultdict

from django.core.management.base import BaseCommand

from friprosveta.models import Timetable
from friprosveta.studis import Najave, Studij
from timetable.models import WORKHOURS, PreferenceSet, Tag, TagTimePreference

logger = logging.getLogger("friprosveta")


class Command(BaseCommand):
    """
    Add tags to activities.
    """

    help = """Add tags to activities in the given activity set.
If activity option is specified only tags for the given activity are set.
When given preferenceset option it also creates default time preferences for added tags.
Default time preferences are hard coded into this python script.
Usage: add_activity_tags [--act=activity_id] [--pset=preferenceset_slug] [--rm_prefs] \
timetable_slug year"""

    def add_arguments(self, parser):
        parser.add_argument(
            "timetable_slug", nargs=1, type=str, help="Slug of the timetable to use"
        )
        parser.add_argument(
            "year",
            nargs=1,
            type=int,
            help="Studis year (to get information about obligatory subjects)",
        )
        parser.add_argument(
            "--act",
            nargs=1,
            action="store",
            type=int,
            dest="activity_id",
            help="Only set the tags for the activity with this id",
        ),

        parser.add_argument(
            "--pset",
            nargs=1,
            action="store",
            type=str,
            dest="preferenceset_slug",
            help="Slug of the preferenceset",
        ),

        parser.add_argument(
            "--rm_prefs",
            nargs=1,
            action="store",
            type=bool,
            default=False,
            dest="remove_old_preferences",
            help="Remove old preferences for tags. This option is only valid when option \
pset is also given, otherwise it is silently ignored.",
        ),

    def handle(self, *args, **options):
        logger.info("Entering handle")
        logger.debug("Args: {}".format(args))
        logger.debug("Options: {}".format(options))
        tt = Timetable.objects.get(slug=options["timetable_slug"][0])
        year = options["year"][0]
        activityset = tt.activityset
        logger.debug("Got activity set: {}".format(activityset))
        self.prepare()
        if options["activity_id"] is not None:
            logger.debug("Activity_id is not None")
            self.tag_activities(
                activityset.activities.get(pk=options["activity_id"][0]), year
            )
        else:
            print("Tagging all activities")
            self.tag_activities(activityset.activities.all(), year)
        if options["preferenceset_slug"] is not None:
            logger.debug("Preferenceset slug given")
            preferenceset = PreferenceSet.objects.get(
                slug=options["preferenceset_slug"][0]
            )
            logger.debug("Got ps:  {}".format(preferenceset))
            if options["remove_old_preferences"]:
                self.remove_old_preferences(preferenceset)
            self.add_default_preferences(preferenceset)
        logger.info("Exiting handle")

    def tag_activities(self, activities, year):
        logger.info("Entering tag_activities")
        logger.debug("Activities: {}".format(activities))
        tag_obligatory = Tag.objects.get(name="Predavanja - redna")
        studij = Studij(year)
        najave = Najave(year)
        # logger.debug('Tagging activities {}'.format(activities))
        for activity in activities:
            logger.debug("Processing activity {0}".format(activity))
            activity.tags.remove(*self.safe_to_delete)
            logger.debug(
                "Removing {0} from activity {1}".format(self.safe_to_delete, activity)
            )
            for (atype, min_size, max_size), tag in self.tags.items():
                if activity.type == atype and min_size <= activity.size <= max_size:
                    logger.debug("Adding tag {0} to activity {1}".format(tag, activity))
                    activity.tags.add(*tag)
            if activity.type == "P":
                try:
                    if activity.activity.subject.is_obligatory(
                        year, studij=studij, najave=najave
                    ):
                        activity.tags.add(tag_obligatory)
                except Exception:
                    pass

        logger.info("Exiting tag_activities")

    def remove_old_preferences(self, preferenceset):
        logger.info("Entering remove_old_preferences")
        logger.debug("preferenceset: {}".format(preferenceset))
        TagTimePreference.objects.filter(
            preferenceset=preferenceset,
            tag__in=self.safe_to_delete,
        ).delete()
        logger.info("Exiting remove_old_preferences")

    def add_default_preferences(self, preferenceset):
        logger.info("Entering add_default_preferences")

        def duration(start, end):
            i = WORKHOURS.index((start, start))
            j = WORKHOURS.index((end, end))
            return j - i

        level = "WANT"
        for day in self.preferences:
            logger.debug("Processing day {}".format(day))
            for tag_name, values in self.preferences[day].items():
                tag = Tag.objects.get(name=tag_name)
                logger.debug("Processing tag {}".format(tag))
                for start, end, weight in values:
                    logger.debug("Adding s: {} e: {} w: {}".format(start, end, weight))
                    preference = TagTimePreference(
                        day=day,
                        tag=tag,
                        start=start,
                        duration=duration(start, end),
                        weight=1.0 * weight / 100,
                        preferenceset=preferenceset,
                        level=level,
                    )
                    preference.save()
        logger.info("Exiting add_default_preferences")

    def prepare(self):
        self.safe_to_delete = [
            "Vaje",
            "Predavanja",
            "Predavanja - redna",
            "Predavanja 100 < x < 200",
            "Predavanja < 30",
            "Predavanja 50 < x < 100",
            "Predavanja 30 < x < 50",
            "Avditorne vaje",
            "Laboratorijske vaje",
        ]
        self.tags = {
            ("P", 0, 35): ["Predavanja", "Predavanja < 30"],
            ("P", 36, 55): ["Predavanja", "Predavanja 30 < x < 50"],
            ("P", 56, 110): ["Predavanja", "Predavanja 50 < x < 100"],
            ("P", 111, 220): ["Predavanja", "Predavanja 100 < x < 200"],
            ("P", 221, 10000): ["Predavanja"],
            ("AV", 0, 10000): ["Avditorne vaje"],
            ("LV", 0, 10000): ["Laboratorijske vaje"],
        }

        days = ["MON", "TUE", "WED", "THU", "FRI"]
        self.preferences = defaultdict(dict)
        self.preferences["MON"]["Predavanja"] = [
            ("08:00", "20:00", 100),
            # ('08:00', '16:00', 99),
        ]
        self.preferences["TUE"]["Predavanja"] = [
            ("08:00", "20:00", 100),
            # ('08:00', '16:00', 99),
        ]
        self.preferences["WED"]["Predavanja"] = [
            ("08:00", "20:00", 100),
            # ('08:00', '16:00', 99),
        ]
        self.preferences["THU"]["Predavanja"] = [
            ("08:00", "20:00", 100),
            # ('08:00', '16:00', 99),
        ]
        self.preferences["FRI"]["Predavanja"] = [
            ("08:00", "20:00", 100),
            # ('08:00', '16:00', 99),
        ]
        self.preferences["MON"]["Predavanja - redna"] = [
            ("08:00", "18:00", 100),
            # ('08:00', '14:00', 99),
        ]
        self.preferences["TUE"]["Predavanja - redna"] = [
            ("08:00", "20:00", 100),
            # ('08:00', '14:00', 99),
        ]
        self.preferences["WED"]["Predavanja - redna"] = [
            ("08:00", "19:00", 100),
            # ('08:00', '19:00', 99),
        ]
        self.preferences["THU"]["Predavanja - redna"] = [
            ("08:00", "19:00", 100),
            # ('08:00', '15:00', 99),
        ]
        self.preferences["FRI"]["Predavanja - redna"] = [
            ("08:00", "16:00", 100),
            # ('08:00', '14:00', 99),
        ]
        self.preferences["MON"]["Predavanja < 30"] = [
            ("08:00", "16:00", 100),
        ]
        self.preferences["TUE"]["Predavanja < 30"] = [
            ("08:00", "16:00", 100),
        ]
        self.preferences["WED"]["Predavanja < 30"] = [
            ("08:00", "16:00", 100),
        ]
        self.preferences["THU"]["Predavanja < 30"] = [
            ("08:00", "16:00", 100),
        ]
        self.preferences["FRI"]["Predavanja < 30"] = [
            ("08:00", "16:00", 100),
        ]
        self.preferences["MON"]["Predavanja 30 < x < 50"] = [
            ("08:00", "17:00", 100),
        ]
        self.preferences["TUE"]["Predavanja 30 < x < 50"] = [
            ("08:00", "17:00", 100),
        ]
        self.preferences["WED"]["Predavanja 30 < x < 50"] = [
            ("08:00", "17:00", 100),
        ]
        self.preferences["THU"]["Predavanja 30 < x < 50"] = [
            ("08:00", "17:00", 100),
        ]
        self.preferences["FRI"]["Predavanja 30 < x < 50"] = [
            ("08:00", "17:00", 100),
        ]
        self.preferences["MON"]["Predavanja 50 < x < 100"] = [
            ("08:00", "17:00", 100),
        ]
        self.preferences["TUE"]["Predavanja 50 < x < 100"] = [
            ("08:00", "17:00", 100),
        ]
        self.preferences["WED"]["Predavanja 50 < x < 100"] = [
            ("08:00", "17:00", 100),
        ]
        self.preferences["THU"]["Predavanja 50 < x < 100"] = [
            ("08:00", "17:00", 100),
        ]
        self.preferences["FRI"]["Predavanja 50 < x < 100"] = [
            ("08:00", "17:00", 100),
        ]
        self.preferences["MON"]["Predavanja 100 < x < 200"] = [
            ("08:00", "16:00", 100),
        ]
        self.preferences["TUE"]["Predavanja 100 < x < 200"] = [
            ("08:00", "20:00", 100),
        ]
        self.preferences["WED"]["Predavanja 100 < x < 200"] = [
            ("08:00", "17:00", 100),
        ]
        self.preferences["THU"]["Predavanja 100 < x < 200"] = [
            ("08:00", "16:00", 100),
        ]
        self.preferences["FRI"]["Predavanja 100 < x < 200"] = [
            ("08:00", "16:00", 100),
        ]
        self.preferences["MON"]["Avditorne vaje"] = [
            ("08:00", "16:00", 100),
        ]
        self.preferences["TUE"]["Avditorne vaje"] = [
            ("08:00", "16:00", 100),
        ]
        self.preferences["WED"]["Avditorne vaje"] = [
            ("08:00", "16:00", 100),
        ]
        self.preferences["THU"]["Avditorne vaje"] = [
            ("08:00", "16:00", 100),
        ]
        self.preferences["FRI"]["Avditorne vaje"] = [
            ("08:00", "16:00", 100),
        ]
        self.preferences["MON"]["Laboratorijske vaje"] = [
            ("07:00", "18:00", 100),
            # ('08:00', '16:00', 99),
        ]
        self.preferences["TUE"]["Laboratorijske vaje"] = [
            ("07:00", "18:00", 100),
            # ('08:00', '16:00', 99),
        ]
        self.preferences["WED"]["Laboratorijske vaje"] = [
            ("07:00", "18:00", 100),
            # ('08:00', '16:00', 99),
        ]
        self.preferences["THU"]["Laboratorijske vaje"] = [
            ("07:00", "18:00", 100),
            # ('08:00', '16:00', 99),
        ]
        self.preferences["FRI"]["Laboratorijske vaje"] = [
            ("07:00", "18:00", 100),
            # ('08:00', '16:00', 99),
        ]

        self.safe_to_delete = [
            Tag.objects.get(name=name) for name in self.safe_to_delete
        ]
        for k in self.tags.keys():
            self.tags[k] = [Tag.objects.get(name=name) for name in self.tags[k]]
