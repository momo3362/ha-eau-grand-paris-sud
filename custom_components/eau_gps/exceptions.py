"""Exceptions de l'intégration Eau Grand Paris Sud."""

from __future__ import annotations

from homeassistant.exceptions import HomeAssistantError


class EauGpsError(HomeAssistantError):
    """Erreur générique de communication avec le portail."""


class EauGpsAuthError(EauGpsError):
    """Identifiants refusés par le portail."""
