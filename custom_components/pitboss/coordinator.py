"""DataUpdateCoordinator for PitBoss."""

from math import floor

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
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

    def accepted_setpoints(self, unit: str) -> list[float]:
        """Grill setpoints the control board honours, expressed in `unit`.

        The board ignores anything that is not on this list. A couple of
        models publish a Celsius list of their own; for everyone else it is
        derived from the Fahrenheit one using the same conversion the boards
        that convert in their own parsing routine use -- `floor((F - 32) /
        1.8)` -- so the values match what the panel will show.
        """
        fahrenheit = self.api.spec.temp_increments or []
        if unit != UnitOfTemperature.CELSIUS:
            return [float(v) for v in fahrenheit]
        raw = self.api.spec.json.get("celsius_temp_increment") or ""
        if celsius := [int(v) for v in raw.split("/") if v.strip().isdigit()]:
            return [float(v) for v in celsius]
        return [float(floor((v - 32) / 1.8)) for v in fahrenheit]

    async def _async_setup(self) -> None:
        """Set up the coordinator."""
        await self.api.subscribe_state(self._on_state_update)
        await self._start_api()

    def _merge_state(self, state: StateDict) -> StateDict:
        """Fold a state frame onto the last known one.

        The board answers with two independent frames, status (`sc_11`) and
        temperatures (`sc_12`), and clears them as soon as it forwards a
        command to the MCU. A read landing in that window returns one frame
        without the other, and pytboss simply omits the missing half's keys,
        so every entity backed by them would go unknown until the next
        successful read.

        Only *absent* keys are carried over. A key present with a null value
        is a real reading -- an unplugged probe -- and overwrites.
        """
        # Copy rather than hand back the incoming dict: pytboss gives every
        # subscriber the same StateDict instance and keeps mutating it.
        if not self.data:
            return state.copy()
        if not state:
            return self.data
        merged = self.data.copy()
        merged.update(state)
        return merged

    async def _on_state_update(self, data: StateDict) -> None:
        self.logger.debug("Received data: %s", data)
        self.async_set_updated_data(self._merge_state(data))

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

        # Always fetch the current state to ensure sensors stay up-to-date.
        # Relying solely on push notifications means sensors can go stale after
        # a reconnect if push notifications stop being delivered.
        try:
            return self._merge_state(await self.api.get_state())
        except NotConnectedError as ex:
            raise UpdateFailed("Grill not connected") from ex
        except RPCError as ex:
            raise UpdateFailed(str(ex)) from ex
