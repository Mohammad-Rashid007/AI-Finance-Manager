from django import template
from django.template.defaultfilters import stringfilter
import locale
from datetime import datetime, date
from dateutil.relativedelta import relativedelta

register = template.Library()

@register.filter
def min_value(value, max_value):
    """
    Returns the minimum of value and max_value
    """
    try:
        return min(float(value), float(max_value))
    except (ValueError, TypeError):
        return 0

@register.filter
def multiply(value, arg):
    """
    Multiplies the value by the argument
    """
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return '' 

@register.filter
def percentage(value, total):
    """
    Calculates percentage of value against total
    Returns a formatted percentage with 1 decimal place
    """
    try:
        if float(total) == 0:
            return '0.0'
        percent = (float(value) / float(total)) * 100
        return f"{percent:.1f}"
    except (ValueError, TypeError):
        return '0.0'

@register.filter
def subtract(value, arg):
    """
    Subtracts the argument from the value
    """
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def monthly_amount(value, target_date):
    """
    Calculates the monthly amount needed to reach a target by the given date
    """
    try:
        if not target_date or not isinstance(target_date, date):
            return 0
            
        # Get current date and calculate months between now and target date
        today = date.today()
        if target_date <= today:
            return value  # Return full amount if date is in the past
            
        # Calculate months between dates
        months = (target_date.year - today.year) * 12 + (target_date.month - today.month)
        if months <= 0:
            return value
            
        return float(value) / months
    except (ValueError, TypeError):
        return 0 

@register.filter
def format_percentage(value):
    """
    Format number as percentage with 1 decimal place
    Example: 76.55 -> 76.6%
    """
    try:
        formatted = float(value)
        return f"{formatted:.1f}%"
    except (ValueError, TypeError):
        return "0.0%" 

@register.filter
def abs(value):
    """
    Returns the absolute value of a number
    """
    try:
        return __builtins__['abs'](float(value))
    except (ValueError, TypeError):
        return 0 