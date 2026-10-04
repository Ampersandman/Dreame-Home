# Home Assistant OS: HACS installation

Target: Home Assistant OS 18.3, Core 2026.9.4, Supervisor 2026.09.3 and Frontend 20260826.7. The current integration is the read-only `dreame_home` beta, version `0.2.0b3`. Core 2026.9.4 is the minimum advertised version. Installation uses HACS; no file upload or terminal access is required.

On 2026-10-04, the user confirmed completing HACS installation and account setup: all three target devices appeared, showed values and received updates. The checks below cover the remaining details; entity counts and Home Assistant MQTT status have not yet been supplied.

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
- Initial L9 read plans contain 24 washer and 17 dryer coordinates; actual entity counts depend on successful replies and MQTT observations. The earlier capture observed 27 washer and 22 dryer coordinates. Those are capture counts, not guaranteed entity totals.
- Let MQTT collect updates while viewing the L9 pages in the official app. Unknown addresses keep neutral labels. No cycle needs to be started for the first test.
- Reload the Dreame Home integration from its menu, then confirm that entities and MQTT recover without duplicate entities or a setup error. A later Core restart can check stored-token setup once the first run works.

If setup fails, provide the error and relevant `dreame_home` traceback from **Settings > System > Logs**. If it loads, download its diagnostics from the integration menu and report whether all three devices appear. Diagnostics include source coverage, property response codes, null-reply flags, ages of retained values and per-device errors. The component excludes account credentials and raw account envelopes. See [Home Assistant diagnostics](https://www.home-assistant.io/integrations/diagnostics/).

Cloud discovery runs every ten minutes, so a physical power change can remain behind a cached cloud-online flag until that refresh. HTTP property reads run about once a minute. A null RPC preserves an earlier MQTT value with `last_reply_null`, without refreshing its successful-observation timestamp.

## What was checked before this installation

Core 2026.9.4's pinned framework sources were reviewed for config-flow schemas, reauthentication, coordinator setup/shutdown, platform loading, entities and sensor numeric validation. This found and fixed three failure paths: MQTT startup now occurs before entity-platform forwarding; entity discovery pauses during platform unload and resumes if removal fails; structured values cannot become a numeric sensor state with a measurement unit. Regression tests exercise those paths.

Pycryptodome 3.24.0 and paho-mqtt 2.1.0 were independently checked against fresh HTTPS PyPI metadata. Both releases exist; the Crypto release includes stable-ABI Linux wheels for x86_64 and aarch64 with both glibc and musl. The manifest pins Crypto and permits `paho-mqtt>=2.1.0,<3`, allowing Home Assistant's shared MQTT dependency. Repeat the pinned/minimum release availability check locally with `python tools/check_ha_dependencies.py`. Package availability does not establish actual installation inside Home Assistant.

Core 2026.9.4 requires Python 3.14.2 or newer and installs probatio's voluptuous compatibility layer before its flow framework imports. The component selects the schema API exposed by that framework. These facts come from the pinned [project metadata](https://github.com/home-assistant/core/blob/2026.9.4/pyproject.toml), [package initialization](https://github.com/home-assistant/core/blob/2026.9.4/homeassistant/__init__.py), [data-entry flow](https://github.com/home-assistant/core/blob/2026.9.4/homeassistant/data_entry_flow.py), [config-entry lifecycle](https://github.com/home-assistant/core/blob/2026.9.4/homeassistant/config_entries.py), [coordinator](https://github.com/home-assistant/core/blob/2026.9.4/homeassistant/helpers/update_coordinator.py) and [sensor implementation](https://github.com/home-assistant/core/blob/2026.9.4/homeassistant/components/sensor/__init__.py).

Source review and offline tests are separate from the user's successful first-run report. Initial installation, login, device discovery and updating telemetry have user-reported runtime acceptance. Reload, stored-token restart, reauthentication, exact coverage and normal-cycle/event behavior remain to be checked. Supervisor, OS and frontend versions describe the supplied environment; controls and vacuum maps remain later work.
