# Home Assistant OS: HACS installation

Target: Home Assistant OS 18.3, Core 2026.9.4, Supervisor 2026.09.3 and Frontend 20260826.7. The current `dreame_home` beta is version `0.3.0b2`, adding readable cycle sensors, corrected dryer time metadata and recurring known-property retries to the named appliance controls. Core 2026.9.4 is the minimum advertised version. Installation uses HACS; no file upload or terminal access is required.

On 2026-10-04, the user confirmed the earlier `0.2.0b3` telemetry beta's HACS installation and account setup: all three target devices appeared, showed values and received updates. Its diagnostic from Core 2026.9.4 / Python 3.14.6 confirmed complete discovery, a successful API update, and all three devices present, reported online and MQTT connected, without reported metadata/read/cloud-data errors or drops. The [historical review](ha-diagnostics-review.md) records those findings.

A later `0.3.0b1` diagnostic was downloaded after the laundry cycles ended. Both laundry devices reported offline with retained power-off status and old values; this is expected after switching off and does not establish a running-cycle failure. That snapshot expands vacuum coverage to 167 property rows, with 145 source-mapped coordinates and 22 neutral coordinates. See the [2026-10-06 review](ha-diagnostics-review-2026-10-06.md). Actual entity totals, accepted writes, the new cycle sensors and the two vacuum progress candidates still need separate acceptance.

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
- Recurring known-model seeds contain 24 washer, 17 dryer and 22 vacuum coordinates. Exact candidates are retried after null/empty/error replies within a 240-address budget; unknown models receive no guessed seeds. Earlier diagnostics showed fresh 27 washer and 22 dryer valued roots, with dryer `3.11` unvalued and `4.7` neutral. The later post-cycle diagnostic retains those laundry values and expands vacuum coverage to 167 rows. Counts describe property coordinates, not entity totals.
- On the L9 devices, look for **Program duration**, **Remaining time**, **Cycle progress** and **Elapsed cycle time**. Dryer timing labels and units are corrected without changing existing property identities. Derived values require fresh powered-cycle context; they can be unknown after switch-off, for invalid estimates or before AI Wash has a time estimate. See [cycle sensors](cycle-progress.md).
- Let MQTT collect updates while viewing the L9 pages in the official app. Unknown addresses keep neutral labels. No cycle needs to be started for the first test.
- Reload the Dreame Home integration from its menu, then confirm that entities and MQTT recover without duplicate entities or a setup error. A later Core restart can check stored-token setup once the first run works.

Diagnostics have already been supplied and reviewed for this installation. For a later setup or update failure, the integration menu provides a fresh diagnostic download, and **Settings > System > Logs** contains relevant `dreame_home` tracebacks. Diagnostics include source coverage, current-reply flags, ages of retained values, per-device errors and separate supported/available command lists. They do not report actual HA entity totals or identify cached values; the configured cloud-data allowlist and cached-key count cannot establish acceptance of the firmware-update setting. A null command status does not prove that controls were never used. The component excludes account credentials and raw account envelopes. See [Home Assistant diagnostics](https://www.home-assistant.io/integrations/diagnostics/).

Cloud discovery runs every ten minutes, so a physical power change can remain behind a cached cloud-online flag until that refresh. HTTP property reads run about once a minute. A null RPC preserves an earlier MQTT value with `last_reply_null`, without refreshing its successful-observation timestamp.

## Controls after setup

Version `0.3.0b2` retains 16 exact-model washer controls, 12 dryer controls and native vacuum start/pause/stop/return-to-base/fan controls. These comprise 13 washer writable properties and 9 dryer writable properties, plus 3 action buttons each. Required observations must be successful, recognized and no more than 180 seconds old. Missing/null/stale context leaves affected controls unavailable; cloud-online or MQTT-connected alone is insufficient. The 22-candidate vacuum seed includes progress `4.63`/`4.64`, neither present in the later diagnostic; no progress value is manufactured from missing replies.

Laundry start/resume also needs child lock off, no fault and appliance network authorization `3.14=1`. Follow DreameHome's on-device **Authorize Network** instructions to enable that permission; account login alone does not grant it. Settings retain program and phase restrictions. Laundry **Stop and power off** sends the source power-off action and can end a cycle. Dryer wrinkle care requires pause in phase 1, 2 or 3, so it is unavailable in standby. See the [complete control guide](appliance-controls.md) for exact lists and omissions. No hardware commands were issued to validate these controls.

## What was checked before this installation

Core 2026.9.4's pinned framework sources were reviewed for config-flow schemas, reauthentication, coordinator setup/shutdown, platform loading, entities and sensor numeric validation. This found and fixed three failure paths: MQTT startup now occurs before entity-platform forwarding; entity discovery pauses during platform unload and resumes if removal fails; structured values cannot become a numeric sensor state with a measurement unit. Regression tests exercise those paths.

Pycryptodome 3.24.0 and paho-mqtt 2.1.0 were independently checked against fresh HTTPS PyPI metadata. Both releases exist; the Crypto release includes stable-ABI Linux wheels for x86_64 and aarch64 with both glibc and musl. The manifest pins Crypto and permits `paho-mqtt>=2.1.0,<3`, allowing Home Assistant's shared MQTT dependency. Repeat the pinned/minimum release availability check locally with `python tools/check_ha_dependencies.py`. Package availability does not establish actual installation inside Home Assistant.

Core 2026.9.4 requires Python 3.14.2 or newer and installs probatio's voluptuous compatibility layer before its flow framework imports. The component selects the schema API exposed by that framework. These facts come from the pinned [project metadata](https://github.com/home-assistant/core/blob/2026.9.4/pyproject.toml), [package initialization](https://github.com/home-assistant/core/blob/2026.9.4/homeassistant/__init__.py), [data-entry flow](https://github.com/home-assistant/core/blob/2026.9.4/homeassistant/data_entry_flow.py), [config-entry lifecycle](https://github.com/home-assistant/core/blob/2026.9.4/homeassistant/config_entries.py), [coordinator](https://github.com/home-assistant/core/blob/2026.9.4/homeassistant/helpers/update_coordinator.py) and [sensor implementation](https://github.com/home-assistant/core/blob/2026.9.4/homeassistant/components/sensor/__init__.py).

Genuine GitHub HACS, hassfest and Python 3.12/3.14 offline CI passed for earlier published revisions. Those checks and source review are separate from user reports and diagnostic snapshots. Initial installation, login, discovery, updating telemetry and MQTT connectivity have runtime evidence; the later diagnostic adds vacuum observations and post-cycle retained state. Accepted control writes, `0.3.0b2` progress/time comparisons during a running cycle, reload, stored-token restart, reauthentication, token rotation, reconnect and recorder behavior remain to be checked. Compound projection is not established by scalar-only snapshots. Supervisor, OS and frontend versions describe the reported installation; vacuum maps remain future work. See [verification](verification.md) for current offline checks.
