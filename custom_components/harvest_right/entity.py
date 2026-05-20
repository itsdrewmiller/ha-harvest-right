"""Base entity for the Harvest Right integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import HarvestRightCoordinator


class HarvestRightEntity(CoordinatorEntity[HarvestRightCoordinator]):
    """Base class for Harvest Right entities tied to one dryer."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: HarvestRightCoordinator,
        dryer: dict,
        key: str,
    ) -> None:
        """Initialize the entity and its device info."""
        super().__init__(coordinator)
        self._dryer_id: int = dryer["id"]
        serial = dryer["serial"]
        self._attr_unique_id = f"{serial}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, serial)},
            name=dryer["name"],
            manufacturer="Harvest Right",
            model=dryer.get("model"),
            serial_number=serial,
            sw_version=dryer.get("firmware"),
            hw_version=dryer.get("hardware"),
            configuration_url="https://harvestright.com",
        )

    @property
    def _telemetry(self) -> dict:
        """Return the accumulated telemetry for this dryer."""
        return self.coordinator.dryer_telemetry(self._dryer_id)

    @property
    def available(self) -> bool:
        """Return True only when recent telemetry is flowing for this dryer."""
        return super().available and self.coordinator.dryer_available(self._dryer_id)
