"""Binary sensor entities for the Harvest Right integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HarvestRightConfigEntry
from .const import DRYING_SCREENS, ERROR_SCREENS, FREEZING_SCREENS, RUNNING_SCREENS
from .coordinator import HarvestRightCoordinator
from .entity import HarvestRightEntity

# Sentinel: this binary sensor reflects connectivity itself, so it must
# stay "available" even when the dryer is offline (to report "off").
_CONNECTIVITY_KEY = "online"


@dataclass(frozen=True, kw_only=True)
class HarvestRightBinarySensorDescription(BinarySensorEntityDescription):
    """Describe a Harvest Right binary sensor."""

    is_on_fn: Callable[[dict], bool | None]


def _screen_in(data: dict, screens: set[int]) -> bool | None:
    """Return whether the current screen is in a set, or None if unknown."""
    screen = data.get("screen")
    return screen in screens if screen is not None else None


BINARY_SENSOR_DESCRIPTIONS: tuple[HarvestRightBinarySensorDescription, ...] = (
    HarvestRightBinarySensorDescription(
        key="running",
        translation_key="running",
        device_class=BinarySensorDeviceClass.RUNNING,
        is_on_fn=lambda d: _screen_in(d, RUNNING_SCREENS),
    ),
    HarvestRightBinarySensorDescription(
        key="freezing",
        translation_key="freezing",
        icon="mdi:snowflake",
        is_on_fn=lambda d: _screen_in(d, FREEZING_SCREENS),
    ),
    HarvestRightBinarySensorDescription(
        key="drying",
        translation_key="drying",
        icon="mdi:weather-sunny",
        is_on_fn=lambda d: _screen_in(d, DRYING_SCREENS),
    ),
    HarvestRightBinarySensorDescription(
        key="error",
        translation_key="error",
        device_class=BinarySensorDeviceClass.PROBLEM,
        is_on_fn=lambda d: _screen_in(d, ERROR_SCREENS),
    ),
    HarvestRightBinarySensorDescription(
        key=_CONNECTIVITY_KEY,
        translation_key="online",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        # is_on is derived from the coordinator, not telemetry — see is_on.
        is_on_fn=lambda d: None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HarvestRightConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Harvest Right binary sensor entities."""
    coordinator = entry.runtime_data
    async_add_entities(
        HarvestRightBinarySensor(coordinator, dryer, description)
        for dryer in coordinator.dryers
        for description in BINARY_SENSOR_DESCRIPTIONS
    )


class HarvestRightBinarySensor(HarvestRightEntity, BinarySensorEntity):
    """A Harvest Right binary sensor entity."""

    entity_description: HarvestRightBinarySensorDescription

    def __init__(
        self,
        coordinator: HarvestRightCoordinator,
        dryer: dict,
        description: HarvestRightBinarySensorDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, dryer, description.key)
        self.entity_description = description

    @property
    def _is_connectivity(self) -> bool:
        """Return True if this is the connectivity ('online') sensor."""
        return self.entity_description.key == _CONNECTIVITY_KEY

    @property
    def available(self) -> bool:
        """Return availability.

        The connectivity sensor must stay available even when the dryer is
        offline so it can correctly report "off"; all others go unavailable
        when telemetry is stale.
        """
        if self._is_connectivity:
            return self.coordinator.last_update_success
        return super().available

    @property
    def is_on(self) -> bool | None:
        """Return the binary state."""
        if self._is_connectivity:
            return self.coordinator.dryer_available(self._dryer_id)
        return self.entity_description.is_on_fn(self._telemetry)
