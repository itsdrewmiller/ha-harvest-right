"""Constants for the Harvest Right integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "harvest_right"

API_BASE = "https://prod.harvestrightapp.com"
MQTT_BROKER = "mqtt.harvestrightapp.com"
MQTT_PORT = 8883
MQTT_KEEPALIVE = 20
MQTT_SESSION_EXPIRY = 60

# Config entry data keys
CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_CUSTOMER_ID = "customer_id"

# Options keys
OPT_TEMPERATURE_UNIT = "temperature_unit"
OPT_SCAN_INTERVAL = "scan_interval"

TEMP_UNIT_FAHRENHEIT = "fahrenheit"
TEMP_UNIT_CELSIUS = "celsius"
DEFAULT_TEMPERATURE_UNIT = TEMP_UNIT_FAHRENHEIT

# How often to re-poll the REST dryer list to discover added/removed dryers.
DEFAULT_SCAN_INTERVAL_MINUTES = 30
MIN_SCAN_INTERVAL_MINUTES = 5
MAX_SCAN_INTERVAL_MINUTES = 360

# A dryer is considered offline if no MQTT message has arrived for this long.
# The watchdog republishes "on" every 30s and a connected adapter answers
# within seconds, so 5 minutes (10 missed cycles) is a safe offline signal.
STALE_THRESHOLD = timedelta(minutes=5)

# Service name for forcing a telemetry refresh.
SERVICE_REFRESH = "refresh"

# Event fired on the HA bus when a batch-summary MQTT message is received.
EVENT_BATCH_SUMMARY = f"{DOMAIN}_batch_summary"

# Screen number to state name mapping
# Note: spec listed "Offline" as screen 0, but offline means no telemetry.
# Actual device screen numbers are offset by -1 from the spec.
# Screens 5/6 show "Drying" by default; the `df` bitmask determines sub-states.
SCREEN_STATES: dict[int, str] = {
    0: "Ready to Start",
    1: "Load Trays",
    2: "Rotate Trays",
    3: "Warming Trays",
    4: "Freezing",
    5: "Drying (Heating)",
    6: "Drying (Max Temp)",
    7: "Extra Dry Time",
    8: "Batch Complete",
    9: "Defrosting",
    10: "Defrosted",
    12: "System Setup",
    13: "Time Setup",
    14: "Factory Setup",
    15: "Testing",
    16: "Settings",
    17: "Restarting",
    18: "Preparing",
    19: "Setup",
    20: "Welcome",
    21: "Authorizing",
    22: "Recipe Creation",
    23: "Unable to Achieve Vacuum",
    24: "Freeze Dryer Not Cooling",
    25: "Not Detecting Heat",
    26: "Time Expired",
}

# df bitmask flags (from mobile app main.dart.js)
# The `df` telemetry field is a bitmask that modifies the display label
# for drying screens (5 and 6).
DF_VAC_FREEZE = 1  # bit 0: Vac Freeze drying mode
DF_FINAL_DRY = 4  # bit 2: Final Dry Time active
DF_EXTRA_DRY = 8  # bit 3: Extra Dry Time active
DF_DEHYDRATE = 64  # bit 6: Dehydrate mode

# Drying sub-state labels get_drying_state() can return.
DRYING_STATE_DEHYDRATING = "Dehydrating"
DRYING_STATE_EXTRA_DRY = "Extra Dry Time"
DRYING_STATE_DEFAULT = "Drying"


def get_drying_state(screen: int, df: int) -> str:
    """Determine the drying sub-state from the df bitmask.

    The mobile app checks bits in this priority order (from main.dart.js):
    1. df & 1  -> "Drying" (Vac Freeze mode)
    2. df & 64 -> "Dehydrating"
    3. df & 8  -> "Extra Dry Time"
    4. else    -> fall back to screen-based label

    When no special bit is set, returns the default SCREEN_STATES label
    (e.g. "Drying (Heating)" or "Drying (Max Temp)").
    """
    if df & DF_DEHYDRATE:
        return DRYING_STATE_DEHYDRATING
    if df & DF_EXTRA_DRY:
        return DRYING_STATE_EXTRA_DRY
    return SCREEN_STATES.get(screen, DRYING_STATE_DEFAULT)


# Full set of values the "state" ENUM sensor can report. Includes the bare
# "Drying" fallback that get_drying_state() can return for an unmapped screen.
STATE_OPTIONS: list[str] = list(
    dict.fromkeys(
        [
            *SCREEN_STATES.values(),
            DRYING_STATE_EXTRA_DRY,
            DRYING_STATE_DEHYDRATING,
            DRYING_STATE_DEFAULT,
            "Unknown",
        ]
    )
)

# Screen sets for binary sensor conditions
RUNNING_SCREENS = {1, 2, 3, 4, 5, 6, 7, 18}
FREEZING_SCREENS = {4}
DRYING_SCREENS = {5, 6}
ERROR_SCREENS = {23, 24, 25, 26}
