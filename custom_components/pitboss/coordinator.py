"""DataUpdateCoordinator for PitBoss."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from pytboss.api import PitBoss
from pytboss.exceptions import GrillUnavailable, NotConnectedError, RPCError
from pytboss.grills import StateDict

from .const import DOMAIN, LOGGER, PING_INTERVAL


class PitBossDataUpdateCoordinator(DataUpdateCoordinator[StateDict]):
    """Class to manage fetching data from the API."""

    config_entry: ConfigEntry
    device_info: DeviceInfo
    api: PitBoss

    def __init__(
        self,
        hass: HomeAssistant,
        device_info: DeviceInfo,
        api: PitBoss,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass=hass, logger=LOGGER, name=DOMAIN, update_interval=PING_INTERVAL
        )
        self.device_info = device_info
        self.api = api
        self._api_started = False

    async def _async_setup(self) -> None:
        """Set up the coordinator."""
        await self.api.subscribe_state(self._on_state_update)
        await self._start_api()

    async def _on_state_update(self, data: StateDict) -> None:
        self.logger.debug("Received data: %s", data)
        self.async_set_updated_data(data)

    async def _start_api(self) -> None:
        try:
            await self.api.start()
            self._api_started = True
        except GrillUnavailable as ex:
            raise UpdateFailed("Grill unavailable") from ex

    async def _async_update_data(self) -> StateDict:
        if not self._api_started:
            self.logger.debug("Starting API")
            await self._start_api()

        if not self.api.is_connected():
            raise UpdateFailed("Grill not connected")

        try:
            await self.api.ping(timeout=10.0)
        except NotConnectedError as ex:
            raise UpdateFailed("Grill not connected") from ex

        if self.data is None:
            # We haven't received a WebSocket push. Try to manually fetch the state.
            try:
                return await self.api.get_state()
            except NotConnectedError as ex:
                raise UpdateFailed("Grill not connected") from ex
            except RPCError as ex:
                raise UpdateFailed(str(ex)) from ex

        # Return the last data received from the WebSocket push.
        return self.data
