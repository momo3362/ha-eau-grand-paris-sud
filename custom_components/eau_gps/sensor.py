"""Capteurs de l'intégration Eau Grand Paris Sud."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EauGpsCoordinator


@dataclass(frozen=True, kw_only=True)
class EauGpsSensorDescription(SensorEntityDescription):
    """Description d'un capteur, avec son extracteur de valeur."""

    valeur: Callable[[dict[str, Any]], Any]


CAPTEURS: tuple[EauGpsSensorDescription, ...] = (
    EauGpsSensorDescription(
        key="index",
        name="Index compteur d'eau",
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        suggested_display_precision=3,
        valeur=lambda d: d["index_m3"],
    ),
    EauGpsSensorDescription(
        key="conso_jour",
        name="Consommation d'eau du jour",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        valeur=lambda d: d["conso_jour_l"],
    ),
    EauGpsSensorDescription(
        key="moyenne_30j",
        name="Consommation d'eau moyenne 30 jours",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        valeur=lambda d: d["moyenne_30j_l"],
    ),
    EauGpsSensorDescription(
        key="date_releve",
        name="Dernier relevé d'eau",
        device_class=SensorDeviceClass.TIMESTAMP,
        valeur=lambda d: d["date_releve"],
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Crée les capteurs pour une entrée de configuration."""
    coordinator: EauGpsCoordinator = entry.runtime_data
    async_add_entities(
        EauGpsSensor(coordinator, description) for description in CAPTEURS
    )


class EauGpsSensor(CoordinatorEntity[EauGpsCoordinator], SensorEntity):
    """Un capteur adossé au coordinateur."""

    _attr_has_entity_name = False
    entity_description: EauGpsSensorDescription

    def __init__(
        self,
        coordinator: EauGpsCoordinator,
        description: EauGpsSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.contrat}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.contrat)},
            manufacturer="Eau de Grand Paris Sud",
            model="Compteur télérelevé",
            name=f"Eau — contrat {coordinator.contrat}",
            configuration_url="https://abonne-eau.grandparissud.fr",
        )

    @property
    def native_value(self) -> Any:
        if not self.coordinator.data:
            return None
        return self.entity_description.valeur(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.key != "index" or not self.coordinator.data:
            return None
        return {
            "contrat": self.coordinator.contrat,
            "statistique_externe": self.coordinator.statistic_id,
            "nombre_de_releves": self.coordinator.data.get("nb_releves"),
        }
