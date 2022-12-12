from collections import OrderedDict

from django import forms
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.forms import widgets
from django.forms.boundfield import BoundField
from django.forms.utils import ErrorList
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _

from timetable.models import (
    PREFERENCELEVELS,
    WEEKDAYS,
    WORKHOURS,
    Activity,
    ActivityRealization,
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
        for (hour, hourname) in WORKHOURS:
            self.levelFieldsByHourDay[hour] = OrderedDict()
            self.weightFieldsByHourDay[hour] = OrderedDict()
            for (day, dayname) in WEEKDAYS:
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
        for (day, dayname) in WEEKDAYS:
            last_weight = 0.0
            last_level = None
            duration = 0
            start = WORKHOURS[0][0]
            for (hour, hourname) in WORKHOURS:
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
        for (day, dayname) in WEEKDAYS:
            s += "<th class='day'>{0}</th>".format(_(dayname), dayname)
        s += "</tr>"
        for (hour, hourname) in WORKHOURS:
            s += "<tr>\n"
            s += "    <td>{0}</td>\n".format(hourname)
            for (day, dayname) in WEEKDAYS:
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
        #        print "validating preferences"
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
            should_delete = super(
                CheckDeleteUsedInlineFormSet, self
            )._should_delete_form(form)
            # try:
            #     raw_pk_value = form._raw_value(pk_name)
            # clean() for different types of PK fields can sometimes return
            # the model instance, and sometimes the PK. Handle either.
            #     pk_value = form.fields[pk_name].clean(raw_pk_value)
            #     pk_value = getattr(pk_value, 'pk', pk_value)
            #     obj = self._existing_object(pk_value)
            # except:
            #     obj = None
            if form.instance is not None and should_delete:
                if form.instance.allocations.count() > 0:
                    should_delete = False
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
