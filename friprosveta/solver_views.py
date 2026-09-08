"""
Superuser-only, server-rendered views for the OR-Tools Solver Setup UI.

Every view requires an authenticated superuser and scopes all object access
to the timetable resolved from the URL slug. Objects accessed by primary key
are verified to belong to that timetable so an operator cannot edit or delete
another timetable's constraints.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.forms import modelformset_factory
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from friprosveta.models import (
    Activity as FriActivity,
    ActivityRealizationSchedulingWindow,
    ActivityTypeSchedulingRestriction,
    ActivityTypeSchedulingWindow,
    ManualActivity,
    SolverWeightSettings,
    TeacherSchedulingWindow,
)
from .scheduling_window_override_forms import (
    ActivityRealizationSchedulingWindowForm,
)
from timetable.models import (
    Activity,
    Group,
    GroupTimePreference,
    SolverConstraint,
    StudyModule,
    Teacher,
    Timetable,
    WEEKDAYS,
)

from .scheduling_window_forms import (
    ActivityTypeSchedulingWindowForm,
    TeacherSchedulingWindowGridForm,
)
from .solver_forms import (
    ActivityBeforeRelationForm,
    CATEGORY_TYPE_MAP,
    SchedulingScopeActivityForm,
    ManualActivityForm,
    CopyGroupTimePreferencesForm,
    SolverConstraintCategoryForm,
    SolverConstraintForm,
    SolverWeightSettingsForm,
    StudyModuleForm,
)
from .solver_summary import active_rule_sources
from .solver_run_views import get_solver_generation_status
from .studis_workflow_views import get_studis_workflow_status
from .services.manual_activities import apply_manual_activities


def _require_staff(user):
    if not (user.is_authenticated and user.is_superuser):
        raise PermissionDenied


def _get_timetable_or_404(timetable_slug):
    return get_object_or_404(Timetable, slug=timetable_slug)


def _scoped_constraint(timetable, pk):
    """Return a SolverConstraint only if it belongs to the given timetable."""
    return get_object_or_404(SolverConstraint, pk=pk, timetable=timetable)


def _scoped_study_module(timetable, pk):
    return get_object_or_404(StudyModule, pk=pk, timetable=timetable)


def _category_for_type(constraint_type):
    for category, types in CATEGORY_TYPE_MAP.items():
        if constraint_type in types:
            return category
    return None


@login_required
def solver_dashboard(request, timetable_slug):
    _require_staff(request.user)
    timetable = _get_timetable_or_404(timetable_slug)
    constraints = SolverConstraint.objects.filter(timetable=timetable).order_by("name")
    generation_status = get_solver_generation_status(timetable_slug)
    studis_workflow_status = get_studis_workflow_status(timetable_slug)
    counts = {
        "relation": constraints.filter(
            constraint_type__in=CATEGORY_TYPE_MAP["relation"]
        ).count(),
        "ends_day": constraints.filter(
            constraint_type__in=CATEGORY_TYPE_MAP["ends_day"]
        ).count(),
        "workload": constraints.filter(
            constraint_type__in=CATEGORY_TYPE_MAP["workload"]
        ).count(),
        "lecture_group": constraints.filter(
            constraint_type__in=CATEGORY_TYPE_MAP["lecture_group"]
        ).count(),
        "room": constraints.filter(
            constraint_type__in=CATEGORY_TYPE_MAP["room"]
        ).count(),
        "placement": constraints.filter(
            constraint_type__in=CATEGORY_TYPE_MAP["placement"]
        ).count(),
        "time": constraints.filter(
            constraint_type__in=CATEGORY_TYPE_MAP["time"]
        ).count(),
    }
    return render(
        request,
        "friprosveta/solver_dashboard.html",
        {
            "timetable": timetable,
            "timetable_slug": timetable_slug,
            "counts": counts,
            "custom_constraint_count": constraints.count(),
            "study_module_count": timetable.study_modules.count(),
            "manual_activity_count": timetable.manual_activities.filter(enabled=True).count(),
            "before_relation_count": Activity.objects.filter(
                activityset=timetable.activityset,
                before__activityset=timetable.activityset,
            ).count(),
            "generation_status": generation_status,
            "studis_workflow_status": studis_workflow_status,
            "automatic_rule_sources": active_rule_sources(timetable),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def manual_activity_list(request, timetable_slug):
    _require_staff(request.user)
    timetable = _get_timetable_or_404(timetable_slug)
    if request.method == "POST":
        entry = get_object_or_404(
            ManualActivity, pk=request.POST.get("entry"), timetable=timetable
        )
        with transaction.atomic():
            constraint = entry.solver_constraint
            entry.delete()
            if constraint is not None:
                constraint.delete()
        messages.success(request, "Manual activity configuration removed.")
        return redirect("manual_activity_list", timetable_slug=timetable_slug)
    entries = timetable.manual_activities.select_related(
        "subject", "lecture_type", "fixed_room"
    ).prefetch_related("teachers", "required_rooms")
    return render(
        request,
        "friprosveta/manual_activity_list.html",
        {"timetable": timetable, "timetable_slug": timetable_slug, "entries": entries},
    )


@login_required
@require_http_methods(["GET", "POST"])
def manual_activity_edit(request, timetable_slug, pk=None):
    _require_staff(request.user)
    timetable = _get_timetable_or_404(timetable_slug)
    entry = (
        get_object_or_404(ManualActivity, pk=pk, timetable=timetable) if pk is not None else None
    )
    form = ManualActivityForm(request.POST or None, instance=entry, timetable=timetable)
    if request.method == "POST" and form.is_valid():
        entry = form.save(commit=False)
        entry.timetable = timetable
        entry.save()
        form.save_m2m()
        apply_manual_activities(timetable)
        messages.success(request, "Manual activity configuration saved and applied.")
        return redirect("manual_activity_list", timetable_slug=timetable_slug)
    return render(
        request,
        "friprosveta/manual_activity_form.html",
        {
            "timetable": timetable,
            "timetable_slug": timetable_slug,
            "form": form,
            "is_create": entry is None,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def activity_before_relations(request, timetable_slug):
    _require_staff(request.user)
    timetable = _get_timetable_or_404(timetable_slug)

    if request.method == "POST" and request.POST.get("action") == "remove":
        before_activity = get_object_or_404(
            Activity,
            pk=request.POST.get("before_activity"),
            activityset=timetable.activityset,
        )
        after_activity = get_object_or_404(
            Activity,
            pk=request.POST.get("after_activity"),
            activityset=timetable.activityset,
        )
        before_activity.before.remove(after_activity)
        messages.success(request, "Before relation removed.")
        return redirect("activity_before_relations", timetable_slug=timetable_slug)

    form = ActivityBeforeRelationForm(
        request.POST or None,
        timetable=timetable,
    )
    if request.method == "POST" and form.is_valid():
        before_activity, after_activities = form.save()
        messages.success(
            request,
            "Added {} before relation(s) from {}.".format(
                len(after_activities), before_activity.short_name
            ),
        )
        return redirect("activity_before_relations", timetable_slug=timetable_slug)

    activities = list(
        Activity.objects.filter(activityset=timetable.activityset)
        .prefetch_related("before")
        .order_by("name", "id")
    )
    relations = [
        (before_activity, after_activity)
        for before_activity in activities
        for after_activity in before_activity.before.all()
        if after_activity.activityset_id == timetable.activityset_id
    ]
    relations.sort(
        key=lambda relation: (
            relation[0].name,
            relation[0].id,
            relation[1].name,
            relation[1].id,
        )
    )
    return render(
        request,
        "friprosveta/activity_before_relations.html",
        {
            "timetable": timetable,
            "timetable_slug": timetable_slug,
            "form": form,
            "relations": relations,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def solver_scheduling_scope(request, timetable_slug):
    _require_staff(request.user)
    timetable = _get_timetable_or_404(timetable_slug)
    activities = (
        FriActivity.objects.filter(activityset=timetable.activityset)
        .select_related("subject", "lecture_type")
        .order_by("subject__code", "type", "short_name")
    )

    formset_class = modelformset_factory(
        FriActivity,
        form=SchedulingScopeActivityForm,
        extra=0,
    )
    if request.method == "POST" and request.POST.get("action") == "schedule_all":
        activities.update(ready_to_schedule=True)
        return redirect("solver_scheduling_scope", timetable_slug=timetable_slug)
    if request.method == "POST" and request.POST.get("action") == "exclude_doctoral":
        activities.filter(subject__code__startswith="638").update(ready_to_schedule=False)
        return redirect("solver_scheduling_scope", timetable_slug=timetable_slug)
    formset = formset_class(request.POST or None, queryset=activities)
    if request.method == "POST" and formset.is_valid():
        formset.save()
        return redirect("solver_scheduling_scope", timetable_slug=timetable_slug)
    return render(
        request,
        "friprosveta/solver_scheduling_scope.html",
        {
            "timetable": timetable,
            "timetable_slug": timetable_slug,
            "formset": formset,
            "ready_count": activities.filter(ready_to_schedule=True).count(),
            "activity_count": activities.count(),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def solver_automatic_rules(request, timetable_slug):
    _require_staff(request.user)
    timetable = _get_timetable_or_404(timetable_slug)
    settings, _created = SolverWeightSettings.objects.get_or_create(timetable=timetable)
    form = SolverWeightSettingsForm(request.POST or None, instance=settings)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("solver_automatic_rules", timetable_slug=timetable_slug)
    return render(
        request,
        "friprosveta/solver_automatic_rules.html",
        {
            "timetable": timetable,
            "timetable_slug": timetable_slug,
            "form": form,
        },
    )


def _group_time_preference_copy_preview(timetable, source_timetable):
    source_preferences = list(
        GroupTimePreference.objects.filter(preferenceset=source_timetable.preferenceset)
        .select_related("group")
        .order_by("group__short_name", "day", "start", "id")
    )
    target_groups = Group.objects.filter(groupset=timetable.groupset).order_by("id")
    target_by_short_name = {}
    duplicate_short_names = set()
    for group in target_groups:
        if group.short_name in target_by_short_name:
            duplicate_short_names.add(group.short_name)
        target_by_short_name[group.short_name] = group
    matching_preferences = [
        preference
        for preference in source_preferences
        if preference.group.short_name in target_by_short_name
        and preference.group.short_name not in duplicate_short_names
    ]
    unmatched_source_groups = sorted(
        {
            preference.group.short_name
            for preference in source_preferences
            if preference.group.short_name not in target_by_short_name
            or preference.group.short_name in duplicate_short_names
        }
    )
    matched_group_ids = {
        target_by_short_name[preference.group.short_name].id
        for preference in matching_preferences
    }
    return {
        "preferences": matching_preferences,
        "target_by_short_name": target_by_short_name,
        "matched_group_ids": matched_group_ids,
        "matched_group_count": len(matched_group_ids),
        "unmatched_source_groups": unmatched_source_groups,
        "duplicate_short_names": sorted(duplicate_short_names),
        "source_preference_count": len(source_preferences),
    }


@login_required
@require_http_methods(["GET", "POST"])
def copy_group_time_preferences(request, timetable_slug):
    _require_staff(request.user)
    timetable = _get_timetable_or_404(timetable_slug)
    form = CopyGroupTimePreferencesForm(request.POST or None, timetable=timetable)
    preview = None
    if request.method == "POST" and form.is_valid():
        source_timetable = form.cleaned_data["source_timetable"]
        preview = _group_time_preference_copy_preview(timetable, source_timetable)
        if preview["duplicate_short_names"]:
            form.add_error(
                None,
                "Target groups have duplicate short names: {}.".format(
                    ", ".join(preview["duplicate_short_names"])
                ),
            )
        else:
            with transaction.atomic():
                GroupTimePreference.objects.filter(
                    preferenceset=timetable.preferenceset,
                    group_id__in=preview["matched_group_ids"],
                ).delete()
                for preference in preview["preferences"]:
                    GroupTimePreference.objects.create(
                        preferenceset=timetable.preferenceset,
                        group=preview["target_by_short_name"][preference.group.short_name],
                        level=preference.level,
                        weight=preference.weight,
                        day=preference.day,
                        start=preference.start,
                        duration=preference.duration,
                    )
            messages.success(
                request,
                "Copied {} group time preferences for {} matching groups from {}; {} source groups had no target match.".format(
                    len(preview["preferences"]),
                    preview["matched_group_count"],
                    source_timetable.name,
                    len(preview["unmatched_source_groups"]),
                ),
            )
            return redirect("copy_group_time_preferences", timetable_slug=timetable_slug)
    return render(
        request,
        "friprosveta/copy_group_time_preferences.html",
        {
            "timetable": timetable,
            "timetable_slug": timetable_slug,
            "form": form,
            "preview": preview,
        },
    )


@login_required
def study_module_list(request, timetable_slug):
    _require_staff(request.user)
    timetable = _get_timetable_or_404(timetable_slug)
    modules = timetable.study_modules.prefetch_related("activities", "non_overlapping_with")
    return render(
        request,
        "friprosveta/study_module_list.html",
        {"timetable": timetable, "timetable_slug": timetable_slug, "modules": modules},
    )


@login_required
@require_http_methods(["GET", "POST"])
def study_module_create(request, timetable_slug):
    _require_staff(request.user)
    timetable = _get_timetable_or_404(timetable_slug)
    form = StudyModuleForm(request.POST or None, timetable=timetable)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("study_module_list", timetable_slug=timetable_slug)
    return render(
        request,
        "friprosveta/study_module_form.html",
        {"timetable": timetable, "timetable_slug": timetable_slug, "form": form, "is_create": True},
    )


@login_required
@require_http_methods(["GET", "POST"])
def study_module_edit(request, timetable_slug, pk):
    _require_staff(request.user)
    timetable = _get_timetable_or_404(timetable_slug)
    module = _scoped_study_module(timetable, pk)
    form = StudyModuleForm(request.POST or None, instance=module, timetable=timetable)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("study_module_list", timetable_slug=timetable_slug)
    return render(
        request,
        "friprosveta/study_module_form.html",
        {"timetable": timetable, "timetable_slug": timetable_slug, "form": form, "is_create": False, "module": module},
    )


@login_required
@require_http_methods(["GET", "POST"])
def study_module_delete(request, timetable_slug, pk):
    _require_staff(request.user)
    timetable = _get_timetable_or_404(timetable_slug)
    module = _scoped_study_module(timetable, pk)
    if request.method == "POST":
        module.delete()
        return redirect("study_module_list", timetable_slug=timetable_slug)
    return render(
        request,
        "friprosveta/study_module_delete.html",
        {"timetable": timetable, "timetable_slug": timetable_slug, "module": module},
    )


@login_required
def solver_constraint_list(request, timetable_slug):
    _require_staff(request.user)
    timetable = _get_timetable_or_404(timetable_slug)
    constraints = SolverConstraint.objects.filter(timetable=timetable).order_by("name")
    return render(
        request,
        "friprosveta/solver_constraint_list.html",
        {
            "timetable": timetable,
            "timetable_slug": timetable_slug,
            "constraints": constraints,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def solver_constraint_create(request, timetable_slug):
    _require_staff(request.user)
    timetable = _get_timetable_or_404(timetable_slug)

    category = request.GET.get("category") or request.POST.get("category")
    if category and category not in CATEGORY_TYPE_MAP:
        raise Http404("Unknown constraint category.")

    if not category:
        if request.method == "POST":
            form = SolverConstraintCategoryForm(request.POST)
        else:
            form = SolverConstraintCategoryForm()
        if request.method == "POST" and form.is_valid():
            return redirect(
                "{}?category={}".format(
                    reverse(
                        "solver_constraint_create",
                        kwargs={"timetable_slug": timetable_slug},
                    ),
                    form.cleaned_data["category"],
                )
            )
        return render(
            request,
            "friprosveta/solver_constraint_category.html",
            {
                "timetable": timetable,
                "timetable_slug": timetable_slug,
                "form": form,
            },
        )

    selected_type = request.GET.get("constraint_type")
    if selected_type and selected_type not in CATEGORY_TYPE_MAP[category]:
        raise Http404("Constraint type does not belong to this category.")

    if request.method == "POST":
        form = SolverConstraintForm(request.POST, timetable=timetable, category=category)
    else:
        form = SolverConstraintForm(
            timetable=timetable,
            category=category,
            initial={"constraint_type": selected_type} if selected_type else None,
        )

    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect(
            "solver_constraint_list", timetable_slug=timetable_slug
        )
    return render(
        request,
        "friprosveta/solver_constraint_form.html",
        {
            "timetable": timetable,
            "timetable_slug": timetable_slug,
            "form": form,
            "category": category,
            "is_create": True,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def solver_constraint_edit(request, timetable_slug, pk):
    _require_staff(request.user)
    timetable = _get_timetable_or_404(timetable_slug)
    constraint = _scoped_constraint(timetable, pk)
    category = _category_for_type(constraint.constraint_type)
    if category is None:
        raise Http404("Constraint type is not supported by the solver UI.")

    if request.method == "POST":
        form = SolverConstraintForm(
            request.POST, instance=constraint, timetable=timetable, category=category
        )
    else:
        form = SolverConstraintForm(
            instance=constraint, timetable=timetable, category=category
        )

    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("solver_constraint_list", timetable_slug=timetable_slug)
    return render(
        request,
        "friprosveta/solver_constraint_form.html",
        {
            "timetable": timetable,
            "timetable_slug": timetable_slug,
            "form": form,
            "category": category,
            "is_create": False,
            "constraint": constraint,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def solver_constraint_delete(request, timetable_slug, pk):
    _require_staff(request.user)
    timetable = _get_timetable_or_404(timetable_slug)
    constraint = _scoped_constraint(timetable, pk)
    if request.method == "POST":
        constraint.delete()
        return redirect("solver_constraint_list", timetable_slug=timetable_slug)
    return render(
        request,
        "friprosveta/solver_constraint_delete.html",
        {
            "timetable": timetable,
            "timetable_slug": timetable_slug,
            "constraint": constraint,
        },
    )


@login_required
def solver_group_rules(request, timetable_slug):
    _require_staff(request.user)
    timetable = _get_timetable_or_404(timetable_slug)
    return render(
        request,
        "friprosveta/solver_group_rules.html",
        {
            "timetable": timetable,
            "timetable_slug": timetable_slug,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def scheduling_windows(request, timetable_slug):
    """
    Staff-only, server-rendered table form for activity-type time restrictions.

    Saves rows directly to the model; no management command is invoked and the
    solver is never executed inside this request.
    """
    _require_staff(request.user)
    timetable = _get_timetable_or_404(timetable_slug)
    if request.method == "POST":
        form = ActivityTypeSchedulingWindowForm(request.POST, timetable=timetable)
        if form.is_valid():
            form.save()
            return redirect("scheduling_windows", timetable_slug=timetable_slug)
    else:
        form = ActivityTypeSchedulingWindowForm(timetable=timetable)
    return render(
        request,
        "friprosveta/scheduling_windows.html",
        {
            "timetable": timetable,
            "timetable_slug": timetable_slug,
            "form": form,
            "weekdays": WEEKDAYS,
            "window_count": ActivityTypeSchedulingRestriction.objects.filter(timetable=timetable).count(),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def scheduling_window_overrides(request, timetable_slug):
    _require_staff(request.user)
    timetable = _get_timetable_or_404(timetable_slug)
    teacher_id = request.POST.get("teacher") or request.GET.get("teacher")
    teachers = (
        timetable.teachers.select_related("user").order_by("user__last_name", "user__first_name")
        if timetable.activityset_id is not None
        else Teacher.objects.none()
    )
    selected_teacher = teachers.filter(pk=teacher_id).first() if teacher_id else None
    if request.method == "POST":
        form_type = request.POST.get("form_type")
        if form_type == "teacher":
            teacher_form = TeacherSchedulingWindowGridForm(
                request.POST, timetable=timetable, teacher=selected_teacher
            )
            realization_form = ActivityRealizationSchedulingWindowForm(timetable=timetable)
        else:
            teacher_form = TeacherSchedulingWindowGridForm(
                timetable=timetable, teacher=selected_teacher
            )
            realization_form = ActivityRealizationSchedulingWindowForm(
                request.POST, timetable=timetable
            )
        submitted_form = teacher_form if form_type == "teacher" else realization_form
        if submitted_form.is_valid():
            submitted_form.save()
            return redirect(
                "{}?teacher={}".format(
                    reverse("scheduling_window_overrides", kwargs={"timetable_slug": timetable_slug}),
                    selected_teacher.id if selected_teacher else "",
                )
            )
    else:
        realization_form = ActivityRealizationSchedulingWindowForm(timetable=timetable)
        teacher_form = TeacherSchedulingWindowGridForm(
            timetable=timetable, teacher=selected_teacher
        )
    overrides = ActivityRealizationSchedulingWindow.objects.filter(
        timetable=timetable
    ).select_related("realization", "realization__activity")
    teacher_overrides = TeacherSchedulingWindow.objects.filter(timetable=timetable).select_related(
        "teacher", "teacher__user"
    )
    return render(
        request,
        "friprosveta/scheduling_window_overrides.html",
        {
            "timetable": timetable,
            "timetable_slug": timetable_slug,
            "form": realization_form,
            "teacher_form": teacher_form,
            "teachers": teachers,
            "selected_teacher": selected_teacher,
            "weekdays": WEEKDAYS,
            "overrides": overrides,
            "teacher_overrides": teacher_overrides,
        },
    )
