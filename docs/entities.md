# Entities and controls

Open **Settings → Devices & services → Dreame Home Laundry** and select a device to see its entities. Cycle information appears under sensors, program parameters and cycle buttons under controls, and persistent preferences such as child lock under configuration. Additional telemetry is kept in diagnostics. The exact set depends on the model, firmware, and values the appliance reports.

Integration-provided entity names, program choices, and card text are always in English, independently of your Home Assistant language. Names you assign yourself are preserved.

## Supported devices

| Device | Supported cloud model |
| --- | --- |
| Dreame Washing Machine L9 | `dreame.washer.l9nacn` |
| Dreame Twin Inverter Dryer L9 | `dreame.dryer.l9nacn` |

This guide covers the two L9 models listed above. Feature availability can vary with firmware and the values reported by the appliance.

## Primary laundry entity

Each L9 washer and dryer has a **Run status** sensor that combines its operating state with cycle information and settings in one entity. Open the sensor's details or view it in **Developer tools → States** to inspect its attributes.

| Attribute | Meaning |
| --- | --- |
| `appliance_type` | `washer` or `dryer`. |
| `status`, `status_code` | English operating status and the corresponding appliance code. |
| `is_running`, `is_paused`, `is_powered_on` | Operating-state flags derived from recent reported status. |
| `program`, `program_code` | Current English program name and appliance code. |
| `program_options` | Standard English program choices for the model. Actual selectable options can be further limited by current control availability. |
| `phase`, `phase_code` | Current wash or dry phase and appliance code. |
| `error`, `error_code`, `has_error` | Reported fault information. |
| `program_duration`, `remaining_time` | Estimated total and remaining cycle time, in minutes. |
| `progress`, `elapsed_time` | Estimated progress in percent and elapsed cycle time in minutes, calculated from valid cycle timing. |
| `settings` | Reported settings keyed by control name, with English choices or boolean values. |

The consolidated attributes use recent successful observations. Missing, invalid, or stale values are `null`, and unobserved settings are omitted; a missing running flag does not mean the appliance is stopped. Settings describe observed appliance state. Sending a command does not replace them with an assumed result. Progress and timing follow the [cycle-sensor rules](#cycle-sensors).

The sensor retains its existing entity ID and status values. Individual cycle sensors, program selectors, settings, and start/pause/stop buttons remain available for dashboards and automations. The [laundry card](dashboard-card.md) presents these sensors and controls together.

## Cycle sensors

The L9 washer and dryer provide the following useful cycle information when reported:

| Entity | Purpose |
| --- | --- |
| **Run status** | Whether the appliance is off, waiting, running, paused, or in another reported operating state. |
| **Wash phase / Dry phase** | The current stage of washing or drying. |
| **Program** | The current program. The program selector also provides a control for choosing a supported program. |
| **Program duration** | The appliance's estimated total duration, in minutes. |
| **Remaining time** | The appliance's estimated time left, in minutes. |
| **Cycle progress** | Estimated progress as a percentage. |
| **Elapsed cycle time** | The difference between reported program duration and remaining time, in minutes. |

Cycle progress is calculated from reported timing:

```text
progress = (program duration − remaining time) / program duration × 100
elapsed time = program duration − remaining time
```

The appliance can revise its estimated duration while it runs. Progress may move backward, and elapsed time is not a stopwatch. Invalid or missing timing stays unknown.

Progress and elapsed time need recent successful state and suitable cycle context. After power-off or when data is stale, these values become unknown. A zero remaining-time estimate in the washer's AI program can also mean that an estimate is not yet available.

For the washer, 100% can mean that washing has finished while fresh-air care continues. It does not always indicate appliance shutdown.

## Washer controls

The program selector offers **15 standard programs**, all named in English. Additional programs reported by the appliance can still be recognized as current state without being offered for selection.

| Control | Purpose |
| --- | --- |
| **Program** | Choose a standard washing program. |
| **Temperature** | Choose a supported wash temperature. |
| **Extra time** | Adjust the supported additional washing time. |
| **Water level** | Choose the supported water setting. |
| **Rinse cycles** | Set the supported rinse count. |
| **Spin speed** | Choose a supported spin setting. |
| **Detergent dosing** | Choose the supported detergent-dosing setting. |
| **Softener dosing** | Choose the supported softener-dosing setting. |
| **Child lock** | Change the appliance's child-lock state. |
| **Fresh air circulation** | Change fresh-air care where the current cycle permits it. |
| **Dynamic rinse** | Change the supported dynamic-rinse setting. |
| **Speed mode** | Change the supported faster-cycle setting. |
| **Night mode** | Change the supported quieter-cycle setting. |

Choices are filtered for the selected program and current settings. Some combinations are incompatible; for example, a program may limit spin speed or temperature. The integration offers only the options it can validate for the current state.

## Dryer controls

The program selector offers **25 standard programs**: **16 drying programs** and **9 care programs**, all named in English.

| Control | Purpose |
| --- | --- |
| **Program** | Choose a standard drying or care program. |
| **Dryness level** | Choose a supported target dryness. |
| **Airflow** | Choose a supported airflow setting. |
| **Extra time** | Adjust the supported additional drying time. |
| **Steam level** | Choose the supported steam setting. |
| **Child lock** | Change the appliance's child-lock state. |
| **Wrinkle care** | Change wrinkle care when the cycle phase permits it. |
| **Low temperature** | Change the supported lower-temperature drying setting. |
| **Speed mode** | Change the supported faster-drying setting. |

Low-temperature drying and speed mode are mutually exclusive. Turn off the active mode before enabling the other. Program-specific restrictions can further limit options.

## Standard program names

The English program names are:

| Appliance | Group | Programs |
| --- | --- | --- |
| Washer | Wash | AI Wash, ECO 40-60, Quick Wash, Mixed, Large Items, Cotton, Down, Wool, Towels, Underwear, Baby Care, Anti-Allergen, Spin Only, Rinse & Spin, Drum Clean |
| Dryer | Dry | AI Dry, Quick Dry, Large Items, Wool, Down, ECO, Shirts, Baby Care, Underwear, Synthetics, Sportswear, Outerwear, Small Load, Silk, Sanitize Dry, Pet Hair Removal |
| Dryer | Care | Hot Air, Cold Air, Quilt Refresh, Wool, Down, Shirts, Silk, Cotton, Hygiene Care |

Names that occur in both dryer groups are distinguished in the Home Assistant selector, for example **Dry: Wool** and **Care: Wool**. The card displays them in separate tabs. Use the exact text in your selector's options when creating an automation.

## Start, pause, and stop

Both laundry appliances have separate buttons:

| Button | Effect |
| --- | --- |
| **Start or resume** | Start a prepared cycle or resume a paused cycle when authorized. |
| **Pause** | Pause a running cycle. |
| **Stop and power off** | End the current operation and power off the appliance. |

**Choosing a program does not start a cycle.** Select the program and any available settings first, then use **Start or resume** when ready.

Most program settings are available before a cycle starts. Controls require an online device and successful required state received within the last three minutes. Child lock, faults, network-control authorization, and the current phase can disable individual commands.

State changes are shown after the appliance reports them. A submitted command does not immediately replace the displayed state with an assumed result.

## Diagnostics and additional telemetry

**Cloud reported online** describes Dreame's account-discovery status. **MQTT connected** describes the connection to Dreame's messaging service. These are separate signals: a broker connection can remain active while an appliance is powered off.

Additional reported properties may appear as diagnostic entities. Properties without a confirmed meaning keep a neutral label. Some raw or duplicate diagnostic entities are hidden or disabled by default to keep the device page focused; you can inspect their entity settings in Home Assistant if needed.

## Entity IDs and updates

Home Assistant assigns entity IDs, and you can rename them. The example IDs in the [automation guide](automations.md) are placeholders; replace them with the IDs from **Settings → Devices & services → Entities** or **Developer tools → States**.

Entity identities remain stable when labels and grouping improve. Existing IDs and automations are retained. User-assigned names and entity visibility settings are respected.

[Dashboard card](dashboard-card.md) · [Troubleshooting](troubleshooting.md) · [Back to README](../README.md)
