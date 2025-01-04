"""
Custom integration to integrate PitBoss grills and smokers with Home Assistant.

For more details about this integration, please refer to
https://github.com/dknowles2/ha-pitboss
"""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICE_ID, CONF_MODEL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceInfo
from pytboss.api import PitBoss
from pytboss.wss import WebSocketConnection

from .const import DOMAIN, MANUFACTURER
from .coordinator import PitBossDataUpdateCoordinator

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.LIGHT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up this integration using UI."""
    hass.data.setdefault(DOMAIN, {})
    device_id = entry.data[CONF_DEVICE_ID]
    model = entry.data[CONF_MODEL]
    conn = WebSocketConnection(
        device_id, session=async_get_clientsession(hass), loop=hass.loop
    )
    api = PitBoss(conn, model)
    device_info = DeviceInfo(
        identifiers={(DOMAIN, device_id)},
        name=device_id,
        model=model,
        manufacturer=MANUFACTURER,
    )
    hass.data[DOMAIN][entry.entry_id] = coordinator = PitBossDataUpdateCoordinator(
        hass, device_info, api
    )
    await coordinator.async_config_entry_first_refresh()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Handle removal of an entry."""
    if unloaded := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN].pop(
            entry.entry_id
        )
        await coordinator.api.stop()
    return unloaded
