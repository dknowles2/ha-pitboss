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

**This integration will set up the following platforms:**

| Platform        | Description                                                     |
| --------------- | --------------------------------------------------------------- |
| `binary_sensor` | Shows various grill sensors                                     |
| `climate`       | Controls grill temperature                                      |
| `switch`        | *(Not implemented yet)* Enables/disables various grill features |

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

## Tips to get a better connection
The antenna that comes with the modules are failry weak considering 90% of it is blocked by the hopper (which is all metal). Most of us will use this outside and far away from the nearest bluetooth proxy/whatever youre using to connect this to HA. To get a better connection, you can buy a magnetic antenna that has a coax male terminal as well as an IPEX connector with a female coax. There are also antennas that have IPEX connections which removes the need for the adapter. Simply disconnect the current antenna and atach the new one. It's easily accessible from the back of the unit without any need for modifications. Feed the cable through the bottom holes of the hopper access panel and stick the antenna anywhere on the hopper. This option allows your antenna to be mounted outside the hopper and give you much better range.

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
