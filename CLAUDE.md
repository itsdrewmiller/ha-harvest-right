Please implement a home assistant integration for this architecture.

1. Architecture Overview
The app is a Flutter web app that communicates via:

REST API (https://prod.harvestrightapp.com) — authentication, freeze dryer registration, user management
MQTT over WebSocket (wss://mqtt.harvestrightapp.com/mqtt:8084) — real-time telemetry, system state, and commands
CMS API (https://cms.harvestrightapp.com) — content, recipes, articles (not needed for HA)


2. Authentication

### Login Flow (Password-based — preferred for HA integration)
The API supports a standard username/password login, which is the approach we use for the HA integration:
```
POST https://prod.harvestrightapp.com/auth/v1
Content-Type: application/json

{"username": "user@example.com", "password": "...", "rememberme": true}
```
Note: The field is called `username` (not `email`), even though the value is an email address.

### Login Flow (Passwordless — email code verification)
The app also supports a code-based auth flow:
Step 1: Request Code
POST https://prod.harvestrightapp.com/auth/v2/request-code
Content-Type: application/json

{"email": "user@example.com"}
Step 2: Verify Code
POST https://prod.harvestrightapp.com/auth/v2/verify-account
Content-Type: application/json

{"email": "user@example.com", "code": "123456"}

### Auth Response
Both login methods return the same token structure:
json{
  "userId": 139716,
  "customerId": 126592,
  "firstName": null,
  "lastName": null,
  "accessToken": "eyJhbG...(JWT)...",
  "accessExpire": 1770669899,
  "refreshAfter": 1770627557,
  "refreshExpire": 1778359499,
  "refreshToken": "eyJhbG...(JWT)...",
  "error": null,
  "roles": ["CUSTOMER"],
  "shared": []
}
```

The JWT payload contains: `email`, `id` (userId), `customerId`, `roles`, `exp`, `iat`.

**Step 3: Token Refresh**
```
POST https://prod.harvestrightapp.com/auth/v1/refresh-token
Authorization: Bearer {refreshToken}
```
Returns a new full login response with fresh tokens. The `refreshAfter` field tells you when to refresh (before `accessExpire`).

### API Authentication
All REST API calls use:
```
Authorization: Bearer {accessToken}
Content-Type: application/json

3. REST API Endpoints
Core Endpoints (on prod.harvestrightapp.com)
EndpointMethodPurpose/auth/v1POSTPassword-based login (username + password)/auth/v2/request-codePOSTRequest email verification code/auth/v2/verify-accountPOSTVerify code and get tokens/auth/v2/create-accountPOSTCreate new account/auth/v1/refresh-tokenPOSTRefresh access token/auth/v1/delete-accountPOST/DELETEDelete account/freeze-dryer/v1GETList all registered freeze dryers/freeze-dryer/v1/activationPOSTActivate a freeze dryer/freeze-dryer/v1/update-cpuPOSTUpdate CPU info/freeze-dryer/v2/preregisterPOSTPre-register a freeze dryer/freeze-dryer/groups/v1GETGet freeze dryer groups/wifi-adapter/v1GETWiFi adapter info/user/v1/notification-settingsGET/PUTNotification preferences/user/v2/account-sharingGETAccount sharing info/user/v1/device-tokenPOSTRegister push notification device/ota/v1/groupsGETOTA update groups
Freeze Dryer List Response
json[
  {
    "id": 64283,
    "customer_id": 126592,
    "serial": "NOV22PMTF66565WHC",
    "cpuSerial": "90C8239F3134",
    "firmware": "HOME",
    "hardware": "ZONE_1",
    "model": "MEDIUM",
    "dryer_name": "Kelvin",
    "shelves": 5,
    "status": "VERIFIED",
    "lastUpdated": "2026-01-19 23:38:07 +0000 UTC",
    "candyMachine": false,
    "softwareVersion": ""
  }
]
Notification Settings Response
json{
  "pushEnabled": true,
  "byAccount": [{
    "account": 126592,
    "softwareUpdate": true,
    "warrantyUpdate": true,
    "pCooled": true,
    "pDryCompleted": true,
    "pDefrostComplete": true,
    "pError": true
  }],
  "maintenance": true,
  "promotion": true
}
```

---

## 4. MQTT Protocol

### Connection Details
- **Broker URL**: `wss://mqtt.harvestrightapp.com/mqtt`
- **Port**: `8084`
- **Protocol**: MQTT v5 over WebSocket
- **WebSocket subprotocol**: `["mqtt"]`
- **Keep-alive**: 150 seconds
- **Default QoS**: 0 (at most once)
- **Clean session**: Yes (inferred from code)

### MQTT Authentication
**VERIFIED:** The MQTT broker uses `username=email, password=accessToken`. The customerId and userId were tested and rejected. The email (the same one used for REST API login) is the MQTT username, and the current access token is the password.

### Topic Structure

Topics follow the pattern:
```
{prefix}/{accountId}/ed/{dryerId}/m/{messageType}
```

Where:
- `prefix` = `act` (for account-owned dryers) or `group` (for shared/group dryers)
- `accountId` = `customerId` from login response (e.g., `126592`)
- `ed` = "electronic dryer" (device type)
- `dryerId` = freeze dryer `id` (e.g., `64283`)
- `m` = message namespace
- `messageType` = the specific data type

### Subscribe Topics (receive data FROM freeze dryer)

| Topic Pattern | Purpose |
|---|---|
| `act/{custId}/ed/+/m/telemetry` | Real-time telemetry data (temp, time, phase) |
| `act/{custId}/ed/+/m/system` | System state data (firmware, config, phases) |
| `act/{custId}/ed/+/m/name-update` | Dryer name changes |
| `act/{custId}/ed/+/m/batch-summary` | Batch summary data |
| `act/{custId}/ed/+/m/test-history` | Test history |
| `act/{custId}/ed/+/m/test-summary` | Test summary |
| `act/{custId}/ed/+/m/system-prefs` | System preferences |
| `act/{custId}/ed/+/m/pending-uploads` | Pending data uploads |
| `act/{custId}/ed/+/m/ota` | OTA update status |
| `act/{custId}/ed/+/m/recipe` | Current recipe info |
| `act/{custId}/ed/+/m/system-info` | Detailed system info |
| `act/{custId}/ed/+/m/gotit` | Command acknowledgment |
| `act/{custId}/gd/+` | Group dryer updates |
| `act/{custId}/on` | Online/offline status |

The `+` is the MQTT single-level wildcard, matching any dryer ID.

### Publish Topics (send commands TO freeze dryer)

Commands are published to topics like:
```
act/{custId}/ed/{dryerId}/{command}
```

Specific command topics found in the code:

| Command Topic Suffix | Payload Fields | Purpose |
|---|---|---|
| `/telemetry` (via `hr/telemetry`) | `{}` | Request telemetry update |
| `/quick-start` | (batch config) | Quick start a batch |
| `/fd-list-logs` | `{"type": "ALL"}` | Request log data |
| `/d/activate` | (activation data) | Activate freeze dryer |
| `/retry` | `""` | Retry failed connection |

### Command Payload Types (via `hr/` prefix)

These are the high-level command types the app sends:

| Command | Payload | Purpose |
|---|---|---|
| `hr/click` | `{"screen": N, "button": N}` | Simulate button press on the freeze dryer's screen |
| `hr/start-batch` | `{"type": "..."}` | Start a new batch |
| `hr/batch-name` | `{"name": "..."}` | Set batch name |
| `hr/batch-history` | `{"run": N, "read": N}` | Request batch history |
| `hr/rename` | `{"name": "..."}` | Rename freeze dryer |
| `hr/fdcolor` | `{"color": "...", "id": N}` | Set dryer color in app |
| `hr/system-prefs` | `{...}` | Update system preferences |
| `hr/config` | `{"data": "..."}` | Send configuration |
| `hr/telemetry` | `{}` | Request telemetry refresh |
| `hr/test` | `{...}` | Run a test |
| `hr/test-history` | `{"offset": N}` | Get test history |

The `hr/click` command is the primary mechanism for controlling the freeze dryer remotely — it sends the current screen number and the button index to simulate physical button presses.

---

## 5. Telemetry Data Model

### Telemetry Message Fields (from `/m/telemetry`)

| Field | Likely Meaning | Notes |
|---|---|---|
| `screen` | Current screen/state number | Maps to machine state |
| `sbt` | Sub-batch type | Batch process type |
| `sbn` | Sub-batch name | |
| `ssd` | Sub-step data? | |
| `df` | Defrost flag? | |
| `nm` | Name | |
| `v` | Vacuum level | In mTorr |
| `lt` | Low temperature? | |
| `otmp` | Oil temperature | |
| `omin` | Oil minimum? | |
| `wp` | Watts/power? | |
| `tmp` | Temperature | Primary temp display |
| `tim` | Time (elapsed) | In seconds |
| `cp` | Condenser pressure? | |
| `ift` | Initial freeze temp? | |
| `dtl` | Drying temp limit | |
| `eft` | Extra freeze time? | |
| `et` | Estimated time | |
| `tmt` | Target mTorr | Target vacuum |
| `fdt` | Final dry temp | |
| `sl` | Shelf | Current shelf |
| `wtmp` | Warmer temperature | Tray warmer |
| `wt` | Warmer time? | |
| `frz` | Freeze? | Freeze flag |
| `ext` | Extra dry time | |
| `fd` | Freeze dryer ID? | |
| `tm` | Total minutes? | |
| `ftm` | Freeze time minutes? | |
| `cn` | Count? | |
| `fup` | Firmware update pending? | |
| `mid` | Machine ID? | |
| `wtim` | Warmer time? | |
| `pdp` | Power during phase? | |
| `ds` | Dryer status? | |
| `vt` | Vacuum time? | |
| `eps` | Elapsed phase seconds? | |
| `lfs` | Last freeze status? | |
| `bv` | Board voltage? | |
| `bi` | Board info? | |
| `kf` | Key flag? | |
| `ku` | Key unlock? | |

### System Message Fields (from `/m/system`)

| Field | Likely Meaning |
|---|---|
| `r` | Run state? |
| `rs` | Run status? |
| `fn` | Firmware name |
| `ph` | Phase (current) |
| `pmp` | Pump status |
| `sh` | Shelves count |
| `bc` | Batch count (lifetime) |
| `dat` | Date/time |
| `cpu` | CPU code |
| `cfg` | Configuration key |
| `mfg` | Manufacturing info |
| `pt` | Pump type |
| `spp` | Spare pump parameter? |
| `def` | Default settings? |
| `cur` | Current settings |
| `crp` | Current recipe |
| `ltl` | Low temp limit |
| `wtl` | Warmer temp limit |
| `dtl` | Drying temp limit |
| `dntl` | Dehydrate temp limit |
| `wm` | Warmer mode |
| `dm` | Dry mode |
| `dnm` | Dehydrate mode |
| `monitor` | Monitor data |
| `bn` | Batch name |
| `dps` | Dry process settings |
| `temp` | Temperature data |
| `mt` | mTorr/vacuum |
| `els` | Elapsed time |
| `eps` | Estimated phase seconds |
| `pct` | Percentage complete |
| `pdc` | Power during cycle? |
| `pdm` | Power during mode? |
| `bf` | Batch flag? |
| `rssi` | WiFi signal strength |

### Test Data Fields (from test messages)

| Field | Likely Meaning |
|---|---|
| `pv` | Pump vacuum |
| `ta` | Test ambient? |
| `tt1` | Test temp 1 |
| `tt2` | Test temp 2 |
| `tt3` | Test temp 3 |
| `ft` | Freeze temp |
| `ht` | Heat temp |
| `ftc` | Freeze temp check |
| `htc` | Heat temp check |
| `stat1` | Status 1 |
| `stat2` | Status 2 |
| `stat3` | Status 3 |
| `shelf` | Shelf under test |
| `sec` | Seconds elapsed |
| `ot` | Oil temp |

---

## 6. Machine States (Screen Numbers → Names)

The `screen` field in telemetry maps to these states (in order):

| # | State |
|---|---|
| 0 | Offline |
| 1 | Ready to Start |
| 2 | Load Trays |
| 3 | Rotate Trays |
| 4 | Warming Trays |
| 5 | Freezing |
| 6 | Drying |
| 7 | Drying (continued) |
| 8 | Extra Dry Time |
| 9 | Batch Complete |
| 10 | Remove Trays |
| 11 | Defrosting |
| 12 | Defrosted |
| 13 | System Setup |
| 14 | Time Setup |
| 15 | Factory Setup |
| 16 | Testing |
| 17 | Settings |
| 18 | Restarting |
| 19 | Preparing |
| 20 | Setup |
| 21 | Welcome |
| 22 | Authorizing |
| 23 | Recipe Creation |
| 24 | Unable to Achieve Vacuum |
| 25 | Freeze Dryer Not Cooling |
| 26 | Not Detecting Heat |
| 27 | Time Expired |
| 28+ | Customizing, Pump Setup, Name Setup, Batch View, History View, Recipe View, etc. |

---

## 7. Models & Enums

**Dryer Models**: `SMALL`, `MEDIUM`, `LARGE`, `XLARGE`, `XXLARGE`

**Firmware Types**: `HOME`, `PHARMACEUTICAL`, `COMMERCIAL`, `SCIENTIFIC`

**Hardware Types**: `ZONE_1`, `ZONE_2`

**Modes**: `auto`, `manual`, `standard`, `custom`

**Dry Process Types**: `processNone` (0), `processQuality` (1), `processFast` (2), `processSpecial` (3)

**Vacuum Units**: mTorr (mT)

**Temperature Units**: °F or °C (user configurable)

---

## 8. Firebase Configuration

The app uses Firebase for analytics and push notifications:
- **Project**: `hr-remote-mobile-app`
- **App ID**: `1:875540397932:web:c5cc67667b113bbc3b7d49`
- **Messaging Sender ID**: `875540397932`
- **Auth Domain**: `hr-remote-mobile-app.firebaseapp.com`
- **Measurement ID**: `G-7X72DMGWX5`

(You won't need Firebase for the HA integration — it's only used for push notifications and analytics.)

---

## 9. Recommended Home Assistant Integration Architecture

### File Structure
```
custom_components/harvest_right/
├── __init__.py           # Integration setup, platforms
├── manifest.json         # HA manifest
├── config_flow.py        # Config flow (email + password auth)
├── const.py              # Constants, field mappings
├── coordinator.py        # DataUpdateCoordinator (MQTT + REST)
├── api.py                # REST API client
├── mqtt_client.py        # MQTT WebSocket client
├── sensor.py             # Sensor entities
├── binary_sensor.py      # Binary sensor entities
├── button.py             # Button entities (End Batch, Defrost)
├── strings.json          # Translations
└── translations/
    └── en.json
```

### Config Flow
Using the password-based auth (single-step, standard HA pattern):
1. User enters email + password → call `POST /auth/v1` with `{"username": email, "password": password, "rememberme": "default"}`
2. Store `refreshToken` in HA config entry (it lasts ~90 days based on `refreshExpire`)
3. Use `refreshToken` to get new `accessToken` as needed via `/auth/v1/refresh-token`

### Entities to Create

**Sensors:**
- Temperature (main `tmp`)
- Oil Temperature (`otmp`)
- Warmer Temperature (`wtmp`)
- Vacuum Pressure (`v` in mTorr)
- Elapsed Time (`tim`)
- Estimated Time (`et`)
- Progress Percentage (`pct`)
- WiFi Signal Strength (`rssi`)
- Current Phase/State (from `screen` mapping)
- Mode (`auto`/`manual`/`custom`)
- Batch Count (`bc`)
- Batch Name (`bn`)

**Binary Sensors:**
- Running (derived from `screen` state)
- Freezing (screen == 5)
- Drying (screen == 6 or 7)
- Error/Fault (screen 24-27)
- Online/Offline (screen != 0)

**Buttons:**
- End Batch (via `hr/click`)
- Defrost (via `hr/click`)

### Data Flow
```
[Freeze Dryer] → [WiFi Adapter] → [MQTT Broker] → [HA MQTT Client]
                                                         ↓
[HA REST API Client] ←→ [prod.harvestrightapp.com]    [DataUpdateCoordinator]
                                                         ↓
                                                    [HA Entities]
Key Implementation Notes

MQTT is the primary data source — telemetry updates come in real-time via MQTT. REST API is mainly for auth, device list, and initial setup.
Token refresh — implement a background task that refreshes the access token before it expires (use refreshAfter timestamp).
MQTT reconnection — the app implements exponential backoff reconnection. Implement similar logic.
The hr/click command is the main control mechanism — you'd need to map the current screen state to know which button index to send for specific actions (e.g., "End Batch" is a button available on certain screens).
Temperature unit conversion — the API sends temperature in the user's configured unit (°F or °C). You may want to query the user's preference or handle both.
Multiple dryers — the API supports multiple freeze dryers per account. Each has its own id and separate MQTT topics.

---

## 10. Verified Corrections from Live Testing (2026-02-08)

The following corrections were discovered by testing against the live API and MQTT broker:

### REST API
- `rememberme` field must be a boolean (`true`), NOT the string `"default"`. Sending `"default"` returns HTTP 400: `type mismatch for field "rememberme"`.
- Token refresh (`POST /auth/v1/refresh-token`) requires `Content-Type: application/json` header in addition to the `Authorization: Bearer {refreshToken}` header.

### MQTT Authentication
- **VERIFIED: `username=email, password=accessToken`** — the email used for login is the MQTT username, and the current JWT access token is the password.
- Tested and rejected: `customerId` as username (returns "Bad user name or password"), `userId` as username (same), no auth ("Not authorized"), token in WS headers ("Not authorized").

### Telemetry Payload Field Names
The actual field names differ significantly from the spec's guesses. Observed telemetry payload during "Warming Trays" (screen 4):
```json
{
  "V": "6.0.644170",        // firmware version (string)
  "f": 5,                   // shelves count
  "m": 2,                   // mode (numeric)
  "scp": 8698433,           // unknown
  "ce": true,               // unknown flag
  "name": "Kelvin",         // dryer name
  "rssi": -65,              // wifi signal (IN TELEMETRY, not system)
  "a": 31201,               // unknown
  "aName": "HR_b8f862e7c5ac", // adapter name
  "screen": 4,              // current state ✓
  "temp": 7,                // temperature (NOT "tmp")
  "mt": 10000,              // vacuum mTorr (NOT "v")
  "els": 10879,             // elapsed seconds (NOT "tim")
  "eps": 0,                 // estimated phase seconds (NOT "et")
  "hlp": 45,                // unknown (help screen? percentage?)
  "bn": "Auto",             // batch name (IN TELEMETRY, not system)
  "bf": 5,                  // batch flag
  "dps": 1,                 // dry process setting
  "pct": 70,                // progress % (IN TELEMETRY, not system)
  "pdc": 0,                 // power during cycle
  "pdm": 0,                 // power during mode
  "ssd": {"ext": 0},        // sub-step data
  "cfg": "HM-5B~05"         // configuration key
}
```

Key field mapping corrections:
| Spec field | Actual field | Notes |
|---|---|---|
| `tmp` | `temp` | Temperature |
| `v` | `mt` | Vacuum pressure (mTorr) |
| `tim` | `els` | Elapsed time (seconds) |
| `et` | `eps` | Estimated time (seconds) |
| `otmp` | ? | Oil temp — not seen in "Warming Trays" state, may appear during drying |
| `wtmp` | ? | Warmer temp — not seen in "Warming Trays" state, may appear during drying |

Fields that are in telemetry (NOT system as spec suggested): `rssi`, `bn`, `pct`, `els`, `eps`

### Online/Offline Topic
The `act/{custId}/on` topic sends **plain strings** (`"on"`, `"continue"`), NOT JSON. Must handle non-JSON payloads on this topic.

### Screen Number Mapping (Off-by-One)
The spec lists "Offline" as screen 0, but the device doesn't send a screen number when offline (no telemetry). The actual screen numbers are shifted down by 1 from the spec:
- screen 0 = Ready to Start (spec said 1)
- screen 3 = Warming Trays (spec said 4)
- screen 4 = Freezing (spec said 5) — **verified by user**
- screen 5 = Drying (spec said 6)
- etc.