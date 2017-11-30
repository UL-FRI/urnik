import re
from django.conf import settings
from django.utils.safestring import mark_safe
from django import template
register = template.Library()


class_re = re.compile(r'(?<=class=["\'])(.*)(?=["\'])')


@register.filter
def add_class(value, css_class):
    string = str(value) # value.decode('latin-1')
    match = class_re.search(string)
    if match:
        m = re.search(r'^%s$|^%s\s|\s%s\s|\s%s$' % (css_class, css_class, 
                                                    css_class, css_class), match.group(1))
        if not m:
            return mark_safe(class_re.sub(match.group(1) + " " + css_class, 
                                          string))
    else:
        p = string.find('>')
        if p > -1:
            if string[(p-1):] == '/>':
                string = string[:(p-1)]+ ' class="{0}"/>'.format(css_class) + string[p+1:]
            else:
                string = string[:p] + ' class="{0}">'.format(css_class) + string[p+1:]
        return mark_safe(string)
    return value.encode('latin-1')


@register.tag
def value_from_settings(parser, token):
    try:
        # split_contents() knows not to split quoted strings.
        tag_name, var = token.split_contents()
    except ValueError:
        raise template.TemplateSyntaxError("%r tag requires a single argument" % token.contents.split()[0])
    return ValueFromSettings(var)


class ValueFromSettings(template.Node):
    def __init__(self, var):
        self.arg = template.Variable(var)

    def render(self, context):
        return settings.__getattr__(str(self.arg))
