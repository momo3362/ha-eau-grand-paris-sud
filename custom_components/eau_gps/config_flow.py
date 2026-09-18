"""Assistant de configuration de l'intégration Eau Grand Paris Sud."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from aiohttp import CookieJar
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import EauGpsApi
from .const import CONF_CONTRAT, DOMAIN
from .exceptions import EauGpsAuthError, EauGpsError

_LOGGER = logging.getLogger(__name__)

SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class EauGpsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Demande les identifiants du portail et détecte le contrat."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        # Le portail renvoie ses propres messages (compte inconnu, mot de passe
        # a renouveler...). On les remonte tels quels : un « identifiant
        # incorrect » generique masquait la vraie cause.
        placeholders: dict[str, str] = {"message": ""}

        if user_input is not None:
            session = async_create_clientsession(self.hass, cookie_jar=CookieJar())
            api = EauGpsApi(
                session, user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
            )
            try:
                contrat = await api.authenticate()
            except EauGpsAuthError as err:
                _LOGGER.error("Authentification refusee par le portail : %s", err)
                errors["base"] = "invalid_auth"
                placeholders["message"] = f"↯ Réponse du portail : {err}"
            except EauGpsError as err:
                _LOGGER.error("Connexion au portail impossible : %s", err)
                errors["base"] = "cannot_connect"
                placeholders["message"] = f"↯ Réponse du portail : {err}"
            else:
                numero = str(contrat["numeroContrat"])
                await self.async_set_unique_id(numero)
                self._abort_if_unique_id_configured()

                titulaire = contrat.get("nomClientTitulaire") or numero
                return self.async_create_entry(
                    title=f"Eau — {titulaire}",
                    data={
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_CONTRAT: numero,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=SCHEMA,
            errors=errors,
            description_placeholders=placeholders,
        )

    # Le portail impose periodiquement le renouvellement du mot de passe
    # (HTTP 412) : sans cette etape, l'utilisateur devrait supprimer puis
    # recreer l'integration et perdrait son historique.
    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        if entry is None:
            return self.async_abort(reason="reauth_failed")

        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {
            "identifiant": entry.data[CONF_USERNAME],
            "message": "",
        }

        if user_input is not None:
            session = async_create_clientsession(self.hass, cookie_jar=CookieJar())
            api = EauGpsApi(
                session, entry.data[CONF_USERNAME], user_input[CONF_PASSWORD]
            )
            try:
                await api.authenticate()
            except EauGpsAuthError as err:
                _LOGGER.error("Reauthentification refusee : %s", err)
                errors["base"] = "invalid_auth"
                placeholders["message"] = f"↯ Réponse du portail : {err}"
            except EauGpsError as err:
                _LOGGER.error("Portail injoignable : %s", err)
                errors["base"] = "cannot_connect"
                placeholders["message"] = f"↯ Réponse du portail : {err}"
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data={**entry.data, CONF_PASSWORD: user_input[CONF_PASSWORD]},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
            description_placeholders=placeholders,
        )
