# Home Assistant OS: HACS installation

Target: Home Assistant OS 18.3, Core 2026.9.4, Supervisor 2026.09.3 and Frontend 20260826.7. The current `dreame_home` beta is version `0.3.0b1`, adding named appliance controls to the earlier validated telemetry. Core 2026.9.4 is the minimum advertised version. Installation uses HACS; no file upload or terminal access is required.

On 2026-10-04, the user confirmed the earlier telemetry beta's HACS installation and account setup: all three target devices appeared, showed values and received updates. Supplied HA diagnostics from Core 2026.9.4 / Python 3.14.6 confirm complete discovery, a successful API update, and all three devices present, reported online and MQTT connected. There were no metadata/read/cloud-data errors or reported drops/truncation. The [HA diagnostics review](ha-diagnostics-review.md) records sanitized counts and their limits; actual HA entity totals remain unreported. New controls and five added vacuum read candidates have no live acceptance yet.

## Install the integration

1. Open **HACS** and select **Custom repositories** from its top-right menu.
2. Add `https://github.com/Ampersandman/Dreame-Home` with category **Integration**.
3. Open **Dreame Home** and download it. HACS can install the default branch when no release exists.
4. Restart **Home Assistant Core** to load the integration. No YAML integration entry is required. Home Assistant installs the Python dependencies during setup.

See the [official HACS custom repository instructions](https://www.hacs.xyz/docs/faq/custom_repositories/) and [repository publishing guide](hacs-publishing.md).

## Add the account

In **Settings > Devices & services**, add **Dreame Home**. Select `eu`, enter your Dreame account credentials locally and leave MQTT enabled for this first test. If the integration is missing after the Core restart, refresh the browser and check **Settings > System > Logs** for `dreame_home` import/dependency errors.

Keep the washer and dryer switched on for the first setup. The component discovers the whole account, makes bounded property reads and subscribes to MQTT. It does not start a program, write settings or call the app's status-report action. Opening an appliance page in DreameHome may independently trigger reports from the official app.

The expected devices are `dreame.washer.l9nacn`, `dreame.dryer.l9nacn` and `dreame.vacuum.r5023a`. Device IDs are discovered from the account rather than entered manually. The setup form stores a refresh token; the password and access token are not persisted by this component.

## Validate the first run

- Confirm that all three devices appear. Check separate cloud-online and MQTT-connected entities.
- Confirm that the vacuum battery has a numeric percentage and the L9 properties have their source-derived names. Unsupported/null values produce no invented states.
- Initial L9 read plans contain 24 washer and 17 dryer coordinates. Supplied HA diagnostics show 27 usable washer roots and 22 usable dryer roots from MQTT, with 23 dryer coordinates recorded, plus 15 vacuum RPC roots. Dryer `3.11` has no observed value and `4.7` remains unknown. These property counts do not establish actual entity totals; no compound property values occur in this snapshot.
- Let MQTT collect updates while viewing the L9 pages in the official app. Unknown addresses keep neutral labels. No cycle needs to be started for the first test.
- Reload the Dreame Home integration from its menu, then confirm that entities and MQTT recover without duplicate entities or a setup error. A later Core restart can check stored-token setup once the first run works.

Diagnostics have already been supplied and reviewed for this installation. For a later setup or update failure, the integration menu provides a fresh diagnostic download, and **Settings > System > Logs** contains relevant `dreame_home` tracebacks. Diagnostics include source coverage, property response codes, null-reply flags, ages of retained values and per-device errors. They do not report actual HA entity totals or identify cached values; the configured cloud-data allowlist and cached-key count cannot establish acceptance of the firmware-update setting. The component excludes account credentials and raw account envelopes. See [Home Assistant diagnostics](https://www.home-assistant.io/integrations/diagnostics/).

Cloud discovery runs every ten minutes, so a physical power change can remain behind a cached cloud-online flag until that refresh. HTTP property reads run about once a minute. A null RPC preserves an earlier MQTT value with `last_reply_null`, without refreshing its successful-observation timestamp.

## Controls after setup

Version `0.3.0b1` provides 16 exact-model washer controls, 12 dryer controls and native vacuum start/pause/stop/return-to-base/fan controls. Required observations must be successful, recognized and no more than 180 seconds old. Missing/null/stale context leaves affected controls unavailable; cloud-online or MQTT-connected alone is insufficient. The new vacuum baseline contains 20 candidates; the existing diagnostic proves the earlier 15 successful vacuum coordinates only.

Laundry start/resume also needs child lock off, no fault and appliance network authorization `3.14=1`. Follow DreameHome's on-device **Authorize Network** instructions to enable that permission; account login alone does not grant it. Settings retain program and phase restrictions. Laundry **Stop and power off** sends the source power-off action and can end a cycle. Dryer wrinkle care requires pause in phase 1, 2 or 3, so it is unavailable in standby. See the [complete control guide](appliance-controls.md) for exact lists and omissions. No hardware commands were issued to validate these controls.

## What was checked before this installation

Core 2026.9.4's pinned framework sources were reviewed for config-flow schemas, reauthentication, coordinator setup/shutdown, platform loading, entities and sensor numeric validation. This found and fixed three failure paths: MQTT startup now occurs before entity-platform forwarding; entity discovery pauses during platform unload and resumes if removal fails; structured values cannot become a numeric sensor state with a measurement unit. Regression tests exercise those paths.

Pycryptodome 3.24.0 and paho-mqtt 2.1.0 were independently checked against fresh HTTPS PyPI metadata. Both releases exist; the Crypto release includes stable-ABI Linux wheels for x86_64 and aarch64 with both glibc and musl. The manifest pins Crypto and permits `paho-mqtt>=2.1.0,<3`, allowing Home Assistant's shared MQTT dependency. Repeat the pinned/minimum release availability check locally with `python tools/check_ha_dependencies.py`. Package availability does not establish actual installation inside Home Assistant.

Core 2026.9.4 requires Python 3.14.2 or newer and installs probatio's voluptuous compatibility layer before its flow framework imports. The component selects the schema API exposed by that framework. These facts come from the pinned [project metadata](https://github.com/home-assistant/core/blob/2026.9.4/pyproject.toml), [package initialization](https://github.com/home-assistant/core/blob/2026.9.4/homeassistant/__init__.py), [data-entry flow](https://github.com/home-assistant/core/blob/2026.9.4/homeassistant/data_entry_flow.py), [config-entry lifecycle](https://github.com/home-assistant/core/blob/2026.9.4/homeassistant/config_entries.py), [coordinator](https://github.com/home-assistant/core/blob/2026.9.4/homeassistant/helpers/update_coordinator.py) and [sensor implementation](https://github.com/home-assistant/core/blob/2026.9.4/homeassistant/components/sensor/__init__.py).

Genuine GitHub HACS, hassfest and Python 3.12/3.14 offline CI passed for the earlier published telemetry revision. Those checks and source review are separate from the first-run report and HA diagnostic snapshot. Initial installation, login, discovery, updating telemetry and initial MQTT connectivity have runtime evidence. Control execution, reload, stored-token restart, reauthentication, token rotation, reconnect, detailed app-to-entity comparisons, recorder behavior and normal-cycle/events remain to be checked. Compound projection is not established by scalar-only snapshots. Supervisor, OS and frontend versions describe the reported installation; vacuum maps remain future work. See [verification](verification.md) for current offline checks.
