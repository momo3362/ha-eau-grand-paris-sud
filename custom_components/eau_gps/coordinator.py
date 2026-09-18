"""Coordinateur de mise à jour + import des statistiques historiques."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import async_add_external_statistics
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import EauGpsApi
from .const import DOMAIN, STAT_ID_TEMPLATE, UPDATE_INTERVAL
from .exceptions import EauGpsError

_LOGGER = logging.getLogger(__name__)


class EauGpsCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Récupère les relevés et alimente les statistiques long terme."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: EauGpsApi,
        contrat: str,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {contrat}",
            update_interval=UPDATE_INTERVAL,
            config_entry=entry,
        )
        self.api = api
        self.contrat = contrat
        self.statistic_id = STAT_ID_TEMPLATE.format(contrat=contrat)

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            releves = await self.api.releves_journaliers(self.contrat)
        except EauGpsError as err:
            raise UpdateFailed(str(err)) from err

        if not releves:
            raise UpdateFailed("Aucun relevé retourné par le portail")

        await self._importer_statistiques(releves)

        dernier = releves[-1]
        volumes = [r["volumeConsoEnLitres"] for r in releves]
        trente = volumes[-30:]

        return {
            "dernier": dernier,
            "index_m3": dernier["valeurIndex"] / 1000.0,
            "conso_jour_l": dernier["volumeConsoEnLitres"],
            "date_releve": dt_util.parse_datetime(dernier["dateReleve"]),
            "moyenne_30j_l": round(sum(trente) / len(trente)) if trente else None,
            "nb_releves": len(releves),
        }

    async def _importer_statistiques(self, releves: list[dict[str, Any]]) -> None:
        """Publie l'historique journalier comme statistique externe.

        `valeurIndex` est l'index du compteur en litres : il sert directement de
        somme cumulée, ce qui évite tout recalcul et garde l'alignement exact
        avec ce que facture la régie.
        """
        points: list[StatisticData] = []
        for releve in releves:
            horodatage = dt_util.parse_datetime(releve["dateReleve"])
            if horodatage is None:
                continue
            # Les statistiques HA se calent sur une heure pleine. Le relevé
            # tombe vers 00h46 : on le rattache au jour qu'affiche le portail.
            debut = dt_util.as_local(horodatage).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            points.append(
                StatisticData(
                    start=debut,
                    state=releve["volumeConsoEnLitres"] / 1000.0,
                    sum=releve["valeurIndex"] / 1000.0,
                )
            )

        if not points:
            return

        metadata = StatisticMetaData(
            has_mean=False,
            has_sum=True,
            name=f"Eau Grand Paris Sud {self.contrat}",
            source=DOMAIN,
            statistic_id=self.statistic_id,
            unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        )
        async_add_external_statistics(self.hass, metadata, points)
        _LOGGER.debug(
            "%s : %d points de statistique publiés", self.statistic_id, len(points)
        )
