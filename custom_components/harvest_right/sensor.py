"""Sensor entities for Harvest Right integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    UnitOfPressure,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SCREEN_STATES
from .coordinator import HarvestRightCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class HarvestRightSensorDescription(SensorEntityDescription):
    """Describe a Harvest Right sensor."""

    value_fn: Callable[[dict], str | int | float | None]


def _get_telemetry(data: dict, key: str):
    """Get a value from telemetry data."""
    return data.get(key)


def _get_system(data: dict, key: str):
    """Get a value from system data."""
    system = data.get("system")
    if system is None:
        return None
    return system.get(key)


def _get_screen_state(data: dict) -> str | None:
    """Map screen number to state name."""
    screen = data.get("screen")
    if screen is None:
        return None
    return SCREEN_STATES.get(screen, "Unknown")


SENSOR_DESCRIPTIONS: tuple[HarvestRightSensorDescription, ...] = (
    HarvestRightSensorDescription(
        key="temperature",
        translation_key="temperature",
        name="Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        value_fn=lambda data: _get_telemetry(data, "temp"),
    ),
    HarvestRightSensorDescription(
        key="vacuum_pressure",
        translation_key="vacuum_pressure",
        name="Vacuum Pressure",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="mTorr",
        icon="mdi:gauge-low",
        value_fn=lambda data: _get_telemetry(data, "mt"),
    ),
    HarvestRightSensorDescription(
        key="elapsed_time",
        translation_key="elapsed_time",
        name="Batch Elapsed Time",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        value_fn=lambda data: _get_telemetry(data, "els"),
    ),
    HarvestRightSensorDescription(
        key="phase_elapsed_time",
        translation_key="phase_elapsed_time",
        name="Phase Elapsed Time",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        value_fn=lambda data: _get_telemetry(data, "eps"),
    ),
    HarvestRightSensorDescription(
        key="progress",
        translation_key="progress",
        name="Progress",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="%",
        icon="mdi:progress-clock",
        value_fn=lambda data: _get_telemetry(data, "pct"),
    ),
    HarvestRightSensorDescription(
        key="wifi_signal",
        translation_key="wifi_signal",
        name="WiFi Signal",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        value_fn=lambda data: _get_telemetry(data, "rssi"),
    ),
    HarvestRightSensorDescription(
        key="state",
        translation_key="state",
        name="State",
        device_class=SensorDeviceClass.ENUM,
        options=[*dict.fromkeys(SCREEN_STATES.values()), "Unknown"],
        icon="mdi:state-machine",
        value_fn=_get_screen_state,
    ),
    HarvestRightSensorDescription(
        key="batch_name",
        translation_key="batch_name",
        name="Batch Name",
        icon="mdi:label-outline",
        value_fn=lambda data: _get_telemetry(data, "bn"),
    ),
    HarvestRightSensorDescription(
        key="batch_count",
        translation_key="batch_count",
        name="Batch Count",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:counter",
        value_fn=lambda data: _get_system(data, "bc"),
    ),
    HarvestRightSensorDescription(
        key="firmware_version",
        translation_key="firmware_version",
        name="Firmware Version",
        icon="mdi:chip",
        value_fn=lambda data: _get_telemetry(data, "V"),
        entity_registry_enabled_default=False,
    ),
    HarvestRightSensorDescription(
        key="mode",
        translation_key="mode",
        name="Mode (m)",
        icon="mdi:cog",
        value_fn=lambda data: _get_telemetry(data, "m"),
        entity_registry_enabled_default=False,
    ),
    HarvestRightSensorDescription(
        key="shelves",
        translation_key="shelves",
        name="Shelves (f)",
        icon="mdi:tray-full",
        value_fn=lambda data: _get_telemetry(data, "f"),
        entity_registry_enabled_default=False,
    ),
    HarvestRightSensorDescription(
        key="defrost_flag",
        translation_key="defrost_flag",
        name="Defrost Flag (df)",
        icon="mdi:snowflake-melt",
        value_fn=lambda data: _get_telemetry(data, "df"),
        entity_registry_enabled_default=False,
    ),
    HarvestRightSensorDescription(
        key="hlp",
        translation_key="hlp",
        name="Unknown (hlp)",
        icon="mdi:help-circle-outline",
        value_fn=lambda data: _get_telemetry(data, "hlp"),
        entity_registry_enabled_default=False,
    ),
    HarvestRightSensorDescription(
        key="ce_flag",
        translation_key="ce_flag",
        name="Unknown Flag (ce)",
        icon="mdi:help-circle-outline",
        value_fn=lambda data: _get_telemetry(data, "ce"),
        entity_registry_enabled_default=False,
    ),
    HarvestRightSensorDescription(
        key="scp",
        translation_key="scp",
        name="Unknown (scp)",
        icon="mdi:help-circle-outline",
        value_fn=lambda data: _get_telemetry(data, "scp"),
        entity_registry_enabled_default=False,
    ),
    HarvestRightSensorDescription(
        key="a_value",
        translation_key="a_value",
        name="Unknown (a)",
        icon="mdi:help-circle-outline",
        value_fn=lambda data: _get_telemetry(data, "a"),
        entity_registry_enabled_default=False,
    ),
    HarvestRightSensorDescription(
        key="adapter_name",
        translation_key="adapter_name",
        name="Adapter Name",
        icon="mdi:wifi",
        value_fn=lambda data: _get_telemetry(data, "aName"),
        entity_registry_enabled_default=False,
    ),
    HarvestRightSensorDescription(
        key="config_key",
        translation_key="config_key",
        name="Config Key (cfg)",
        icon="mdi:key-variant",
        value_fn=lambda data: _get_telemetry(data, "cfg"),
        entity_registry_enabled_default=False,
    ),
    HarvestRightSensorDescription(
        key="dry_process",
        translation_key="dry_process",
        name="Dry Process (dps)",
        icon="mdi:heat-wave",
        value_fn=lambda data: _get_telemetry(data, "dps"),
        entity_registry_enabled_default=False,
    ),
    HarvestRightSensorDescription(
        key="batch_flag",
        translation_key="batch_flag",
        name="Batch Flag (bf)",
        icon="mdi:flag",
        value_fn=lambda data: _get_telemetry(data, "bf"),
        entity_registry_enabled_default=False,
    ),
    HarvestRightSensorDescription(
        key="power_during_cycle",
        translation_key="power_during_cycle",
        name="Power During Cycle (pdc)",
        icon="mdi:flash",
        value_fn=lambda data: _get_telemetry(data, "pdc"),
        entity_registry_enabled_default=False,
    ),
    HarvestRightSensorDescription(
        key="power_during_mode",
        translation_key="power_during_mode",
        name="Power During Mode (pdm)",
        icon="mdi:flash",
        value_fn=lambda data: _get_telemetry(data, "pdm"),
        entity_registry_enabled_default=False,
    ),
    HarvestRightSensorDescription(
        key="screen_number",
        translation_key="screen_number",
        name="Screen Number",
        icon="mdi:monitor",
        value_fn=lambda data: _get_telemetry(data, "screen"),
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Harvest Right sensor entities."""
    coordinator: HarvestRightCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for dryer in coordinator.dryers:
        for description in SENSOR_DESCRIPTIONS:
            entities.append(
                HarvestRightSensor(coordinator, dryer, description)
            )
    async_add_entities(entities)


class HarvestRightSensor(SensorEntity):
    """A Harvest Right sensor entity."""

    entity_description: HarvestRightSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: HarvestRightCoordinator,
        dryer: dict,
        description: HarvestRightSensorDescription,
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
    def native_value(self):
        """Return the sensor value."""
        data = self.coordinator.dryer_data.get(self._dryer_id, {})
        return self.entity_description.value_fn(data)

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
