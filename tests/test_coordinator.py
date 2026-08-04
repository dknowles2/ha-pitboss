from unittest.mock import Mock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytboss.exceptions import GrillUnavailable, NotConnectedError, RPCError
from pytboss.grills import StateDict

from custom_components.pitboss.const import (
    ACTIVE_SCAN_INTERVAL,
    STANDBY_SCAN_INTERVAL,
)
from custom_components.pitboss.coordinator import PitBossDataUpdateCoordinator

pytestmark = pytest.mark.parametrize("model", ["PBV4PS2"])


@pytest.fixture
def coordinator(
    hass: HomeAssistant, mock_pitboss: Mock
) -> PitBossDataUpdateCoordinator:
    return PitBossDataUpdateCoordinator(hass, DeviceInfo(), mock_pitboss)


async def test_async_setup_subscribes_and_starts(
    coordinator: PitBossDataUpdateCoordinator, mock_pitboss: Mock
) -> None:
    await coordinator._async_setup()
    mock_pitboss.subscribe_state.assert_awaited_once_with(coordinator._on_state_update)
    mock_pitboss.start.assert_awaited_once()
    assert coordinator._api_started is True


async def test_on_state_update_sets_data(
    coordinator: PitBossDataUpdateCoordinator,
) -> None:
    await coordinator._on_state_update({"grillTemp": 200})
    assert coordinator.data == {"grillTemp": 200}


async def test_start_api_raises_update_failed_on_grill_unavailable(
    coordinator: PitBossDataUpdateCoordinator, mock_pitboss: Mock
) -> None:
    mock_pitboss.start.side_effect = GrillUnavailable("nope")
    with pytest.raises(UpdateFailed):
        await coordinator._start_api()
    assert coordinator._api_started is False


async def test_async_update_data_starts_api_if_not_started(
    coordinator: PitBossDataUpdateCoordinator, mock_pitboss: Mock
) -> None:
    mock_pitboss.is_connected.return_value = True
    mock_pitboss.get_state.return_value = {"grillTemp": 100}
    assert coordinator._api_started is False

    data = await coordinator._async_update_data()

    mock_pitboss.start.assert_awaited_once()
    assert coordinator._api_started is True
    assert data == {"grillTemp": 100}


async def test_async_update_data_raises_when_not_connected(
    coordinator: PitBossDataUpdateCoordinator, mock_pitboss: Mock
) -> None:
    coordinator._api_started = True
    mock_pitboss.is_connected.return_value = False
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_async_update_data_raises_when_ping_not_connected(
    coordinator: PitBossDataUpdateCoordinator, mock_pitboss: Mock
) -> None:
    coordinator._api_started = True
    mock_pitboss.is_connected.return_value = True
    mock_pitboss.ping.side_effect = NotConnectedError("nope")
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_async_update_data_raises_when_get_state_not_connected(
    coordinator: PitBossDataUpdateCoordinator, mock_pitboss: Mock
) -> None:
    coordinator._api_started = True
    mock_pitboss.is_connected.return_value = True
    mock_pitboss.get_state.side_effect = NotConnectedError("nope")
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_async_update_data_raises_on_rpc_error(
    coordinator: PitBossDataUpdateCoordinator, mock_pitboss: Mock
) -> None:
    coordinator._api_started = True
    mock_pitboss.is_connected.return_value = True
    mock_pitboss.get_state.side_effect = RPCError("boom")
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_async_update_data_success(
    coordinator: PitBossDataUpdateCoordinator, mock_pitboss: Mock
) -> None:
    coordinator._api_started = True
    mock_pitboss.is_connected.return_value = True
    mock_pitboss.get_state.return_value = {"grillTemp": 225}
    data = await coordinator._async_update_data()
    mock_pitboss.ping.assert_awaited_once_with(timeout=10.0)
    assert data == {"grillTemp": 225}


async def test_async_update_data_keeps_fields_missing_from_a_partial_frame(
    coordinator: PitBossDataUpdateCoordinator, mock_pitboss: Mock
) -> None:
    """A read between the two frames must not blank the other half."""
    coordinator._api_started = True
    mock_pitboss.is_connected.return_value = True

    mock_pitboss.get_state.return_value = {"grillTemp": 225, "moduleIsOn": True}
    coordinator.async_set_updated_data(await coordinator._async_update_data())

    # Only the status frame came back this time.
    mock_pitboss.get_state.return_value = {"moduleIsOn": False}
    data = await coordinator._async_update_data()
    assert data == {"grillTemp": 225, "moduleIsOn": False}


async def test_async_update_data_lets_null_readings_through(
    coordinator: PitBossDataUpdateCoordinator, mock_pitboss: Mock
) -> None:
    """A key present with no value is a real reading, not a missing frame."""
    coordinator._api_started = True
    mock_pitboss.is_connected.return_value = True

    mock_pitboss.get_state.return_value = {"p1Temp": 70}
    coordinator.async_set_updated_data(await coordinator._async_update_data())

    # The probe was unplugged: pytboss reports the key as None.
    mock_pitboss.get_state.return_value = {"p1Temp": None}
    data = await coordinator._async_update_data()
    assert data == {"p1Temp": None}


async def test_on_state_update_merges_onto_previous_data(
    coordinator: PitBossDataUpdateCoordinator,
) -> None:
    """Pushed updates are merged too, and never stored by reference."""
    pushed: StateDict = {"grillTemp": 225, "moduleIsOn": True}
    await coordinator._on_state_update(pushed)
    assert coordinator.data is not pushed

    await coordinator._on_state_update({"moduleIsOn": False})
    assert coordinator.data == {"grillTemp": 225, "moduleIsOn": False}


async def test_a_poll_reconnects_a_transport_with_no_reconnect_of_its_own(
    hass: HomeAssistant, mock_pitboss: Mock
) -> None:
    """The local HTTP transport recovers only by being spoken to.

    It marks itself disconnected when a request fails, and its recovery is
    the next request -- which never came, because every cycle refused to
    talk to a transport reporting disconnected. One blip stranded the
    integration until a reload, on the one transport that has no other
    reconnect path.
    """
    coordinator = PitBossDataUpdateCoordinator(
        hass, DeviceInfo(), mock_pitboss, reconnect_on_poll=True
    )
    coordinator._api_started = True
    mock_pitboss.is_connected.return_value = False
    mock_pitboss.start.side_effect = lambda: setattr(
        mock_pitboss.is_connected, "return_value", True
    )
    mock_pitboss.get_state.return_value = {"grillTemp": 225}

    data = await coordinator._async_update_data()

    mock_pitboss.start.assert_awaited_once()
    assert data == {"grillTemp": 225}


async def test_a_failed_reconnect_is_a_failed_cycle_not_a_crash(
    hass: HomeAssistant, mock_pitboss: Mock
) -> None:
    """A grill still away raises `NotConnectedError` from the probe."""
    coordinator = PitBossDataUpdateCoordinator(
        hass, DeviceInfo(), mock_pitboss, reconnect_on_poll=True
    )
    coordinator._api_started = True
    mock_pitboss.is_connected.return_value = False
    mock_pitboss.start.side_effect = NotConnectedError("still nothing there")

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_transports_that_reconnect_themselves_still_fail_fast(
    coordinator: PitBossDataUpdateCoordinator, mock_pitboss: Mock
) -> None:
    """Without the opt-in, a disconnected transport is not spoken to.

    Bluetooth is reconnected by the discovery callback and the websocket by
    its own loop; calling `connect()` on those from here is not safe on the
    pinned pytboss (a websocket mid-backoff would start a second receive
    loop).
    """
    coordinator._api_started = True
    mock_pitboss.is_connected.return_value = False

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
    mock_pitboss.start.assert_not_awaited()


async def test_a_ping_timeout_is_reported_as_a_failed_update(
    coordinator: PitBossDataUpdateCoordinator, mock_pitboss: Mock
) -> None:
    """`send_command` raises `TimeoutError` when no reply arrives.

    That is the ordinary outcome for a grill that is off behind a socket
    which is still open, so it must not reach Home Assistant's generic
    handler as an unexpected error.
    """
    coordinator._api_started = True
    mock_pitboss.is_connected.return_value = True
    mock_pitboss.ping.side_effect = TimeoutError()

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_repeated_failures_back_the_poll_interval_off(
    coordinator: PitBossDataUpdateCoordinator, mock_pitboss: Mock
) -> None:
    """The interval was otherwise whatever the last success set.

    On the cloud relay the socket outlives the grill, so a grill switched
    off keeps failing at the active cadence -- a ten-second ping in flight
    for as long as it is off. One failure keeps the interval: it is as
    likely a mid-cook hiccup as a grill gone away, and backing off on it
    turned a lost ten-second poll into a sixty-second gap exactly when
    freshness matters most. A pattern of them backs off.
    """
    coordinator._api_started = True
    mock_pitboss.is_connected.return_value = True
    coordinator._apply_poll_interval(StateDict(moduleIsOn=True))
    assert coordinator.update_interval == ACTIVE_SCAN_INTERVAL

    mock_pitboss.ping.side_effect = TimeoutError()
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
    assert coordinator.update_interval == ACTIVE_SCAN_INTERVAL

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
    assert coordinator.update_interval == STANDBY_SCAN_INTERVAL


async def test_a_success_resets_the_failure_pattern(
    coordinator: PitBossDataUpdateCoordinator, mock_pitboss: Mock
) -> None:
    """Isolated failures never accumulate into a backoff.

    Only consecutive ones make the pattern; a success in between means the
    grill is there and the cadence should stay whatever its state asks for.
    """
    coordinator._api_started = True
    mock_pitboss.is_connected.return_value = True
    coordinator._apply_poll_interval(StateDict(moduleIsOn=True))

    mock_pitboss.ping.side_effect = TimeoutError()
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
    assert coordinator.update_interval == ACTIVE_SCAN_INTERVAL

    mock_pitboss.ping.side_effect = None
    mock_pitboss.get_state.return_value = StateDict(moduleIsOn=True)
    await coordinator._async_update_data()

    mock_pitboss.ping.side_effect = TimeoutError()
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
    assert coordinator.update_interval == ACTIVE_SCAN_INTERVAL
