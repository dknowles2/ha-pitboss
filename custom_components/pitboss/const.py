"""Constants for pitboss."""

from datetime import timedelta
from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

NAME = "PitBoss"
DOMAIN = "pitboss"
MANUFACTURER = NAME
# How often the coordinator polls, depending on what the grill is doing.
#
# Nothing interesting changes on a grill sitting in standby, and each cycle
# costs several round trips -- but once it is lit, temperatures move and the
# delay is what the user actually feels. Against the flat 30s these replace,
# an idle day halves its requests and even a four-hour cook makes slightly
# fewer of them overall.
#
# Constants rather than options because this integration has no options flow
# yet. They are the two values that would become fields when it grows one.
ACTIVE_SCAN_INTERVAL = timedelta(seconds=10)
STANDBY_SCAN_INTERVAL = timedelta(seconds=60)
# Consecutive failed cycles before the poll interval backs off. One failure
# is as likely a mid-cook hiccup as a grill gone away, and backing off on it
# turns a lost ten-second poll into a sixty-second gap in the one situation
# where freshness matters most. Two in a row is a pattern.
FAILURES_BEFORE_BACKOFF = 2
# Diagnostics change slowly; no need to read them at the poll rate.
SYS_INFO_INTERVAL = 60.0
PROTOCOL_WSS = "wss"
PROTOCOL_BLE = "ble"
PROTOCOL_LOCAL = "local"
ALL_PROTOCOLS = (PROTOCOL_BLE, PROTOCOL_LOCAL, PROTOCOL_WSS)
DEFAULT_PROTOCOL = PROTOCOL_WSS
DEFAULT_PROBE_MIN_TEMP = 50
DEFAULT_PROBE_MAX_TEMP = 250
DEFAULT_PROBE_FAHRENHEIT_STEP = 1
DEFAULT_PROBE_CELSIUS_STEP = 1


def probe_label(has_mpc: bool, probe_number: int) -> str:
    """The label the vendor's own app prints next to a probe port.

    Taken from `getProbeLabel` in the Pit Boss Android app (2.10.3), not
    inferred: on a grill with a control port, protocol probe 1 is that port
    and the rest keep their protocol number.

    The app's `isMpcProbe(n, settings)` is `settings.hasMpc === true &&
    n === 1`, so probe 1 -- and only probe 1 -- is the control probe. Its
    label is `mpcType.toUpperCase()`, defaulting to `MPC`. Every other probe
    falls through to `"P" + n`, which is why the numbering does not shift.

    Grills without a control port keep the name they have today.
    """
    if not has_mpc:
        return f"Probe {probe_number}"
    return "MPC" if probe_number == 1 else f"P{probe_number}"


MCU_SETTLE_SECONDS = 6
"""Seconds to show a value we asked for before believing the grill again.

The board wipes its cached status the moment it forwards a command to the
MCU, so the next poll still carries the old value and an entity that read it
straight back would appear to snap to the previous setting."""

# Remote start is off unless the user turns it on in the integration options.
CONF_ENABLE_REMOTE_START = "enable_remote_start"
