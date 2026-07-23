# PitBoss

[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)

[![hacs][hacsbadge]][hacs]
![Project Maintenance][maintenance-shield]

A Home Assistant custom integration to interact with [PitBoss grills and smokers][pitboss].

> **WARNING: THIS INTEGRATION IS STILL UNDER ACTIVE DEVELOPMENT AND MAY NOT YET WORK PROPERLY.**
>
> **USE AT YOUR OWN RISK**

Supported models can be found at https://github.com/dknowles2/pytboss#supported-models.

## Features

- **100% local, no cloud required.** Communicates directly with the grill over Bluetooth (BLE) or your local WiFi (WebSocket), reported to Home Assistant as a `local_push` integration.
- **Automatic discovery.** Power on your grill and it's discovered automatically over Bluetooth; manual setup by device ID is also supported.
- **Dual connection protocols.** Choose Bluetooth (`ble`) or WebSocket (`wss`, default) when configuring the integration, and switch between them later via reconfigure.
- **Reconfigurable.** Change the grill model, password, or connection protocol after initial setup without deleting the integration.
- **Adapts to your grill's capabilities.** Entities such as the grill light, meat probes, primer motor switch, and recipe sensors are only created if your specific model supports them.
- **Safety first.** For safety reasons, the integration can never turn the grill on remotely — you can only monitor it and turn it off. This mirrors the physical safety design of the grill itself.

**This integration will set up the following platforms:**

| Platform        | Description                                                                                                    |
| ---------------- | --------------------------------------------------------------------------------------------------------------- |
| `binary_sensor`  | Diagnostic error sensors (probe/startup/high-temp/fan/igniter/auger/pellet errors) and an auger "running" sensor |
| `climate`        | Monitors and controls grill temperature; reports heating/cooling/fan/idle status; turn off only (safety)         |
| `light`          | Controls the grill's built-in light, if the model has one                                                        |
| `number`         | Sets target temperatures for meat probes 1 and 2, on models that support probe-based shutoff/alerts              |
| `sensor`         | Meat probe temperatures (up to 4 probes, enabled based on how many the grill has), and recipe time/step for models with guided-recipe functionality |
| `switch`         | Grill module power (turn off only, for safety) and primer motor control, if supported by the model               |

### Entity details

- **Climate (`Grill temperature`):** Shows current and target grill temperature, and HVAC action (heating/cooling/fan/idle/off). Setting HVAC mode to `off` turns off the grill and resets the target temperature to the model's minimum. The grill cannot be turned on remotely for safety reasons.
- **Light (`Light`):** On/off control for the grill's light, only created for models that have one.
- **Sensor (`Probe 1`–`Probe 4`):** Meat probe temperatures in °F or °C, matching the grill's current unit setting. Only as many probes as the grill physically supports are enabled by default.
- **Sensor (`Recipe Time` / `Recipe Step`):** Progress through a guided recipe, for models with recipe functionality.
- **Number (`Probe 1 Target` / `Probe 2 Target`):** Set a target temperature for probes 1 and 2, on models that support it.
- **Switch (`Module power`):** Turns the grill module off (cannot turn it on remotely, for safety).
- **Switch (`Prime`):** Runs the auger primer motor, on models that support it.
- **Binary sensor:** Diagnostic error flags (probe errors, startup error, high-temperature error, fan error, igniter error, auger error, no-pellets) plus an `Auger` running-state sensor.

## Installation

### HACS

If you have HACS, go to the three-dot menu and click `Custom
repositories`. Paste the link to the Github repository and select "Integration"
as the category.

### Manual

1. Using the tool of choice open the directory (folder) for your HA configuration (where you find `configuration.yaml`).
1. If you do not have a `custom_components` directory (folder) there, you need to create it.
1. In the `custom_components` directory (folder) create a new folder called `pitboss`.
1. Download _all_ the files from the `custom_components/pitboss/` directory (folder) in this repository.
1. Place the files you downloaded in the new directory (folder) you created.
1. Restart Home Assistant
1. In the HA UI go to "Configuration" -> "Integrations" click "+" and search for "PitBoss"

## Configuration is done in the UI

Power on your grill and it should be discovered automatically over Bluetooth. Once you
initiate the setup process, it will ask for your exact grill model so we can properly
communicate with it. No cloud access necessary!

If your grill isn't discovered automatically, you can add it manually by entering its
device ID. You'll then choose your exact model and, optionally, a connection password
and whether to connect over Bluetooth or WebSocket (WiFi).

Already set up? You can change the model, password, or connection protocol at any time
via the integration's "Reconfigure" option, without needing to remove and re-add it.

## Contributions are welcome!

If you want to contribute to this please read the [Contribution guidelines](CONTRIBUTING.md)

***

[pitboss]: https://github.com/dknowles2/ha-pitboss
[commits-shield]: https://img.shields.io/github/commit-activity/y/dknowles2/ha-pitboss.svg?style=for-the-badge
[commits]: https://github.com/dknowles2/ha-pitboss/commits/main
[hacs]: https://github.com/hacs/integration
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge
[discord]: https://discord.gg/Qa5fW2R
[discord-shield]: https://img.shields.io/discord/330944238910963714.svg?style=for-the-badge
[exampleimg]: example.png
[forum-shield]: https://img.shields.io/badge/community-forum-brightgreen.svg?style=for-the-badge
[forum]: https://community.home-assistant.io/
[license-shield]: https://img.shields.io/github/license/dknowles2/ha-pitboss.svg?style=for-the-badge
[maintenance-shield]: https://img.shields.io/badge/maintainer-David%20Knowles%20%40dknowles2-blue.svg?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/dknowles2/ha-pitboss.svg?style=for-the-badge
[releases]: https://github.com/dknowles2/ha-pitboss/releases
