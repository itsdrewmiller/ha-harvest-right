# Harvest Right for Home Assistant

A Home Assistant custom integration for [Harvest Right](https://harvestright.com) freeze dryers. It connects to Harvest Right's cloud services to provide real-time, push-based sensor data for each of your freeze dryers.

## Features

Each freeze dryer registered to your account appears as its own Home Assistant device.

**Sensors**

- Temperature
- Vacuum pressure (mTorr)
- Batch elapsed time
- Phase elapsed time
- Progress (%)
- State (Ready to Start, Freezing, Drying, Batch Complete, error states, …)
- Batch name
- Batch count

**Binary sensors**

- Running
- Freezing
- Drying
- Error
- Online — reflects whether live telemetry is currently being received

**Diagnostic sensors** (Wi-Fi signal, screen number, mode, etc.) are also created and grouped under the device's diagnostics section. Most are disabled by default.

**Services**

- `harvest_right.refresh` — ask the dryer(s) to send fresh telemetry immediately.

**Other**

- A `harvest_right_batch_summary` event is fired on the Home Assistant event bus when a batch finishes, so you can build automations around completed batches.
- Config entry **diagnostics** and **system health** support for easier troubleshooting.

## Installation

### HACS (recommended)

If you don't have HACS installed yet, follow the [HACS installation guide](https://hacs.xyz/docs/use/) first.

1. Open HACS in Home Assistant.
2. Click the three-dot menu in the top right and select **Custom repositories**.
3. Paste the repository URL and select **Integration** as the category.
4. Click **Add**.
5. Find "Harvest Right" in the HACS integrations list and click **Download**.
6. Restart Home Assistant.

### Manual

Copy the `custom_components/harvest_right` folder into your Home Assistant `config/custom_components/` directory and restart Home Assistant.

## Setup

1. Make sure your freeze dryer is **powered on and connected to Wi-Fi**, and is set up in the Harvest Right mobile app — the integration reads the same account.
2. Go to **Settings → Devices & Services → Add Integration**.
3. Search for **Harvest Right**.
4. Enter your Harvest Right account email and password.
5. Your freeze dryer(s) are discovered automatically.

Only the account's long-lived refresh token is stored — your password is not kept on disk. If the session ever expires, Home Assistant will prompt you to re-authenticate.

## Options

After setup, open the integration's **Configure** dialog to set:

- **Temperature unit** — match the unit your dryer's display uses (°F or °C) so readings are labelled correctly.
- **Dryer list refresh interval** — how often the account is re-checked for added or removed dryers. Live telemetry is always pushed instantly regardless of this setting.

## How it works

The integration authenticates against Harvest Right's REST API and subscribes to their MQTT broker over a TLS connection for real-time telemetry. While a dryer is awake, it pushes data roughly every 15 seconds. Newly added or removed dryers are picked up automatically on the next refresh interval.

All network traffic goes only to Harvest Right's own servers (`prod.harvestrightapp.com` and `mqtt.harvestrightapp.com`).

## Troubleshooting

- **Entities show "unavailable":** the dryer is offline or has lost Wi-Fi. Entities go unavailable when no telemetry has been received for several minutes, which keeps stale values out of your history.
- **No data after install:** confirm the dryer is powered on, connected to Wi-Fi, and visible in the Harvest Right app.
- **Re-authentication prompt:** enter your account password again — the saved session has expired.
- To capture logs, download **diagnostics** from the integration's device page, or enable debug logging for `custom_components.harvest_right`.

## Requirements

- A Harvest Right freeze dryer with Wi-Fi connectivity.
- A Harvest Right account (the same one you use in the Harvest Right app).
- Home Assistant 2025.1.0 or newer.

## Development

```bash
pip install -r requirements_test.txt
ruff check custom_components tests
pytest
```
