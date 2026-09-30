from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from rest_framework import serializers

from timetable.models import Classroom
from timetable.models.activities import ActivitySet
from timetable.models.classrooms import ClassroomSet
from timetable.models.timetables import Allocation, TimetableSite

from .models import *


class TimetableSerializer(serializers.ModelSerializer):
    class Meta:
        model = Timetable
        fields = "__all__"

class SiteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Site
        fields = "__all__"    

class TimetableSiteSerializer(serializers.ModelSerializer):
    site = SiteSerializer()
    class Meta:
        model = TimetableSite
        fields = "__all__"

class ActivityRealizationSerializer(serializers.ModelSerializer):
	class Meta:
		model = ActivityRealization
		fields = ("id", "activity", "teachers")

class AllocationSerializer(serializers.ModelSerializer):
    activityRealization = ActivityRealizationSerializer()
    class Meta:
        model = Allocation
        fields = "__all__"

class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ("id", "code", "name", "short_name", "heads")

class TeacherUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("first_name", "last_name")

class TeacherSerializer(serializers.ModelSerializer):
    user = TeacherUserSerializer()
    class Meta:
        model = Teacher
        fields = "__all__"

class ClassroomSerializer(serializers.ModelSerializer):
    class Meta:
        model = Classroom
        fields = "__all__"

class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = "__all__"

class ClassroomSetSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClassroomSet
        fields = "__all__"

class ActivitySetSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActivitySet
        fields = "__all__"

class ActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Activity
        fields = ("id", "name", "short_name", "type", "duration", "activityset", "subject", "lecture_type",)
