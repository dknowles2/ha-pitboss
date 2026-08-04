import asyncio
from collections.abc import Awaitable, Callable
from unittest.mock import Mock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    CONF_DEVICE_ID,
    CONF_HOST,
    CONF_MODEL,
    CONF_PASSWORD,
    CONF_PROTOCOL,
)
from homeassistant.core import HomeAssistant
from pytboss.exceptions import GrillUnavailable, RPCError, Unauthorized
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pitboss.const import (
    ACTIVE_SCAN_INTERVAL,
    CONF_ENABLE_REMOTE_START,
    DOMAIN,
    PROTOCOL_BLE,
    PROTOCOL_LOCAL,
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


async def test_setup_passes_the_advertised_control_board(
    hass: HomeAssistant, mock_wss_conn: Mock, mock_pitboss_cls: Mock
) -> None:
    """The device-id prefix names the board, so setup must resolve with it.

    A few models were sold on two board generations; by name alone pytboss
    returns the board the vendor lists most recently, which is wrong for
    every grill on the older one.
    """
    mock_pitboss_cls.return_value.get_state.return_value = {}
    entry = MockConfigEntry(
        title="title",
        domain=DOMAIN,
        data={
            CONF_DEVICE_ID: "PBL-AABBCC",
            CONF_MODEL: "PBV4PS2",
            CONF_PASSWORD: "asdfasdf",
            CONF_PROTOCOL: PROTOCOL_WSS,
        },
        unique_id="pbl-aabbcc",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert mock_pitboss_cls.call_args.kwargs["control_board"] == "PBL"


async def test_setup_falls_back_when_the_board_has_no_such_model(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
    mock_pitboss_cls: Mock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An entry whose prefix and model do not pair keeps today's behaviour.

    The board-remap workarounds this repo used to ship could store a model
    that was never sold under the advertised prefix; those entries resolve
    by name alone, as every release so far did.
    """
    entry = await mock_add_config_entry()  # device id "mygrill"

    assert entry.state is ConfigEntryState.LOADED
    assert mock_pitboss_cls.call_args.kwargs["control_board"] is None
    assert "has no variant on control board mygrill" in caplog.text


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


async def test_setup_entry_local_connects_and_forwards_platforms(
    hass: HomeAssistant, mock_pitboss: Mock
) -> None:
    """The local protocol builds an HttpConnection on the shared session."""
    with patch("pytboss.http.HttpConnection", autospec=True) as mock_http_cls:
        mock_pitboss.get_state.return_value = {}

        entry = MockConfigEntry(
            title="title",
            domain=DOMAIN,
            data={
                CONF_DEVICE_ID: "PBL-ABC123",
                CONF_MODEL: "PBV4PS2",
                CONF_PASSWORD: "asdfasdf",
                CONF_PROTOCOL: PROTOCOL_LOCAL,
                CONF_HOST: "192.168.1.50",
            },
            unique_id="pbl-abc123",
        )
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert mock_http_cls.call_args.args == ("192.168.1.50",)
    # The shared Home Assistant session, so disconnect() must not close it.
    assert mock_http_cls.call_args.kwargs["session"] is not None


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


async def test_changing_a_live_option_does_not_reload_the_entry(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    """Every current option is read live, so saving one must not reload.

    A reload is not free: on Bluetooth it waits for the grill to advertise
    again, so flipping a toggle while the grill was asleep took the whole
    integration down until the grill next woke up.
    """
    entry = await mock_add_config_entry()
    coordinator_before = hass.data[DOMAIN][entry.entry_id]

    hass.config_entries.async_update_entry(
        entry, options={CONF_ENABLE_REMOTE_START: True}
    )
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert hass.data[DOMAIN][entry.entry_id] is coordinator_before


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


async def test_setup_fails_permanently_for_a_model_not_in_the_catalogue(
    hass: HomeAssistant,
    model: str,
) -> None:
    """Retrying cannot introduce a model to the catalogue.

    The fallback to resolving by name alone is for entries whose prefix and
    model do not pair. When that fails too the model itself is unknown, and
    `api.start()` would raise the same thing on every retry -- so the entry
    has to stop and ask, rather than back off forever.
    """
    entry = MockConfigEntry(
        title="title",
        domain=DOMAIN,
        data={
            CONF_DEVICE_ID: "mygrill",
            CONF_MODEL: "NO-SUCH-MODEL",
            CONF_PASSWORD: "asdfasdf",
            CONF_PROTOCOL: PROTOCOL_WSS,
        },
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_ERROR
