"""Constants for pitboss."""

from datetime import timedelta
from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

NAME = "PitBoss"
DOMAIN = "pitboss"
MANUFACTURER = NAME
PING_INTERVAL = timedelta(seconds=30)
PROTOCOL_WSS = "wss"
PROTOCOL_BLE = "ble"
ALL_PROTOCOLS = (PROTOCOL_BLE, PROTOCOL_WSS)
DEFAULT_PROTOCOL = PROTOCOL_WSS
