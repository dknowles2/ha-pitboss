from collections.abc import Awaitable, Callable
from unittest.mock import Mock

import pytest
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pitboss.const import DOMAIN

pytestmark = pytest.mark.parametrize("model", ["PBV4PS2"])


def _device_id(hass: HomeAssistant) -> str:
    device = dr.async_get(hass).async_get_device({(DOMAIN, "mygrill")})
    assert device is not None
    return device.id


async def test_sets_the_password_and_keeps_the_entry_in_sync(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
    mock_pitboss: Mock,
) -> None:
    """Otherwise a restart would reconnect with the old password."""
    entry = await mock_add_config_entry()
    mock_pitboss.is_connected.return_value = True

    await hass.services.async_call(
        DOMAIN,
        "set_grill_password",
        {"device_id": _device_id(hass), CONF_PASSWORD: "hunter2"},
        blocking=True,
    )

    mock_pitboss.set_grill_password.assert_awaited_once_with("hunter2")
    assert entry.data[CONF_PASSWORD] == "hunter2"


async def test_removing_the_password_stores_an_empty_one(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
    mock_pitboss: Mock,
) -> None:
    entry = await mock_add_config_entry()
    mock_pitboss.is_connected.return_value = True

    await hass.services.async_call(
        DOMAIN, "set_grill_password", {"device_id": _device_id(hass)}, blocking=True
    )

    mock_pitboss.set_grill_password.assert_awaited_once_with("")
    assert entry.data[CONF_PASSWORD] == ""


async def test_refuses_while_disconnected(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
    mock_pitboss: Mock,
) -> None:
    """Half-applying a password change is the worst outcome."""
    await mock_add_config_entry()
    mock_pitboss.is_connected.return_value = False

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN,
            "set_grill_password",
            {"device_id": _device_id(hass), CONF_PASSWORD: "hunter2"},
            blocking=True,
        )
    mock_pitboss.set_grill_password.assert_not_awaited()


async def test_rejects_an_unknown_device(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    await mock_add_config_entry()
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "set_grill_password",
            {"device_id": "nope", CONF_PASSWORD: "hunter2"},
            blocking=True,
        )


async def test_a_failed_change_leaves_the_entry_alone(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
    mock_pitboss: Mock,
) -> None:
    """The whole point is that the two cannot drift apart."""
    entry = await mock_add_config_entry()
    mock_pitboss.is_connected.return_value = True
    mock_pitboss.set_grill_password.side_effect = RuntimeError("boom")

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN,
            "set_grill_password",
            {"device_id": _device_id(hass), CONF_PASSWORD: "hunter2"},
            blocking=True,
        )
    assert entry.data[CONF_PASSWORD] == "asdfasdf"
