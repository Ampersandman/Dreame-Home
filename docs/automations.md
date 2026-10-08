# Automations and action examples

Use Dreame Home Laundry entities with standard Home Assistant actions. These examples use **generic English entity IDs**; replace them with your actual IDs before saving.

Find IDs in **Settings → Devices & services → Entities** or **Developer tools → States**. Select entities also expose an `options` attribute: use the exact option text shown there. Program options are always in English.

## Read the primary laundry entity

The appliance's **Run status** sensor also carries its consolidated cycle information as attributes. You can read these attributes in a template without selecting a separate sensor for each value:

```jinja
{{ state_attr('sensor.washer_run_status', 'program') }}
{{ state_attr('sensor.washer_run_status', 'phase') }}
```

Replace the entity ID with your washer's Run status sensor, or use the dryer's sensor for dryer information. Check for `none` before using an attribute in a calculation or action. See [primary laundry entity attributes](entities.md#primary-laundry-entity) for the available fields and freshness rules.

## Notify when the washer is nearly finished

This automation creates a Home Assistant notification when the reported remaining time enters the last five minutes. The message describes an estimate rather than guaranteed completion.

```yaml
alias: Laundry - washer nearly finished
triggers:
  - trigger: numeric_state
    entity_id: sensor.washer_remaining_time
    above: 0
    below: 6
conditions:
  - condition: numeric_state
    entity_id: sensor.washer_cycle_progress
    above: 0
    below: 100
actions:
  - action: persistent_notification.create
    data:
      title: Washer nearly finished
      message: >-
        The washer estimates {{ states('sensor.washer_remaining_time') }}
        minutes remaining. Check the appliance before unloading.
mode: single
```

The appliance may change its estimate. A notification can occur again if remaining time rises above the threshold and later falls below it.

See [Home Assistant numeric-state triggers](https://www.home-assistant.io/docs/automation/trigger/#numeric-state-trigger) and [persistent notifications](https://www.home-assistant.io/integrations/persistent_notification/).

## Select a washer program

Add the following as a script, or use its action in an automation. `Quick Wash` is the option regardless of your Home Assistant language. Check your entity's `options` before using it.

```yaml
alias: Laundry - choose quick wash
sequence:
  - action: select.select_option
    target:
      entity_id: select.washer_program
    data:
      option: Quick Wash
mode: single
```

This changes the selected program only. It does not start a cycle or automatically apply other settings. The appliance must report a suitable current state for program selection.

## Start a prepared cycle explicitly

After preparing the appliance and choosing its settings, this separate script presses the start/resume button:

```yaml
alias: Laundry - start prepared washer
sequence:
  - action: button.press
    target:
      entity_id: button.washer_start_or_resume
mode: single
```

Start requires the appliance's remote-control authorization, no blocking fault or child lock, and suitable recent state. A program-selection action does not implicitly invoke this script.

Use the actual dryer start/resume entity to create the equivalent dryer script. Pause and stop buttons use the same `button.press` action; **laundry stop ends the operation and powers the appliance off**.

## Choose useful triggers

Cycle progress is estimated, and washer 100% can precede the end of fresh-air care. Do not treat the percentage alone as proof that an appliance is powered off. Use the reported phase or status for automations that need a particular physical state.

Unknown or unavailable state is not zero. Numeric-state triggers naturally ignore non-numeric values; avoid templates that turn unknown timing into zero for completion detection.

Commands follow the same availability rules as dashboard controls. Automations can receive a validation error when an appliance is off, data is stale, or the selected program does not permit a change. After an ambiguous command error, inspect the appliance before retrying.

[Entities and controls](entities.md) · [Dashboard card](dashboard-card.md) · [Back to README](../README.md)
