from .settings_common import *

DEBUG = True

ADMINS = (("username", "email@email.si"),)

MANAGERS = ADMINS

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql_psycopg2",
        "NAME": "timetable",  # Or path to database file if using sqlite3.
        "USER": "timetable",  # Not used with sqlite3.
        "PASSWORD": "database_password",  # Not used with sqlite3.
        "HOST": "127.0.0.1",  # Set to empty string for localhost. Not used with sqlite3.
        "PORT": "",  # Set to empty string for default. Not used with sqlite3.
    },
    "unitime": {
        "NAME": "timetable",
        "ENGINE": "django.db.backends.mysql",
        "USER": "unitime",
        "PASSWORD": "unitime",
    },
}

DATABASE_ROUTERS = [
    "urnik_fri.database_routers.UrnikRouter",
]

UNITIME_DB_USER = "unitime"
UNITIME_DB_PASSWORD = "database_password"
UNITIME_DB_HOST = "localhost"
UNITIME_DB_NAME = "timetable"

# Make this unique, and don't share it with anybody.
SECRET_KEY = "my_very_secret_key"


# ldap settings
# import ldap
# from django_auth_ldap.config import LDAPSearch, GroupOfNamesType
# from friprosveta.ul_groupname import ULNestedGroupOfNamesType

# AUTH_LDAP_SERVER_URI = "ldap://ldap_server"

# AUTH_LDAP_BIND_DN = "CN=..."
# AUTH_LDAP_BIND_PASSWORD = "geslo_za_ldap"
# AUTH_LDAP_USER_SEARCH = LDAPSearch("DC",
#    ldap.SCOPE_SUBTREE, "(userPrincipalName=%(user)s)")

# Mirror groups in LDAP
# AUTH_LDAP_GROUP_SEARCH = LDAPSearch("DC=...",
#    ldap.SCOPE_SUBTREE, "(objectClass=group)"
# )
# AUTH_LDAP_GROUP_TYPE = ULNestedGroupOfNamesType(name_attr="cn")
# AUTH_LDAP_MIRROR_GROUPS = True

# Populate the Django user from the LDAP directory.
# AUTH_LDAP_USER_ATTR_MAP = {
#    "first_name": "givenName",
#    "last_name": "sn",
#    "email": "mail"
# }

# AUTH_LDAP_USER_FLAGS_BY_GROUP = {
#    "is_active": "cn=active,ou=django,ou=groups,dc=example,dc=com",
#    "is_staff": "cn=staff,ou=django,ou=groups,dc=example,dc=com",
#    "is_superuser": "cn=superuser,ou=django,ou=groups,dc=example,dc=com"
# }

# This is the default, but I like to be explicit.
# AUTH_LDAP_ALWAYS_UPDATE_USER = True

# Cache group memberships for an hour to minimize LDAP traffic
# AUTH_LDAP_CACHE_GROUPS = True
# AUTH_LDAP_GROUP_CACHE_TIMEOUT = 3600


# Email settings
EMAIL_HOST = "mail.host.example"
EMAIL_PORT = 25
EMAIL_HOST_USER = "mail_user"
EMAIL_HOST_PASSWORD = "mail_user_password"
EMAIL_USE_TLS = True

# Absolute path to the directory that holds media.
# Example: "/home/media/media.lawrence.com/"
STATIC_ROOT = "/path/to/static/files"

MEDIA_ROOT = "/path/to/media/files"

# Studis API setting
STUDIS_API_BASE_URL = "https://studis.api/base_url"
STUDIS_API_TOKEN = "my_secret_token"


LOGGING = {
    "version": 1,
    "disable_existing_loggers": True,
    "formatters": {
        "verbose": {
            "format": "%(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s"
        },
        "simple": {"format": "%(levelname)s %(message)s"},
    },
    "handlers": {
        "null": {
            "level": "DEBUG",
            "class": "logging.NullHandler",
        },
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
        "file": {
            "level": "DEBUG",
            "class": "logging.FileHandler",
            "filename": "/home/gregor/personal/urnik/debug.log",
            "formatter": "verbose",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["null"],
            "propagate": True,
            "level": "INFO",
        },
        "friprosveta": {
            "handlers": ["console", "file"],
            "level": "INFO",
        },
        "friprosveta": {
            "handlers": ["file"],
            "level": "DEBUG",
        },
    },
}

TEST_RUNNER = "django.test.runner.DiscoverRunner"

# whether to use the studis api (production) or a best-effort solution
STUDENT_MAPPER_PRODUCTION = False
