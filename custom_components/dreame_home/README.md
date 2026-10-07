# Dreame Home

Dreame Home connects Home Assistant to devices registered in your Dreame Home account. It supports the L9 washing machine, L9 Twin Inverter dryer, and L10s Ultra Gen 3 vacuum, with available telemetry for additional discovered devices.

The integration includes laundry sensors and controls, a native vacuum entity, and the **Dreame Home Laundry** dashboard card. The card loads automatically and has a visual editor; no file copying or dashboard-resource configuration is required.

## Install

Requires Home Assistant Core **2026.9.4 or newer**. Add `https://github.com/Ampersandman/Dreame-Home` to HACS as a custom repository of type **Integration**, download **Dreame Home**, and restart Home Assistant. Then add **Dreame Home** under **Settings → Devices & services** and sign in using the server region selected in the Dreame Home app.

## Guides

- [Installation and updates](https://github.com/Ampersandman/Dreame-Home/blob/main/docs/installation.md)
- [Entities and controls](https://github.com/Ampersandman/Dreame-Home/blob/main/docs/entities.md)
- [Laundry dashboard card](https://github.com/Ampersandman/Dreame-Home/blob/main/docs/dashboard-card.md)
- [Automation examples](https://github.com/Ampersandman/Dreame-Home/blob/main/docs/automations.md)
- [Troubleshooting and privacy](https://github.com/Ampersandman/Dreame-Home/blob/main/docs/troubleshooting.md)

Program selection does not start an appliance. Use the separate start/resume control when you are ready. Controls become available only when the appliance reports recent suitable state.

Current version: **0.4.0b1 — beta**. This community integration is not affiliated with Dreame.
