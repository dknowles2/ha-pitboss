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
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.typing import ConfigType
from pytboss import api, ble, grills, wss
from pytboss.exceptions import InvalidGrill
from pytboss.transport import Transport

from .const import (
    DEFAULT_PROTOCOL,
    DOMAIN,
    LOGGER,
    MANUFACTURER,
    PROTOCOL_BLE,
    PROTOCOL_WSS,
)
from .coordinator import PitBossDataUpdateCoordinator
from .services import async_register_services

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.LIGHT,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def _connect_ble(
    hass: HomeAssistant, entry: ConfigEntry, device_id: str
) -> ble.BleConnection:
    conn = ble.BleConnection(None, loop=hass.loop)  # type: ignore
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


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the integration.

    Actions belong to the integration rather than to any one grill, so they
    are registered once here instead of per config entry.
    """
    async_register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up this integration using UI."""
    hass.data.setdefault(DOMAIN, {})
    device_id = entry.data[CONF_DEVICE_ID]
    model = entry.data[CONF_MODEL]
    password = entry.data.get(CONF_PASSWORD, "")
    conn: Transport

    if (protocol := entry.data.get(CONF_PROTOCOL, DEFAULT_PROTOCOL)) == PROTOCOL_WSS:
        conn = wss.WebSocketConnection(
            device_id, session=async_get_clientsession(hass), loop=hass.loop
        )
    elif protocol == PROTOCOL_BLE:
        conn = await _connect_ble(hass, entry, device_id)
    else:
        raise ValueError(f"Unknown protocol: {protocol}")

    # The prefix the grill advertises names its control board, and a few
    # models were sold on two board generations that do not parse alike.
    # Resolving by model name alone picks the board the vendor lists most
    # recently, which is the wrong one for every grill on the older board.
    control_board: str | None = device_id.split("-")[0]
    try:
        await hass.async_add_executor_job(grills.get_grill, model, control_board)
    except InvalidGrill:
        # An entry from the era of board remapping can hold a model that was
        # never sold under the advertised prefix. Resolving by name alone is
        # what every release so far did, so those keep working unchanged.
        LOGGER.warning(
            "Model %s has no variant on control board %s; "
            "using the vendor's latest listing for it",
            model,
            control_board,
        )
        control_board = None
        try:
            await hass.async_add_executor_job(grills.get_grill, model, None)
        except InvalidGrill as ex:
            # Not "not ready": `api.start()` would raise this again on every
            # retry, and no amount of waiting introduces a model to the
            # catalogue. Asking the user to reconfigure is the only way out.
            raise ConfigEntryError(f"Unknown grill model: {model}") from ex

    # Constructed inline: since spec resolution moved into `start()`, the
    # constructor only assigns attributes. The executor job it ran in was a
    # holdover from when it read the grill catalogue.
    pitboss = api.PitBoss(conn, model, password=password, control_board=control_board)
    device_info = DeviceInfo(
        identifiers={(DOMAIN, device_id)},
        name=device_id,
        model=model,
        manufacturer=MANUFACTURER,
    )
    hass.data[DOMAIN][entry.entry_id] = coordinator = PitBossDataUpdateCoordinator(
        hass, device_info, pitboss
    )
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        # Any failure here aborts the setup, so the transport has to be
        # released. Catching only ConfigEntryNotReady stranded the socket and
        # its receive task on every other error, and each retry added another.
        hass.data[DOMAIN].pop(entry.entry_id, None)
        await conn.disconnect()
        await pitboss.stop()
        raise

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
