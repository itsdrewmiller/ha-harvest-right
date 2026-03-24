"""Constants for the Harvest Right integration."""

DOMAIN = "harvest_right"

API_BASE = "https://prod.harvestrightapp.com"
MQTT_BROKER = "mqtt.harvestrightapp.com"
MQTT_PORT = 8883
MQTT_KEEPALIVE = 20
MQTT_SESSION_EXPIRY = 60

CONF_EMAIL = "email"
CONF_PASSWORD = "password"

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
DF_VAC_FREEZE = 1      # bit 0: Vac Freeze drying mode
DF_FINAL_DRY = 4       # bit 2: Final Dry Time active
DF_EXTRA_DRY = 8       # bit 3: Extra Dry Time active
DF_DEHYDRATE = 64      # bit 6: Dehydrate mode


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
        return "Dehydrating"
    if df & DF_EXTRA_DRY:
        return "Extra Dry Time"
    return SCREEN_STATES.get(screen, "Drying")


# Screen sets for binary sensor conditions
RUNNING_SCREENS = {1, 2, 3, 4, 5, 6, 7, 18}
FREEZING_SCREENS = {4}
DRYING_SCREENS = {5, 6}
ERROR_SCREENS = {23, 24, 25, 26}

PLATFORMS = ["sensor", "binary_sensor"]
