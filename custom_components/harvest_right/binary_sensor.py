"""Binary sensor entities for Harvest Right integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    DRYING_SCREENS,
    ERROR_SCREENS,
    FREEZING_SCREENS,
    RUNNING_SCREENS,
)
from .coordinator import HarvestRightCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class HarvestRightBinarySensorDescription(BinarySensorEntityDescription):
    """Describe a Harvest Right binary sensor."""

    is_on_fn: Callable[[dict], bool | None]


def _get_screen(data: dict) -> int | None:
    """Get the current screen number."""
    return data.get("screen")


BINARY_SENSOR_DESCRIPTIONS: tuple[HarvestRightBinarySensorDescription, ...] = (
    HarvestRightBinarySensorDescription(
        key="running",
        translation_key="running",
        name="Running",
        device_class=BinarySensorDeviceClass.RUNNING,
        is_on_fn=lambda data: (
            _get_screen(data) in RUNNING_SCREENS
            if _get_screen(data) is not None
            else None
        ),
    ),
    HarvestRightBinarySensorDescription(
        key="freezing",
        translation_key="freezing",
        name="Freezing",
        icon="mdi:snowflake",
        is_on_fn=lambda data: (
            _get_screen(data) in FREEZING_SCREENS
            if _get_screen(data) is not None
            else None
        ),
    ),
    HarvestRightBinarySensorDescription(
        key="drying",
        translation_key="drying",
        name="Drying",
        icon="mdi:weather-sunny",
        is_on_fn=lambda data: (
            _get_screen(data) in DRYING_SCREENS
            if _get_screen(data) is not None
            else None
        ),
    ),
    HarvestRightBinarySensorDescription(
        key="error",
        translation_key="error",
        name="Error",
        device_class=BinarySensorDeviceClass.PROBLEM,
        is_on_fn=lambda data: (
            _get_screen(data) in ERROR_SCREENS
            if _get_screen(data) is not None
            else None
        ),
    ),
    HarvestRightBinarySensorDescription(
        key="online",
        translation_key="online",
        name="Online",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        is_on_fn=lambda data: (
            _get_screen(data) != 0
            if _get_screen(data) is not None
            else None
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Harvest Right binary sensor entities."""
    coordinator: HarvestRightCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for dryer in coordinator.dryers:
        for description in BINARY_SENSOR_DESCRIPTIONS:
            entities.append(
                HarvestRightBinarySensor(coordinator, dryer, description)
            )
    async_add_entities(entities)


class HarvestRightBinarySensor(BinarySensorEntity):
    """A Harvest Right binary sensor entity."""

    entity_description: HarvestRightBinarySensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: HarvestRightCoordinator,
        dryer: dict,
        description: HarvestRightBinarySensorDescription,
    ) -> None:
        self.coordinator = coordinator
        self._dryer = dryer
        self._dryer_id: int = dryer["id"]
        self.entity_description = description

        serial = dryer["serial"]
        self._attr_unique_id = f"{serial}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, serial)},
            name=dryer.get("dryer_name", serial),
            manufacturer="Harvest Right",
            model=dryer.get("model"),
            sw_version=dryer.get("firmware"),
            hw_version=dryer.get("hardware"),
        )

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        data = self.coordinator.dryer_data.get(self._dryer_id, {})
        return self.entity_description.is_on_fn(data)

    async def async_added_to_hass(self) -> None:
        """Subscribe to dispatcher updates."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{DOMAIN}_{self._dryer_id}_update",
                self._handle_update,
            )
        )

    @callback
    def _handle_update(self) -> None:
        """Handle data update from coordinator."""
        self.async_write_ha_state()
