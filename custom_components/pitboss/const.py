"""Constants for pitboss."""

from datetime import timedelta
from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

NAME = "PitBoss"
DOMAIN = "pitboss"
MANUFACTURER = NAME
PING_INTERVAL = timedelta(seconds=30)
# Diagnostics change slowly; no need to read them at the poll rate.
SYS_INFO_INTERVAL = 60.0
PROTOCOL_WSS = "wss"
PROTOCOL_BLE = "ble"
ALL_PROTOCOLS = (PROTOCOL_BLE, PROTOCOL_WSS)
DEFAULT_PROTOCOL = PROTOCOL_WSS
DEFAULT_MIN_TEMP = 180
DEFAULT_MAX_TEMP = 500
DEFAULT_PROBE_MIN_TEMP = 50
DEFAULT_PROBE_MAX_TEMP = 250
DEFAULT_PROBE_FAHRENHEIT_STEP = 1
DEFAULT_PROBE_CELSIUS_STEP = 1


def probe_label(has_mpc: bool, probe_number: int) -> str:
    """The label the controller prints next to a probe port.

    Grills with a meat probe control port label their ports MPC, MP1, MP2 and
    so on -- the control probe comes first, and the numbered ones start after
    it. Matching that avoids an off-by-one between what the panel says and
    what Home Assistant shows. Everything else just counts from 1.
    """
    if not has_mpc:
        return f"Probe {probe_number}"
    return "MPC" if probe_number == 1 else f"MP{probe_number - 1}"
