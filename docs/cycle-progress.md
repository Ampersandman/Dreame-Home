# Cycle and time sensors in 0.3.0b2

The exact L9 washer and dryer expose **Cycle progress** (%) and **Elapsed cycle time** (minutes), derived from their reported timing and cycle context. Existing duration and remaining-time sensors receive readable names and duration units without changing their property identities. These sensors issue no appliance commands.

| Exact model | Program duration | Remaining time | Context |
| --- | --- | --- | --- |
| `dreame.washer.l9nacn` | `2.12`, minutes | `2.13`, minutes | Run status `2.1`, program `2.3`, phase `2.4` |
| `dreame.dryer.l9nacn` | `2.9`, minutes | `2.11`, minutes | Run status `2.1`, program `2.3`, phase `2.4` |

The dryer's source names `programTime` and `finishTime` refer to duration and remaining minutes here. `finishTime` is not a timestamp. Dividing these values by 60 in the app formats hours; the wire values are already minutes. Duration sensors use Home Assistant's duration device class. The two derived sensors have separate stable identities, `cycle:progress` and `cycle:elapsed_time`, attached to the same discovered device.

## Formula and validity

For total reported minutes `T` and remaining reported minutes `R`:

```text
Elapsed cycle time = T - R
Cycle progress = (T - R) / T * 100
```

The app formula is unrounded and unclamped. The integration rounds progress to one decimal for display. This is an estimated ratio of appliance-reported timing, not a stopwatch or a wall-clock completion forecast. Both values can move backward when the appliance revises its duration estimate. They are measurement sensors, not cumulative counters.

Required replies must be successful RPC/MQTT observations with a value in the latest reply, no null-reply flag and a successful-observation age of at most **180 seconds**. Duration, status, program and phase values must have the source's integer wire types; Boolean values and numeric strings do not substitute for those property values. Unsupported models, powered-off status, stale/missing/failed context and unknown source enums stay unknown/unavailable.

Ordinary ratio derivation requires running or paused status and a recognized active phase. Standby, scheduled state and the dryer's completed phase do not imply a running estimate. Missing durations, `T <= 0`, negative remaining time or `R > T` produce unknown values rather than clamping or inventing time. For washer AI Wash program `0`, a remaining value of `0` in a nonterminal phase means no usable estimate: the app displays `--min`, so the integration does not turn it into measured 0% or 100%.

The washer has a source-specific exception: fresh, powered phase `5` (Air Refresh Cruise) or `6` (Completed) reports **100% washing completion**, even without usable duration rows. This does not imply appliance shutdown; fresh known powered status and program/phase context remain required. Elapsed time still needs valid durations. An old completed phase retained after power off cannot create a current 100% reading.

## Source provenance

The pure [cycle helper](../src/dreamehome/laundry_progress.py) records the pinned plugin source and evidence; the [telemetry overlay](../src/dreamehome/telemetry.py) applies read-only labels and units without changing generated source catalogues.

| Exact plugin | Evidence |
| --- | --- |
| Washer plugin 83, [catalogue](../src/dreamehome/data/l9_washer.json) | `projects_dreame.washer.l9nacn_views_components_Timeline_index`: property bindings at lines 20042–20048, minute formatting at 20065–20085, progress and terminal-phase handling at 20092–20101 |
| Dryer plugin 130, [catalogue](../src/dreamehome/data/l9_dryer.json) | `projects_dreame.dryer.l9nacn_request_index`: bindings at 7920/7926; `views_Run_index` at 16455/16470/17068/17072; `views_components_Timeline_index`: minute formatting at 17413/17421 and progress at 17428–17449 |

## Vacuum telemetry

For exact `dreame.vacuum.r5023a`, source metadata names cleaning time `4.2` in minutes and cleaned area `4.3` in square metres. Cleaning progress `4.63` and mop-drying progress `4.64` use reported percentages in the valid 0–100 range. These are source-backed property readings, not the L9 timing formula; their labels do not manufacture values or a task context that the device has not supplied.

The value itself and its source-required context must be successful current replies no more than 180 seconds old. Time, area and cleaning progress use recognized state `2.1`, status `4.1` and task `4.7`; historical time/area can remain valid while idle. Source mapping/cruising conditions exclude time, area and cleaning progress. Cleaning progress requires active or paused cleaning context. Mop-drying progress requires fresh self-wash status `4.25=2` (drying). Missing, null, stale or unknown context disables the corresponding sensor. The [vacuum telemetry helper](../src/dreamehome/vacuum_telemetry.py) records the pinned upstream availability rules and source lines.

The vacuum read seed now contains 22 candidates, including `4.63` and `4.64`. Neither progress coordinate appears in the latest supplied diagnostic. Its 167 rows include 145 source-mapped coordinates and 22 neutral ones; this does not establish acceptance of the two new reads. Progress appears only when an actual usable property value is reported.

Known-model candidates are retried after null, empty or failed replies, and previously valued exact-model addresses remain retryable after an error. The 240-address budget, request-coordinate checks, per-device command/poll lock, cloud-online gate and rate-limit cooldown remain intact. This repairs a provable one-shot-read starvation case; it is not evidence of a failure in the post-cycle diagnostic.

## Runtime acceptance still needed

The supplied `0.3.0b1` diagnostic was downloaded after the laundry cycles ended, so it cannot validate a running percentage, elapsed-time estimate or app-to-entity correspondence for `0.3.0b2`. A fresh running snapshot and comparison with the official app are still needed, including estimate revisions and completion/refresh phases. Earlier telemetry installation and MQTT evidence remain valid historical checks. See the [latest diagnostic review](ha-diagnostics-review-2026-10-06.md) and [verification](verification.md).
