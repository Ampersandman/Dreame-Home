# Troubleshooting

## Sign-in fails

Check that the credentials work in the **Dreame Home** app and that the selected server region matches the account. An account connected through a different Dreame or Xiaomi service may not use the same sign-in credentials.

If Home Assistant cannot connect, check its internet connection and try again later. If Dreame is limiting requests, wait before retrying.

If an existing integration requests reauthentication, use its sign-in prompt with the same account and region. Removing and adding the integration again is usually unnecessary.

## A device is missing

Confirm that the device appears in the Dreame Home app under the same account and server region. Account discovery refreshes approximately every ten minutes. A newly added device may appear after the next refresh or an integration reload.

Check that the appliance matches one of the [supported L9 models](entities.md#supported-devices).

## Sensors show unknown or unavailable

These states describe different situations:

| State | Meaning |
| --- | --- |
| **Unknown** | The device has not supplied a usable value, or the value cannot currently be interpreted. |
| **Unavailable** | The device or connection is unavailable, or the entity requires fresher suitable state. |

After a laundry appliance powers off, unavailable controls and unknown cycle progress are expected. Previously reported diagnostic values may remain visible. They are not evidence of a running cycle.

The **Cloud reported online** status comes from Dreame and may lag physical power changes. Offline L9 appliances are checked about once a minute so that live reads resume after the cloud reports them online again. Account discovery still runs approximately every ten minutes. **MQTT connected** indicates a connection to the messaging service; it does not prove that the appliance is powered on or sending fresh values.

If the appliance is on, check whether the app itself shows current values. Leave live MQTT updates enabled for the most complete telemetry and allow time for fresh state to arrive.

**Active program** is unknown when no running or paused cycle is reported; use **Selected program** to see the prepared program. **Program finish time** is unavailable unless the appliance reports a running cycle, an active washing or drying phase, and recent valid remaining time. It is also unavailable while paused or during aftercare. These states are expected and do not indicate a connection failure by themselves.

## An entity moved or has a different label

Cycle settings, child lock, and night mode appear under **Controls**. Cycle information appears under **Sensors**, and connection details and additional telemetry under **Diagnostic**. Home Assistant controls the visual layout and order within those sections.

**Operation state**, **Selected program**, and **Program progress** replace the previous display labels Run status, Program, and Cycle progress. Existing entity IDs and automations remain attached to the same entities. User-defined names and explicit disabled settings are preserved. Raw duplicate settings, fault codes, and delay-related telemetry are disabled by default; enable them in the entity settings if needed.

If **Active program** or **Remote start** is missing, check whether you previously disabled the entity yourself. The integration preserves that choice. **Remote start** reports appliance authorization; it is read-only and cannot enable remote authorization from Home Assistant.

## Appliances go offline after a cycle

The L9 appliances automatically power off after use. [Dreame Support confirms](https://de.forum.dreametech.com/forum.php?mod=viewthread&tid=7579) that the L9 washer powers off and becomes offline after a wash program. The [L9 dryer manual](https://d.otto.de/files/e3d3a3a1-eb49-5f81-a1e9-91d66687a19a.pdf), printed page 15, states that the dryer powers off if there is no operation for one minute after the program ends.

If both Home Assistant and Dreame Home show the appliance offline only while idle or after finishing, this matches automatic shutdown. The integration has no verified setting to disable automatic power-off or command that can wake an offline appliance. Cloud polling and MQTT keepalive maintain Home Assistant's connection to Dreame; they cannot keep an appliance's network connection awake.

Switch the appliance on at its panel before using controls. Once Dreame reports it online, the integration resumes reads on its normal polling schedule, usually within about a minute. Cloud delays, authentication failures, and rate limits can take longer. A metadata response alone does not make previous cycle readings fresh.

For remote starting, Dreame Support also states that the washer requires renewed network authorization before each start, with the door closed. Enable this authorization on the appliance when required. The integration keeps those appliance restrictions in place.

Going offline during an active cycle, or staying offline in Dreame Home after switching on, requires separate troubleshooting; it is not explained by post-cycle automatic shutdown.

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

Card text and integration-provided program choices are always in English. User-assigned device, entity, and card names keep the text you chose. If an older automation fails to select a program, replace its previous localized option with the current English option from the entity's `options` attribute.

## The integration icon is missing or outdated

The Dreame app icon is bundled with the integration. After updating, restart
Home Assistant and refresh the browser or reopen its app to clear cached images.

Home Assistant displays bundled brand images on the integration and device
pages. HACS 2.0.5 still retrieves its catalogue and update icons from a separate
brand service, so those views may show a placeholder even when Home Assistant
shows the correct icon. HACS needs its [upstream branding update](https://github.com/hacs/integration/pull/5388)
to use the bundled image. Reinstalling the integration does not fix that HACS limitation.

## Report a problem

[Open an issue](https://github.com/Ampersandman/Dreame-Home-Laundry/issues) with:

- Your Dreame Home Laundry integration version and Home Assistant Core version.
- The device model and the affected feature.
- What you expected and what happened, including whether the appliance was powered on and which cycle phase it was in.
- Relevant error text or reviewed diagnostics, if useful.

You can download diagnostics from the integration's menu in **Settings → Devices & services**. Review the file before attaching it publicly. Diagnostic redaction reduces exposed information but is not a substitute for checking what you share.

Keep passwords, refresh/access tokens, account identifiers, device identifiers, signed download URLs, and Home Assistant backups private. Do not post configuration-storage files or raw account responses. The integration stores a refresh token in Home Assistant; protect configuration access and backups.

[Installation](installation.md) · [Entities and controls](entities.md) · [Back to README](../README.md)
