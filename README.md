# Dreame Home for Home Assistant

Connect your Dreame Home account to Home Assistant and bring your laundry appliances and robot vacuum into one dashboard.

**Dreame Home** provides device status, useful sensors, model-specific controls, and a bundled laundry dashboard card. Devices are discovered automatically from your account. You do not need to find device IDs or configure an MQTT broker.

## Features

- **Laundry at a glance:** current program and phase, remaining time, program duration, estimated cycle progress, and elapsed cycle time.
- **Appliance controls:** program selection, supported settings, and separate start/resume, pause, and stop buttons.
- **App-aligned programs:** 15 standard washer programs and 25 dryer programs, including 16 drying programs and 9 care programs.
- **Robot vacuum:** a native Home Assistant vacuum entity with start, pause, stop, return to base, and fan-speed controls.
- **Laundry dashboard card:** an appliance illustration, cycle information, and controls, with English and German text and a visual editor.
- **Live updates:** cloud reads and optional MQTT updates, with additional telemetry exposed as it becomes available.

## Supported devices

| Device | Cloud model | Features |
| --- | --- | --- |
| Dreame Washing Machine L9 | `dreame.washer.l9nacn` | Laundry sensors, program selection, settings, and cycle controls |
| Dreame Twin Inverter Dryer L9 | `dreame.dryer.l9nacn` | Laundry sensors, drying/care programs, settings, and cycle controls |
| Dreame L10s Ultra Gen 3 | `dreame.vacuum.r5023a` | Vacuum entity and available telemetry |

Other devices in the account can appear with available telemetry. Model-specific controls are limited to the models listed above. Features and reported sensors can vary with firmware.

Current version: **0.4.0b1 — beta**. Requires **Home Assistant Core 2026.9.4 or newer** and an internet connection to the Dreame cloud.

## Install with HACS

1. In **HACS**, open the menu and select **Custom repositories**.
2. Add `https://github.com/Ampersandman/Dreame-Home` with type **Integration**.
3. Download **Dreame Home** and restart Home Assistant.
4. Open **Settings → Devices & services → Add integration → Dreame Home**.
5. Enter your Dreame Home account credentials and select the server region used in the app. Leave live MQTT updates enabled for the most complete telemetry.

Your devices will appear under the integration. The password is used to sign in; Home Assistant stores a refresh token for subsequent connections.

[Full installation and update guide](docs/installation.md)

## Add the laundry card

![Dreame Home laundry cards for a washer and dryer](docs/assets/laundry-card.png)

*Preview with sample values.*

The card is included with the integration and loads automatically. Edit a dashboard, choose **Add card**, and select **Dreame Home Laundry**. Use the visual editor to select your washer or dryer and its entities.

Program selection and **Start** are separate actions. Choosing a program does not start the appliance.

[Dashboard card setup and examples](docs/dashboard-card.md)

## User guides

| Guide | What it covers |
| --- | --- |
| [Installation](docs/installation.md) | HACS setup, account connection, and updates |
| [Entities and controls](docs/entities.md) | Sensors, programs, settings, and control availability |
| [Dashboard card](docs/dashboard-card.md) | Visual editor, card options, and YAML examples |
| [Automations](docs/automations.md) | Notifications and examples using Home Assistant actions |
| [Troubleshooting](docs/troubleshooting.md) | Sign-in, unavailable devices, card loading, and privacy |

Controls require the device to be online and to report recent usable state. Some settings are available only for particular programs or cycle phases. Home Assistant shows confirmed appliance state after updates; it does not assume that a submitted command succeeded.

Vacuum maps, room selection, and appliance scheduling are not provided by this integration.

## Support

For help, check the [troubleshooting guide](docs/troubleshooting.md) or [open an issue](https://github.com/Ampersandman/Dreame-Home/issues). Include the integration version, Home Assistant version, device model, and a description of the problem. Review diagnostics and logs before sharing them, and keep account credentials private.

This is a community integration and is not affiliated with Dreame. See [LICENSE](LICENSE) and [third-party notices](THIRD_PARTY_NOTICES.md) for licensing and attribution.
