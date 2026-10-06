# Appliance controls in 0.3.0b2

Version `0.3.0b2` retains the named controls introduced in `0.3.0b1` for the exact L9 washer, exact L9 Twin Inverter dryer and L10s Ultra Gen 3 vacuum. Encoders come from their model plugins or the pinned upstream vacuum implementation. Offline tests exercise payloads, constraints and the gateway. **The supplied evidence does not establish an accepted live control or setting write.** The earlier [HA diagnostic review](ha-diagnostics-review.md) establishes telemetry and MQTT operation. The [2026-10-06 review](ha-diagnostics-review-2026-10-06.md) concerns a later diagnostic downloaded after the laundry cycles ended.

Controls appear for supported exact models. A setting stays unavailable when its value or required command context is missing, null, failed, unknown or stale. The descriptor counts below are separate from telemetry/connectivity entities and actual entity totals. Diagnostics now list `supported_commands`, `available_commands`, `gateway_ready` and `fresh_coordinate_count`; these distinguish model support from eligibility at the time of download. The earlier static coverage field `controls_enabled: false` did not describe the writable platforms accurately and has been replaced.

## Shared command behavior

The appliance must be present, reported online and have a successful account API update. Required successful RPC/MQTT observations must be no more than **180 seconds old**, with an actual value in the latest reply and recognized source values. Cached listing/metadata and retained values following null or value-less replies cannot enable a command. Pending commands disable further controls on that device; commands are serialized per device.

Only named source encoders can send commands. The gateway binds the discovered device ID, checks property/action result codes and requests fresh telemetry afterward. Command writes, readbacks and periodic property polling are serialized per device to prevent older RPC replies racing a command. It never predicts resulting state or replays a command after an uncertain failure. Cancellation after transmission leaves the outcome unconfirmed. Check actual appliance state before another attempt after a rejected or unconfirmed command.

A rate-limited command does not trigger immediate readback. The gateway honors the device's `Retry-After` within a bounded 60–3600-second cooldown for commands and polling. Settings use HA's configuration category; start/pause/stop buttons remain ordinary device controls.

Switches accept Boolean requests and encode integer `0` or `1`. Selects map labels to exact integer codes; duplicate dryer labels include the code, such as **Wool (3)** and **Wool (17)**. Unknown codes, numeric strings, floats and Boolean-as-integer inputs cannot become arbitrary writes. There is no raw-coordinate write service or number control without complete source-defined bounds.

## L9 washing machine

Exact model: `dreame.washer.l9nacn`. **13 writable property coordinates: 8 selects and 5 switches, plus 3 buttons; 16 descriptors in total.**

| Control | Platform | Source property or action |
| --- | --- | --- |
| Program | Select | Property `2.3` |
| Temperature | Select | Property `2.8` |
| Extra time | Select | Property `2.14` |
| Water level | Select | Property `2.15` |
| Rinse cycles | Select | Property `2.16` |
| Spin speed | Select | Property `2.18` |
| Detergent dosing | Select | Property `2.24` |
| Softener dosing | Select | Property `2.25` |
| Child lock | Switch | Property `3.4` |
| Fresh air circulation | Switch | Property `3.6` |
| Dynamic rinse | Switch | Property `3.7` |
| Speed mode | Switch | Property `3.8` |
| Night mode | Switch | Property `3.9` |
| Start or resume | Button | Action `siid=2, aiid=2`, input `piid=2, value=1` |
| Pause | Button | Action `siid=2, aiid=2`, input `piid=2, value=0` |
| Stop and power off | Button | Action `siid=2, aiid=1`, input `piid=1, value=0` |

Program parameters change only in standby. This is narrower than the app's multi-command editing flow, which can pause/resume an existing cycle. Choosing a program sets its code alone; it does not power on, apply remembered defaults or start. Source configurations disable null fields and exclude codes in their filters. ECO 40-60, for example, restricts temperature/spin choices and disables several settings. Temperature and spin labels describe encoded settings, not raw measurement units.

Stain mode blocks temperature editing; speed mode blocks extra-time changes; dynamic rinse excludes zero rinses; night mode fixes spin speed. Enabling dynamic rinse requires an existing nonzero rinse count. Enabling speed mode requires zero extra time and, for Mixed/Cotton, a compatible temperature. These switches do not rewrite neighboring settings. Night mode and fresh air preserve program/phase restrictions; fresh air during a wash phase requires pause. Child lock can be changed independently; other controls require it off.

Start/resume requires standby or pause, no fault at property `2.2`, and authorization `3.14=1`. Pause requires running. **Stop means power off**, using the source power action; it can end a cycle.

## L9 Twin Inverter dryer

Exact model: `dreame.dryer.l9nacn`. **9 writable property coordinates: 5 selects and 4 switches, plus 3 buttons; 12 descriptors in total.**

| Control | Platform | Source property or action |
| --- | --- | --- |
| Program | Select | Property `2.3` |
| Dryness level | Select | Property `2.6` |
| Air flow | Select | Property `2.5` |
| Extra time | Select | Property `2.10` |
| Steam level | Select | Property `2.13` |
| Child lock | Switch | Property `3.4` |
| Wrinkle care | Switch | Property `3.8` |
| Low temperature | Switch | Property `3.12` |
| Speed mode | Switch | Property `3.10` |
| Start or resume | Button | Action `siid=2, aiid=2`, input `piid=2, value=1` |
| Pause | Button | Action `siid=2, aiid=2`, input `piid=2, value=0` |
| Stop and power off | Button | Action `siid=2, aiid=1`, input `piid=1, value=0` |

The exact export plugin selects `ProgramMode_W`; controls preserve its raw codes, null fields and exclusion filters. Configurations follow program codes, including entries whose display order differs. Wool `3` disables extra time explicitly even though its default table contains a value. Program parameters require standby. Low-temperature and speed modes cannot be enabled together: turn the other off first. **Wrinkle care requires paused status `2` and phase `1`, `2` or `3`; it is unavailable in standby.** This follows the direct runtime switch, while the app's before-start bulk configuration is a separate flow. Other controls require child lock off; start/resume also requires authorization `3.14=1` and no fault. Pause/stop have the same status checks and payloads as the washer.

## Authorization 3.14

This is the appliance's network-control authorization, separate from cloud login and online status. Both exact plugin tutorials say to start the machine by holding its power button, then pull down its page and tap **Authorize Network**. The unauthorized dialog asks for network authorization **on the device**. Enable this permission locally on the appliance using its DreameHome instructions; the integration reads it and does not grant or write it.

The washer wrapper checks `3.14` before start/resume. The dryer does the same for the export plugin selected by this exact model. Both also gate delay enable, whose scheduling flow is omitted. The source does not apply this permission check generally to pause, stop or every setter. Tutorial and wrapper provenance comes from the pinned plugins in [L9 schema research](l9-schema-research.md).

## Deliberately omitted settings

- Laundry delay duration/enable: complete bounds and ordered scheduling are unresolved; a UI minimum alone is insufficient.
- Washer stain selection: also writes temperature sentinel `999` and remembers local configuration.
- Dryer night mode: subscription `3.11` conflicts with UI `3.13`; neither is writable here.
- Dryer `4.7`: observed but source-unknown; retains neutral telemetry.
- Dryer sanitize `3.3`: hidden by the exact export plugin.
- Automatic firmware updates: native cloud helper known, HTTP write contract unverified. The read-only sensor still requires a returned value.
- Add-clothes and status-report actions: separate physical prerequisites or background behavior have not been adopted. Discovery never calls `reportAll`.

The pure backend's `omitted_controls(model)` records these reasons. Source catalogues remain unchanged and successful telemetry remains visible.

## L10s Ultra Gen 3 vacuum

Exact model: `dreame.vacuum.r5023a`. A native HA vacuum entity offers **start, pause, stop, return to base and fan speed**. Battery, activity and fan state come from successful observations. Fan options **silent, standard, strong and turbo** preserve source codes `0..3`.

The adapter retains model/task/status rules. Maintenance, dock washing/drying, specialized resume tasks, automatic/customized cleaning and missing context can block individual commands. Source-defined docking cases use return-to-base behavior. Fan changes require maximum-suction state and, during active cleaning, additional task context. Where source requires it, maximum suction is disabled before selecting fan speed. Room cleaning, maps and the full upstream feature set are not included.

The recurring vacuum seed contains **22 candidates**. Version `0.3.0b1` added control-context properties `4.4`, `4.26`, `4.47`, `4.50` and `4.60` to the earlier 15-property baseline; `0.3.0b2` adds source-backed progress candidates `4.63` and `4.64`. The later diagnostic contains 167 vacuum property rows, of which 145 have source mappings and 22 retain neutral labels. Neither progress candidate is present in that snapshot, so acceptance of those reads remains unverified. Actual successful context determines available vacuum features; candidate counts are not entity totals. See [cycle sensors](cycle-progress.md).

## Unavailable after a cycle

The user confirmed that the later diagnostic was downloaded after the laundry cycles ended. Both appliances reported cloud offline and retained power-off status `2.1=0`, with observations older than the 180-second command limit. Their unavailable controls are expected in that snapshot; it does not demonstrate a running-cycle or mapping failure. MQTT broker connectivity alone does not establish fresh appliance state.

During a running cycle, parameter selects can also be unavailable because this integration restricts them to standby. Pause, stop and child-lock controls follow their separate source conditions; a fresh running snapshot is needed to check their eligibility. `last_command_status: null` records no command status in the current coordinator session and does not prove that controls were never used.

## Remaining acceptance

Source encoders and offline gateway checks are separate from hardware execution. The investigation issued no device writes, but the diagnostic cannot establish the user's complete command history. Accepted writes require an explicit acknowledgement and subsequent actual-state comparison; supplied snapshots do not establish that acceptance. Fresh running-cycle telemetry is also needed to compare the new [progress/time sensors](cycle-progress.md) with the app. Lifecycle, ordinary-cycle events, richer vacuum behavior, maps/history and compound-state acceptance remain pending. See [verification](verification.md) and [live coverage](live-coverage.md).
