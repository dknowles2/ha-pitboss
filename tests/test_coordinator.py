from unittest.mock import Mock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytboss.exceptions import GrillUnavailable, NotConnectedError, RPCError

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
