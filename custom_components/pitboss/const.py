"""Constants for pitboss."""

from datetime import timedelta
from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

NAME = "PitBoss"
DOMAIN = "pitboss"
MANUFACTURER = NAME
PING_INTERVAL = timedelta(seconds=30)
