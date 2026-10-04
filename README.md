# Dreame Home for Home Assistant

HACS custom integration for devices registered to a Dreame Home account. This repository includes a self-contained Home Assistant component and a standalone Python API extracted from [Tasshack/dreame-vacuum at commit `9857362d37fa6a1788a0ce2eb6e1290b3ec7d6fb`](https://github.com/Tasshack/dreame-vacuum/tree/9857362d37fa6a1788a0ce2eb6e1290b3ec7d6fb), extended with exact L9 washer and dryer definitions.

The priority devices are the **L9 washing machine**, **L9 Twin Inverter dryer**, and **L10s Ultra Gen 3 vacuum**. Their confirmed cloud models are `dreame.washer.l9nacn`, `dreame.dryer.l9nacn`, and `dreame.vacuum.r5023a`. Exact L9 app plugins have been extracted: 27 washer property definitions and 22 dryer definitions, including programs, enums and action payloads. Live EU reads and MQTT supplied values for 27 washer coordinates, 22 dryer coordinates, and 15 vacuum coordinates; all three authenticated MQTT connections succeeded with verified TLS. See [live coverage](docs/live-coverage.md) for firmware, null replies and remaining limits.

## Install through HACS

Requires **Home Assistant Core 2026.9.4 or newer** and HACS. Version `0.2.0b3` is a read-only telemetry beta. A user confirmed HACS installation, account setup, discovery of all three target devices, and values updating on their Home Assistant Core 2026.9.4 installation. Detailed property coverage and further lifecycle checks remain to be verified.

1. Open **HACS > menu > Custom repositories**.
2. Add `https://github.com/Ampersandman/Dreame-Home`, category **Integration**.
3. Download **Dreame Home** and restart Home Assistant.
4. Open **Settings > Devices & services > Add integration > Dreame Home**.
5. Choose your Dreame Home server region and enter the account credentials. Use `eu` for a European account and leave MQTT enabled to receive additional telemetry.

HACS installs the component and its bundled API. Device IDs are discovered automatically. A GitHub release is optional: HACS can install the default branch. See the [Home Assistant OS guide](docs/ha-os-installation.md) for the first-run checks and [publishing guide](docs/hacs-publishing.md) for CI and releases.

The component stores a refresh token in Home Assistant's configuration entry and supports reauthentication. It does not persist the password or access token. Repository files contain no account credentials, actual device IDs or private captures.

The beta discovers every registered device, exposes successful observed properties with stable coordinates, and retains unknown compound data. Exact L9 definitions give observed fields names and explicit enum labels; raw codes remain available. Initial read plans contain 24 washer and 17 dryer coordinates; MQTT discovers additional fields, which are then polled. The component also exposes cloud-online/MQTT status and the verified vacuum battery reading. Failed or null replies do not create entities. There are no appliance controls in this beta.

Controls, writable entities, typed appliance events and vacuum maps remain future work. Observed properties are exposed even when their meaning is unknown, using neutral coordinate labels. This beta does not yet expose every feature implemented by the official app or the upstream vacuum integration.

## Extracted artifacts

| Artifact | Contents |
| --- | --- |
| [API reference](docs/dreamehome-api.md) | Login, refresh, signing, headers, regional servers, all 12 routes, RPC, MQTT, files and history |
| [Python client](src/dreamehome/client.py) | Account-wide discovery with pagination, property reads/writes, actions, cloud data, history and downloads |
| [Machine-readable catalogs](src/dreamehome/data/provenance.json) | 370 vacuum properties, 45 actions, 79 enums, 762 known vacuum model identifiers, 245 entity description templates, source locations and hashes |
| [Source implementations](src/dreamehome/data/implementations.json) | Cloud/TLS source, computed states, model capabilities, command encoders and map decoding preserved as reference text |
| [Exact L9 catalogs](src/dreamehome/data/l9_washer.json) | Washer definitions, 22 programs and 4 actions; [dryer catalog](src/dreamehome/data/l9_dryer.json) contains 31 programs and 4 actions |
| [L9 investigation](docs/l9-investigation.md) | Confirmed identities, exact-model evidence and remaining cycle validation |
| [HACS implementation handoff](docs/home-assistant-roadmap.md) | Account setup, device discovery, schema-driven entities, events and validation requirements |
| [Verification](docs/verification.md) | Offline checks and the limits of what has been tested |
| [Read-only component](custom_components/dreame_home/README.md) | Account setup, observed telemetry, diagnostics and lifecycle |
| [L9 app research](docs/l9-schema-research.md) | Authenticated iOS/Android plugin lookup, safe extraction and source provenance |
| [MQTT trust investigation](docs/mqtt-trust-research.md) | Vendor CA recovered from a signature-verified official APK and verified broker connections |

The generated vacuum catalogs describe the upstream integration. A device only exposes the subset supported by its model and firmware. Entity counts describe templates, including per-room/per-map templates, rather than the number of entities on a particular device.

## Use the extraction

The optional standalone API requires Python 3.11 or newer. For a fresh development checkout:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[mqtt]"
```

View the extraction without making network requests:

```powershell
.\.venv\Scripts\python.exe -m dreamehome catalog
```

List cloud devices, including unfamiliar model categories and shared devices:

```powershell
.\.venv\Scripts\python.exe -m dreamehome inventory --region eu
```

The command prompts locally for your account and a hidden password. `eu` is the app server region; select the region used by your Dreame account. `DREAME_USERNAME`, `DREAME_PASSWORD` or `DREAME_REFRESH_TOKEN` can also be supplied through your local environment. Credentials are not saved by the CLI.

To obtain exact device IDs without dumping unrelated cloud fields, run the dedicated interactive scanner in a local terminal:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\scan_cloud_account.ps1
```

Both account ID and password are entered without echo. The scanner checks verified TLS before requesting credentials, lists all device categories, and reads device metadata. It saves an allowlisted report with exact device IDs/model codes in the ignored `private/` directory. No access/refresh tokens, account UID, MAC address, signed URLs, or raw property blobs are included. This report can identify the washer, dryer and vacuum before their property mappings are selected.

Collect device listing pages, device metadata and OTC information:

```powershell
.\.venv\Scripts\python.exe -m dreamehome capture --region eu --label initial --output captures\initial.json
```

Capture files redact common account identifiers, credentials and URLs by default. `--private` retains raw device data for local investigation. New output files are created exclusively so earlier evidence is preserved. Redaction is a best effort for known fields; review captures before sharing.

Inspect the exact L9 source definitions without connecting to the cloud:

```powershell
.\.venv\Scripts\python.exe -m dreamehome schema --model dreame.washer.l9nacn
.\.venv\Scripts\python.exe -m dreamehome schema --model dreame.dryer.l9nacn
```

Observe the identified washer during ordinary app use:

```powershell
.\.venv\Scripts\python.exe -m dreamehome watch --region eu --model dreame.washer.l9nacn --seconds 300 --label idle --output captures\washer-idle.jsonl
```

The CLI performs device discovery and read-only capture. Property writes and actions are available explicitly through the Python API for the later integration. Capture never automatically polls the vacuum catalog on a washing machine or dryer.

## Reproduce and verify

```powershell
.\.venv\Scripts\python.exe tools\build_component.py --check --archive
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The offline suite uses committed source catalogs and synthetic responses; it needs no account credentials or research downloads. GitHub CI runs it on Python 3.12 and 3.14 and also runs official HACS and hassfest validation. These checks do not replace execution in Home Assistant.

Source extraction reproduction additionally requires the pinned upstream checkout, public schema responses or proprietary L9 plugin bundles, according to the relevant tool. Those local research inputs are deliberately excluded from this repository. See [third-party notices](THIRD_PARTY_NOTICES.md) for licenses and provenance. Capture and identification tools save local output under ignored `private/` or `captures/` directories; review it before sharing.
