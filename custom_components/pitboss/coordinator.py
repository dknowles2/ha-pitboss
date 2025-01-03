"""DataUpdateCoordinator for PitBoss."""

from __future__ import annotations

from asyncio import Lock

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from pytboss.api import PitBoss
from pytboss.ble import BleConnection
from pytboss.grills import StateDict, get_grill

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
        LOGGER.debug("Resetting device: %s", device)
        async with self._lock:
            if self.conn is None or self.api is None:
                LOGGER.debug("Setting up PitBoss API with device: %s", device)
                self.conn = BleConnection(
                    device, disconnect_callback=self._on_disconnect, loop=self.hass.loop
                )
                self.api = PitBoss(self.conn, self.model)
                await self.api.start()
                await self.api.subscribe_state(self.async_set_updated_data)
            else:
                LOGGER.debug("Resetting device: %s", device)
                await self.conn.reset_device(device)

    def _on_disconnect(self, client: BleakClient) -> None:
        self.async_set_updated_data({})
        if self.hass.is_stopping:
            return
        device = bluetooth.async_ble_device_from_address(
            self.hass, client.address, connectable=True
        )
        if device is None:
            return
        self.config_entry.async_create_task(self.hass, self.reset_device(device))
