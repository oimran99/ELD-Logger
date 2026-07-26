"""FMCSA Hours-of-Service constants for a property-carrying driver on the
70-hour / 8-day cycle, with no adverse driving conditions.

References (49 CFR Part 395):
  * 11-hour driving limit ............... 395.3(a)(3)(i)
  * 14-hour on-duty window .............. 395.3(a)(2)
  * 30-minute driving break ............. 395.3(a)(3)(ii)
  * 60/70-hour on-duty limit ............ 395.3(b)
  * 34-hour restart (optional) .......... 395.3(c)
"""

# Driving / window limits (hours)
MAX_DRIVE_PER_SHIFT = 11.0          # max driving after 10 consecutive hrs off
MAX_DUTY_WINDOW = 14.0              # cannot drive beyond the 14th on-duty hour
DRIVE_HOURS_BEFORE_BREAK = 8.0      # 30-min break required after 8 hrs driving

# Rest / reset durations (hours)
BREAK_DURATION = 0.5               # the mandatory 30-minute break
DAILY_RESET = 10.0                # consecutive off-duty hours to reset a shift
CYCLE_RESTART = 34.0              # consecutive off-duty hours to reset the cycle

# Cycle limit (hours in the rolling 8-day window)
CYCLE_LIMIT_HOURS = 70.0

# Operational assumptions
FUEL_INTERVAL_MILES = 1000.0      # fuel at least once every 1,000 miles
FUEL_DURATION = 0.5               # on-duty time budgeted for fueling
PICKUP_DROPOFF_DURATION = 1.0     # on-duty time for pickup and for drop-off

# Any non-driving period at least this long resets the 8-hour driving clock
# (post-2020 rule: the break may be satisfied by any non-driving status).
BREAK_QUALIFYING_MIN = 0.5
