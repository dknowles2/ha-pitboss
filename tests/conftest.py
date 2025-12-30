from typing import Awaitable, Callable, Generator
from unittest.mock import Mock, patch

import pytest
from homeassistant.const import CONF_DEVICE_ID, CONF_MODEL, CONF_PASSWORD, CONF_PROTOCOL
from homeassistant.core import HomeAssistant
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM, UnitSystem
from pytboss.grills import Grill, get_grill
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pitboss.const import DOMAIN, PROTOCOL_WSS


@pytest.fixture(autouse=True)
def mock_bluetooth(enable_bluetooth):
    """Auto mock bluetooth."""


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading custom integrations."""
    yield


@pytest.fixture
def model() -> str:
    return "DEFAULT-MODEL"


@pytest.fixture
def spec(model: str) -> Grill:
    return get_grill(model)


@pytest.fixture
def mock_config_entry(model: str) -> MockConfigEntry:
    """Mock ConfigEntry."""
    return MockConfigEntry(
        title="title",
        domain=DOMAIN,
        data={
            CONF_DEVICE_ID: "mygrill",
            CONF_MODEL: model,
            CONF_PASSWORD: "asdfasdf",
            CONF_PROTOCOL: PROTOCOL_WSS,
        },
        unique_id="mygrillid",
    )


@pytest.fixture
def units() -> UnitSystem:
    return US_CUSTOMARY_SYSTEM


@pytest.fixture
async def mock_add_config_entry(
    hass: HomeAssistant,
    units: UnitSystem,
    mock_config_entry: MockConfigEntry,
    mock_wss_conn: Mock,
    mock_pitboss: Mock,
) -> Callable[[], Awaitable[MockConfigEntry]]:
    async def callback() -> MockConfigEntry:
        hass.config.units = units
        mock_pitboss.get_state.return_value = {}
        mock_config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
        assert DOMAIN in hass.config_entries.async_domains()
        return mock_config_entry

    return callback


@pytest.fixture
def mock_conn() -> Generator[Mock]:
    with patch("pytboss.transport.Transport", autospec=True) as mock_conn_cls:
        yield mock_conn_cls.return_value


@pytest.fixture
def mock_wss_conn() -> Generator[Mock]:
    with patch("pytboss.wss.WebSocketConnection", autospec=True) as mock_conn_cls:
        yield mock_conn_cls.return_value


@pytest.fixture
def mock_pitboss(spec: Grill) -> Generator[Mock]:
    with patch("pytboss.api.PitBoss", autospec=True) as mock_pitboss_cls:
        api = mock_pitboss_cls.return_value
        api.spec = spec
        yield api
