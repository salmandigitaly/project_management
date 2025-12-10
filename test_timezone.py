"""
Test script to verify IST timezone conversion
"""
import sys
sys.path.insert(0, 'e:/NEW_PM/project-management - Copy (2)')

from datetime import datetime, timezone
from app.core.timezone_utils import utc_to_ist, format_datetime_ist, get_ist_now

# Test 1: Convert UTC to IST
print("=" * 60)
print("TEST 1: UTC to IST Conversion")
print("=" * 60)

# Create a UTC datetime (like what's stored in database)
utc_time = datetime(2025, 12, 9, 9, 37, 11, 545000, tzinfo=timezone.utc)
print(f"UTC Time:  {utc_time}")
print(f"UTC ISO:   {utc_time.isoformat()}")

# Convert to IST
ist_time = utc_to_ist(utc_time)
print(f"IST Time:  {ist_time}")
print(f"IST ISO:   {ist_time.isoformat()}")

# Test 2: Format datetime as IST string
print("\n" + "=" * 60)
print("TEST 2: Format as IST String")
print("=" * 60)

formatted = format_datetime_ist(utc_time)
print(f"Formatted IST: {formatted}")

# Test 3: Current time
print("\n" + "=" * 60)
print("TEST 3: Current IST Time")
print("=" * 60)

current_ist = get_ist_now()
print(f"Current IST: {current_ist}")
print(f"Current IST ISO: {current_ist.isoformat()}")

# Test 4: Naive datetime (no timezone)
print("\n" + "=" * 60)
print("TEST 4: Naive Datetime Conversion")
print("=" * 60)

naive_time = datetime(2025, 12, 9, 9, 37, 11)
print(f"Naive Time: {naive_time}")
ist_from_naive = utc_to_ist(naive_time)
print(f"IST Time:   {ist_from_naive}")
print(f"IST ISO:    {ist_from_naive.isoformat()}")

print("\n" + "=" * 60)
print("✅ All tests completed!")
print("=" * 60)
