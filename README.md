# Harvest Right for Home Assistant

A Home Assistant custom integration for [Harvest Right](https://harvestright.com) freeze dryers. Connects to Harvest Right's cloud services to provide real-time sensor data from your freeze dryer.

## Features

**Sensors:**
- Temperature
- Vacuum Pressure (mTorr)
- Batch Elapsed Time
- Phase Elapsed Time
- Progress (%)
- WiFi Signal Strength (dBm)
- State (Ready, Freezing, Drying, Batch Complete, etc.)
- Batch Name
- Batch Count

**Binary Sensors:**
- Running
- Freezing
- Drying
- Error
- Online

Each freeze dryer appears as its own device in Home Assistant with model, serial number, and firmware info.

## Installation

### HACS (recommended)

1. Open HACS in Home Assistant
2. Click the three-dot menu in the top right and select **Custom repositories**
3. Paste `https://github.com/itsdrewmiller/ha-harvest-right` and select **Integration** as the category
4. Click **Add**
5. Find "Harvest Right" in the HACS integrations list and click **Download**
6. Restart Home Assistant

### Manual

Copy the `custom_components/harvest_right` folder into your Home Assistant `config/custom_components/` directory and restart Home Assistant.

## Setup

1. Go to **Settings** > **Devices & Services** > **Add Integration**
2. Search for **Harvest Right**
3. Enter your Harvest Right account email and password
4. Your freeze dryer(s) will be discovered automatically

## How it works

The integration uses Harvest Right's REST API for authentication and device discovery, and connects to their MQTT broker over WebSocket for real-time telemetry updates. Sensor data is pushed from the freeze dryer every ~15 seconds while it's running.

## Requirements

- A Harvest Right freeze dryer with WiFi connectivity
- A Harvest Right account (the same one you use in the Harvest Right app)
- Home Assistant 2024.1.0 or newer
