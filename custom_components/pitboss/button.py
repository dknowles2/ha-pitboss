"""Button platform for pitboss."""

from __future__ import annotations

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PROTOCOL, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEFAULT_PROTOCOL, DOMAIN, PROTOCOL_WSS
from .coordinator import PitBossDataUpdateCoordinator
from .entity import BaseEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Setup button platform."""
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    assert entry.unique_id is not None
    entities: list[ButtonEntity] = [
        RestartControllerButton(coordinator, entry.unique_id)
    ]
    # The fast-updates request accelerates the grill's push to the Dansons
    # relay and nothing else, so it would be a decorative button on any other
    # protocol.
    if entry.data.get(CONF_PROTOCOL, DEFAULT_PROTOCOL) == PROTOCOL_WSS:
        entities.append(FastUpdatesButton(coordinator, entry.unique_id))
    async_add_entities(entities)


class RestartControllerButton(BaseEntity, ButtonEntity):
    """Reboots the grill's WiFi module.

    The standard remedy when the module wedges. It drops the connection for a
    short while; the grill itself keeps running.
    """

    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: PitBossDataUpdateCoordinator,
        entry_unique_id: str,
    ) -> None:
        super().__init__(coordinator, entry_unique_id)
        self._attr_unique_id = f"restart_{entry_unique_id}"
        self._attr_name = "Restart controller"

    async def async_press(self) -> None:
        """Reboot the module."""
        await self.coordinator.api.reboot()


class FastUpdatesButton(BaseEntity, ButtonEntity):
    """Asks the grill to push status to the cloud every 5s for 5 minutes.

    Despite the underlying RPC being named `PB.WiFiAwakeWDT` this does not
    keep the WiFi module awake: it arms a five-minute countdown that makes the
    firmware reschedule its push timer to the fast interval instead of the
    slow one. It does nothing at all unless the grill is on, and nothing on
    any transport but the cloud one.
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:speedometer"

    def __init__(
        self,
        coordinator: PitBossDataUpdateCoordinator,
        entry_unique_id: str,
    ) -> None:
        super().__init__(coordinator, entry_unique_id)
        self._attr_unique_id = f"fast_updates_{entry_unique_id}"
        self._attr_name = "Request fast updates"

    async def async_press(self) -> None:
        """Request the faster push cadence."""
        await self.coordinator.api.request_fast_updates()
