from django.contrib import admin
from django import forms
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
    #filter_horizontal = ("activities",)


class ClassroomNResourcesInline(admin.TabularInline):
    model = ClassroomNResources


# class ResourcesInline(admin.TabularInline):
#    model = Resource


class ClassroomAdmin(ImportExportActionModelAdmin):
    #filter_horizontal = ("resources",)
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


class TradeRequestAdminForm(forms.ModelForm):
    """Optimized form for admin interface."""
    class Meta:
        model = TradeRequest
        fields = '__all__'
        widgets = {
            'offered_allocation': admin.widgets.ForeignKeyRawIdWidget(TradeRequest._meta.get_field('offered_allocation').remote_field, admin.site),
            'desired_allocation': admin.widgets.ForeignKeyRawIdWidget(TradeRequest._meta.get_field('desired_allocation').remote_field, admin.site),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Make optional fields clearly marked
        self.fields['desired_allocation'].required = False
        self.fields['expires_at'].required = False


class TradeRequestAdmin(ImportExportActionModelAdmin):
    form = TradeRequestAdminForm
    list_display = (
        'requesting_teacher', 
        'offered_allocation_summary', 
        'desired_allocation_summary',
        'status', 
        'created_at',
        'expires_at'
    )
    list_filter = (
        'status',
        'created_at',
        'expires_at',
        'desired_day',
        'offered_allocation__timetable',
    )
    raw_id_fields = ('requesting_teacher', 'offered_allocation', 'desired_allocation', 'matched_with', 'approved_by')
    list_per_page = 50  # Limit items per page for performance
    search_fields = (
        'requesting_teacher__user__first_name',
        'requesting_teacher__user__last_name',
        'requesting_teacher__code',
        'offered_allocation__activityRealization__activity__name',
        'desired_allocation__activityRealization__activity__name',
        'reason',
    )
    readonly_fields = ('created_at', 'matched_with')
    fieldsets = (
        ('Basic Information', {
            'fields': ('requesting_teacher', 'status', 'reason', 'created_at')
        }),
        ('Offered Allocation', {
            'fields': ('offered_allocation',)
        }),
        ('Desired Allocation', {
            'fields': ('desired_allocation', 'desired_day', 'desired_start_time', 'desired_duration'),
            'description': 'Either specify a specific allocation OR set criteria (day/time/duration)'
        }),
        ('Request Details', {
            'fields': ('expires_at', 'matched_with')
        }),
        ('Approval Information', {
            'fields': ('approved_by', 'approval_date', 'approval_notes'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['mark_as_cancelled', 'mark_as_expired', 'find_matches', 'auto_match_requests']
    
    def offered_allocation_summary(self, obj):
        """Display a summary of the offered allocation."""
        alloc = obj.offered_allocation
        return f"{alloc.activityRealization.activity.name} - {alloc.day} {alloc.start}"
    offered_allocation_summary.short_description = "Offered"
    
    def desired_allocation_summary(self, obj):
        """Display a summary of the desired allocation or criteria."""
        if obj.desired_allocation:
            alloc = obj.desired_allocation
            return f"{alloc.activityRealization.activity.name} - {alloc.day} {alloc.start}"
        else:
            criteria = []
            if obj.desired_day:
                criteria.append(f"Day: {obj.desired_day}")
            if obj.desired_start_time:
                criteria.append(f"Time: {obj.desired_start_time}")
            if obj.desired_duration:
                criteria.append(f"Duration: {obj.desired_duration}h")
            return ", ".join(criteria) if criteria else "Any suitable"
    desired_allocation_summary.short_description = "Desired"
    
    def mark_as_cancelled(self, request, queryset):
        """Mark selected trade requests as cancelled."""
        updated = queryset.filter(status__in=['OPEN', 'MATCHED']).update(status='CANCELLED')
        self.message_user(request, f"{updated} trade requests marked as cancelled.")
    mark_as_cancelled.short_description = "Mark selected requests as cancelled"
    
    def mark_as_expired(self, request, queryset):
        """Mark selected trade requests as expired."""
        updated = queryset.filter(status__in=['OPEN', 'MATCHED']).update(status='EXPIRED')
        self.message_user(request, f"{updated} trade requests marked as expired.")
    mark_as_expired.short_description = "Mark selected requests as expired"
    
    def find_matches(self, request, queryset):
        """Find potential matches for selected trade requests."""
        # Limit the number of requests to process to prevent performance issues
        open_requests = queryset.filter(status='OPEN')[:20]  # Limit to 20 requests
        
        if open_requests.count() == 0:
            self.message_user(request, "No open trade requests selected.")
            return
        
        matches_found = 0
        for trade_request in open_requests:
            potential_matches = trade_request.find_potential_matches()
            matches_found += len(potential_matches)
        
        self.message_user(request, f"Found {matches_found} potential matches for {open_requests.count()} selected requests.")
    find_matches.short_description = "Find potential matches for selected requests (max 20)"
    
    def auto_match_requests(self, request, queryset):
        """Automatically match selected trade requests."""
        open_requests = queryset.filter(status='OPEN')[:10]  # Limit to 10 requests
        
        if open_requests.count() == 0:
            self.message_user(request, "No open trade requests selected.")
            return
        
        matches_created = 0
        for trade_request in open_requests:
            match = trade_request.auto_match()
            if match:
                matches_created += 1
        
        self.message_user(request, f"Created {matches_created} automatic matches from {open_requests.count()} selected requests.")
    auto_match_requests.short_description = "Auto-match selected requests (max 10)"
    
    def get_queryset(self, request):
        """Optimize the admin queryset."""
        return super().get_queryset(request).select_related(
            'requesting_teacher__user',
            'offered_allocation__activityRealization__activity',
            'offered_allocation__classroom',
            'desired_allocation__activityRealization__activity',
            'desired_allocation__classroom',
            'matched_with',
            'approved_by__user'
        )


class TradeMatchAdmin(ImportExportActionModelAdmin):
    list_display = (
        'trade_summary',
        'status',
        'created_at',
        'reviewed_by',
        'reviewed_at'
    )
    list_filter = (
        'status',
        'created_at',
        'reviewed_at',
        'executed_at',
    )
    search_fields = (
        'request_1__requesting_teacher__user__first_name',
        'request_1__requesting_teacher__user__last_name',
        'request_2__requesting_teacher__user__first_name',
        'request_2__requesting_teacher__user__last_name',
        'review_notes',
    )
    readonly_fields = ('created_at', 'reviewed_at', 'executed_at')
    fieldsets = (
        ('Trade Details', {
            'fields': ('request_1', 'request_2', 'status', 'created_at')
        }),
        ('Review Information', {
            'fields': ('reviewed_by', 'reviewed_at', 'review_notes'),
            'classes': ('collapse',)
        }),
        ('Execution Information', {
            'fields': ('executed_at', 'executed_by'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['approve_trades', 'reject_trades']
    
    def trade_summary(self, obj):
        """Display a summary of the trade match."""
        teacher1 = obj.request_1.requesting_teacher
        teacher2 = obj.request_2.requesting_teacher
        return f"{teacher1} ↔ {teacher2}"
    trade_summary.short_description = "Trade"
    
    def approve_trades(self, request, queryset):
        """Approve selected trade matches."""
        approved_count = 0
        for trade_match in queryset.filter(status='PENDING_APPROVAL'):
            try:
                # Get the current user as reviewer (you might want to use a proper admin user)
                reviewer = request.user.teacher if hasattr(request.user, 'teacher') else None
                if reviewer:
                    trade_match.approve(reviewer, "Approved via admin interface")
                    approved_count += 1
                else:
                    # Create a default admin teacher if needed
                    from django.contrib.auth.models import User
                    admin_user = User.objects.filter(is_superuser=True).first()
                    if admin_user and hasattr(admin_user, 'teacher'):
                        trade_match.approve(admin_user.teacher, "Approved via admin interface")
                        approved_count += 1
            except Exception as e:
                self.message_user(request, f"Error approving trade {trade_match}: {e}", level='ERROR')
        
        self.message_user(request, f"{approved_count} trade matches approved.")
    approve_trades.short_description = "Approve selected trade matches"
    
    def reject_trades(self, request, queryset):
        """Reject selected trade matches."""
        rejected_count = 0
        for trade_match in queryset.filter(status='PENDING_APPROVAL'):
            try:
                # Get the current user as reviewer
                reviewer = request.user.teacher if hasattr(request.user, 'teacher') else None
                if reviewer:
                    trade_match.reject(reviewer, "Rejected via admin interface")
                    rejected_count += 1
                else:
                    # Create a default admin teacher if needed
                    from django.contrib.auth.models import User
                    admin_user = User.objects.filter(is_superuser=True).first()
                    if admin_user and hasattr(admin_user, 'teacher'):
                        trade_match.reject(admin_user.teacher, "Rejected via admin interface")
                        rejected_count += 1
            except Exception as e:
                self.message_user(request, f"Error rejecting trade {trade_match}: {e}", level='ERROR')
        
        self.message_user(request, f"{rejected_count} trade matches rejected.")
    reject_trades.short_description = "Reject selected trade matches"


class ResourceInline(admin.TabularInline):
    model = Resource
    extra = 1
    fields = ('name', 'order')
    ordering = ('order', 'name')


class ResourceGroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'required', 'exactly_one', 'order', 'resource_count')
    list_editable = ('required', 'exactly_one', 'order')
    list_filter = ('required', 'exactly_one')
    search_fields = ('name',)
    inlines = [ResourceInline]
    
    def resource_count(self, obj):
        return obj.resources.count()
    resource_count.short_description = 'Number of Resources'


class ResourceAdmin(admin.ModelAdmin):
    list_display = ('name', 'group', 'order')
    list_editable = ('order',)
    list_filter = ('group',)
    search_fields = ('name',)
    ordering = ('group__order', 'group__name', 'order', 'name')


admin.site.register(ResourceGroup, ResourceGroupAdmin)
admin.site.register(Resource, ResourceAdmin)
admin.site.register(NRequirementsPerStudent)

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

# Register the new trade-related models
admin.site.register(TradeRequest, TradeRequestAdmin)
admin.site.register(TradeMatch, TradeMatchAdmin)
