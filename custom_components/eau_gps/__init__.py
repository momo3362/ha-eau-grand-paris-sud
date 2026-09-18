"""Intégration Eau Grand Paris Sud (portail SOMEI « Agence en ligne »)."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from aiohttp import CookieJar
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import EauGpsApi
from .const import CONF_CONTRAT, DOMAIN
from .coordinator import EauGpsCoordinator
from .exceptions import EauGpsAuthError, EauGpsError

PLATFORMS: list[Platform] = [Platform.SENSOR]

# Alias volontairement simple : compatible avec toutes les versions de Python
# embarquées par Home Assistant, sans la syntaxe `type X = ...` (3.12+).
EauGpsConfigEntry = ConfigEntry


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Monte une entrée de configuration."""
    # Session dédiée : le portail s'appuie sur ses propres cookies de session.
    session = async_create_clientsession(hass, cookie_jar=CookieJar())
    api = EauGpsApi(
        session,
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
    )

    try:
        await api.authenticate()
    except EauGpsAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except EauGpsError as err:
        raise ConfigEntryNotReady(str(err)) from err

    coordinator = EauGpsCoordinator(hass, entry, api, entry.data[CONF_CONTRAT])
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Démonte une entrée de configuration."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
