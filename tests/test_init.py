import asyncio
from unittest.mock import Mock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_DEVICE_ID, CONF_MODEL, CONF_PASSWORD, CONF_PROTOCOL
from homeassistant.core import HomeAssistant
from pytboss.exceptions import GrillUnavailable
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pitboss.const import DOMAIN, PROTOCOL_BLE, PROTOCOL_WSS

pytestmark = pytest.mark.parametrize("model", ["PBV4PS2"])


async def test_setup_entry_unknown_protocol_errors(
    hass: HomeAssistant, mock_wss_conn: Mock, mock_pitboss: Mock
) -> None:
    entry = MockConfigEntry(
        title="title",
        domain=DOMAIN,
        data={
            CONF_DEVICE_ID: "mygrill",
            CONF_MODEL: "PBV4PS2",
            CONF_PASSWORD: "asdfasdf",
            CONF_PROTOCOL: "bogus",
        },
        unique_id="mygrillid",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR


async def test_setup_entry_not_ready_disconnects_and_stops(
    hass: HomeAssistant, mock_wss_conn: Mock, mock_pitboss: Mock
) -> None:
    mock_pitboss.start.side_effect = GrillUnavailable("nope")
    entry = MockConfigEntry(
        title="title",
        domain=DOMAIN,
        data={
            CONF_DEVICE_ID: "mygrill",
            CONF_MODEL: "PBV4PS2",
            CONF_PASSWORD: "asdfasdf",
            CONF_PROTOCOL: PROTOCOL_WSS,
        },
        unique_id="mygrillid",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY
    mock_wss_conn.disconnect.assert_awaited_once()
    mock_pitboss.stop.assert_awaited_once()


async def test_setup_entry_ble_connects_and_forwards_platforms(
    hass: HomeAssistant, mock_pitboss: Mock
) -> None:
    with patch("pytboss.ble.BleConnection", autospec=True) as mock_ble_cls:
        mock_ble_conn = mock_ble_cls.return_value
        mock_ble_conn.is_connected.return_value = True
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
    assert DOMAIN in hass.config_entries.async_domains()


async def test_connect_ble_timeout_raises_not_ready(
    hass: HomeAssistant, mock_pitboss: Mock
) -> None:
    with (
        patch("pytboss.ble.BleConnection", autospec=True) as mock_ble_cls,
        patch(
            "custom_components.pitboss.timeout",
            side_effect=lambda _seconds: asyncio.timeout(0),
        ),
    ):
        mock_ble_conn = mock_ble_cls.return_value
        mock_ble_conn.is_connected.return_value = False

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

    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_unload_entry_stops_api(
    hass: HomeAssistant, mock_wss_conn: Mock, mock_pitboss: Mock
) -> None:
    mock_pitboss.get_state.return_value = {}
    entry = MockConfigEntry(
        title="title",
        domain=DOMAIN,
        data={
            CONF_DEVICE_ID: "mygrill",
            CONF_MODEL: "PBV4PS2",
            CONF_PASSWORD: "asdfasdf",
            CONF_PROTOCOL: PROTOCOL_WSS,
        },
        unique_id="mygrillid",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert entry.entry_id not in hass.data.get(DOMAIN, {})
    mock_pitboss.stop.assert_awaited_once()
