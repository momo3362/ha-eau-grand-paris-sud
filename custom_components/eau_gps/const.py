"""Constantes de l'intégration Eau Grand Paris Sud."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "eau_gps"

# Portail SOMEI « Agence en ligne » de la régie Eau de Grand Paris Sud.
BASE_URL = "https://abonne-eau.grandparissud.fr"
API_BASE = f"{BASE_URL}/webapi"

# Identifiants d'application, publics : ils sont servis dans le bundle Angular
# du portail (constante `configuration.AEL_WEBAPI`). Ce ne sont pas des secrets
# utilisateur — ils autorisent seulement l'appel à /Acces/generateToken.
WS_APPLICATION_LOGIN = "AEL-TOKEN-GPS-PRD"
WS_APPLICATION_PWD = "REGPS-hc-GPS-MP-PRD"

CONF_CONTRAT = "contrat"

# Le compteur ne remonte qu'un index par nuit, vers 00h46. Interroger toutes
# les 6 h suffit largement et reste poli avec le portail.
UPDATE_INTERVAL = timedelta(hours=6)

REQUEST_TIMEOUT = 30

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

STAT_ID_TEMPLATE = DOMAIN + ":consommation_{contrat}"
