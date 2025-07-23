"""
Date parsing utilities for Echo bot.
"""

from datetime import datetime
from typing import Optional
from dateutil import parser as dateutil_parser


def parse_dd_mm_yyyy(date_string: str) -> datetime:
    """
    Parse date string in DD.MM.YYYY format.
    
    :param date_string: Date string to parse
    :return: Parsed datetime object
    :raises ValueError: If date format is invalid
    """
    try:
        return datetime.strptime(date_string.strip(), "%d.%m.%Y")
    except ValueError:
        raise ValueError(f"Date '{date_string}' must be in DD.MM.YYYY format")


def parse_flexible_date(date_string: str) -> Optional[datetime]:
    """
    Parse date string using flexible parsing.
    
    :param date_string: Date string to parse
    :return: Parsed datetime object or None if parsing fails
    """
    try:
        return dateutil_parser.parse(date_string)
    except (ValueError, TypeError):
        return None


def is_valid_cutoff_date(date_obj: datetime) -> bool:
    """
    Check if a date is valid as a cutoff date (not in the future).
    
    :param date_obj: Date object to validate
    :return: True if valid, False otherwise
    """
    return date_obj <= datetime.now()


def format_date_readable(date_obj: datetime) -> str:
    """
    Format datetime object to human-readable string.
    
    :param date_obj: Date object to format
    :return: Formatted date string
    """
    return date_obj.strftime("%d %B %Y")


def get_date_range_description(start_date: datetime, end_date: datetime) -> str:
    """
    Get a description of a date range.
    
    :param start_date: Start date
    :param end_date: End date
    :return: Human-readable date range description
    """
    start_str = format_date_readable(start_date)
    end_str = format_date_readable(end_date)
    
    if start_date.date() == end_date.date():
        return f"on {start_str}"
    else:
        return f"from {start_str} to {end_str}"