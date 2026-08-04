"""DataUpdateCoordinator for PitBoss."""

from math import floor
from time import monotonic

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from pytboss.api import PitBoss
from pytboss.exceptions import (
    GrillUnavailable,
    NotConnectedError,
    RPCError,
    Unauthorized,
    UnsupportedOperation,
)
from pytboss.grills import StateDict

from .const import (
    ACTIVE_SCAN_INTERVAL,
    DOMAIN,
    FAILURES_BEFORE_BACKOFF,
    LOGGER,
    STANDBY_SCAN_INTERVAL,
    SYS_INFO_INTERVAL,
)


class PitBossDataUpdateCoordinator(DataUpdateCoordinator[StateDict]):
    """Class to manage fetching data from the API."""

    config_entry: ConfigEntry
    device_info: DeviceInfo
    api: PitBoss
    firmware_version: str | None = None

    def __init__(
        self,
        hass: HomeAssistant,
        device_info: DeviceInfo,
        api: PitBoss,
        reconnect_on_poll: bool = False,
    ) -> None:
        """Initialize the coordinator.

        `reconnect_on_poll` is for transports with no reconnect of their own.
        Bluetooth is reconnected by the discovery callback and the websocket
        transport by its internal loop, so for those a disconnected transport
        fails the cycle fast and something else restores it. The local HTTP
        transport is request/response: its recovery *is* the next request,
        which never comes if every cycle refuses to talk to a transport that
        reports disconnected -- one failed request would strand it until a
        reload.
        """
        super().__init__(
            hass=hass,
            logger=LOGGER,
            name=DOMAIN,
            # Starts in standby; the first state that arrives corrects it.
            update_interval=STANDBY_SCAN_INTERVAL,
        )
        self.device_info = device_info
        self.api = api
        self._reconnect_on_poll = reconnect_on_poll
        self._api_started = False
        # Latest Sys.GetInfo payload from the control board.
        self.sys_info: dict = {}
        self._sys_info_at = 0.0
        # When the firmware version was last asked for. `None` rather than
        # 0.0 so the first attempt is never gated: `monotonic()` can be
        # small at process start, which 0.0 would read as "just tried".
        self._firmware_attempted_at: float | None = None
        # What the grill is holding, and what we are holding for it. See
        # `probe_target` for why both exist.
        self.probe_targets: dict[int, int] = {}
        self.restored_targets: dict[int, int] = {}
        self._targets_seeded = False
        # Consecutive failed cycles, for the backoff decision below.
        self._failed_polls = 0

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

    @property
    def has_mpc(self) -> bool:
        """Whether the grill has a meat probe control port."""
        return self.api.spec.has_mpc

    @property
    def grill_unit(self) -> str:
        """The unit the grill is currently working in."""
        if (data := self.data) and not data.get("isFahrenheit"):
            return UnitOfTemperature.CELSIUS
        return UnitOfTemperature.FAHRENHEIT

    def probe_target(self, probe_number: int) -> int | None:
        """This probe's target, in the grill's own unit.

        Board-reported first: `pNTarget` is already in the state we hold, so
        reading it here means a target the grill announces shows immediately
        rather than at the next poll. Then what pytboss resolved from the
        grill's store. Then ours -- a target we set and restored across a
        restart, which exists only because Home Assistant outlives that store.
        """
        reported = (self.data or {}).get(f"p{probe_number}Target")
        if isinstance(reported, (int, float)):
            return int(reported)
        if (target := self.probe_targets.get(probe_number)) is not None:
            return target
        return self.restored_targets.get(probe_number)

    async def async_set_probe_target(self, probe_number: int, temp: int) -> None:
        """Set a probe's target, keeping it if the grill cannot take it yet."""
        self.restored_targets[probe_number] = temp
        try:
            await self.api.set_probe_target(probe_number, temp)
        except UnsupportedOperation:
            # The grill is off: its store rejects writes and is wiped anyway.
            # Held here and written when it comes on.
            return
        self.probe_targets[probe_number] = temp

    def note_restored_target(self, probe_number: int, temp: int) -> None:
        """Take a target restored from a previous run.

        Re-arms seeding when the grill does not already hold this probe's
        target. Entities are added after the coordinator's first refresh, so
        a grill that power-cycled while Home Assistant was down has already
        been marked seeded -- against an empty set -- by the time a restored
        value arrives. Without this the target would show in Home Assistant
        and never reach the grill, which is the one case the restore exists
        for.
        """
        self.restored_targets[probe_number] = temp
        if probe_number not in self.probe_targets:
            self._targets_seeded = False

    async def _async_refresh_probe_targets(self, state: StateDict) -> None:
        """Track the targets the grill is holding. Never fatal."""
        if not state.get("moduleIsOn"):
            self.probe_targets = {}
            self._targets_seeded = False
            return
        try:
            # Copied: we add to this below, and it is not ours to mutate.
            self.probe_targets = dict(await self.api.get_probe_targets())
        except Exception as ex:  # noqa: BLE001
            self.logger.debug("Could not fetch the probe targets: %s", ex)
            return
        if self._targets_seeded:
            return
        self._targets_seeded = True
        # The grill has just come on, so anything we are holding that it does
        # not know about goes over now. That is what makes setting a target on
        # a cold grill mean anything. A target the grill already has was set
        # elsewhere and wins.
        for probe_number, temp in self.restored_targets.items():
            if probe_number in self.probe_targets:
                continue
            try:
                await self.api.set_probe_target(probe_number, temp)
            except Exception as ex:  # noqa: BLE001
                self.logger.debug("Could not seed a probe target: %s", ex)
            else:
                self.probe_targets[probe_number] = temp

    async def _async_setup(self) -> None:
        """Set up the coordinator."""
        await self.api.subscribe_state(self._on_state_update)
        await self._start_api()
        await self._async_refresh_firmware_version()

    async def _async_refresh_firmware_version(self) -> None:
        """Fetch the firmware version until one read succeeds. Never fatal.

        The version does not change outside a reload, so this is a no-op once
        known. Retrying until then matters because the read at setup used to
        be the only attempt: a grill that failed to answer it once had no
        firmware sensor until the integration was reloaded.

        Retries are gated to the diagnostics cadence, like the system info
        read above. Gating on success alone meant a grill that persistently
        failed this read was asked again on every poll -- every ten seconds
        for as long as it was lit, once the poll interval followed the grill.
        """
        if self.firmware_version is not None:
            return
        now = monotonic()
        if (
            self._firmware_attempted_at is not None
            and now - self._firmware_attempted_at < SYS_INFO_INTERVAL
        ):
            return
        self._firmware_attempted_at = now
        try:
            result = await self.api.get_firmware_version()
            self.firmware_version = result.get("firmwareVersion")
        except Exception as ex:  # noqa: BLE001
            # Cosmetic; never worth failing a refresh over.
            self.logger.debug("Could not fetch the firmware version: %s", ex)
            return
        if self.firmware_version:
            self._async_publish_firmware_version()

    def _async_publish_firmware_version(self) -> None:
        """Put the version where the device page reads it from.

        `device_info` covers the first read, which happens before the device
        exists -- the registry entry is created from it when the platforms
        are set up. A read that only succeeds later has to update the
        registry itself, which is the whole point of retrying: the sensor
        would populate while the device page stayed blank until a reload.
        """
        self.device_info["sw_version"] = self.firmware_version
        registry = dr.async_get(self.hass)
        device = registry.async_get_device(
            identifiers=self.device_info.get("identifiers", set())
        )
        if device is not None:
            registry.async_update_device(device.id, sw_version=self.firmware_version)

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

    def _apply_poll_interval(self, state: StateDict) -> None:
        """Poll hard while the grill runs, back off in standby."""
        wanted = (
            ACTIVE_SCAN_INTERVAL if state.get("moduleIsOn") else STANDBY_SCAN_INTERVAL
        )
        if self.update_interval != wanted:
            self.logger.debug("Polling every %s", wanted)
            self.update_interval = wanted

    async def _on_state_update(self, data: StateDict) -> None:
        self.logger.debug("Received data: %s", data)
        merged = self._merge_state(data)
        # Applied on the push path too: on Bluetooth a power change arrives
        # this way, and the poll interval should follow it without waiting
        # for the next poll to notice.
        self._apply_poll_interval(merged)
        self.async_set_updated_data(merged)

    async def _start_api(self) -> None:
        try:
            await self.api.start()
            self._api_started = True
        except GrillUnavailable as ex:
            raise UpdateFailed("Grill unavailable") from ex
        except NotConnectedError as ex:
            # What the local HTTP transport raises when nothing answers its
            # probe; a failed reconnect is a failed cycle, not a crash.
            raise UpdateFailed("Grill not connected") from ex
        except (Unauthorized, RPCError) as ex:
            # The probe can also be *answered* badly: an HTTP-auth build
            # (`rpc.auth_file`) turns it away, and something that is not a
            # grill answers it with non-JSON. Neither is the grill password,
            # so neither is reauth's to fix -- they land where every other
            # failed cycle lands.
            raise UpdateFailed(f"Grill refused the reconnect: {ex}") from ex

    async def _async_refresh_sys_info(self) -> None:
        """Refresh the control board's system info. Never fatal.

        Uptime and free memory change slowly and are diagnostic, so they are
        not worth a round trip on every poll.
        """
        now = monotonic()
        if self.sys_info and now - self._sys_info_at < SYS_INFO_INTERVAL:
            return
        try:
            self.sys_info = await self.api.config.get_info()
            self._sys_info_at = now
        except Exception as ex:  # noqa: BLE001
            self.logger.debug("Could not fetch the system info: %s", ex)

    async def _async_update_data(self) -> StateDict:
        try:
            state = await self._async_poll()
        except UpdateFailed:
            # Back off, but on a pattern rather than a single miss. The
            # interval is otherwise whatever the last *successful* read set,
            # so a grill that goes off while the connection stays up -- the
            # normal case on the cloud relay, where the socket outlives the
            # grill -- kept a ten-second ping in flight for as long as it
            # was off. But one failure is as likely a mid-cook hiccup as a
            # grill gone away, and backing off on it turned a lost ten-second
            # poll into a sixty-second gap exactly when freshness matters
            # most. A grill that is genuinely off fails every cycle, so it
            # still reaches the slow interval, one failed poll later.
            self._failed_polls += 1
            if self._failed_polls >= FAILURES_BEFORE_BACKOFF:
                self._apply_poll_interval(StateDict())
            raise
        self._failed_polls = 0
        return state

    async def _async_poll(self) -> StateDict:
        if not self._api_started:
            self.logger.debug("Starting API")
            await self._start_api()

        if not self.api.is_connected():
            if not self._reconnect_on_poll:
                # Bluetooth and the websocket transport reconnect themselves;
                # fail the cycle fast and let them.
                raise UpdateFailed("Grill not connected")
            # The local HTTP transport recovers only by being spoken to, and
            # a poll is the only speaker. `connect()` is its reachability
            # probe, so success here means connected again. Calling this for
            # the other transports would not be safe: `connect()` on a
            # websocket mid-backoff starts a second receive loop on the
            # pinned pytboss (serialized upstream in pytboss#572, not yet
            # released).
            self.logger.debug("Reconnecting to the grill")
            await self._start_api()

        try:
            await self.api.ping(timeout=10.0)
        except NotConnectedError as ex:
            raise UpdateFailed("Grill not connected") from ex
        except TimeoutError as ex:
            # `send_command` raises this when a reply does not arrive, which
            # is the ordinary outcome for a grill that is off behind a socket
            # that is still open. Uncaught it reaches Home Assistant's generic
            # handler, which reports "Timeout fetching pitboss data" instead.
            raise UpdateFailed("Grill did not answer") from ex

        await self._async_refresh_sys_info()
        await self._async_refresh_firmware_version()

        # Always fetch the current state to ensure sensors stay up-to-date.
        # Relying solely on push notifications means sensors can go stale after
        # a reconnect if push notifications stop being delivered.
        try:
            state = self._merge_state(await self.api.get_state())
            self._apply_poll_interval(state)
            await self._async_refresh_probe_targets(state)
            return state
        except NotConnectedError as ex:
            raise UpdateFailed("Grill not connected") from ex
        except TimeoutError as ex:
            raise UpdateFailed("Grill did not answer") from ex
        except Unauthorized as ex:
            # The grill rejected the password rather than failing the call.
            # Retrying cannot fix that, and on a transport where `PB.GetState`
            # is itself password-gated it takes the whole integration down --
            # so ask for the password instead of retrying forever.
            raise ConfigEntryAuthFailed(
                "The grill rejected the stored password"
            ) from ex
        except RPCError as ex:
            raise UpdateFailed(str(ex)) from ex
