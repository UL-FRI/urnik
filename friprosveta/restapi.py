from rest_framework import generics, permissions

from .models import Subject, Teacher
from .serializers import SubjectSerializer


class IsManagerOrNone(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to edit it.
    """

    def has_object_permission(self, request, view, obj):
        teacher = Teacher.objects.get(user=request.user)
        return obj.managers.filter(id=teacher.id).count() == 1


class SubjectsView(generics.ListAPIView):
    """
    List all subject objects.
    """
    queryset = Subject.objects.all()
    serializer_class = SubjectSerializer
    permission_classes = (permissions.IsAuthenticatedOrReadOnly, IsManagerOrNone)


class SubjectDetailsView(generics.RetrieveUpdateDestroyAPIView):
    """
    Get subject details.
    """
    lookup_field = 'code'
    queryset = Subject.objects.all()
    serializer_class = SubjectSerializer
    permission_classes = (permissions.IsAuthenticated, IsManagerOrNone)
