"""
Custom integration to integrate PitBoss grills and smokers with Home Assistant.

For more details about this integration, please refer to
https://github.com/dknowles2/ha-pitboss
"""

from __future__ import annotations

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth.match import LOCAL_NAME
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICE_ID, CONF_MODEL, Platform
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN, LOGGER
from .coordinator import PitBossDataUpdateCoordinator


PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.LIGHT,
    Platform.SENSOR,
    Platform.SWITCH,
]


# https://developers.home-assistant.io/docs/config_entries_index/#setting-up-an-entry
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up this integration using UI."""
    hass.data.setdefault(DOMAIN, {})
    device_id = entry.data[CONF_DEVICE_ID]
    model = entry.data[CONF_MODEL]

    coordinator = hass.data[DOMAIN][entry.entry_id] = PitBossDataUpdateCoordinator(
        hass, device_id, model
    )

    @callback
    def _detection_callback(
        service_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ):
        LOGGER.debug("Bluetooth device detected: %s (%s)", service_info, change)
        entry.async_create_task(hass, coordinator.reset_device(service_info.device))

    entry.async_on_unload(
        bluetooth.async_register_callback(
            hass,
            _detection_callback,
            bluetooth.BluetoothCallbackMatcher({LOCAL_NAME: device_id}),
            bluetooth.BluetoothScanningMode.ACTIVE,
        )
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Handle removal of an entry."""
    if unloaded := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
