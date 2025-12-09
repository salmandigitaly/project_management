"""
Timezone utility functions for converting UTC to IST
"""
from datetime import datetime, timezone, timedelta
from typing import Optional

# Indian Standard Time (UTC+5:30)
IST = timezone(timedelta(hours=5, minutes=30))


def utc_to_ist(dt: Optional[datetime]) -> Optional[datetime]:
    """
    Convert UTC datetime to IST
    
    Args:
        dt: UTC datetime (can be naive or aware)
        
    Returns:
        IST datetime or None
    """
    if dt is None:
        return None
    
    # If naive datetime, assume it's UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    
    # Convert to IST
    return dt.astimezone(IST)


def format_datetime_ist(dt: Optional[datetime]) -> Optional[str]:
    """
    Format datetime as IST ISO string
    
    Args:
        dt: UTC datetime
        
    Returns:
        ISO formatted string in IST or None
        Example: "2025-12-09T15:07:11.545+05:30"
    """
    if dt is None:
        return None
    
    ist_dt = utc_to_ist(dt)
    return ist_dt.isoformat()


def get_ist_now() -> datetime:
    """
    Get current time in IST (timezone-aware)
    
    Returns:
        Current IST datetime
    """
    return datetime.now(IST)
