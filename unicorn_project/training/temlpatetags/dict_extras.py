from django import template

register = template.Library()

@register.filter(name="get")
def get_item(mapping, key):
    """
    Safe dict lookup in templates: {{ mydict|get:"key" }}
    Returns "" if not a mapping or key missing.
    """
    try:
        return mapping.get(key, "")
    except Exception:
        return ""

@register.filter(name="dot")
def dot(obj, attr):
    """
    Safe getattr in templates: {{ obj|dot:"field_name" }}
    Returns "" if attribute missing.
    """
    try:
        return getattr(obj, attr)
    except Exception:
        return ""

@register.simple_tag
def param_replace(request, **kwargs):
    """
    Common helper for sortable/paginated links:
    Usage: <a href="?{% param_replace request o='date' dir='asc' %}">
    """
    if not hasattr(request, "GET"):
        return ""
    params = request.GET.copy()
    for k, v in kwargs.items():
        if v is None or v == "":
            params.pop(k, None)
        else:
            params[k] = v
    return params.urlencode()

def split_name(full_name):
    """
    Returns (first, last). Very simple split: first token = first; rest = last.
    """
    if not full_name:
        return ("","")
    parts = str(full_name).strip().split()
    if len(parts) == 1:
        return (parts[0], "")
    return (parts[0], " ".join(parts[1:]))
