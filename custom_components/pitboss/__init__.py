"""
Custom integration to integrate PitBoss grills and smokers with Home Assistant.

For more details about this integration, please refer to
https://github.com/dknowles2/ha-pitboss
"""

from asyncio import Condition, timeout

from bleak.backends.device import BLEDevice
from homeassistant.components import bluetooth
from homeassistant.components.bluetooth.match import LOCAL_NAME
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_DEVICE_ID,
    CONF_MODEL,
    CONF_PASSWORD,
    CONF_PROTOCOL,
    Platform,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceInfo
from pytboss.api import PitBoss
from pytboss.ble import BleConnection
from pytboss.transport import Transport
from pytboss.wss import WebSocketConnection

from .const import (
    DEFAULT_PROTOCOL,
    DOMAIN,
    LOGGER,
    MANUFACTURER,
    PROTOCOL_BLE,
    PROTOCOL_WSS,
)
from .coordinator import PitBossDataUpdateCoordinator

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.LIGHT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def _connect_ble(
    hass: HomeAssistant, entry: ConfigEntry, device_id: str
) -> BleConnection:
    conn = BleConnection(None, loop=hass.loop)  # type: ignore
    ready = Condition()

    async def reset_device(ble_device: BLEDevice):
        await conn.reset_device(ble_device)
        async with ready:
            ready.notify_all()

    @callback
    def _detection_callback(
        service_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ):
        LOGGER.debug("Bluetooth device detected: %s (%s)", service_info, change)
        if conn.is_connected():
            return
        entry.async_create_task(hass, reset_device(service_info.device))

    entry.async_on_unload(
        bluetooth.async_register_callback(
            hass,
            _detection_callback,
            bluetooth.BluetoothCallbackMatcher({LOCAL_NAME: device_id}),
            bluetooth.BluetoothScanningMode.ACTIVE,
        )
    )

    try:
        async with timeout(30):
            async with ready:
                await ready.wait_for(conn.is_connected)
    except TimeoutError:
        raise ConfigEntryNotReady

    return conn


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up this integration using UI."""
    hass.data.setdefault(DOMAIN, {})
    device_id = entry.data[CONF_DEVICE_ID]
    model = entry.data[CONF_MODEL]
    password = entry.data.get(CONF_PASSWORD, "")
    conn: Transport

    if (protocol := entry.data.get(CONF_PROTOCOL, DEFAULT_PROTOCOL)) == PROTOCOL_WSS:
        conn = WebSocketConnection(
            device_id, session=async_get_clientsession(hass), loop=hass.loop
        )
    elif protocol == PROTOCOL_BLE:
        conn = await _connect_ble(hass, entry, device_id)
    else:
        raise ValueError(f"Unknown protocol: {protocol}")

    api = PitBoss(conn, model, password=password)
    device_info = DeviceInfo(
        identifiers={(DOMAIN, device_id)},
        name=device_id,
        model=model,
        manufacturer=MANUFACTURER,
    )
    hass.data[DOMAIN][entry.entry_id] = coordinator = PitBossDataUpdateCoordinator(
        hass, device_info, api
    )
    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryNotReady as ex:
        await conn.disconnect()
        await api.stop()
        raise ex

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
