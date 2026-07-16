"""Sensor platform for the Inforcer integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import InforcerConfigEntry
from .const import CONF_REGION, DOMAIN, MANUFACTURER
from .coordinator import InforcerDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: InforcerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Inforcer sensors, adding baseline/tenant sensors as they appear."""
    coordinator = entry.runtime_data

    added_baseline_ids: set[str] = set()
    added_tenant_ids: set[str] = set()

    @callback
    def _add_new_entities() -> None:
        new_entities: list[SensorEntity] = []
        data = coordinator.data

        for baseline in data.baseline_scores:
            if baseline.baseline_id and baseline.baseline_id not in added_baseline_ids:
                added_baseline_ids.add(baseline.baseline_id)
                new_entities.append(
                    InforcerBaselineAlignmentScoreSensor(
                        coordinator, entry, baseline.baseline_id
                    )
                )

        for tenant in data.tenant_secure_scores:
            if tenant.tenant_id and tenant.tenant_id not in added_tenant_ids:
                added_tenant_ids.add(tenant.tenant_id)
                new_entities.append(
                    InforcerTenantSecureScoreSensor(
                        coordinator, entry, tenant.tenant_id
                    )
                )

        if new_entities:
            async_add_entities(new_entities)

    async_add_entities(
        [
            InforcerTenantsOnboardedSensor(coordinator, entry),
            InforcerAlignmentScoreOverallSensor(coordinator, entry),
            InforcerSecureScoreOverallSensor(coordinator, entry),
        ]
    )
    _add_new_entities()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_entities))


def _hub_device_info(entry: InforcerConfigEntry) -> DeviceInfo:
    region = entry.data[CONF_REGION]
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=f"Inforcer ({region.upper()})",
        manufacturer=MANUFACTURER,
        entry_type=DeviceEntryType.SERVICE,
        configuration_url="https://app.inforcer.com",
    )


def _tenant_device_info(entry: InforcerConfigEntry, tenant_id: str, name: str) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry.entry_id}_{tenant_id}")},
        name=name,
        manufacturer=MANUFACTURER,
        via_device=(DOMAIN, entry.entry_id),
        entry_type=DeviceEntryType.SERVICE,
    )


class InforcerTenantsOnboardedSensor(
    CoordinatorEntity[InforcerDataUpdateCoordinator], SensorEntity
):
    """Total number of tenants onboarded to this Inforcer account."""

    _attr_has_entity_name = True
    _attr_name = "Tenants onboarded"
    _attr_icon = "mdi:domain"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self, coordinator: InforcerDataUpdateCoordinator, entry: InforcerConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_tenants_onboarded"
        self._attr_device_info = _hub_device_info(entry)

    @property
    def native_value(self) -> int:
        return self.coordinator.data.tenant_count


class InforcerAlignmentScoreOverallSensor(
    CoordinatorEntity[InforcerDataUpdateCoordinator], SensorEntity
):
    """Overall alignment score across all baselines."""

    _attr_has_entity_name = True
    _attr_name = "Alignment score overall"
    _attr_icon = "mdi:shield-check"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(
        self, coordinator: InforcerDataUpdateCoordinator, entry: InforcerConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_alignment_score_overall"
        self._attr_device_info = _hub_device_info(entry)

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.alignment_overall


class InforcerBaselineAlignmentScoreSensor(
    CoordinatorEntity[InforcerDataUpdateCoordinator], SensorEntity
):
    """Alignment score for a single baseline."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:shield-star"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(
        self,
        coordinator: InforcerDataUpdateCoordinator,
        entry: InforcerConfigEntry,
        baseline_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._baseline_id = baseline_id
        self._attr_unique_id = f"{entry.entry_id}_alignment_score_baseline_{baseline_id}"
        self._attr_device_info = _hub_device_info(entry)

    def _current(self) -> Any | None:
        for baseline in self.coordinator.data.baseline_scores:
            if baseline.baseline_id == self._baseline_id:
                return baseline
        return None

    @property
    def available(self) -> bool:
        return super().available and self._current() is not None

    @property
    def name(self) -> str | None:
        current = self._current()
        baseline_name = current.name if current else self._baseline_id
        return f"Alignment score - {baseline_name}"

    @property
    def native_value(self) -> float | None:
        current = self._current()
        return current.score if current else None


class InforcerSecureScoreOverallSensor(
    CoordinatorEntity[InforcerDataUpdateCoordinator], SensorEntity
):
    """Secure score averaged across all tenants.

    Per-tenant scores are also exposed as attributes here for convenience,
    in addition to their own sensors under each tenant device.
    """

    _attr_has_entity_name = True
    _attr_name = "Secure score overall"
    _attr_icon = "mdi:security"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(
        self, coordinator: InforcerDataUpdateCoordinator, entry: InforcerConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_secure_score_overall"
        self._attr_device_info = _hub_device_info(entry)

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.secure_score_overall

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            tenant.name: tenant.score
            for tenant in self.coordinator.data.tenant_secure_scores
        }


class InforcerTenantSecureScoreSensor(
    CoordinatorEntity[InforcerDataUpdateCoordinator], SensorEntity
):
    """Secure score for a single tenant, on that tenant's own device."""

    _attr_has_entity_name = True
    _attr_name = "Secure score"
    _attr_icon = "mdi:security"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(
        self,
        coordinator: InforcerDataUpdateCoordinator,
        entry: InforcerConfigEntry,
        tenant_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._tenant_id = tenant_id
        self._attr_unique_id = f"{entry.entry_id}_secure_score_tenant_{tenant_id}"
        self._entry = entry

    def _current(self) -> Any | None:
        for tenant in self.coordinator.data.tenant_secure_scores:
            if tenant.tenant_id == self._tenant_id:
                return tenant
        return None

    @property
    def available(self) -> bool:
        return super().available and self._current() is not None

    @property
    def device_info(self) -> DeviceInfo:
        current = self._current()
        name = current.name if current else self._tenant_id
        return _tenant_device_info(self._entry, self._tenant_id, name)

    @property
    def native_value(self) -> float | None:
        current = self._current()
        return current.score if current else None
