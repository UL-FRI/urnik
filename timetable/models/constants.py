"""
Constants and choices used across the timetable models.
"""

WEEKDAYS = (
    ("MON", "ponedeljek"),
    ("TUE", "torek"),
    ("WED", "sreda"),
    ("THU", "četrtek"),
    ("FRI", "petek"),
)

WEEKDAYSSLO = dict()
for en, slo in WEEKDAYS:
    WEEKDAYSSLO[en] = slo

PREFERENCELEVELS = (
    ("WANT", "Want"),
    ("HATE", "Hate"),
    ("CANT", "Unable"),
)

WORKHOURS = (
    ("07:00", "07:00"),
    ("08:00", "08:00"),
    ("09:00", "09:00"),
    ("10:00", "10:00"),
    ("11:00", "11:00"),
    ("12:00", "12:00"),
    ("13:00", "13:00"),
    ("14:00", "14:00"),
    ("15:00", "15:00"),
    ("16:00", "16:00"),
    ("17:00", "17:00"),
    ("18:00", "18:00"),
    ("19:00", "19:00"),
    ("20:00", "20:00"),
    ("21:00", "21:00"),
)

AFTERHOURS = ("22:00", "22:00")

PEOPLEVALUEPREFERENCES = (
    ("MAXDAYSWEEK", "Max days per week"),
    ("MINDAYSWEEK", "Min days per week"),
    ("MAXHOURSDAY", "Max hours per day"),
    ("MINHOURSDAY", "Min hours per day"),
    ("MAXHOURSCONT", "Max hours continuously"),
    ("MAXSPANDAY", "Max span per day"),
    ("MAXGAPSDAY", "Max gaps per day"),
    ("MAXGAPSWEEK", "Max gaps per week"),
    ("MAXCHANGESWEEK", "Max building changes per week"),
    ("MAXCHANGESDAY", "Max building changes per day"),
    ("MINCHANGEGAP", "Min gap between changes"),
)

TAGVALUEPREFERENCES = (
    ("MAXDAYSWEEK", "Max days per week for a tag"),
    ("MINDAYSWEEK", "Min days per week for a tag"),
    ("MAXHOURSDAY", "Max hours per day for a tag"),
    ("MINHOURSDAY", "Min hours per day for a tag"),
    ("MAXSPANDAY", "Max span per day"),
    ("MAXGAPSDAY", "Max gaps per day for a tag"),
    ("MAXGAPSWEEK", "Max gaps per week for a tag"),
    ("MAXCHANGESWEEK", "Max building changes per week"),
    ("MAXCHANGESDAY", "Max building changes per day"),
    ("MINCHANGEGAP", "Min gap between changes"),
    ("MINACTIVITYGAP", "Min gap between a set of activities"),
    ("MULSIZE", "Multiply group size for activities with this tag by a factor"),
    ("SHRINKGROUPS", "Group size for activity -> Group size - VALUE"),
    (
        "MAXROOMSREALIZATIONS",
        "Maximal number of different rooms used by the set of realization",
    ),
    ("TAGMAXHOURSDAILY", "Mas hours daily for given tag for given students"),
)

PREFERENCETYPES = (
    ("COMMENT", "A random comment"),
    ("NOOVERLAP", "Must not overlap"),
    ("GROUPED", "Activities must be grouped"),
    ("CONSECUTIVE", "Realizations must be consecutive"),
    ("ENDSSTUDENTSDAY", "Activity ends student's day"),
    ("SAMEDAY", "A set of activities/realizations must be on the same day"),
    (
        "SAMESTARTINGTIME",
        "A set of activities/realizations must start on the same time (day + hour)",
    ),
)

ACTIVITYTYPES = (
    ("LAB", "Laborant vaje"),
    ("LV", "Laboratorijske vaje"),
    ("AV", "Avditorne vaje"),
    ("P", "Predavanja"),
    ("TUT", "Tutorstvo"),
    ("REP", "Repetitorij"),
)