from django.contrib import admin
from import_export.admin import ImportExportActionModelAdmin

from friprosveta.models import *


class ActivityAdmin(ImportExportActionModelAdmin):
    filter_horizontal = ('groups', 'mustNotOverlap')
    search_fields = ('name', 'teachers__user__first_name', 'teachers__user__last_name', 'activityset__timetable__name')
    fieldsets = (
        (None, {
            'fields': ('name', 'activityset', 'short_name', 'type', 'locations', 'duration', 'requirements', 'subject',
                       'lecture_type'),
        }),
        ('Advanced options', {
            'classes': ('collapse',),
            'fields': ('mustNotOverlap', 'before',)
        }),
    )
    list_filter = ('activityset', 'activityset__timetable__timetable_sets')


class StudentAdmin(ImportExportActionModelAdmin):
    filter_horizontal = ('groups',)
    search_fields = ('name', 'surname', 'id', 'groups__name', 'groups__short_name')


class CathedraAdmin(ImportExportActionModelAdmin):
    filter_horizontal = ('heads', 'najave_deputies', 'members')


class SubjectAdmin(ImportExportActionModelAdmin):
    search_fields = ('short_name', 'name', 'code')
    list_filter = ('activities__activityset__timetable',)


class StudyAdmin(ImportExportActionModelAdmin):
    pass


class LectureTypeAdmin(ImportExportActionModelAdmin):
    pass


class StudentEnrollmentAdmin(ImportExportActionModelAdmin):
    list_filter = ('groupset', 'study', 'classyear')
    search_fields = ('student__name', 'student__surname', 'student__studentId',
                     'subject__name', 'subject__code')


admin.site.register(Activity, ActivityAdmin)
admin.site.register(Teacher, timetable.admin.TeacherAdmin)
admin.site.register(Subject, SubjectAdmin)
admin.site.register(SubjectHeadTeachers)
admin.site.register(Cathedra, CathedraAdmin)
admin.site.register(Study, StudyAdmin)
admin.site.register(LectureType, LectureTypeAdmin)
admin.site.register(StudentEnrollment, StudentEnrollmentAdmin)
# admin.site.register(CathedraHeads)
admin.site.register(Student, StudentAdmin)
