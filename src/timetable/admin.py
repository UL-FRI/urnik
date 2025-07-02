from django.contrib import admin
from import_export.admin import ImportExportActionModelAdmin

from timetable.models import *


class ActivityAdmin(ImportExportActionModelAdmin):
    # filter_horizontal = ('groups', 'mustNotOverlap', 'before',)
    exclude = (
        "groups",
        "mustNotOverlap",
        "before",
    )
    search_fields = ("name",)
    # form = autocomplete_light.modelform_factory(Activity)
    list_filter = ("activityset",)


class ActivityAutocompleteAdmin(ImportExportActionModelAdmin):
    search_fields = ("name",)
    # form = ActivityAutocompleteForm
    # form = al.modelform_factory(Activity, fields = '__all__')


class TeacherAdmin(ImportExportActionModelAdmin):
    search_fields = (
        "user__first_name",
        "user__last_name",
        "activities__name",
        "activities__short_name",
    )
    # filter_horizontal = ("activities",)


class ClassroomNResourcesInline(admin.TabularInline):
    model = ClassroomNResources


# class ResourcesInline(admin.TabularInline):
#    model = Resource


class ClassroomAdmin(ImportExportActionModelAdmin):
    # filter_horizontal = ("resources",)
    list_filter = ("classroomset",)
    inlines = [
        ClassroomNResourcesInline,
    ]


class ClassroomSetAdmin(ImportExportActionModelAdmin):
    filter_horizontal = ("classrooms",)


class GroupAdmin(ImportExportActionModelAdmin):
    search_fields = ("name", "short_name")
    list_filter = ("groupset",)


class AllocationAdmin(ImportExportActionModelAdmin):
    search_fields = (
        "activityRealization__teachers__user__first_name",
        "activityRealization__teachers__user__last_name",
        "activityRealization__activity__name",
        "activityRealization__activity__short_name",
        "timetable__name",
    )

    list_filter = ("timetable__timetable_sets",)


class TeacherTimePreferenceAdmin(ImportExportActionModelAdmin):
    search_fields = ("teacher__user__first_name", "teacher__user__last_name")
    list_filter = ("preferenceset",)


class TagAdmin(ImportExportActionModelAdmin):
    search_fields = (
        "name",
        "teacher__user__first_name",
        "teacher__user__last_name",
        "activity__name",
        "activity__short_name",
        "activityRealization__activity__name",
        "activityRealization__activity__short_name",
        "group__name",
        "group__short_name",
    )
    filter_horizontal = ("teachers", "activities", "groups", "activity_realizations")


class ActivityRealizationAdmin(ImportExportActionModelAdmin):
    filter_horizontal = ("groups", "teachers")
    search_fields = (
        "teachers__user__first_name",
        "teachers__user__last_name",
        "activity__name",
        "activity__short_name",
        "groups__name",
    )


class TimetableSetAdmin(ImportExportActionModelAdmin):
    filter_horizontal = ("timetables",)


class TimetableAdmin(ImportExportActionModelAdmin):
    pass


class PreferenceAdmin(ImportExportActionModelAdmin):
    list_filter = ("preferenceset",)


class GroupPreferenceAdmin(ImportExportActionModelAdmin):
    list_filter = ("preferenceset",)


class GroupValuePreferenceAdmin(ImportExportActionModelAdmin):
    list_filter = ("preferenceset",)


class GroupTimePreferenceAdmin(ImportExportActionModelAdmin):
    list_filter = ("preferenceset",)


class TeacherPreferenceAdmin(ImportExportActionModelAdmin):
    list_filter = ("preferenceset",)


class TeacherValuePreferenceAdmin(ImportExportActionModelAdmin):
    list_filter = ("preferenceset",)


class TeacherDescriptivePreferenceAdmin(ImportExportActionModelAdmin):
    list_filter = ("preferenceset",)


class TagPreferenceAdmin(ImportExportActionModelAdmin):
    list_filter = ("preferenceset",)


class TagTimePreferenceAdmin(ImportExportActionModelAdmin):
    list_filter = ("preferenceset",)


class TagValuePreferenceAdmin(ImportExportActionModelAdmin):
    list_filter = ("preferenceset",)


class TagDescriptivePreferenceAdmin(ImportExportActionModelAdmin):
    list_filter = ("preferenceset",)


admin.site.register(Resource)
admin.site.register(NRequirementsPerStudent)

admin.site.register(Heuristic)
# admin.site.register(Activity, ActivityAutocompleteAdmin)
admin.site.register(Activity, ActivityAdmin)
admin.site.register(ActivityRealization, ActivityRealizationAdmin)
admin.site.register(ActivitySet)
admin.site.register(PreferenceSet)

admin.site.register(ClassroomSet, ClassroomSetAdmin)
admin.site.register(Classroom, ClassroomAdmin)
admin.site.register(ClassroomNResources)

admin.site.register(Allocation, AllocationAdmin)
admin.site.register(Group, GroupAdmin)
admin.site.register(GroupSet)
admin.site.register(Teacher, TeacherAdmin)
admin.site.register(Timetable, TimetableAdmin)
admin.site.register(Location)
admin.site.register(TimetableSet, TimetableSetAdmin)
admin.site.register(TimetableSite)


admin.site.register(GroupPreference, GroupPreferenceAdmin)
admin.site.register(GroupValuePreference, GroupValuePreferenceAdmin)
admin.site.register(GroupTimePreference, GroupTimePreferenceAdmin)
admin.site.register(TeacherPreference, TeacherPreferenceAdmin)
admin.site.register(TeacherTimePreference, TeacherTimePreferenceAdmin)
admin.site.register(TeacherValuePreference, TeacherValuePreferenceAdmin)
admin.site.register(TeacherDescriptivePreference, TeacherDescriptivePreferenceAdmin)
admin.site.register(Preference, PreferenceAdmin)

admin.site.register(Tag, TagAdmin)
admin.site.register(TagPreference, TagPreferenceAdmin)
admin.site.register(TagTimePreference, TagTimePreferenceAdmin)
admin.site.register(TagValuePreference, TagValuePreferenceAdmin)
admin.site.register(TagDescriptivePreference, TagDescriptivePreferenceAdmin)
