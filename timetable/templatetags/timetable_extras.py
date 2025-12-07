import re

from django import template
from django.conf import settings
from django.utils.safestring import mark_safe

register = template.Library()

class_re = re.compile(r'(?<=class=["\'])(.*)(?=["\'])')


@register.filter
def add_class(value, css_class):
    string = str(value)  # value.decode('latin-1')
    match = class_re.search(string)
    if match:
        m = re.search(
            r"^%s$|^%s\s|\s%s\s|\s%s$" % (css_class, css_class, css_class, css_class),
            match.group(1),
        )
        if not m:
            return mark_safe(class_re.sub(match.group(1) + " " + css_class, string))
    else:
        p = string.find(">")
        if p > -1:
            if string[(p - 1) :] == "/>":
                string = (
                    string[: (p - 1)]
                    + ' class="{0}"/>'.format(css_class)
                    + string[p + 1 :]
                )
            else:
                string = (
                    string[:p] + ' class="{0}">'.format(css_class) + string[p + 1 :]
                )
        return mark_safe(string)
    return value.encode("latin-1")


@register.tag
def value_from_settings(parser, token):
    try:
        # split_contents() knows not to split quoted strings.
        tag_name, var = token.split_contents()
    except ValueError:
        raise template.TemplateSyntaxError(
            "%r tag requires a single argument" % token.contents.split()[0]
        )
    return ValueFromSettings(var)


@register.filter
def format_time(time_str):
    """Format time string to be more readable (e.g., '08:00' -> '8:00 AM')"""
    if not time_str:
        return time_str
    try:
        hour, minute = time_str.split(':')
        hour = int(hour)
        if hour == 0:
            return f"12:{minute} AM"
        elif hour < 12:
            return f"{hour}:{minute} AM"
        elif hour == 12:
            return f"12:{minute} PM"
        else:
            return f"{hour-12}:{minute} PM"
    except (ValueError, AttributeError):
        return time_str


@register.filter
def format_duration(hours):
    """Format duration to be more readable"""
    if not hours:
        return ""
    hours = int(hours)
    if hours == 1:
        return "1 hour"
    else:
        return f"{hours} hours"


@register.filter
def format_day_short(day):
    """Convert day to short format (e.g., 'Monday' -> 'Mon')"""
    day_map = {
        'Monday': 'Mon',
        'Tuesday': 'Tue', 
        'Wednesday': 'Wed',
        'Thursday': 'Thu',
        'Friday': 'Fri',
        'Saturday': 'Sat',
        'Sunday': 'Sun'
    }
    return day_map.get(day, day)


@register.filter
def truncate_activity(activity_name, length=30):
    """Truncate activity name to specified length with ellipsis"""
    if not activity_name:
        return ""
    if len(activity_name) <= length:
        return activity_name
    return activity_name[:length-3] + "..."


@register.filter
def status_icon(status):
    """Return FontAwesome icon for trade request status"""
    icons = {
        'OPEN': 'fas fa-clock',
        'MATCHED': 'fas fa-handshake',
        'PENDING_APPROVAL': 'fas fa-hourglass-half',
        'APPROVED': 'fas fa-check-circle',
        'REJECTED': 'fas fa-times-circle',
        'CANCELLED': 'fas fa-ban',
        'EXPIRED': 'fas fa-calendar-times'
    }
    return icons.get(status, 'fas fa-question-circle')


@register.filter
def time_since_short(date):
    """Show time since in a short format"""
    if not date:
        return ""
    
    from django.utils import timezone
    import datetime
    
    now = timezone.now()
    diff = now - date
    
    if diff.days > 0:
        return f"{diff.days}d ago"
    elif diff.seconds > 3600:
        hours = diff.seconds // 3600
        return f"{hours}h ago"
    elif diff.seconds > 60:
        minutes = diff.seconds // 60
        return f"{minutes}m ago"
    else:
        return "just now"


@register.filter
def filter_by_status(queryset, status):
    """Filter a queryset by status"""
    return [item for item in queryset if item.status == status]


class ValueFromSettings(template.Node):
    def __init__(self, var):
        self.arg = template.Variable(var)

    def render(self, context):
        return settings.__getattr__(str(self.arg))
