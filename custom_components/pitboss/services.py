"""Services for pitboss."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_DEVICE_ID, CONF_PASSWORD
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from pytboss.exceptions import Unauthorized

from .const import CONF_ENABLE_REMOTE_START, DOMAIN, LOGGER
from .coordinator import PitBossDataUpdateCoordinator

SERVICE_SET_GRILL_PASSWORD = "set_grill_password"
SERVICE_START_GRILL = "start_grill"

# Conditions that make lighting the grill a bad idea. The board would likely
# refuse or fail anyway, but failing here says why.
BLOCKING_ERRORS = {
    "noPellets": "the hopper reports no pellets",
    "highTempErr": "the grill reports a high temperature error",
    "erL": "the grill reports an ignition (ErL) error",
    "fanErr": "the grill reports a fan error",
    "motorErr": "the grill reports an auger error",
    "hotErr": "the grill reports an igniter error",
}

START_GRILL_SCHEMA = vol.Schema({vol.Required(ATTR_DEVICE_ID): cv.string})

SET_GRILL_PASSWORD_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        # Omit (or pass an empty string) to remove the password.
        vol.Optional(CONF_PASSWORD, default=""): cv.string,
    }
)


def _coordinator_for_device(
    hass: HomeAssistant, device_id: str
) -> tuple[PitBossDataUpdateCoordinator, ConfigEntry]:
    """Return the coordinator and config entry for a PitBoss device.

    Returns the entry itself rather than its id so the caller cannot end up
    holding one without the other.
    """
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        raise ServiceValidationError(f"Unknown device: {device_id}")
    for entry_id in device.config_entries:
        coordinator = hass.data.get(DOMAIN, {}).get(entry_id)
        entry = hass.config_entries.async_get_entry(entry_id)
        if coordinator is not None and entry is not None:
            return coordinator, entry
    raise ServiceValidationError(f"Device {device_id} is not a PitBoss grill")


async def _async_set_grill_password(hass: HomeAssistant, call: ServiceCall) -> None:
    """Set or remove the grill password."""
    coordinator, entry = _coordinator_for_device(hass, call.data[ATTR_DEVICE_ID])
    new_password: str = call.data[CONF_PASSWORD]

    if not coordinator.api.is_connected():
        raise HomeAssistantError(
            "The grill is not connected; turn it on and try again."
        )

    try:
        await coordinator.api.set_grill_password(new_password)
    except Unauthorized as ex:
        # Changing the password is authenticated with the current one, so
        # this means the one Home Assistant holds is not the grill's. That is
        # the same condition the coordinator opens a reauth flow for, and it
        # is the only thing that lets the user fix it.
        entry.async_start_reauth(hass)
        raise HomeAssistantError(
            "The grill rejected the password Home Assistant holds. "
            "Enter the current one and try again."
        ) from ex
    except Exception as ex:
        raise HomeAssistantError(f"Could not set the grill password: {ex}") from ex

    # Keep the config entry in sync, otherwise Home Assistant would reconnect
    # with the old password after a restart and every command would be
    # rejected by the grill.
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_PASSWORD: new_password}
    )
    LOGGER.info("Grill password %s", "removed" if not new_password else "updated")


async def _async_start_grill(hass: HomeAssistant, call: ServiceCall) -> None:
    """Light the grill, if the user has deliberately allowed it."""
    coordinator, entry = _coordinator_for_device(hass, call.data[ATTR_DEVICE_ID])

    if not entry.options.get(CONF_ENABLE_REMOTE_START, False):
        raise ServiceValidationError(
            "Remote start is disabled. Enable it in the integration options "
            "first, and only if you accept lighting the grill without "
            "standing next to it."
        )

    if not coordinator.api.is_connected():
        raise HomeAssistantError("The grill is not connected.")

    data = coordinator.data or {}
    if data.get("moduleIsOn"):
        raise HomeAssistantError("The grill is already on.")
    for key, reason in BLOCKING_ERRORS.items():
        if data.get(key):
            raise HomeAssistantError(f"Refusing to start: {reason}.")

    LOGGER.warning(
        "Lighting the grill remotely. Make sure the lid is open and the burn "
        "pot is clear of unburned pellets."
    )
    await coordinator.api.turn_grill_on()
    await coordinator.async_request_refresh()


@callback
def async_register_services(hass: HomeAssistant) -> None:
    """Register PitBoss services."""

    async def handle_start_grill(call: ServiceCall) -> None:
        await _async_start_grill(hass, call)

    hass.services.async_register(
        DOMAIN, SERVICE_START_GRILL, handle_start_grill, schema=START_GRILL_SCHEMA
    )

    async def handle_set_grill_password(call: ServiceCall) -> None:
        await _async_set_grill_password(hass, call)

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_GRILL_PASSWORD,
        handle_set_grill_password,
        schema=SET_GRILL_PASSWORD_SCHEMA,
    )
