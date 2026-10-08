# Dreame Home Laundry

<img src="https://raw.githubusercontent.com/Ampersandman/Dreame-Home/main/custom_components/dreame_home/brand/icon.png" alt="Dreame Home Laundry" width="96" height="96">

Dreame Home Laundry connects Home Assistant to the Dreame Washing Machine L9 and Twin Inverter Dryer L9 registered in your Dreame Home account. Supported cloud models are `dreame.washer.l9nacn` and `dreame.dryer.l9nacn`.

The integration includes laundry sensors and controls and the **Dreame Home Laundry** dashboard card. Each appliance's **Run status** sensor provides a consolidated overview through its attributes, including program, phase, timing, progress, and settings. Separate program selectors and buttons provide controls.

The card shows washer and dryer product images with a drum animation while running. It loads automatically and has a visual editor; no file copying or dashboard-resource configuration is required.

Entity names, program choices, and card text are provided in English regardless of your Home Assistant language. Names you set yourself remain yours to customize.

## Install

Requires Home Assistant Core **2026.9.4 or newer**. Add `https://github.com/Ampersandman/Dreame-Home` to HACS as a custom repository of type **Integration**, download **Dreame Home Laundry**, and restart Home Assistant. Then add **Dreame Home Laundry** under **Settings → Devices & services** and sign in using the server region selected in the Dreame Home app.

## Guides

- [Installation and updates](https://github.com/Ampersandman/Dreame-Home/blob/main/docs/installation.md)
- [Entities and controls](https://github.com/Ampersandman/Dreame-Home/blob/main/docs/entities.md)
- [Laundry dashboard card](https://github.com/Ampersandman/Dreame-Home/blob/main/docs/dashboard-card.md)
- [Automation examples](https://github.com/Ampersandman/Dreame-Home/blob/main/docs/automations.md)
- [Troubleshooting and privacy](https://github.com/Ampersandman/Dreame-Home/blob/main/docs/troubleshooting.md)

Program selection does not start an appliance. Use the separate start/resume control when you are ready. Controls become available only when the appliance reports recent suitable state.

Current version: **0.4.0b5 — beta**. This community integration is not affiliated with Dreame.
