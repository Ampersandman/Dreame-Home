# Troubleshooting

## Sign-in fails

Check that the credentials work in the **Dreame Home** app and that the selected server region matches the account. An account connected through a different Dreame or Xiaomi service may not use the same sign-in credentials.

If Home Assistant cannot connect, check its internet connection and try again later. If Dreame is limiting requests, wait before retrying.

If an existing integration requests reauthentication, use its sign-in prompt with the same account and region. Removing and adding the integration again is usually unnecessary.

## A device is missing

Confirm that the device appears in the Dreame Home app under the same account and server region. Account discovery refreshes approximately every ten minutes. A newly added device may appear after the next refresh or an integration reload.

Model-specific controls are available for the [supported models](entities.md#supported-devices). Other discovered devices may have fewer sensors and no controls.

## Sensors show unknown or unavailable

These states describe different situations:

| State | Meaning |
| --- | --- |
| **Unknown** | The device has not supplied a usable value, or the value cannot currently be interpreted. |
| **Unavailable** | The device or connection is unavailable, or the entity requires fresher suitable state. |

After a laundry appliance powers off, unavailable controls and unknown cycle progress are expected. Previously reported diagnostic values may remain visible. They are not evidence of a running cycle.

The **Cloud reported online** status comes from Dreame and may lag physical power changes until discovery refreshes. **MQTT connected** indicates a connection to the messaging service; it does not prove that the appliance is powered on or sending fresh values.

If the appliance is on, check whether the app itself shows current values. Leave live MQTT updates enabled for the most complete telemetry and allow time for fresh state to arrive.

## A setting or button is unavailable

Controls need an online appliance and successful required state received within the last three minutes. They also follow the supported program and cycle restrictions.

Check the following:

- The appliance is powered on and visible in the Dreame Home app.
- Child lock is off where required.
- The selected program supports the setting.
- The appliance is in a suitable phase. Most program settings are changed before starting a cycle; **Pause** is used while running.
- Network/remote-control authorization is enabled if the appliance requires it for **Start**.
- There is no active fault preventing the command.

The integration's diagnostics distinguish supported commands from commands available in the current state. An unavailable button does not necessarily mean the model lacks that feature.

If a command returns a network or ambiguous-result error, check the appliance before trying again. Home Assistant does not automatically replay an uncertain command. The displayed state changes after the appliance confirms it through a subsequent update.

## Progress looks different from the app or moves backward

Laundry progress is an estimate from the appliance's reported program duration and remaining time. If the appliance revises its estimate, progress can move backward and elapsed time can change. Unknown timing is shown as unknown rather than a fabricated percentage.

For the washer, 100% can indicate that washing has completed while fresh-air care continues. It does not necessarily mean that the appliance has powered off. See [cycle sensors](entities.md#cycle-sensors).

## The laundry card is missing or outdated

The card is loaded by the integration automatically. After installing or updating:

1. Restart Home Assistant.
2. Reload the dashboard. If necessary, refresh the browser without its cache or fully reopen the Home Assistant app.
3. Edit the dashboard and look for **Dreame Home Laundry** in **Add card**.

Do not copy the JavaScript file to `www` or add a duplicate dashboard resource. See [dashboard card setup](dashboard-card.md).

If a card shows missing entities, open its visual editor and select the current entities. Entity IDs can differ from examples and can be renamed in Home Assistant. Find the actual IDs under **Settings → Devices & services → Entities** or **Developer tools → States**.

## Report a problem

[Open an issue](https://github.com/Ampersandman/Dreame-Home/issues) with:

- Your Dreame Home integration version and Home Assistant Core version.
- The device model and the affected feature.
- What you expected and what happened, including whether the appliance was powered on and which cycle phase it was in.
- Relevant error text or reviewed diagnostics, if useful.

You can download diagnostics from the integration's menu in **Settings → Devices & services**. Review the file before attaching it publicly. Diagnostic redaction reduces exposed information but is not a substitute for checking what you share.

Keep passwords, refresh/access tokens, account identifiers, device identifiers, signed download URLs, and Home Assistant backups private. Do not post configuration-storage files or raw account responses. The integration stores a refresh token in Home Assistant; protect configuration access and backups.

[Installation](installation.md) · [Entities and controls](entities.md) · [Back to README](../README.md)
