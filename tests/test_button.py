from collections.abc import Awaitable, Callable
from unittest.mock import Mock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_DEVICE_ID, CONF_MODEL, CONF_PASSWORD, CONF_PROTOCOL
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pitboss.const import DOMAIN, PROTOCOL_BLE

pytestmark = pytest.mark.parametrize("model", ["PBV4PS2"])


async def test_restart_button(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
    mock_pitboss: Mock,
) -> None:
    entry = await mock_add_config_entry()
    coordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.async_set_updated_data({"moduleIsOn": True})
    await hass.async_block_till_done()

    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": "button.mygrill_restart_controller"},
        blocking=True,
    )

    mock_pitboss.reboot.assert_awaited_once_with()


async def test_fast_updates_button(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
    mock_pitboss: Mock,
) -> None:
    entry = await mock_add_config_entry()
    coordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.async_set_updated_data({"moduleIsOn": True})
    await hass.async_block_till_done()

    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": "button.mygrill_request_fast_updates"},
        blocking=True,
    )

    mock_pitboss.request_fast_updates.assert_awaited_once_with()


async def test_no_fast_updates_button_over_bluetooth(
    hass: HomeAssistant, mock_pitboss: Mock
) -> None:
    """It only speeds up the push to the relay, so elsewhere it is a no-op."""
    with patch("pytboss.ble.BleConnection", autospec=True) as mock_ble_cls:
        mock_ble_cls.return_value.is_connected.return_value = True
        mock_pitboss.get_state.return_value = {}

        entry = MockConfigEntry(
            title="title",
            domain=DOMAIN,
            data={
                CONF_DEVICE_ID: "mygrill",
                CONF_MODEL: "PBV4PS2",
                CONF_PASSWORD: "asdfasdf",
                CONF_PROTOCOL: PROTOCOL_BLE,
            },
            unique_id="mygrillid",
        )
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("button.mygrill_restart_controller") is not None
    assert hass.states.get("button.mygrill_request_fast_updates") is None
