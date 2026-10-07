# Laundry dashboard card

The **Dreame Home Laundry** card is bundled with the integration. It shows an appliance illustration, current status, cycle progress, timing, program selection, and available controls for one L9 washer or dryer.

The card loads automatically when the integration starts. You do not need to copy JavaScript files or add dashboard resources.

![Washer and dryer laundry cards](assets/laundry-card.png)

*Preview with sample values.*

## Add a card with the visual editor

1. Install Dreame Home, connect your account, and restart Home Assistant if you have just installed or updated it.
2. Open the dashboard and choose **Edit dashboard**.
3. Choose **Add card**, then select **Dreame Home Laundry**.
4. Select the washer or dryer device.
5. Set an optional card name and review the detected entities.
6. Save the card.

Add a second card for the other appliance. See [Home Assistant's card guide](https://www.home-assistant.io/dashboards/cards/) for dashboard editing.

The editor lets you override detected entities. Use an override when you want a particular entity or an automatic selection needs adjustment. Settings are detected automatically; an optional YAML list lets you choose which settings to display.

The card follows your Home Assistant frontend language: German when it is set to German, English otherwise. There is no separate card-language setting.

## Using the card

- Review status, estimated progress, and remaining time before issuing a command.
- Choose a program and adjust the available settings.
- Use **Start** separately when the appliance is ready. Selecting a program does not start it.
- Use **Pause** during a running cycle, or **Power off** to end the operation and power the appliance off.

Use **All programs** to expand the program list. The dryer separates **Dry** and **Care** programs into tabs. Open the settings button in the card header to show additional controls.

Program tiles can show a **Reference** duration. This is a program's default estimate, not the current cycle's remaining time. The timing at the top of the card comes from actual reported cycle values.

The card reflects entity availability. Settings that are not permitted for the current program or cycle state remain unavailable.

The drum animates only when the appliance reports a recent actual running state. A paused, powered-off, or stale appliance does not display a running animation. The artwork is included in the card; it needs no external image service.

Progress is estimated from appliance timing and can change when the appliance revises its duration. Read [cycle sensors](entities.md#cycle-sensors) for the meaning of progress and unknown values.

## YAML configuration

The visual editor writes the configuration for you. If you prefer YAML, use the selected device's **Home Assistant device registry ID**, not a Dreame cloud ID. The editor supplies the correct value.

A minimal card is:

```yaml
type: custom:dreame-home-laundry-card
device_id: YOUR_HOME_ASSISTANT_DEVICE_ID
name: Washing machine
```

The appliance type and entities are normally detected from the selected device. You can override them explicitly. The following example uses generic English entity IDs; replace them with your own:

```yaml
type: custom:dreame-home-laundry-card
device_id: YOUR_HOME_ASSISTANT_DEVICE_ID
appliance: washer
name: Washing machine
status_entity: sensor.washer_run_status
progress_entity: sensor.washer_cycle_progress
remaining_entity: sensor.washer_remaining_time
duration_entity: sensor.washer_program_duration
program_entity: select.washer_program
start_entity: button.washer_start_or_resume
pause_entity: button.washer_pause
stop_entity: button.washer_stop_and_power_off
settings_entities:
  - select.washer_temperature
  - select.washer_spin_speed
  - switch.washer_child_lock
```

For a dryer card, select its device, use `appliance: dryer`, and choose dryer entities. The visual editor is the easiest way to get the correct IDs.

| Option | Purpose |
| --- | --- |
| `device_id` | Selected Home Assistant laundry device. |
| `name` | Optional card title. |
| `appliance` | Optional `washer` or `dryer` override. |
| `status_entity` | Run-status sensor used for status and running animation. |
| `progress_entity` | Cycle-progress sensor. |
| `remaining_entity` | Remaining-time sensor. |
| `duration_entity` | Program-duration sensor. |
| `program_entity` | Program selector. |
| `start_entity` | Start/resume button. |
| `pause_entity` | Pause button. |
| `stop_entity` | Stop/power-off button. |
| `settings_entities` | Optional list of setting selectors, switches, or numbers to show. |

## After an update

Restart Home Assistant after installing the integration update, then reload the browser or Home Assistant app dashboard. The integration loads the card version automatically; do not add a second resource entry.

If the card is missing from the picker or an entity cannot be found, see [card troubleshooting](troubleshooting.md#the-laundry-card-is-missing-or-outdated).

[Entities and controls](entities.md) · [Automations](automations.md) · [Back to README](../README.md)
