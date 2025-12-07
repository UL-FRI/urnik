"""
Import all models to maintain backward compatibility.
This allows code to continue using "from timetable.models import ModelName"
"""
# Import constants first
from .constants import *

# Import core models
from .core import (
    Resource,
    ResourceGroup,
    Teacher,
    Location,
    LocationDistance,
)

# Import group models
from .groups import (
    Group,
    GroupSet,
)

# Import activity models
from .activities import (
    Activity,
    ActivitySet,
    ActivityRealization,
    NRequirementsPerStudent,
)

# Import classroom models
from .classrooms import (
    Classroom,
    ClassroomSet,
    ClassroomNResources,
)

# Import timetable models (includes PreferenceSet)
from .timetables import (
    PreferenceSet,
    Timetable,
    TimetableSet,
    TimetableSite,
    Allocation,
    TradeRequest,
    TradeMatch,
    default_timetable,
    default_timetable_set,
)

# Import tag models
from .tags import (
    Tag,
)

# Import all preference models
from .preferences import (
    Preference,
    GroupPreference,
    GroupTimePreference,
    GroupValuePreference,
    TeacherPreference,
    TeacherValuePreference,
    TeacherTimePreference,
    TeacherDescriptivePreference,
    ActivityPreference,
    ActivityTimePlacePreference,
    TagPreference,
    TagValuePreference,
    TagTimePreference,
    TagDescriptivePreference,
)

# Make sure all models are available at the package level
__all__ = [
    # Constants
    'WEEKDAYS',
    'WEEKDAYSSLO',
    'PREFERENCELEVELS',
    'WORKHOURS',
    'AFTERHOURS',
    'PEOPLEVALUEPREFERENCES',
    'TAGVALUEPREFERENCES',
    'PREFERENCETYPES',
    'ACTIVITYTYPES',
    
    # Core models
    'Resource',
    'ResourceGroup',
    'Teacher',
    'Location',
    'LocationDistance',
    
    # Group models
    'Group',
    'GroupSet',
    
    # Activity models
    'Activity',
    'ActivitySet',
    'ActivityRealization',
    'NRequirementsPerStudent',
    
    # Classroom models
    'Classroom',
    'ClassroomSet',
    'ClassroomNResources',
    
    # Timetable models
    'PreferenceSet',
    'Timetable',
    'TimetableSet',
    'TimetableSite',
    'Allocation',
    'TradeRequest',
    'TradeMatch',
    'default_timetable',
    'default_timetable_set',
    
    # Tag models
    'Tag',
    
    # Preference models
    'Preference',
    'GroupPreference',
    'GroupTimePreference',
    'GroupValuePreference',
    'TeacherPreference',
    'TeacherValuePreference',
    'TeacherTimePreference',
    'TeacherDescriptivePreference',
    'ActivityPreference',
    'ActivityTimePlacePreference',
    'TagPreference',
    'TagValuePreference',
    'TagTimePreference',
    'TagDescriptivePreference',
]