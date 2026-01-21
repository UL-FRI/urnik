from collections import OrderedDict

from django import forms
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.forms import widgets
from django.forms.boundfield import BoundField
from django.forms.utils import ErrorList
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _, gettext_lazy

from timetable.models import (
    PREFERENCELEVELS,
    WEEKDAYS,
    WORKHOURS,
    Activity,
    ActivityRealization,
    Allocation,
    Group,
    GroupTimePreference,
    Preference,
    PreferenceSet,
    Tag,
    TagTimePreference,
    Teacher,
    TeacherDescriptivePreference,
    TeacherTimePreference,
    TeacherValuePreference,
    TradeRequest,
)


class SimplePreferenceForm(forms.ModelForm):
    class Meta:
        model = Preference
        fields = "__all__"


class TeacherValuePreferenceForm(forms.ModelForm):
    class Meta:
        model = TeacherValuePreference
        fields = "__all__"


class TeacherDescriptivePreferenceForm(forms.ModelForm):
    class Meta:
        model = TeacherDescriptivePreference
        fields = "__all__"
        widgets = {
            "typename": forms.HiddenInput(),
        }


LIMITED_LEVEL_CHOICES = (("", "---"), ("HATE", "Ne bi"), ("CANT", "Zaseden"))
ALL_LEVEL_CHOICES = (
    ("", "---"),
    ("HATE", "Ne bi"),
    ("CANT", "Zaseden"),
    ("WANT", "Bi"),
)
# DEFAULT_LEVEL_CHOICES = LIMITED_LEVEL_CHOICES
DEFAULT_LEVEL_CHOICES = ALL_LEVEL_CHOICES


class CommonTimetablePreferenceForm(forms.Form):
    def __init__(
        self,
        data=None,
        files=None,
        auto_id="id_%s",
        prefix=None,
        initial=None,
        error_class=ErrorList,
        label_suffix=":",
        empty_permitted=True,
        preference_class=None,
        owner_field=None,
        owner_class=None,
        owner=None,
        preferenceset=None,
        level_choices=DEFAULT_LEVEL_CHOICES,
    ):
        forms.Form.__init__(
            self,
            data,
            files,
            auto_id,
            prefix,
            initial,
            error_class,
            label_suffix,
            empty_permitted,
        )
        self.level_choices = DEFAULT_LEVEL_CHOICES
        self.permissible_levels = set()
        timetable_preferencelevels = set([i[0] for i in PREFERENCELEVELS])
        for i in level_choices:
            if i[0] in timetable_preferencelevels:
                self.permissible_levels.add(i[0])
        self.levelFieldsByHourDay = OrderedDict()
        self.weightFieldsByHourDay = OrderedDict()
        self._owner = None
        self._owner_field = owner_field
        self._preference_class = preference_class
        self._owner_class = owner_class
        self._preferenceset = None
        pd = {}
        self.fields = OrderedDict()
        if preferenceset is not None:
            preferenceset_id = preferenceset.id
            self._preferenceset = preferenceset
        else:
            preferenceset_id = None
        if owner is not None:
            self.fields["owner"] = forms.IntegerField(
                widget=forms.HiddenInput(), initial=owner.id, label=""
            )
            self._owner = owner
            self.fields["preferenceset"] = forms.IntegerField(
                widget=forms.HiddenInput(), initial=preferenceset_id, label=""
            )
            for p in self._preference_class.objects.filter(
                preferenceset=preferenceset, **{self._owner_field: self._owner}
            ):
                if p.day not in pd:
                    pd[p.day] = {}
                for hour in p.hours():
                    if hour not in pd[p.day] or pd[p.day][hour][0] != p.level:
                        weight = p.weight
                    else:
                        weight = pd[p.day][hour][1] + p.weight
                    pd[p.day][hour] = (p.level, weight)
        else:
            self.fields["owner"] = forms.IntegerField(widget=forms.HiddenInput())
            self.fields["preferenceset"] = forms.IntegerField(
                widget=forms.HiddenInput(), initial=preferenceset_id
            )
        for hour, hourname in WORKHOURS:
            self.levelFieldsByHourDay[hour] = OrderedDict()
            self.weightFieldsByHourDay[hour] = OrderedDict()
            for day, dayname in WEEKDAYS:
                initial = [None, None]
                if day in pd and hour in pd[day]:
                    initial = pd[day][hour]
                wfield = forms.FloatField(
                    label="",
                    initial=initial[1],
                    required=False,
                    widget=forms.TextInput(
                        attrs={"size": 2, "class": "TTablePrefWeight"}
                    ),
                )
                lfield = forms.TypedChoiceField(
                    label="",
                    initial=initial[0],
                    empty_value=None,
                    choices=level_choices,
                    required=False,
                )
                self.fields["lf-{0}-{1}".format(day, hour)] = lfield
                self.fields["wf-{0}-{1}".format(day, hour)] = wfield
                self.levelFieldsByHourDay[hour][day] = BoundField(
                    self, lfield, "lf-{0}-{1}".format(day, hour)
                )
                self.weightFieldsByHourDay[hour][day] = BoundField(
                    self, wfield, "wf-{0}-{1}".format(day, hour)
                )

    def owner(self):
        if self._owner is None and self["owner"].data is not None:
            self._owner = self._owner_class.objects.get(id=self["owner"].data)
        return self._owner

    def preferenceset(self):
        if self._preferenceset is None and self["preferenceset"].data is not None:
            self._preferenceset = PreferenceSet.objects.get(
                id=self["preferenceset"].data
            )
        return self._preferenceset

    def get_preferences(self):
        # print "get prefs!"
        l = []
        for day, dayname in WEEKDAYS:
            last_weight = 0.0
            last_level = None
            duration = 0
            start = WORKHOURS[0][0]
            for hour, hourname in WORKHOURS:
                duration += 1
                level = self.levelFieldsByHourDay[hour][day].data
                weight = self.weightFieldsByHourDay[hour][day]
                if weight.data:
                    weight = weight.field.to_python(weight.data)
                else:
                    weight = 0.0
                if level == "CANT":
                    weight = 1.0
                if weight != last_weight or level != last_level:
                    if last_weight > 0.0 and last_level in self.permissible_levels:
                        l.append(
                            self._preference_class(
                                day=day,
                                start=start,
                                preferenceset=self.preferenceset(),
                                duration=duration,
                                level=last_level,
                                weight=last_weight,
                                **{self._owner_field: self.owner()}
                            )
                        )
                    duration = 0
                    start = hour
                last_weight = weight
                last_level = level
            duration += 1
            if last_weight > 0.0 and last_level in self.permissible_levels:
                l.append(
                    self._preference_class(
                        day=day,
                        start=start,
                        preferenceset=self.preferenceset(),
                        duration=duration,
                        level=last_level,
                        weight=last_weight,
                        **{self._owner_field: self.owner()}
                    )
                )
        return l

    def save(self, commit=True):
        # print "saving timeprefs"
        if commit:
            self._preference_class.objects.filter(
                preferenceset=self.preferenceset(), **{self._owner_field: self.owner()}
            ).delete()
        l = []
        for i in self.get_preferences():
            l.append(i)
            if commit:
                i.save()
        return l

    def as_table(self):
        "Returns this form rendered as HTML <tr>s without the <table></table>."
        # someday, someone should replace this with proper i18n support
        s = '<tr class="teacherTimePrefTable"><th>{0}</th>'.format(_("Time"))
        for day, dayname in WEEKDAYS:
            s += "<th class='day'>{0}</th>".format(_(dayname), dayname)
        s += "</tr>"
        for hour, hourname in WORKHOURS:
            s += "<tr>\n"
            s += "    <td>{0}</td>\n".format(hourname)
            for day, dayname in WEEKDAYS:
                wf = self.weightFieldsByHourDay[hour][day]
                lf = self.levelFieldsByHourDay[hour][day]
                s += "    <td>"
                s += "{}{} {}{}</td>\n".format(lf.label, lf, wf.label, wf)
            s += "</tr>"
        return mark_safe(s)


#    def is_valid(self):
#        return True


class TeacherTimetablePreferenceForm(CommonTimetablePreferenceForm):
    def __init__(
        self,
        data=None,
        files=None,
        auto_id="id_%s",
        prefix=None,
        initial=None,
        error_class=ErrorList,
        label_suffix=":",
        empty_permitted=False,
        teacher=None,
        preferenceset=None,
    ):
        CommonTimetablePreferenceForm.__init__(
            self,
            data,
            files,
            auto_id,
            prefix,
            initial,
            error_class,
            label_suffix,
            empty_permitted,
            TeacherTimePreference,
            "teacher",
            Teacher,
            teacher,
            preferenceset,
        )

    def teacher(self):
        return self.owner()


class GroupTimetablePreferenceForm(CommonTimetablePreferenceForm):
    def __init__(
        self,
        data=None,
        files=None,
        auto_id="id_%s",
        prefix=None,
        initial=None,
        error_class=ErrorList,
        label_suffix=":",
        empty_permitted=False,
        group=None,
        preferenceset=None,
    ):
        CommonTimetablePreferenceForm.__init__(
            self,
            data,
            files,
            auto_id,
            prefix,
            initial,
            error_class,
            label_suffix,
            empty_permitted,
            GroupTimePreference,
            "group",
            Group,
            group,
            preferenceset,
        )

    def group(self):
        return self.owner()


class TagTimetablePreferenceForm(CommonTimetablePreferenceForm):
    class Media:
        js = ("js/jquery-1.7.1.min.js", "js/preferences.js")
        css = {"all": ("css/teacher_preferences.css",)}

    def __init__(
        self,
        data=None,
        files=None,
        auto_id="id_%s",
        prefix=None,
        initial=None,
        error_class=ErrorList,
        label_suffix=":",
        empty_permitted=False,
        tag=None,
        preferenceset=None,
    ):
        CommonTimetablePreferenceForm.__init__(
            self,
            data,
            files,
            auto_id,
            prefix,
            initial,
            error_class,
            label_suffix,
            empty_permitted,
            TagTimePreference,
            "tag",
            Tag,
            tag,
            preferenceset,
            level_choices=ALL_LEVEL_CHOICES,
        )

    def tag(self):
        return self.owner()


TeacherValuePreferenceFormset = forms.models.modelformset_factory(
    TeacherValuePreference, form=TeacherValuePreferenceForm, extra=1, can_delete=True
)

TeacherDescriptivePreferenceFormset = forms.models.modelformset_factory(
    TeacherDescriptivePreference,
    form=TeacherDescriptivePreferenceForm,
    extra=1,
    can_delete=True,
)


class ShortTVPForm(forms.models.ModelForm):
    level = forms.ChoiceField(
        initial="WANT", choices=PREFERENCELEVELS, widget=forms.HiddenInput()
    )

    class Meta:
        model = TeacherValuePreference
        fields = ["teacher", "preferenceset", "level", "weight"]
        widgets = {
            "teacher": forms.HiddenInput(),
            "preferenceset": forms.HiddenInput(),
            "level": forms.HiddenInput(),
            "weight": forms.HiddenInput(),
        }
        initial = {"level": "WANT"}


ShortTVPFormset = forms.models.modelformset_factory(
    TeacherValuePreference, form=ShortTVPForm, extra=1, can_delete=True
)


class ShortDVPForm(forms.models.ModelForm):
    value = forms.CharField(label="", widget=forms.Textarea())

    level = forms.ChoiceField(
        initial="WANT", choices=PREFERENCELEVELS, widget=forms.HiddenInput()
    )

    class Meta:
        model = TeacherDescriptivePreference
        fields = ["teacher", "preferenceset", "level", "typename", "weight", "value"]
        widgets = {
            "teacher": forms.HiddenInput(),
            "preferenceset": forms.HiddenInput(),
            # 'level': forms.HiddenInput(initial='WANT'),
            "typename": forms.HiddenInput(),
            "weight": forms.HiddenInput(),
            "value": forms.Textarea(),
        }
        initial = {"level": "WANT"}


ShortTDPFormset = forms.models.modelformset_factory(
    TeacherDescriptivePreference, form=ShortDVPForm, extra=1, max_num=1
)


class TeacherPreferenceForm(forms.Form):
    class Media:
        js = ("js/jquery-1.7.1.min.js", "js/preferences.js")
        css = {"all": ("css/teacher_preferences.css",)}

    def __init__(
        self,
        data=None,
        files=None,
        auto_id="id_%s",
        prefix=None,
        initial=None,
        error_class=ErrorList,
        label_suffix=":",
        empty_permitted=False,
        teacher=None,
        preferenceset=None,
    ):
        forms.Form.__init__(
            self,
            data,
            files,
            auto_id,
            prefix,
            initial,
            error_class,
            label_suffix,
            empty_permitted,
        )
        if prefix is None:
            prefix = ""
        initial = {}
        self.timePreferences = TeacherTimetablePreferenceForm(
            data=data,
            files=None,
            auto_id="id_%s",
            prefix=prefix + "tp",
            initial=None,
            error_class=ErrorList,
            label_suffix=":",
            empty_permitted=False,
            teacher=teacher,
            preferenceset=preferenceset,
        )
        teacher = self.timePreferences.teacher()
        preferenceset = self.timePreferences.preferenceset()
        val_prefs = TeacherValuePreference.objects.filter(
            teacher=teacher, preferenceset=preferenceset
        )
        desc_prefs = TeacherDescriptivePreference.objects.filter(
            teacher=teacher, preferenceset=preferenceset
        )
        initial["teacher"] = teacher.id
        initial["preferenceset"] = preferenceset.id
        foo_formset = ShortTDPFormset(
            data=data,
            queryset=desc_prefs,
            prefix=prefix + "dp",
            initial=[initial] * (len(desc_prefs) + 1),
        )
        self.descriptivePreferences = foo_formset
        # raise Exception("Bah!" + foo_formset.as_table())
        self.subforms = [self.timePreferences, self.descriptivePreferences]

    def as_table(self):
        return mark_safe("\n".join([f.as_table() for f in self.subforms]))

    def clean(self):
        for f in self.subforms:
            f.clean()

    def full_clean(self):
        # is_clean = super(TeacherPreferenceForm, self).full_clean()
        for fs in self.subforms:
            fs.full_clean()

    def is_valid(self):
        v = True
        for f in self.subforms:
            if f.is_bound and not f.is_valid():
                v = False
        return v

    def teacher(self):
        return self.timePreferences.teacher()

    def preferenceset(self):
        return self.timePreferences.preferenceset()

    def save(self, commit=True):
        canSave = True
        for f in self.subforms:
            if not f.is_valid and f.is_bound:
                canSave = False
        if canSave and commit:
            for f in self.subforms:
                if f.is_valid():
                    f.save(commit=True)
        return canSave


class GroupPreferenceForm(forms.Form):
    class Media:
        js = ("js/jquery-1.7.1.min.js", "js/preferences.js")
        css = {"all": ("css/teacher_preferences.css",)}

    def __init__(
        self,
        data=None,
        files=None,
        auto_id="id_%s",
        prefix=None,
        initial=None,
        error_class=ErrorList,
        label_suffix=":",
        empty_permitted=False,
        group=None,
        preferenceset=None,
    ):
        forms.Form.__init__(
            self,
            data,
            files,
            auto_id,
            prefix,
            initial,
            error_class,
            label_suffix,
            empty_permitted,
        )
        if prefix is None:
            prefix = ""
        initial = {}
        self.timePreferences = GroupTimetablePreferenceForm(
            data=data,
            files=None,
            auto_id="id_%s",
            prefix=prefix + "tp",
            initial=None,
            error_class=ErrorList,
            label_suffix=":",
            empty_permitted=False,
            group=group,
            preferenceset=preferenceset,
        )
        group = self.timePreferences.group()
        preferenceset = self.timePreferences.preferenceset()
        initial["group"] = group.id
        initial["preferenceset"] = preferenceset.id
        self.subforms = [self.timePreferences]

    def as_table(self):
        return mark_safe("\n".join([f.as_table() for f in self.subforms]))

    def clean(self):
        for f in self.subforms:
            f.clean()

    def full_clean(self):
        for fs in self.subforms:
            fs.full_clean()

    def is_valid(self):
        v = True
        for f in self.subforms:
            v = v and (f.is_valid() or not f.is_bound)
        return v

    def group(self):
        return self.timePreferences.group()

    def preferenceset(self):
        return self.timePreferences.preferenceset()

    def save(self, commit=True):
        canSave = True
        for f in self.subforms:
            if not f.is_valid and f.is_bound:
                canSave = False
        if canSave and commit:
            for f in self.subforms:
                if f.is_valid():
                    f.save(commit=True)
        return canSave


class TagPreferenceForm(forms.Form):
    class Media:
        js = ("js/jquery-1.7.1.min.js", "js/preferences.js")
        css = {"all": ("css/teacher_preferences.css",)}

    def __init__(
        self,
        data=None,
        files=None,
        auto_id="id_%s",
        prefix=None,
        initial=None,
        error_class=ErrorList,
        label_suffix=":",
        empty_permitted=False,
        tag=None,
        preferenceset=None,
    ):
        forms.Form.__init__(
            self,
            data,
            files,
            auto_id,
            prefix,
            initial,
            error_class,
            label_suffix,
            empty_permitted,
        )
        if prefix is None:
            prefix = ""
        initial = {}
        self.timePreferences = TagTimetablePreferenceForm(
            data=data,
            files=None,
            auto_id="id_%s",
            prefix=prefix + "tp",
            initial=None,
            error_class=ErrorList,
            label_suffix=":",
            empty_permitted=False,
            tag=tag,
            preferenceset=preferenceset,
        )
        tag = self.timePreferences.tag()
        preferenceset = self.timePreferences.preferenceset()
        initial["tag"] = tag.id
        initial["preferenceset"] = preferenceset.id
        self.subforms = [self.timePreferences]

    def as_table(self):
        return mark_safe("\n".join([f.as_table() for f in self.subforms]))

    def clean(self):
        for f in self.subforms:
            f.clean()

    def full_clean(self):
        for fs in self.subforms:
            fs.full_clean()

    def is_valid(self):
        v = True
        for f in self.subforms:
            v = v and (f.is_valid() or not f.is_bound)
        return v

    def tag(self):
        return self.timePreferences.tag()

    def preferenceset(self):
        return self.timePreferences.preferenceset()

    def save(self, commit=True):
        canSave = True
        for f in self.subforms:
            if not f.is_valid and f.is_bound:
                canSave = False
        if canSave and commit:
            for f in self.subforms:
                if f.is_valid():
                    f.save(commit=True)
        return canSave


class ActivityForm(forms.ModelForm):
    class Meta:
        model = Activity
        fields = "__all__"


class ActivityLongRequirementsForm(forms.ModelForm):
    class Meta:
        model = Activity
        exclude = ("groups", "locations", "mustNotOverlap", "before", "teachers")

    class Media:
        js = ("js/jquery-1.7.1.min.js", "js/activities.js")

    def __init__(
        self,
        data=None,
        files=None,
        auto_id="id_%s",
        prefix=None,
        initial=None,
        error_class=ErrorList,
        label_suffix=":",
        empty_permitted=False,
        instance=None,
    ):
        super(ActivityLongRequirementsForm, self).__init__(
            data,
            files,
            auto_id,
            prefix,
            initial,
            error_class,
            label_suffix,
            empty_permitted,
            instance,
        )


class ActivityLongRequirementRealizationForm(forms.ModelForm):
    class Meta:
        model = Activity
        exclude = ("groups", "locations", "mustNotOverlap", "before")

    class Media:
        js = ("js/jquery-1.7.1.min.js", "js/activities.js")

    def __init__(
        self,
        data=None,
        files=None,
        auto_id="id_%s",
        prefix=None,
        initial=None,
        error_class=ErrorList,
        label_suffix=":",
        empty_permitted=False,
        instance=None,
    ):
        if prefix is None:
            prefix = ""
        super(ActivityLongRequirementRealizationForm, self).__init__(
            data,
            files,
            auto_id,
            prefix,
            initial,
            error_class,
            label_suffix,
            empty_permitted,
            instance,
        )
        if self.instance is None:
            groupsset = Group.objects.all().order_by("id")
            teachersset = Teacher.objects.all().order_by(
                "user__last_name", "user__first_name"
            )
            activityset = Activity.objects.all()
        else:
            instance = self.instance
            groupsset = instance.groups.all().order_by("id")
            teachersset = instance.teachers.all().order_by(
                "user__last_name", "user__first_name"
            )
            activityset = Activity.objects.filter(id=instance.id)

        class ARForm(forms.ModelForm):
            groups = forms.ModelMultipleChoiceField(queryset=groupsset)
            teachers = forms.ModelMultipleChoiceField(queryset=teachersset)
            activity = forms.ModelChoiceField(
                queryset=activityset, initial=instance.id, widget=forms.HiddenInput()
            )

            class Meta:
                model = ActivityRealization
                fields = "__all__"

        ARFormset = forms.models.modelformset_factory(
            ActivityRealization, form=ARForm, extra=1, can_delete=True
        )
        if instance is not None:
            rs = instance.realizations.all()
        else:
            rs = None
        self.realizations_formset = ARFormset(
            data=data, queryset=rs, prefix=prefix + "-ar", initial=initial
        )

    def as_table(self):
        return mark_safe(
            "\n".join(
                (
                    super(ActivityLongRequirementRealizationForm, self).as_table(),
                    self.realizations_formset.as_table(),
                )
            )
        )

    def clean(self):
        self.realizations_formset.clean()
        return super(ActivityLongRequirementRealizationForm, self).clean()

    def full_clean(self):
        self.realizations_formset.full_clean()
        return super(ActivityLongRequirementRealizationForm, self).full_clean()

    def is_valid(self):
        is_valid = True
        is_valid = (
            is_valid and super(ActivityLongRequirementRealizationForm, self).is_valid()
        )
        is_valid = is_valid and self.realizations_formset.is_valid()
        return is_valid

    def has_changed(self):
        c = super(ActivityLongRequirementRealizationForm, self).has_changed()
        for f in self.realizations_formset.forms:
            c = c or f.has_changed()
            if c:
                return c
        return c

    def save(self, commit=True):
        self.realizations_formset.save(commit)
        return super(ActivityLongRequirementRealizationForm, self).save(commit)


# orig. forms
class ActivityRealizationForm(forms.ModelForm):
    class Meta:
        model = Activity
        exclude = ("groups", "locations", "mustNotOverlap", "before")

    class Media:
        js = ("js/jquery-1.7.1.min.js", "js/activities.js")

    def __init__(
        self,
        data=None,
        files=None,
        auto_id="id_%s",
        prefix=None,
        initial=None,
        error_class=ErrorList,
        label_suffix=":",
        empty_permitted=False,
        instance=None,
    ):
        if prefix is None:
            prefix = ""
        super(ActivityRealizationForm, self).__init__(
            data,
            files,
            auto_id,
            prefix,
            initial,
            error_class,
            label_suffix,
            empty_permitted,
            instance,
        )
        if self.instance is None:
            groupsset = Group.objects.all().order_by("id")
            teachersset = Teacher.objects.all().order_by(
                "user__last_name", "user__first_name"
            )
            activityset = Activity.objects.all()
        else:
            instance = self.instance
            groupsset = instance.groups.all().order_by("id")
            teachersset = instance.teachers.all().order_by(
                "user__last_name", "user__first_name"
            )
            activityset = Activity.objects.filter(id=instance.id)
            # initial_locations = instance.locations.all()
            # print "instance:" + str(instance) + "(" + str(instance.id) + ")"

        class ARForm(forms.ModelForm):
            groups = forms.ModelMultipleChoiceField(queryset=groupsset)
            teachers = forms.ModelMultipleChoiceField(queryset=teachersset)
            activity = forms.ModelChoiceField(
                queryset=activityset, initial=instance.id, widget=forms.HiddenInput()
            )

            class Meta:
                fields = "__all__"
                model = ActivityRealization

        ARFormset = forms.models.modelformset_factory(
            ActivityRealization, form=ARForm, extra=1, can_delete=True
        )
        if instance is not None:
            rs = instance.realizations.all()
        else:
            rs = None
        self.realizations_formset = ARFormset(
            data=data, queryset=rs, prefix=prefix + "-ar", initial=initial
        )

    def as_table(self):
        return mark_safe(
            "\n".join(
                (
                    super(ActivityLongRequirementRealizationForm, self).as_table(),
                    self.realizations_formset.as_table(),
                )
            )
        )

    def clean(self):
        self.realizations_formset.clean()
        return super(ActivityLongRequirementRealizationForm, self).clean()

    def full_clean(self):
        self.realizations_formset.full_clean()
        return super(ActivityLongRequirementRealizationForm, self).full_clean()

    def is_valid(self):
        is_valid = True
        is_valid = (
            is_valid and super(ActivityLongRequirementRealizationForm, self).is_valid()
        )
        is_valid = is_valid and self.realizations_formset.is_valid()
        return is_valid

    def has_changed(self):
        c = super(ActivityLongRequirementRealizationForm, self).has_changed()
        for f in self.realizations_formset.forms:
            c = c or f.has_changed()
            if c:
                return c
        return c

    def save(self, commit=True):
        self.realizations_formset.save(commit)
        return super(ActivityLongRequirementRealizationForm, self).save(commit)


class ActivityMinimalRequirementsForm(ActivityLongRequirementsForm):
    class Meta(ActivityLongRequirementsForm.Meta):
        exclude = ("groups", "locations", "mustNotOverlap", "before", "teachers")
        widgets = {
            "name": forms.HiddenInput(),
            "short_name": forms.HiddenInput(),
            "activityset": forms.HiddenInput(),
            "type": forms.HiddenInput(),
            "duration": forms.HiddenInput(),
            "locations": forms.HiddenInput(),
        }


class ActivityShortForm(forms.ModelForm):
    class Meta(ActivityLongRequirementsForm.Meta):
        model = Activity
        widgets = {
            "teacher": forms.HiddenInput(),
            "name": forms.HiddenInput(),
            "short_name": forms.HiddenInput(),
            "activityset": forms.HiddenInput(),
            "type": forms.HiddenInput(),
            "duration": forms.HiddenInput(),
        }


class ActivityMinimalForm(forms.ModelForm):
    class Meta(ActivityLongRequirementsForm.Meta):
        model = Activity
        exclude = (
            "groups",
            "short_name",
            "locations",
            "mustNotOverlap",
            "before",
            "teachers",
            "activityRealizations",
            "requirements_per_student",
        )
        widgets = {
            "requirements": FilteredSelectMultiple("Zahteve", is_stacked=False),
            "name": forms.HiddenInput(),
            "short_name": forms.HiddenInput(),
            "activityset": forms.HiddenInput(),
            "type": forms.HiddenInput(),
            "duration": forms.HiddenInput(),
        }

    class Media:
        extend = False  # remove this once django is fixed. See below.
        css = {"all": ("admin/css/forms.css",)}
        js = (
            "admin/js/jsi18n.js",
            "admin/js/vendor/jquery/jquery.js",
            "admin/js/jquery.init.js",
            "admin/js/core.js",
            "admin/js/SelectBox.js",
            "admin/js/SelectFilter2.js",
        )


class RealizationMultipleModelGroupChoiceField(forms.ModelMultipleChoiceField):
    """
    Override representation of objects in the MultipleModelChoiceField.
    """

    def label_from_instance(self, obj):
        return "{0} ({1})".format(obj.short_name, obj.size)


def realization_formset(activity, timetable=None):
    a = activity

    class ARForm(forms.ModelForm):
        class Media:
            js = ("js/jquery-1.7.1.min.js", "js/activities.js")
            css = {"all": ("css/teacher_preferences.css",)}

        class Meta:
            model = ActivityRealization
            fields = "__all__"

        groups = RealizationMultipleModelGroupChoiceField(
            widget=widgets.SelectMultiple(
                attrs={"class": "realization_group_select"},
            ),
            queryset=a.groups.order_by("short_name"),
            required=False,
        )
        teachers = forms.ModelMultipleChoiceField(
            widget=widgets.SelectMultiple(
                attrs={"class": "realization_teacher_select"},
            ),
            queryset=a.teachers,
            required=False,
        )
        activity = forms.ModelChoiceField(
            queryset=Activity.objects.filter(id=a.id),
            initial=a.id,
            widget=forms.HiddenInput(),
        )
        activity.displayName = a.displayName

        def __init__(self, *args, **kwargs):
            self.allocations = []
            if timetable is not None and "instance" in kwargs:
                self.allocations = timetable.allocations.filter(
                    activityRealization=kwargs["instance"]
                )
            super(ARForm, self).__init__(*args, **kwargs)

    class CheckDeleteUsedInlineFormSet(forms.models.BaseInlineFormSet):
        def _should_delete_form(self, form):
            """Check if the form should be deleted."""

            def has_instance_allocations(form) -> bool:
                """Return True when form instace has allocations."""
                if form.instance is None or form.instance.id is None:
                    return False
                return form.instance.allocations.exists()

            should_delete = super(
                CheckDeleteUsedInlineFormSet, self
            )._should_delete_form(form)
            # The realization with allocations must not be deleted.
            if should_delete and has_instance_allocations(form):
                should_delete = not form.instance.allocations.exists()
            return should_delete

    return forms.models.inlineformset_factory(
        Activity,
        ActivityRealization,
        formset=CheckDeleteUsedInlineFormSet,
        form=ARForm,
        extra=1,
        can_delete=True,
    )


ActivityRequirementsForm = ActivityMinimalRequirementsForm

TeacherPreferenceFormset = forms.formsets.formset_factory(TeacherPreferenceForm)

ActivityFormset = forms.models.modelformset_factory(
    Activity, form=ActivityForm, extra=0, can_delete=False, max_num=5
)

ActivityRequirementsFormset = forms.models.modelformset_factory(
    Activity, form=ActivityRequirementsForm, extra=0, can_delete=False
)

ActivityShortFormset = forms.models.modelformset_factory(
    Activity, form=ActivityShortForm, extra=1, can_delete=True
)

ActivityMinimalFormset = forms.models.modelformset_factory(
    Activity, form=ActivityMinimalForm, extra=0, can_delete=False
)


class TradeRequestForm(forms.ModelForm):
    """Form for creating a new trade request."""
    
    class Meta:
        model = TradeRequest
        fields = [
            'offered_allocation',
            'desired_allocation', 
            'desired_day',
            'desired_start_time',
            'desired_duration',
            'desired_classroom',
            'reason',
            'expires_at'
        ]
        widgets = {
            'reason': forms.Textarea(attrs={'rows': 3, 'placeholder': gettext_lazy('Optional: Why do you want to make this trade?')}),
            'expires_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'desired_day': forms.Select(choices=[('', '--- Any Day ---')] + list(WEEKDAYS)),
            'desired_start_time': forms.Select(choices=[('', '--- Any Time ---')] + list(WORKHOURS)),
            'desired_duration': forms.NumberInput(attrs={'min': 1, 'max': 8, 'placeholder': 'Hours'}),
        }
        labels = {
            'offered_allocation': gettext_lazy('My time slot to trade away'),
            'desired_allocation': gettext_lazy('Specific time slot I want (optional)'),
            'desired_day': gettext_lazy('OR preferred day'),
            'desired_start_time': gettext_lazy('OR preferred start time'),
            'desired_duration': gettext_lazy('OR preferred duration (hours)'),
            'desired_classroom': gettext_lazy('OR preferred classroom'),
            'reason': gettext_lazy('Reason for time slot trade (optional)'),
            'expires_at': gettext_lazy('Request expires (optional)'),
        }
        help_texts = {
            'offered_allocation': 'The time slot you want to exchange with another teacher',
            'desired_allocation': 'A specific time slot you want, or leave empty to specify preferences',
            'desired_day': 'Choose a preferred day for your new time slot',
            'desired_start_time': 'Choose a preferred start time for your new time slot',
            'desired_duration': 'How many hours should your new time slot last?',
            'desired_classroom': 'Choose a preferred classroom for your new time slot',
            'expires_at': 'When should this request automatically expire?',
        }
    
    def __init__(self, *args, **kwargs):
        teacher = kwargs.pop('teacher', None)
        timetable = kwargs.pop('timetable', None)
        super().__init__(*args, **kwargs)
        
        # Store teacher for validation
        self._teacher = teacher
        
        if teacher:
            # Only show allocations that belong to this teacher
            try:
                teacher_allocations = Allocation.objects.filter(
                    activityRealization__teachers=teacher
                ).select_related(
                    'activityRealization__activity',
                    'classroom',
                    'timetable'
                )
                
                # Filter by timetable if provided
                if timetable:
                    teacher_allocations = teacher_allocations.filter(timetable=timetable)
                
                self.fields['offered_allocation'].queryset = teacher_allocations
                
                # For desired allocation, show all allocations from the same timetable(s)
                if timetable:
                    timetables = [timetable]
                else:
                    timetables = list(set(alloc.timetable for alloc in teacher_allocations if alloc.timetable))
                
                if timetables:
                    all_allocations = Allocation.objects.filter(
                        timetable__in=timetables
                    ).exclude(
                        activityRealization__teachers=teacher
                    ).select_related(
                        'activityRealization__activity',
                        'classroom',
                        'timetable'
                    )
                    self.fields['desired_allocation'].queryset = all_allocations
                else:
                    # If no timetables found, show empty queryset
                    self.fields['desired_allocation'].queryset = Allocation.objects.none()
                    
            except Exception as e:
                # If there's any error in queryset setup, provide empty querysets
                self.fields['offered_allocation'].queryset = Allocation.objects.none()
                self.fields['desired_allocation'].queryset = Allocation.objects.none()
        
        # Make desired_allocation not required
        self.fields['desired_allocation'].required = False
        self.fields['expires_at'].required = False
        self.fields['desired_classroom'].required = False
        
        # Populate classroom choices based on timetable
        # Classrooms are related to timetables through allocations
        if timetable:
            from timetable.models import Classroom
            # Get all classrooms used in this timetable
            classroom_ids = Allocation.objects.filter(
                timetable=timetable
            ).values_list('classroom', flat=True).distinct()
            
            classrooms = Classroom.objects.filter(id__in=classroom_ids).order_by('name')
            self.fields['desired_classroom'].queryset = classrooms
        elif teacher:
            # Get classrooms from teacher's timetables
            from timetable.models import Classroom
            teacher_allocations = Allocation.objects.filter(
                activityRealization__teachers=teacher
            )
            
            # Get timetables
            teacher_timetables = teacher_allocations.values_list('timetable', flat=True).distinct()
            
            # Get classrooms used in those timetables
            classroom_ids = Allocation.objects.filter(
                timetable__in=teacher_timetables
            ).values_list('classroom', flat=True).distinct()
            
            classrooms = Classroom.objects.filter(id__in=classroom_ids).order_by('name')
            self.fields['desired_classroom'].queryset = classrooms
    
    def clean(self):
        cleaned_data = super().clean()
        desired_allocation = cleaned_data.get('desired_allocation')
        desired_day = cleaned_data.get('desired_day')
        desired_start_time = cleaned_data.get('desired_start_time')
        desired_duration = cleaned_data.get('desired_duration')
        offered_allocation = cleaned_data.get('offered_allocation')
        
        # Either specify a specific allocation OR criteria, but not both
        has_specific = bool(desired_allocation)
        has_criteria = any([desired_day, desired_start_time, desired_duration])
        
        if not has_specific and not has_criteria:
            raise forms.ValidationError(
                "Please either select a specific allocation you want, or specify your preferences (day/time/duration)."
            )
        
        if has_specific and has_criteria:
            raise forms.ValidationError(
                "Please choose either a specific allocation OR specify criteria, not both."
            )
        
        # Validate that the teacher can trade the offered allocation
        # This validation is done here since we have access to the teacher through the form
        if offered_allocation and hasattr(self, '_teacher') and self._teacher:
            if not offered_allocation.teachers.filter(id=self._teacher.id).exists():
                raise forms.ValidationError(
                    "You can only trade allocations that you teach."
                )
            
            # Check for existing active trade requests for this allocation
            # Only OPEN and PENDING_APPROVAL are considered blocking statuses
            # MATCHED and APPROVED are essentially completed and don't block new requests
            active_statuses = ['OPEN', 'PENDING_APPROVAL']
            existing_requests = TradeRequest.objects.filter(
                requesting_teacher=self._teacher,
                offered_allocation=offered_allocation,
                status__in=active_statuses
            )
            
            # Exclude current instance if editing
            if self.instance and self.instance.pk:
                existing_requests = existing_requests.exclude(pk=self.instance.pk)
            
            if existing_requests.exists():
                # Get the first matching request for better error message
                existing = existing_requests.first()
                raise forms.ValidationError(
                    f"You already have an active trade request ({existing.get_status_display()}) "
                    f"for this time slot. Please cancel or complete it before creating a new one."
                )
            
            # Check for conflicts when specifying time preferences instead of specific allocation
            if not desired_allocation and (desired_day and desired_start_time and desired_duration):
                desired_classroom = cleaned_data.get('desired_classroom')
                timetable = offered_allocation.timetable
                # Calculate requested slot start/end
                req_start = desired_start_time
                req_end = (datetime.combine(date.today(), desired_start_time) + timedelta(hours=desired_duration)).time()
                # Teacher overlap check
                teacher_conflicts = Allocation.objects.filter(
                    timetable=timetable,
                    day=desired_day,
                    activityRealization__teachers__in=offered_allocation.activityRealization.teachers.all()
                ).exclude(id=offered_allocation.id)
                for alloc in teacher_conflicts:
                    alloc_start = alloc.start
                    alloc_end = (datetime.combine(date.today(), alloc.start) + timedelta(hours=alloc.duration)).time()
                    if (req_start < alloc_end and req_end > alloc_start):
                        self.add_error(None, forms.ValidationError(
                            f"❌ Teacher conflict: One of your teachers already has a class overlapping {dict(WEEKDAYS).get(desired_day)} {desired_start_time}-{req_end} - "
                            f"{alloc.activityRealization.activity.name} in {alloc.classroom}."
                        ))
                        break
                # Classroom overlap check
                if desired_classroom:
                    classroom_conflicts = Allocation.objects.filter(
                        timetable=timetable,
                        day=desired_day,
                        classroom=desired_classroom
                    ).exclude(id=offered_allocation.id)
                    for alloc in classroom_conflicts:
                        alloc_start = alloc.start
                        alloc_end = (datetime.combine(date.today(), alloc.start) + timedelta(hours=alloc.duration)).time()
                        if (req_start < alloc_end and req_end > alloc_start):
                            teachers = ', '.join([str(t) for t in alloc.activityRealization.teachers.all()])
                            self.add_error('desired_classroom', forms.ValidationError(
                                f"❌ Classroom conflict: {desired_classroom} is already occupied (overlap) at "
                                f"{dict(WEEKDAYS).get(desired_day)} {desired_start_time}-{req_end} by "
                                f"{alloc.activityRealization.activity.name} ({teachers})."
                            ))
                            break
                # If no conflicts, check if slot is completely free
                if not self._errors:
                    any_allocations = Allocation.objects.filter(
                        timetable=timetable,
                        day=desired_day
                    ).exclude(id=offered_allocation.id)
                    overlap_found = False
                    for alloc in any_allocations:
                        alloc_start = alloc.start
                        alloc_end = (datetime.combine(date.today(), alloc.start) + timedelta(hours=alloc.duration)).time()
                        if (req_start < alloc_end and req_end > alloc_start):
                            overlap_found = True
                            break
                    if not overlap_found:
                        day_str = dict(WEEKDAYS).get(desired_day)
                        classroom_str = f" in {desired_classroom}" if desired_classroom else ""
                        cleaned_data['_slot_is_free'] = True
                        cleaned_data['_free_slot_description'] = f"{day_str} at {desired_start_time}-{req_end}{classroom_str}"
            # If day or time or duration not fully specified, can't check conflicts thoroughly
        
        return cleaned_data


class TradeRequestSearchForm(forms.Form):
    """Form for searching and filtering trade requests."""
    
    STATUS_CHOICES = [
        ('', gettext_lazy('--- Any Status ---')),
        ('OPEN', gettext_lazy('Open')),
        ('MATCHED', gettext_lazy('Matched')),
        ('PENDING_APPROVAL', gettext_lazy('Pending Approval')),
        ('APPROVED', gettext_lazy('Approved')),
        ('REJECTED', gettext_lazy('Rejected')),
        ('CANCELLED', gettext_lazy('Cancelled')),
        ('EXPIRED', gettext_lazy('Expired')),
    ]
    
    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        required=False,
        label=gettext_lazy('Status'),
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    teacher = forms.ModelChoiceField(
        queryset=Teacher.objects.all(),
        required=False,
        label=gettext_lazy('Teacher'),
        empty_label=gettext_lazy("--- Any Teacher ---"),
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    day = forms.ChoiceField(
        choices=[('', gettext_lazy('--- Any Day ---'))] + list(WEEKDAYS),
        required=False,
        label=gettext_lazy('Day'),
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    search = forms.CharField(
        required=False,
        label=gettext_lazy('Search'),
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': gettext_lazy('Search in activity names, reasons...')
        })
    )
    
    relevant_to_me = forms.BooleanField(
        required=False,
        label=gettext_lazy('Show requests I can fulfill'),
        help_text=gettext_lazy('Show only requests where I teach the desired time slot'),
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
