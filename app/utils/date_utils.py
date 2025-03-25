from datetime import datetime

def parse_date(date_str):
    """Convert a date string to a datetime object"""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, '%Y-%m-%d')
    except (ValueError, TypeError):
        return None 