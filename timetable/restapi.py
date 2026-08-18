from models import Activity, Classroom, Timetable
from rest_framework import generics, permissions

class TimetableView(generics.ListAPIView):
    model = Timetable

class ClassroomView(generics.ListAPIView):
    model = Classroom

class ActivityView(generics.ListAPIView):
    model = Activity
