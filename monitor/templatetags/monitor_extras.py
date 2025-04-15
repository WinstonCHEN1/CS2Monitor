from django import template

register = template.Library()

@register.filter
def sub(value, arg):
    return float(value) - float(arg)

@register.filter
def div(value, arg):
    return float(value) / float(arg)

@register.filter
def mul(value, arg):
    return float(value) * float(arg) 