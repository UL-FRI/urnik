import MySQLdb
from django.conf import settings
from timetable.models import WORKHOURS


# Convert day and duration in start index
def to_start_index(day, start):
    day_start = (24 * 12) * index_days[day]  # 12 5 minut slots per hour
    hour_start = int(start[:2]) * 12  # 12 slots per hour
    return day_start + hour_start


class PreferenceLevel:
    (
        Required,
        StronglyPreferred,
        Preferred,
        Neutral,
        Discouraged,
        StronglyDiscouraged,
        Prohibited,
    ) = ("R", "0", "1", "2", "3", "4", "P")


index_days = {"MON": 0, "TUE": 1, "WED": 2, "THU": 3, "FRI": 4}
allocation_days = {
    "MON": 64,
    "TUE": 32,
    "WED": 16,
    "THU": 8,
    "FRI": 4,
    "SAT": 2,
    "SUN": 1,
}
day_mapping = {k: v for v, k in allocation_days.items()}

itype_type_mapping = {10: "P", 30: "LV", 20: "AV"}
type_itype_mapping = {v: k for k, v in itype_type_mapping.items()}

level_to_type = {
    "WANT": (PreferenceLevel.StronglyPreferred, PreferenceLevel.Preferred),
    "HATE": (PreferenceLevel.StronglyDiscouraged, PreferenceLevel.Discouraged),
    "CANT": (PreferenceLevel.Prohibited, PreferenceLevel.Prohibited),
}

campus = "UL FRI"
term = "Zimski semester"
year = "2021"


class Database:
    options = {
        "user": settings.UNITIME_DB_USER,
        "passwd": settings.UNITIME_DB_PASSWORD,
        "db": settings.UNITIME_DB_NAME,
        "charset": "utf8",
        "use_unicode": True,
        "port": 3306,
        "host": settings.UNITIME_DB_HOST,
    }

    def __init__(self):
        self.connection = MySQLdb.connect(**self.options)
        self.cursor = self.connection.cursor()
        self.low = 0
        self.high = 0
        self.current_id = 0

    def execute(self, query):
        return self.cursor.execute(query)

    @property
    def rowcount(self):
        return self.cursor.rowcount

    def commit(self):
        return self.connection.commit()

    def close(self):
        self.commit()
        return self.connection.close()

    def fetch_all_rows(self):
        return self.cursor.fetchall()

    def fetch_next_row(self):
        return self.cursor.fetchone()

    def get_id_range(self):
        """
        Accepts cursor to the database.
        Returns (start_range, end_range) of reserved ids.
        """
        db = MySQLdb.connect(**self.options)
        c = db.cursor()
        high_query = "SELECT next_hi FROM hibernate_unique_key"
        c.execute(high_query)
        assert (
            c.rowcount == 1
        ), "There must be exactly one \
high value in the database"
        high = c.fetchone()[0]
        lo = 32767
        sql = "UPDATE timetable.hibernate_unique_key SET next_hi={0}".format(high + 1)
        c.execute(sql)
        db.commit()
        db.close()
        return high * lo + 1, (high + 1) * lo - 1

    def get_next_id(self):
        if self.current_id >= self.high:
            self.low, self.high = self.get_id_range()
            self.current_id = self.low
        self.current_id += 1
        return self.current_id - 1

    def get_session_id(self, start_date):
        session_id_query = (
            "SELECT uniqueid FROM sessions " "where session_begin_date_time ='{0}'"
        ).format(start_date)
        self.cursor.execute(session_id_query)
        assert (
            self.rowcount == 1
        ), "There must be exactly one session with the given start in the database"
        return self.fetch_next_row()[0]
