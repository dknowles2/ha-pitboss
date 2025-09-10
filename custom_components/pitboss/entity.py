"""BaseEntity class"""

from __future__ import annotations

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import PitBossDataUpdateCoordinator


class BaseEntity(CoordinatorEntity[PitBossDataUpdateCoordinator]):
    """Base entity class."""

    _device_id: str
    _attr_has_entity_name = True

    def __init__(
        self, coordinator: PitBossDataUpdateCoordinator, entry_unique_id: str
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self.entry_unique_id = entry_unique_id
        self._attr_device_info = coordinator.device_info

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            super().available
            and bool(self.coordinator.api)
            and self.coordinator.api.is_connected()
            and bool(self.coordinator.data)
        )
