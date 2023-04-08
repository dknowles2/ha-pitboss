"""DataUpdateCoordinator for PitBoss."""

from __future__ import annotations

from asyncio import Lock

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from bleak.backends.device import BLEDevice
from pytboss import BleConnection, PitBoss
from pytboss.api import StateDict
from pytboss.grills import get_grill

from .const import DOMAIN, LOGGER, NAME


class PitBossDataUpdateCoordinator(DataUpdateCoordinator[StateDict]):
    """Class to manage fetching data from the API."""

    config_entry: ConfigEntry
    device_info: DeviceInfo
    conn: BleConnection | None = None
    api: PitBoss | None = None

    def __init__(
        self,
        hass: HomeAssistant,
        device_id: str,
        model: str,
    ) -> None:
        """Initialize."""
        super().__init__(hass=hass, logger=LOGGER, name=DOMAIN, update_interval=None)
        self._lock = Lock()
        self.device_id: str = device_id
        self.model: str = model
        self.grill_spec = get_grill(model)
        self.device_info = DeviceInfo(
            identifiers={(DOMAIN, self.device_id)},
            name=self.device_id,
            model=self.model,
            manufacturer=NAME,

        )

    async def reset_device(self, device: BLEDevice) -> None:
        LOGGER.info("Resetting device: %s", device)
        async with self._lock:
            if self.api is None:
                LOGGER.info("Setting up PitBoss API")
                self.conn = BleConnection(device, loop=self.hass.loop)
                self.api = PitBoss(self.conn, self.model)
                await self.api.start()
                await self.api.subscribe_state(self.async_set_updated_data)
            else:
                LOGGER.info("Resetting exisitng device")
                await self.conn.reset_device(device)
