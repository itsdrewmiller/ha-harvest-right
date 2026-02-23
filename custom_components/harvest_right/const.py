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
    9: "Remove Trays",
    10: "Defrosting",
    11: "Defrosted",
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

# Screen sets for binary sensor conditions
RUNNING_SCREENS = {1, 2, 3, 4, 5, 6, 7, 18}
FREEZING_SCREENS = {4}
DRYING_SCREENS = {5, 6}
ERROR_SCREENS = {23, 24, 25, 26}

PLATFORMS = ["sensor", "binary_sensor"]
