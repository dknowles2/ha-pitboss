import threading
from unittest.mock import Mock, patch

import pytest
from bleak.backends.device import BLEDevice
from homeassistant import config_entries
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.const import (
    CONF_DEVICE_ID,
    CONF_HOST,
    CONF_MODEL,
    CONF_PASSWORD,
    CONF_PROTOCOL,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytboss import grills
from pytboss.exceptions import NotConnectedError, RPCError, Unauthorized
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pitboss.const import DOMAIN, PROTOCOL_LOCAL, PROTOCOL_WSS


def _bluetooth_service_info(name: str) -> BluetoothServiceInfoBleak:
    return BluetoothServiceInfoBleak(
        name=name,
        address="AA:BB:CC:DD:EE:FF",
        rssi=-60,
        manufacturer_data={},
        service_data={},
        service_uuids=[],
        source="local",
        device=BLEDevice(address="AA:BB:CC:DD:EE:FF", name=name, details=None),
        advertisement=None,
        connectable=True,
        time=0.0,
        tx_power=None,
    )


async def test_user_flow_shows_form(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_user_flow_unknown_grill_aborts(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICE_ID: "ZZZZZZZZ-ABC123"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "unknown_grill"


async def test_user_flow_shows_more_info_form(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICE_ID: "PBL-ABC123"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "more_info"


async def test_user_flow_creates_entry(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICE_ID: "PBL-ABC123"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_MODEL: "PBV4PS2",
            CONF_PASSWORD: "hunter2",
            CONF_PROTOCOL: PROTOCOL_WSS,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "PBL-ABC123"
    assert result["data"] == {
        CONF_DEVICE_ID: "PBL-ABC123",
        CONF_MODEL: "PBV4PS2",
        CONF_PASSWORD: "hunter2",
        CONF_PROTOCOL: PROTOCOL_WSS,
        # Stored on every entry, empty unless the local protocol is chosen.
        CONF_HOST: "",
    }


@pytest.mark.parametrize("control_board", ["PBL2", "LBL", "LFS"])
async def test_user_flow_offers_that_control_boards_models(
    hass: HomeAssistant, control_board: str
) -> None:
    """The flow lists the models for the board the grill advertises.

    PBL2 used to be rewritten to PBL3 because pytboss had no PBL2 definitions,
    and LBL and LFS aborted the flow outright for the same reason, so a grill
    could be discovered but not added.
    """
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICE_ID: f"{control_board}-ABC123"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "more_info"
    data_schema = result["data_schema"]
    assert data_schema is not None
    models = set(data_schema.schema[CONF_MODEL].container)
    assert models == {g.name for g in grills.get_grills(control_board)}
    assert models


async def test_user_flow_pbl2_is_not_rewritten_to_pbl3(hass: HomeAssistant) -> None:
    """A PBL2 grill gets PBL2 definitions, not the ones PBL3 ships.

    The two boards parse temperatures differently, so resolving one as the
    other is not harmless.
    """
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICE_ID: "PBL2-ABC123"}
    )
    data_schema = result["data_schema"]
    assert data_schema is not None
    models = set(data_schema.schema[CONF_MODEL].container)
    assert models != {g.name for g in grills.get_grills("PBL3")}


async def test_user_flow_already_configured_aborts(hass: HomeAssistant) -> None:
    existing_entry = MockConfigEntry(
        title="title",
        domain=DOMAIN,
        data={
            CONF_DEVICE_ID: "PBL-ABC123",
            CONF_MODEL: "PBV4PS2",
            CONF_PASSWORD: "asdfasdf",
            CONF_PROTOCOL: PROTOCOL_WSS,
        },
        unique_id="pbl-abc123",
    )
    existing_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICE_ID: "PBL-ABC123"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_bluetooth_flow_shows_confirm(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_BLUETOOTH},
        data=_bluetooth_service_info("PBL-ABC123"),
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "bluetooth_confirm"
    assert result["description_placeholders"] == {"name": "PBL-ABC123"}


async def test_bluetooth_flow_confirm_advances_to_more_info(
    hass: HomeAssistant,
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_BLUETOOTH},
        data=_bluetooth_service_info("PBL-ABC123"),
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "more_info"


def _reconfigure_entry() -> MockConfigEntry:
    return MockConfigEntry(
        title="title",
        domain=DOMAIN,
        data={
            CONF_DEVICE_ID: "PBL-ABC123",
            CONF_MODEL: "PBV4PS2",
            CONF_PASSWORD: "oldpw",
            CONF_PROTOCOL: PROTOCOL_WSS,
        },
        unique_id="pbl-abc123",
    )


async def test_reconfigure_flow_shows_prefilled_form(hass: HomeAssistant) -> None:
    entry = _reconfigure_entry()
    entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_reconfigure_flow_updates_entry(
    hass: HomeAssistant,
    mock_wss_conn: Mock,
    mock_pitboss: Mock,
) -> None:
    # Reconfiguring reloads the entry, so the WSS connection and API need to
    # be mocked (keeping the protocol as WSS) for the reload to succeed
    # without a real network connection.
    mock_pitboss.get_state.return_value = {}
    entry = _reconfigure_entry()
    entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_MODEL: "PBV4PS2",
            CONF_PASSWORD: "newpw",
            CONF_PROTOCOL: PROTOCOL_WSS,
        },
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_PASSWORD] == "newpw"


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_reauth_updates_the_password_and_reloads(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_pitboss: Mock,
) -> None:
    mock_config_entry.add_to_hass(hass)

    result = await mock_config_entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "newpassword"}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_config_entry.data[CONF_PASSWORD] == "newpassword"


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_reauth_accepts_an_empty_password(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_pitboss: Mock,
) -> None:
    """Clearing the grill's password is supported; the firmware treats an
    empty one as no authentication at all."""
    mock_config_entry.add_to_hass(hass)

    result = await mock_config_entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert mock_config_entry.data[CONF_PASSWORD] == ""


async def test_model_list_is_built_off_the_event_loop(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reading the model list parses ~180 kB of JSON off disk.

    `async_setup_entry` already hands the equivalent call to the executor.
    This is the path that pays the cost first, though: on a fresh install
    there is no entry yet whose setup could have warmed the cache.
    """
    loop_thread = threading.current_thread()
    called_on: list[threading.Thread] = []
    real_get_grills = grills.get_grills

    def recording_get_grills(*args, **kwargs):
        called_on.append(threading.current_thread())
        return real_get_grills(*args, **kwargs)

    monkeypatch.setattr(grills, "get_grills", recording_get_grills)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICE_ID: "PBL-1234"}
    )

    assert called_on, "the model list was never built"
    assert loop_thread not in called_on


async def test_local_protocol_requires_a_host(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICE_ID: "PBL-ABC123"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_MODEL: "PBV4PS2", CONF_PROTOCOL: PROTOCOL_LOCAL, CONF_HOST: ""},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_HOST: "host_required"}


async def test_local_protocol_checks_the_grill_answers(hass: HomeAssistant) -> None:
    """Not every grill has the local interface on, and it is per-unit.

    So the address is validated by trying it rather than by trusting it.
    """
    with patch(
        "custom_components.pitboss.config_flow.http.HttpConnection", autospec=True
    ) as mock_http:
        mock_http.return_value.connect.side_effect = NotConnectedError("nothing there")

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_DEVICE_ID: "PBL-ABC123"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_MODEL: "PBV4PS2",
                CONF_PROTOCOL: PROTOCOL_LOCAL,
                CONF_HOST: "192.168.1.50",
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_HOST: "cannot_connect"}


@pytest.mark.parametrize(
    ("raised", "expected"),
    [
        (NotConnectedError("nothing there"), "cannot_connect"),
        # Raw rather than wrapped: the transport races its own deadline
        # against aiohttp's, and when its `asyncio.timeout` fires first the
        # failure is a bare TimeoutError, not NotConnectedError.
        (TimeoutError(), "cannot_connect"),
        (Unauthorized("Unauthorized", 401), "invalid_auth"),
        (RPCError("Expected a JSON object, got str"), "not_a_grill"),
    ],
)
async def test_local_protocol_distinguishes_why_it_failed(
    hass: HomeAssistant, raised: Exception, expected: str
) -> None:
    """The three ways this goes wrong are three different things to say.

    Nothing listening, a grill that refused us, and something at that address
    that is not a grill at all -- a mistyped IP landing on a router's admin
    page answers 200 and HTML. A bare timeout counts as nothing listening,
    whichever of the transport's two deadlines fired first.
    """
    with patch(
        "custom_components.pitboss.config_flow.http.HttpConnection", autospec=True
    ) as mock_http:
        mock_http.return_value.connect.side_effect = raised

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_DEVICE_ID: "PBL-ABC123"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_MODEL: "PBV4PS2",
                CONF_PROTOCOL: PROTOCOL_LOCAL,
                CONF_HOST: "192.168.1.50",
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_HOST: expected}


async def test_local_protocol_creates_the_entry(hass: HomeAssistant) -> None:
    with patch(
        "custom_components.pitboss.config_flow.http.HttpConnection", autospec=True
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_DEVICE_ID: "PBL-ABC123"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_MODEL: "PBV4PS2",
                CONF_PROTOCOL: PROTOCOL_LOCAL,
                CONF_HOST: "192.168.1.50",
            },
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_PROTOCOL] == PROTOCOL_LOCAL
    assert result["data"][CONF_HOST] == "192.168.1.50"


async def test_a_host_is_not_required_for_other_protocols(hass: HomeAssistant) -> None:
    """The field is shown always but only means anything for the local one."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICE_ID: "PBL-ABC123"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MODEL: "PBV4PS2", CONF_PROTOCOL: PROTOCOL_WSS}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_HOST] == ""
