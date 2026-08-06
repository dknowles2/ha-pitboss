"""DataUpdateCoordinator for PitBoss."""

from math import floor
from time import monotonic

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util.unit_conversion import TemperatureConverter
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
    MCU_SETTLE_SECONDS,
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
        # `probe_target` for why both exist. `restored_targets` is kept in
        # Fahrenheit regardless of the grill's unit -- the same convention
        # as the grill's own virtual-data store -- because these values
        # outlive unit changes: one captured as "74" while the grill spoke
        # Celsius must not be seeded as 74 F after the panel is flipped.
        self.probe_targets: dict[int, int] = {}
        self.restored_targets: dict[int, int] = {}
        self._targets_seeded = False
        # The unit `probe_targets` was last known to be in, so a unit change
        # can convert the held values instead of serving them mislabeled.
        # `None` until the first update: the unit read before any data is
        # the Fahrenheit default, not something the grill said.
        self._targets_unit: str | None = None
        # The grill setpoint we asked for, held until the grill confirms it.
        # Kept here rather than on the climate entity because the setpoint has
        # more than one reader -- the climate entity and the grill setpoint
        # number are two controls over one setting, and a value held by
        # whichever one was used would leave the other showing the old
        # setpoint for the length of the settle window. `probe_targets` lives
        # here for the same reason.
        self._pending_setpoint: float | None = None
        self._pending_setpoint_unit: str | None = None
        self._cancel_setpoint_settle: CALLBACK_TYPE | None = None
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
        """The unit the grill is currently working in.

        Absent defaults to Fahrenheit, matching pytboss's `_is_fahrenheit` --
        the default the command path snaps setpoints with. The key is only
        emitted by the temperatures frame on most boards, so a state built
        from a status frame alone (a poll landing right after the firmware
        wipes the other half) is non-empty without it; reading that as
        Celsius meant presenting one unit while commands were snapped in the
        other.
        """
        if (data := self.data) and not data.get("isFahrenheit", True):
            return UnitOfTemperature.CELSIUS
        return UnitOfTemperature.FAHRENHEIT

    def grill_setpoint(self) -> float | None:
        """The grill's setpoint, or the one just asked for.

        Shows what was asked until the grill confirms it: the board wipes its
        cached status the moment it forwards a command to the MCU, so the next
        poll still carries the old setpoint and a control reading it straight
        back would appear to snap to the previous setting.
        """
        if self._pending_setpoint is not None:
            return self._pending_setpoint
        if (data := self.data) and (temp := data.get("grillSetTemp")) is not None:
            return float(temp)
        return None

    def snap_setpoint(self, temp: float) -> float:
        """The nearest setpoint the control board will actually honour.

        Snapped here as well as in pytboss -- deliberately the same arithmetic
        -- so what is held and shown is the value the board will report, not
        the one it will silently correct.
        """
        if accepted := self.accepted_setpoints(self.grill_unit):
            return min(accepted, key=lambda value: abs(value - temp))
        return temp

    async def async_set_grill_setpoint(self, temp: float) -> None:
        """Send a grill setpoint, and hold it until the grill confirms it."""
        wanted = self.snap_setpoint(temp)
        await self.api.set_grill_temperature(int(wanted))
        self._pending_setpoint = wanted
        self._pending_setpoint_unit = self.grill_unit
        self.async_update_listeners()
        # The MCU reports back within a couple of seconds; an immediate
        # refresh would only read the cleared status. A second set inside the
        # window replaces the timer rather than queueing another.
        self._cancel_pending_setpoint_settle()
        self._cancel_setpoint_settle = async_call_later(
            self.hass, MCU_SETTLE_SECONDS, self._async_confirm_setpoint
        )

    @callback
    def _cancel_pending_setpoint_settle(self) -> None:
        if self._cancel_setpoint_settle is not None:
            self._cancel_setpoint_settle()
            self._cancel_setpoint_settle = None

    async def _async_confirm_setpoint(self, _now) -> None:
        self._cancel_setpoint_settle = None
        await self.async_request_refresh()
        # One settle window is all the pending value is for. If the refresh
        # confirmed it, `_expire_pending_setpoint` has already cleared it; if
        # the grill did not take it, follow the grill rather than assert a
        # value it will never report.
        if self._pending_setpoint is not None:
            self._pending_setpoint = None
            self.async_update_listeners()

    @callback
    def _expire_pending_setpoint(self) -> None:
        """Stop holding the asked-for setpoint once it stops meaning anything.

        Either the grill has reported it -- from which point its own answer is
        the source again, so a later change made at the panel is not masked by
        a value we are still asserting -- or the grill's unit has flipped,
        which invalidates the held number outright: 225 held from a Fahrenheit
        set must not be presented as 225 C for the rest of the window.
        """
        if self._pending_setpoint is None:
            return
        if self.grill_unit != self._pending_setpoint_unit:
            self._pending_setpoint = None
            return
        reported = (self.data or {}).get("grillSetTemp")
        if reported is not None and float(reported) == self._pending_setpoint:
            self._pending_setpoint = None

    @callback
    def _follow_probe_targets_unit(self) -> None:
        """Convert the held probe targets when the grill's unit flips.

        `probe_targets` holds values in the grill's unit, and the poll is the
        only path that refreshes it -- a unit change arriving by push left
        the old-unit numbers in place for up to a poll interval. In that
        window a target number showed the old value labeled with the new
        unit, and target-reached compared across units: a probe reading
        140 F sat above a target of 74 held from Celsius, so the sensor
        fired for a probe that was 14 degrees C short.

        Converted rather than dropped so the target stays on the dashboard;
        the next poll re-reads what the grill is actually holding. Only the
        probes whose target is not board-reported are exposed to this --
        `probe_target` prefers the state's own `pNTarget`, which arrives
        already flipped -- but those are most probes on most boards.
        `restored_targets` needs nothing: it is kept in Fahrenheit for
        exactly this reason.
        """
        unit = self.grill_unit
        if self._targets_unit is None or not self.probe_targets:
            self._targets_unit = unit
            return
        prev, self._targets_unit = self._targets_unit, unit
        if unit == prev:
            return
        self.probe_targets = {
            probe_number: round(TemperatureConverter.convert(float(target), prev, unit))
            for probe_number, target in self.probe_targets.items()
        }

    @callback
    def async_update_listeners(self) -> None:
        """Reconcile what we hold with what arrived, before any entity reads.

        Overridden rather than hooked into one update path because the state
        these decisions depend on arrives by three of them -- the poll, the
        push callback and `async_set_updated_data` -- and all three end here.
        """
        self._expire_pending_setpoint()
        self._follow_probe_targets_unit()
        super().async_update_listeners()

    async def async_shutdown(self) -> None:
        """Drop the settle timer along with the refresh one.

        Not for the refresh it would ask for -- the base class sets
        `_shutdown_requested`, and `_async_refresh` bails out on that, so a
        late callback does nothing. It is the timer itself: an
        `async_call_later` left scheduled outlives the entry by up to one
        settle window, which is what Home Assistant's own tests fail on as a
        lingering timer.
        """
        self._cancel_pending_setpoint_settle()
        await super().async_shutdown()

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
        if (held := self.restored_targets.get(probe_number)) is not None:
            return self._from_fahrenheit(held)
        return None

    def _to_fahrenheit(self, temp: int) -> int:
        """A grill-unit value, in the unit `restored_targets` is kept in."""
        if self.grill_unit == UnitOfTemperature.FAHRENHEIT:
            return temp
        return round(
            TemperatureConverter.convert(
                temp, UnitOfTemperature.CELSIUS, UnitOfTemperature.FAHRENHEIT
            )
        )

    def _from_fahrenheit(self, temp: int) -> int:
        """A held Fahrenheit value, in the grill's current unit."""
        if self.grill_unit == UnitOfTemperature.FAHRENHEIT:
            return temp
        return round(
            TemperatureConverter.convert(
                temp, UnitOfTemperature.FAHRENHEIT, UnitOfTemperature.CELSIUS
            )
        )

    async def async_set_probe_target(self, probe_number: int, temp: int) -> None:
        """Set a probe's target, given in the grill's current unit."""
        self.restored_targets[probe_number] = self._to_fahrenheit(temp)
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
        self.restored_targets[probe_number] = self._to_fahrenheit(temp)
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
        for probe_number, held in self.restored_targets.items():
            if probe_number in self.probe_targets:
                continue
            # Converted at seeding time, into whatever unit the grill has
            # *now* -- which may not be the unit it had at capture.
            temp = self._from_fahrenheit(held)
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
        except RPCError as ex:
            # The probe can also be *answered* badly: something that is not
            # a grill answers with non-JSON, and an HTTP-auth build
            # (`rpc.auth_file`) turns it away -- `Unauthorized` is an
            # `RPCError`, so this handler covers both. Deliberately not
            # reauth's to fix: that refusal is HTTP-layer auth, not the
            # grill password. They land where every other failed cycle
            # lands.
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
            # probe, so success here means connected again. Still gated on
            # the protocol rather than done for everyone: the other two
            # transports own their reconnect, and a poll reaching into that
            # races whatever they already have in flight. It used to be
            # unsafe outright -- `connect()` on a websocket mid-backoff
            # started a second receive loop -- which pytboss#572 fixed by
            # serializing the lifecycle, so this is now a question of who
            # owns reconnection rather than of corruption.
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
