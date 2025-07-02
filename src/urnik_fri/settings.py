# Django settings for urnik project.
import ldap
from django_auth_ldap.config import LDAPSearch, GroupOfNamesType
from friprosveta.ul_groupname import ULNestedGroupOfNamesType
from django.utils.translation import gettext_lazy as _
from urnik_fri.settings_common import *

# DEBUG = False
DEBUG = True


#--- UNITIME settings ------
UNITIME_DB_USER = "timetable"
UNITIME_DB_PASSWORD = "unitime"
UNITIME_DB_NAME = "timetable"
UNITIME_DB_HOST = "127.0.0.1"
# -------------------------


ADMINS = (  
    ('polz', 'polz@fri.uni-lj.si'),
    ('gregor', 'gregor.jerse@fri.uni-lj.si'),
    ('gasperfele@fri1.uni-lj.si', 'polz@fri.uni-lj.si'),
    # ('Your Name', 'your_email@domain.com'),
)
MANAGERS = ADMINS

# AUTHENTICATION_BACKENDS = (
#     'guardian.backends.ObjectPermissionBackend',
#     'django.contrib.auth.backends.ModelBackend', # this is default
# )

#-----------------------------------------
# Email settings
#-----------------------------------------
EMAIL_HOST = 'mail-fri.fri1.uni-lj.si'
EMAIL_PORT = 2025
EMAIL_HOST_USER = 'urnik'
EMAIL_HOST_PASSWORD = 'pogreglz'
EMAIL_USE_TLS = True 


#-----------------------------------------
# Database settings
#-----------------------------------------
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2', # Add 'postgresql_psycopg2', 'postgresql', 'mysql', 'sqlite3' or 'oracle'.
        'NAME': 'timetable',                      # Or path to database file if using sqlite3.
        'USER': 'timetable',                      # Not used with sqlite3.
        'PASSWORD': 'qOvpzZODQ4n55JKRyRU16PJBEeUde1uK',                 # Not used with sqlite3.
        'HOST': 'simargl.jerse.info',                      # Set to empty string for localhost. Not used with sqlite3.
        'PORT': '',                      # Set to empty string for default. Not used with sqlite3.
    },
}


#-----------------------------------------
# Django secret key
# Make this unique, and don't share it with anybody.
#-----------------------------------------
SECRET_KEY = '!hrtnx694h(n=+%90h-%$^q7jg_-67(@cg^civ%z=-sv1pl(t#'


#-----------------------------------------
# LDAP settings
#-----------------------------------------
# AUTH_LDAP_SERVER_URI = "ldaps://[2001:1470:fffd:ff90::ad1]:3269"
AUTH_LDAP_SERVER_URI = "ldaps://dcv1fri1.fri1.uni-lj.si:3269"
AUTH_LDAP_BIND_DN = "CN=ldapp,OU=System;OU=admin;DC=fri1;DC=uni-lj;DC=si"
AUTH_LDAP_BIND_PASSWORD = "Fu3[EBu`P'JHNuktV]3cNVRN"
AUTH_LDAP_USER_SEARCH = LDAPSearch(
    "DC=uni-lj,DC=si",
    ldap.SCOPE_SUBTREE, "(userPrincipalName=%(user)s)")
# Mirror groups in LDAP
AUTH_LDAP_GROUP_SEARCH = LDAPSearch(
    "DC=uni-lj,DC=si",
    ldap.SCOPE_SUBTREE, "(objectClass=group)"
)
AUTH_LDAP_GROUP_TYPE = ULNestedGroupOfNamesType(name_attr="cn")
AUTH_LDAP_MIRROR_GROUPS = True
# Only users in this group can log in.
# AUTH_LDAP_REQUIRE_GROUP = "cn=enabled,ou=django,ou=groups,dc=example,dc=com"
# Populate the Django user from the LDAP directory.
AUTH_LDAP_USER_ATTR_MAP = {
    "first_name": "givenName",
    "last_name": "sn",
    "email": "mail"
}
# AUTH_LDAP_PROFILE_ATTR_MAP = {
#     "employee_number": "employeeNumber"
# }

AUTH_LDAP_USER_FLAGS_BY_GROUP = {
#    "is_active": "cn=active,ou=django,ou=groups,dc=example,dc=com",
#    "is_staff": "cn=staff,ou=django,ou=groups,dc=example,dc=com",
#    "is_superuser": "cn=superuser,ou=django,ou=groups,dc=example,dc=com"
}

# This is the default, but I like to be explicit.
AUTH_LDAP_ALWAYS_UPDATE_USER = True
# Use LDAP group membership to calculate group permissions.
#AUTH_LDAP_FIND_GROUP_PERMS = True
# Cache group memberships for an hour to minimize LDAP traffic
AUTH_LDAP_CACHE_GROUPS = True
AUTH_LDAP_GROUP_CACHE_TIMEOUT = 3600

# -----------------------------------
# Timplate settings
# Make sure Debug is False
# -----------------------------------
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            'templates',
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'debug': False,
            'context_processors': [
                'django.contrib.auth.context_processors.auth',
                'django.template.context_processors.debug',
                'django.template.context_processors.i18n',
                'django.template.context_processors.media',
                'django.template.context_processors.request',
                'django.template.context_processors.static',
                'django.template.context_processors.tz',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# -----------------------------------
# Logging settings
# -----------------------------------
LOGGING = {
    'version': 1,
    'disable_existing_loggers': True,
    'formatters': {
        'verbose': {
            'format': '%(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s'
        },
        'simple': {
            'format': '%(levelname)s %(message)s'
        },
    },
    'handlers': {
        'null': {
            'level': 'DEBUG',
            'class': 'logging.NullHandler',
        },
        'console':{
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'simple'
        },
        'file':{
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'filename': '/home/urnik/urnik/django.log',
            'formatter': 'verbose'
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file'],
            'propagate': True,
            'level': 'INFO',
        },
        'friprosveta': {
            'handlers': ['console', 'file'],
            # 'handlers': ['null'],
            'level': 'INFO',
        },
        'friprosveta': {
            'handlers': ['file'],
            # 'handlers': ['null'],
            'level': 'DEBUG',
        },

    }
}

# -----------------------------------
# Studis API settings
# -----------------------------------
STUDIS_API_BASE_URL = 'https://studisfri.uni-lj.si/api'
# STUDIS_API_TOKEN = 'DC398579-1B7D-4212-8F35-48976BF9C4C3'
STUDIS_API_TOKEN = '69C36C4D-CD77-433A-B4DD-4943A9CCA83F'


#------------------------------------
# Exchange settings
#------------------------------------
STUDENT_MAPPER_PRODUCTION = True

