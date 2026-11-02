from django import template

from ..legal import render_legal_text


register = template.Library()


@register.filter
def legal_text(value):
    """Render escaped, allow-listed markup for legal body copy."""
    return render_legal_text(value)
