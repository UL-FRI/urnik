'''
Created on 30. sep. 2013

@author: gregor
'''

from rest_framework import serializers

from .models import Subject


class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ('code', 'name', 'short_name')
