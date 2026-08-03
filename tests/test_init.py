import asyncio
from collections.abc import Awaitable, Callable
from unittest.mock import Mock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_DEVICE_ID, CONF_MODEL, CONF_PASSWORD, CONF_PROTOCOL
from homeassistant.core import HomeAssistant
from pytboss.exceptions import GrillUnavailable, RPCError, Unauthorized
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pitboss.const import (
    ACTIVE_SCAN_INTERVAL,
    DOMAIN,
    PROTOCOL_BLE,
    PROTOCOL_WSS,
    STANDBY_SCAN_INTERVAL,
)
from custom_components.pitboss.coordinator import PitBossDataUpdateCoordinator

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


async def test_setup_entry_releases_transport_on_unexpected_error(
    hass: HomeAssistant, mock_wss_conn: Mock, mock_pitboss: Mock
) -> None:
    """Any first-refresh failure releases the transport, not just not-ready."""
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
    with patch.object(
        PitBossDataUpdateCoordinator,
        "async_config_entry_first_refresh",
        side_effect=RuntimeError("boom"),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_ERROR
    mock_wss_conn.disconnect.assert_awaited_once()
    mock_pitboss.stop.assert_awaited_once()
    assert entry.entry_id not in hass.data.get(DOMAIN, {})


async def test_a_rejected_password_asks_for_a_new_one(
    hass: HomeAssistant, mock_pitboss: Mock, mock_wss_conn: Mock
) -> None:
    """Retrying cannot fix a wrong password.

    On a transport where `PB.GetState` is itself password-gated a stale
    password takes the whole integration down, so the entry goes into
    reauth rather than retrying forever.
    """
    mock_pitboss.get_state.side_effect = Unauthorized("Unauthorized", 401)

    entry = MockConfigEntry(
        title="title",
        domain=DOMAIN,
        data={
            CONF_DEVICE_ID: "mygrill",
            CONF_MODEL: "PBV4PS2",
            CONF_PASSWORD: "wrongpassword",
            CONF_PROTOCOL: PROTOCOL_WSS,
        },
        unique_id="mygrillid",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flows] == ["reauth"]


async def test_other_rpc_errors_do_not_ask_for_a_password(
    hass: HomeAssistant, mock_pitboss: Mock, mock_wss_conn: Mock
) -> None:
    """Only a 401 means the password is wrong."""
    mock_pitboss.get_state.side_effect = RPCError("something else", -1)

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
    assert hass.config_entries.flow.async_progress() == []


async def test_the_poll_interval_follows_the_grill(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    """Poll hard while the grill runs, back off in standby."""
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    assert coordinator.update_interval == STANDBY_SCAN_INTERVAL

    await coordinator._on_state_update({"moduleIsOn": True})
    await hass.async_block_till_done()
    assert coordinator.update_interval == ACTIVE_SCAN_INTERVAL

    await coordinator._on_state_update({"moduleIsOn": False})
    await hass.async_block_till_done()
    assert coordinator.update_interval == STANDBY_SCAN_INTERVAL


async def test_a_partial_frame_does_not_change_the_interval(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    """The board answers with two frames and clears them independently.

    A frame carrying no `moduleIsOn` must not read as "the grill is off" --
    the merged state is what decides, not the frame in isolation.
    """
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator._on_state_update({"moduleIsOn": True, "grillTemp": 100})
    assert coordinator.update_interval == ACTIVE_SCAN_INTERVAL

    await coordinator._on_state_update({"grillTemp": 105})

    assert coordinator.update_interval == ACTIVE_SCAN_INTERVAL
