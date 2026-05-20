"""Sensor entities for the Harvest Right integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HarvestRightConfigEntry
from .const import DRYING_SCREENS, SCREEN_STATES, STATE_OPTIONS, get_drying_state
from .coordinator import HarvestRightCoordinator
from .entity import HarvestRightEntity


@dataclass(frozen=True, kw_only=True)
class HarvestRightSensorDescription(SensorEntityDescription):
    """Describe a Harvest Right sensor."""

    value_fn: Callable[[dict], str | int | float | None]


def _system(data: dict, key: str):
    """Return a value from the nested system payload."""
    system = data.get("system")
    return system.get(key) if isinstance(system, dict) else None


def _screen_state(data: dict) -> str | None:
    """Map the screen number (plus df bitmask) to a human state label."""
    screen = data.get("screen")
    if screen is None:
        return None
    if screen in DRYING_SCREENS:
        return get_drying_state(screen, data.get("df", 0) or 0)
    return SCREEN_STATES.get(screen, "Unknown")


# Primary, user-facing sensors.
PRIMARY_SENSORS: tuple[HarvestRightSensorDescription, ...] = (
    HarvestRightSensorDescription(
        key="temperature",
        translation_key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("temp"),
    ),
    HarvestRightSensorDescription(
        key="vacuum_pressure",
        translation_key="vacuum_pressure",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="mTorr",
        icon="mdi:gauge-low",
        value_fn=lambda d: d.get("mt"),
    ),
    HarvestRightSensorDescription(
        key="elapsed_time",
        translation_key="elapsed_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.HOURS,
        suggested_display_precision=1,
        icon="mdi:timer-outline",
        value_fn=lambda d: d.get("els"),
    ),
    HarvestRightSensorDescription(
        key="phase_elapsed_time",
        translation_key="phase_elapsed_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.MINUTES,
        suggested_display_precision=0,
        icon="mdi:timer-sand",
        value_fn=lambda d: d.get("eps"),
    ),
    HarvestRightSensorDescription(
        key="progress",
        translation_key="progress",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="%",
        suggested_display_precision=0,
        icon="mdi:progress-clock",
        value_fn=lambda d: d.get("pct"),
    ),
    HarvestRightSensorDescription(
        key="state",
        translation_key="state",
        device_class=SensorDeviceClass.ENUM,
        options=STATE_OPTIONS,
        icon="mdi:state-machine",
        value_fn=_screen_state,
    ),
    HarvestRightSensorDescription(
        key="batch_name",
        translation_key="batch_name",
        icon="mdi:label-outline",
        value_fn=lambda d: d.get("bn"),
    ),
    HarvestRightSensorDescription(
        key="batch_count",
        translation_key="batch_count",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:counter",
        value_fn=lambda d: _system(d, "bc"),
    ),
)

# Diagnostic sensors — grouped under the device's diagnostic section;
# most are hidden by default and meant for advanced users.
DIAGNOSTIC_SENSORS: tuple[HarvestRightSensorDescription, ...] = (
    HarvestRightSensorDescription(
        key="wifi_signal",
        translation_key="wifi_signal",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("rssi"),
    ),
    HarvestRightSensorDescription(
        key="adapter_name",
        translation_key="adapter_name",
        icon="mdi:wifi",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.get("aName"),
    ),
    HarvestRightSensorDescription(
        key="screen_number",
        translation_key="screen_number",
        icon="mdi:monitor",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.get("screen"),
    ),
    HarvestRightSensorDescription(
        key="mode",
        translation_key="mode",
        icon="mdi:cog",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.get("m"),
    ),
    HarvestRightSensorDescription(
        key="shelves",
        translation_key="shelves",
        icon="mdi:tray-full",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.get("f"),
    ),
    HarvestRightSensorDescription(
        key="drying_flags",
        translation_key="drying_flags",
        icon="mdi:flag-variant",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.get("df"),
    ),
)

SENSOR_DESCRIPTIONS = PRIMARY_SENSORS + DIAGNOSTIC_SENSORS


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HarvestRightConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Harvest Right sensor entities."""
    coordinator = entry.runtime_data
    async_add_entities(
        HarvestRightSensor(coordinator, dryer, description)
        for dryer in coordinator.dryers
        for description in SENSOR_DESCRIPTIONS
    )


class HarvestRightSensor(HarvestRightEntity, SensorEntity):
    """A Harvest Right sensor entity."""

    entity_description: HarvestRightSensorDescription

    def __init__(
        self,
        coordinator: HarvestRightCoordinator,
        dryer: dict,
        description: HarvestRightSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, dryer, description.key)
        self.entity_description = description
        if description.key == "temperature":
            self._attr_native_unit_of_measurement = coordinator.temperature_unit

    @property
    def native_value(self) -> str | int | float | None:
        """Return the current sensor value."""
        return self.entity_description.value_fn(self._telemetry)
