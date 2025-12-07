from django import template
from timetable.models import ResourceGroup

register = template.Library()


@register.inclusion_tag('friprosveta/resource_groups_widget.html')
def render_resource_groups(form_field, activity_id):
    """
    Render resources grouped by their resource groups.
    
    Args:
        form_field: The requirements form field
        activity_id: The activity ID for unique field naming
    
    Returns:
        Context for the template
    """
    # Get all resource groups ordered by order and name
    resource_groups = ResourceGroup.objects.prefetch_related('resources').all()
    
    # Get the selected resources (if any)
    selected_ids = []
    if form_field.value():
        selected_ids = [int(id) for id in form_field.value()]
    
    # Organize resources by group
    grouped_resources = []
    ungrouped_resources = []
    
    for group in resource_groups:
        resources = []
        for resource in group.resources.all():
            resources.append({
                'id': resource.id,
                'name': resource.name,
                'selected': resource.id in selected_ids
            })
        
        if resources:
            grouped_resources.append({
                'group': group,
                'resources': resources
            })
    
    # Get ungrouped resources
    for choice in form_field.field.queryset.filter(group__isnull=True):
        ungrouped_resources.append({
            'id': choice.id,
            'name': choice.name,
            'selected': choice.id in selected_ids
        })
    
    return {
        'form_field': form_field,
        'activity_id': activity_id,
        'grouped_resources': grouped_resources,
        'ungrouped_resources': ungrouped_resources,
    }
