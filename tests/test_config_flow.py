from unittest.mock import Mock

import pytest
from bleak.backends.device import BLEDevice
from homeassistant import config_entries
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.const import CONF_DEVICE_ID, CONF_MODEL, CONF_PASSWORD, CONF_PROTOCOL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pitboss.const import DOMAIN, PROTOCOL_WSS


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
    }


async def test_user_flow_pbl2_maps_to_pbl3_control_board(
    hass: HomeAssistant,
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICE_ID: "PBL2-ABC123"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "more_info"
    data_schema = result["data_schema"]
    assert data_schema is not None
    models = data_schema.schema[CONF_MODEL].container
    assert len(models) > 0


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
