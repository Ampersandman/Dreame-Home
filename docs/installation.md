# Installation and updates

## Before you begin

You need:

- Home Assistant Core **2026.9.4 or newer**.
- [HACS](https://www.hacs.xyz/docs/use/).
- A Dreame Home account with your appliances already registered in the Dreame Home app.
- An internet connection from Home Assistant to the Dreame cloud.

The L9 washer, L9 Twin Inverter dryer, and L10s Ultra Gen 3 have model-specific support. See [supported devices and entities](entities.md).

## Install from HACS

1. Open **HACS** in Home Assistant.
2. Open the menu in the upper-right corner and choose **Custom repositories**.
3. Enter `https://github.com/Ampersandman/Dreame-Home`.
4. Select type **Integration**, then choose **Add**.
5. Find **Dreame Home**, open it, and download it.
6. Restart Home Assistant.

For more information about adding repositories, see [HACS custom repositories](https://www.hacs.xyz/docs/faq/custom_repositories/).

## Connect your account

1. Open **Settings → Devices & services**.
2. Choose **Add integration** and search for **Dreame Home**.
3. Enter the credentials you use to sign in to Dreame Home.
4. Select the **Server region** used by your account in the app. A European account normally uses `eu`; choose the region that matches your app rather than your Home Assistant location.
5. Leave **Enable live MQTT updates** selected to receive additional and more timely telemetry.
6. Submit the form and wait for your devices to appear.

The integration connects to Dreame's MQTT service itself. You do not need an MQTT add-on, a local broker, or MQTT credentials.

With MQTT disabled, device discovery and periodic cloud reads still work. Some telemetry may be available only through live MQTT updates.

## Check your devices

Open **Dreame Home** under **Settings → Devices & services**, then open a device. Power on a laundry appliance to see current cycle information and available settings. Controls can remain unavailable until the appliance supplies suitable recent state.

The Dreame cloud's online status can lag a power change. Discovery refreshes approximately every ten minutes; telemetry reads normally run about once a minute. Live updates can arrive between reads.

For remote laundry start, enable the appliance's network/remote-control authorization using its own controls or app where required. Child lock, current program, and cycle phase can also limit commands. See [entities and controls](entities.md).

Next, [add the bundled laundry dashboard card](dashboard-card.md) or create your own dashboard using the [available entities](entities.md).

## Update

1. Open **Dreame Home** in HACS and install the available update. If you need to fetch the repository again, use HACS's redownload option.
2. Restart Home Assistant.
3. Reload the browser or Home Assistant app dashboard so it loads the updated card.

Entity identities are preserved across updates. Existing entity IDs, automations, and card selections remain attached to the same entities. A displayed name can change as labels improve; you can rename entities in Home Assistant.

The repository currently distributes beta versions. Check the installed version before reporting a problem.

## Sign in again

If Home Assistant requests reauthentication, open the integration's sign-in prompt and enter the credentials for the **same account and server region**. You do not need to remove the integration or recreate your entities.

The password is used for authentication and is not saved by the integration. Home Assistant saves the username, account information, and refresh token, and updates the token when Dreame rotates it. Protect your Home Assistant configuration and backups as you would for other account-connected integrations.

[Troubleshooting](troubleshooting.md) · [Back to README](../README.md)
