from collections import namedtuple
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from timetable.models import Classroom
from timetable.models.classrooms import ClassroomSet
from timetable.models.timetables import Allocation

from .models import *
from .serializers import *

# Currently all views are read-only.
# when this changes, be VERY CAREFUL to set up permissions
class BaseViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = (permissions.DjangoModelPermissionsOrAnonReadOnly,)

class BaseNestedViewSet(BaseViewSet):
    def get_queryset(self):
        return super().get_queryset().filter(**{self.parent_lookup_field: self.kwargs[self.parent_lookup_kwarg]})

    def perform_create(self, serializer):
        serializer.save(**{self.parent_lookup_field: self.kwargs[self.parent_lookup_kwarg]})

###

class TimetableViewSet(BaseViewSet):
    queryset = Timetable.objects.all()
    serializer_class = TimetableSerializer
    lookup_field = 'slug'

class AllocationViewSet(BaseNestedViewSet):
    queryset = Allocation.objects.all()
    serializer_class = AllocationSerializer
    parent_lookup_field = 'timetable__slug'
    parent_lookup_kwarg = 'timetable_slug'

class SubjectViewSet(BaseViewSet):
    queryset = Subject.objects.all()
    serializer_class = SubjectSerializer

class TeacherViewSet(BaseViewSet):
    queryset = Teacher.objects.all()
    serializer_class = TeacherSerializer

class LocationViewSet(BaseViewSet):
    queryset = Location.objects.all()
    serializer_class = LocationSerializer

class ClassroomViewSet(BaseNestedViewSet):
    queryset = Classroom.objects.all()
    serializer_class = ClassroomSerializer
    parent_lookup_field = 'location__pk'
    parent_lookup_kwarg = 'location_pk'

class ClassroomSetViewSet(BaseViewSet):
    queryset = ClassroomSet.objects.all()
    serializer_class = ClassroomSetSerializer

class ActivitySetViewSet(BaseViewSet):
    queryset = ActivitySet.objects.all()
    serializer_class = ActivitySetSerializer
    lookup_field = 'slug'

class ActivityViewSet(BaseNestedViewSet):
    queryset = Activity.objects.all()
    serializer_class = ActivitySerializer
    parent_lookup_field = 'activityset__slug'
    parent_lookup_kwarg = 'activityset_slug'

class DailyAllocationsView(viewsets.ViewSet):
    queryset = Allocation.objects.all()
    serializer_class = DailyAllocationsSerializer
    parent_lookup_field = 'timetable__slug'
    parent_lookup_kwarg = 'timetable_slug'
    filterset_fields = ["date"]
    
    def list(self, request, timetable_slug):
        tt = get_object_or_404(Timetable, slug=timetable_slug)
        allocations = Allocation.objects.filter(timetable=tt)
        DailyAllocationsVM = namedtuple("DailyAllocations", ["allocations"])
        return Response(DailyAllocationsVM(
            allocations=allocations
        ))
        
