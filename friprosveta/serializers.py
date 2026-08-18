from django.contrib.auth.models import User
from rest_framework import serializers

from timetable.models import Classroom
from timetable.models.activities import ActivitySet
from timetable.models.classrooms import ClassroomSet
from timetable.models.timetables import Allocation

from .models import *


class TimetableSerializer(serializers.ModelSerializer):
    class Meta:
        model = Timetable
        fields = "__all__"

class AllocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Allocation
        fields = "__all__"

class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = "__all__"

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

class DailyAllocationsSerializer(serializers.ModelSerializer):
    allocations = AllocationSerializer