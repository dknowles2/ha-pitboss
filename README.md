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
See [`docs/SUPPORTED_GRILLS.md`](docs/SUPPORTED_GRILLS.md) for a per-model breakdown of
which features (lights, meat probes, primer motor, recipe mode) each grill supports in
this integration. That file is auto-generated and kept in sync whenever the `pytboss`
dependency is updated.

## Features

- **No account, no app.** The integration talks to the grill itself. It never signs in to a PitBoss account and never uses the vendor's mobile app.
- **Automatic discovery.** Power on your grill and it's discovered automatically over Bluetooth; manual setup by device ID is also supported.
- **Two connection protocols.** Bluetooth (`ble`) or WebSocket (`wss`, the default), chosen at setup and changeable later via reconfigure. See [Connection protocols](#connection-protocols) — they are not equivalent, and one of them is not local.
- **Reconfigurable, and it asks rather than gives up.** Change the model, password, or protocol without deleting the integration. If the grill starts rejecting the password, the integration asks you to re-enter it instead of retrying forever.
- **Adapts to your grill.** The light, primer motor, recipe sensors, probe count, probe naming, and per-probe targets are all created from what your model and control board declare — not assumed.
- **Polls faster when it matters.** Updates arrive quickly while the grill is running and back off in standby.
- **Safety first.** The integration cannot turn the grill on remotely. You can monitor it and turn it off.

### Connection protocols

| | Reaches the grill via | Needs internet |
| --- | --- | --- |
| `ble` | Bluetooth, directly | No |
| `wss` (default) | `socket.dansonscorp.com`, the vendor's relay | **Yes** |

**`wss` is not a local connection.** Despite being described as "WiFi", it connects outbound to Dansons' servers, which relay to your grill. It is the default because it is the more reliable of the two — Bluetooth range and adapter quirks cause most connection problems — but if you want no cloud in the path, choose `ble`.

A genuinely local option exists in the grill's firmware and is being added to [pytboss](https://github.com/dknowles2/pytboss); it is not wired up here yet, and it does not work on every grill.

**This integration will set up the following platforms:**

| Platform | Description |
| --- | --- |
| `binary_sensor` | Error flags, live fan/igniter/auger state, connectivity, per-probe "target reached", and whether the grill has a meat probe control port |
| `button` | Restart the controller; request fast updates |
| `climate` | Grill temperature and HVAC action; turn off only (safety) |
| `light` | The grill's built-in light, if the model has one |
| `number` | A target temperature for every probe the grill supports |
| `select` | The temperature unit the grill itself displays |
| `sensor` | Probe temperatures, recipe progress, firmware version, controller uptime and free memory |
| `switch` | Grill module power (turn off only) and the primer motor |

### Entity details

- **Climate (`Grill temperature`):** Current and target temperature, plus HVAC action. Target temperatures snap to the values the control board actually accepts — the board silently ignores anything else. Setting HVAC mode to `off` turns the grill off and leaves the setpoint alone.
- **Sensor (`MPC`/`P2`–`P4`, or `Probe 1`–`Probe 4`):** Probe temperatures in the grill's current unit. On grills with a meat probe control port, probe 1 is labelled `MPC` to match what is printed by the socket; other grills keep numbered names. Only as many probes as the grill has are enabled.
- **Number (`… target`):** A target for every probe the board supports, not just the first two. Targets can be set while the probe is unplugged and while the grill is off — they are held and sent when the grill comes on.
- **Binary sensor (`… target reached`):** One per probe, comparing the probe against its target.
- **Binary sensor (`Connectivity`):** Stays available so it can report *disconnected*, rather than vanishing along with everything else.
- **Binary sensor (`Meat probe control`):** Whether the grill has a control port at all.
- **Binary sensor (errors and state):** Probe, startup, high-temperature, fan, igniter, auger and no-pellets errors, plus live fan, igniter and auger state.
- **Select (`Grill temperature unit`):** Switches the unit the *grill's own panel* uses. This does not change how Home Assistant displays temperatures — that follows your Home Assistant unit system.
- **Button (`Restart controller`):** Restarts the WiFi controller, the usual fix when it stops responding.
- **Button (`Request fast updates`):** Asks the grill to push status every 5 seconds for the next 5 minutes. Does nothing unless the grill is on, and nothing on any path but the relay (`wss`) one, since that is where those pushes go.
- **Sensor (`Firmware version`, `Controller uptime`, `Controller free memory`):** Diagnostics, read on a slower cadence than grill state.
- **Switch (`Module power`):** Turns the grill off. Stays available and reports `off` when the grill is off, rather than disappearing.
- **Switch (`Prime`):** Runs the auger primer motor, on models that support it.

### Actions

- **`pitboss.set_grill_password`:** Sets the grill's connection password and stores it in the config entry, so the two cannot drift apart.

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
communicate with it. No PitBoss account is needed either way.

If your grill isn't discovered automatically, you can add it manually by entering its
device ID. You'll then choose your exact model and, optionally, a connection password
and whether to connect over Bluetooth (`ble`) or the vendor relay (`wss`) — see
[Connection protocols](#connection-protocols) for what that choice means.

Already set up? You can change the model, password, or connection protocol at any time
via the integration's "Reconfigure" option, without needing to remove and re-add it.

If the grill starts rejecting your password, the integration starts a reauthentication
flow asking you to enter it again, rather than retrying indefinitely.

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
