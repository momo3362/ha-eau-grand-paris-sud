"""Client du portail SOMEI « Agence en ligne » — Eau Grand Paris Sud.

Le portail répond en HTTP 200 avec une page HTML 404 quand une route est
inconnue ou mal formée : on ne peut donc PAS se fier au code de retour seul.
Chaque réponse est vérifiée sur son contenu.

Particularité de l'instance GPS par rapport aux portails du groupe des Eaux
de Marseille : les routes de consommation exigent le numéro de contrat dans
le chemin (`.../isContratTelereleve/1234567`).
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any
from urllib.parse import quote

import aiohttp
from yarl import URL

from .const import (
    API_BASE,
    BASE_URL,
    REQUEST_TIMEOUT,
    USER_AGENT,
    WS_APPLICATION_LOGIN,
    WS_APPLICATION_PWD,
)
from .exceptions import EauGpsAuthError, EauGpsError

_LOGGER = logging.getLogger(__name__)


def _conversation_id() -> str:
    return f"JS-WEB-Netscape-{uuid.uuid4()}"


class EauGpsApi:
    """Session authentifiée contre le portail."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        identifiant: str,
        mot_de_passe: str,
    ) -> None:
        self._session = session
        self._identifiant = identifiant
        self._mot_de_passe = mot_de_passe
        self._ael_token: str | None = None
        self._contrat_defaut: dict[str, Any] | None = None

    # ------------------------------------------------------------------
    # Bas niveau
    # ------------------------------------------------------------------

    @property
    def _headers(self) -> dict[str, str]:
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": BASE_URL,
            "Referer": f"{BASE_URL}/",
            "ConversationId": _conversation_id(),
        }
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Any:
        url = f"{API_BASE}/{path.lstrip('/')}"
        headers = self._headers
        if extra_headers:
            headers.update(extra_headers)

        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        try:
            async with self._session.request(
                method, url, json=payload, headers=headers, timeout=timeout
            ) as response:
                text = await response.text()
                status = response.status
        except (aiohttp.ClientError, TimeoutError) as err:
            raise EauGpsError(f"Portail injoignable ({url}) : {err}") from err

        # Le portail décrit ses refus dans un corps JSON {severity, message}.
        message = ""
        try:
            corps = json.loads(text)
            if isinstance(corps, dict):
                message = str(corps.get("message") or "")
        except ValueError:
            pass

        # 412 est la réponse réelle d'un refus de connexion sur cette instance
        # (mot de passe à renouveler, compte inconnu), pas seulement 401.
        if status in (401, 403, 412):
            bas = message.lower()
            # Le portail bloque le compte au bout de 5 échecs : on remonte son
            # décompte tel quel et on arrête net, sans jamais réessayer.
            if "essais" in bas or "bloqu" in bas:
                raise EauGpsAuthError(
                    f"{message} STOP : ne pas réessayer, le compte serait "
                    "verrouillé. Vérifiez le mot de passe sur le portail."
                )
            # Mot de passe expiré : l'API refuse tout tant qu'il n'est pas
            # renouvelé, même si une session ouverte dans un navigateur
            # continue de fonctionner.
            if "mot de passe" in bas and ("chang" in bas or "renouvel" in bas):
                raise EauGpsAuthError(
                    f"{message} À faire sur {BASE_URL} : l'API refuse toute "
                    "connexion tant que le mot de passe n'est pas renouvelé."
                )
            raise EauGpsAuthError(
                f"HTTP {status} sur {path} - " + (message or f"corps sans message ({len(text)} octets)")
            )
        if status >= 400:
            raise EauGpsError(
                f"HTTP {status} sur {path} - " + (message or f"corps sans message ({len(text)} octets)")
            )

        stripped = text.lstrip()
        # Le piège maison : une 404 déguisée en 200 qui renvoie du HTML.
        if stripped.startswith("<"):
            raise EauGpsError(
                f"Route inconnue ou mal formée : {path} "
                "(le portail a renvoyé une page HTML avec un statut 200)"
            )
        if not stripped:
            return None
        try:
            return json.loads(text)
        except ValueError as err:
            raise EauGpsError(f"Réponse illisible sur {path} : {err}") from err

    # ------------------------------------------------------------------
    # Authentification — 5 étapes
    # ------------------------------------------------------------------

    async def authenticate(self) -> dict[str, Any]:
        """Ouvre une session et retourne le contrat par défaut."""
        self._ael_token = None

        # 1 à 3. Accueil, jeton applicatif, puis authentification.
        #
        # Le portail est derrière un répartiteur F5 (cookie d'affinité
        # « BIGipServerfrt-ael-gps_pool ») et le jeton reste sur le nœud qui
        # l'a émis : quand la requête de connexion tombe ailleurs, le portail
        # répond « Session Inconnue » en HTTP 400. C'est aléatoire — mesuré à
        # environ une réussite sur trois — et sans rapport avec les
        # identifiants : cette réponse n'entame PAS le compteur d'essais du
        # compte.
        #
        # La reprise repart donc d'une session entièrement neuve (cookies
        # vidés, accueil revisité pour obtenir une affinité fraîche), espacée
        # de quelques secondes pour retomber sur un autre nœud. Un jeton est à
        # usage unique : chaque tentative en redemande un.
        data = None
        derniere_erreur: EauGpsError | None = None
        for tentative in range(1, 7):
            if tentative > 1:
                await asyncio.sleep(4)
            self._session.cookie_jar.clear()

            try:
                async with self._session.get(
                    f"{BASE_URL}/",
                    headers={"User-Agent": USER_AGENT},
                    timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                ) as response:
                    await response.read()
            except (aiohttp.ClientError, TimeoutError) as err:
                raise EauGpsError(f"Portail injoignable : {err}") from err

            cid = _conversation_id()
            jeton = await self._request(
                "POST",
                "Acces/generateToken",
                payload={
                    "ConversationId": cid,
                    "ClientId": WS_APPLICATION_LOGIN,
                    "AccessKey": WS_APPLICATION_PWD,
                },
                extra_headers={
                    "ConversationId": _conversation_id(),
                    "Token": WS_APPLICATION_PWD,
                },
            )
            if not isinstance(jeton, dict) or not jeton.get("token"):
                raise EauGpsError("generateToken n'a pas renvoyé de jeton")

            try:
                data = await self._request(
                    "POST",
                    "Utilisateur/authentification",
                    payload={
                        "identifiant": self._identifiant,
                        "motDePasse": self._mot_de_passe,
                    },
                    extra_headers={"Token": jeton["token"]},
                )
            except EauGpsError as err:
                if "Session Inconnue" not in str(err):
                    raise
                derniere_erreur = err
                _LOGGER.warning(
                    "Jeton rejeté par un autre nœud du portail, tentative %d/6",
                    tentative,
                )
                continue
            break

        if data is None:
            raise EauGpsError(
                "Le portail a renvoyé « Session Inconnue » six fois de suite "
                f"({derniere_erreur}). C'est son répartiteur de charge, pas vos "
                "identifiants, et cela n'entame pas le compteur d'essais du "
                "compte : relancez simplement l'ajout dans une minute."
            )
        if not isinstance(data, dict) or not data.get("tokenAuthentique"):
            raise EauGpsAuthError("Identifiant ou mot de passe incorrect")

        self._ael_token = data["tokenAuthentique"]

        # Le portail authentifie par le COOKIE aelToken, pas seulement par
        # l'en-tête du même nom : il doit être posé AVANT le premier appel
        # authentifié, sinon l'étape 4 repart en 401.
        self._session.cookie_jar.update_cookies(
            {"aelToken": self._ael_token}, response_url=URL(BASE_URL)
        )

        # 4. Contrat par défaut. Le portail est réparti sur plusieurs nœuds et
        # une session toute fraîche n'est pas toujours connue de celui qui
        # répond : on retente avant de conclure à un refus.
        contrat: Any = None
        for essai in range(1, 4):
            try:
                contrat = await self._request(
                    "GET", "Abonnement/getContratParDefaut/"
                )
                break
            except EauGpsAuthError as err:
                _LOGGER.warning(
                    "Contrat refusé (essai %d/3) : %s — champs renvoyés par "
                    "l'authentification : %s — cookies envoyés : %s",
                    essai,
                    err,
                    sorted(data),
                    sorted(
                        self._session.cookie_jar.filter_cookies(URL(BASE_URL))
                    ),
                )
                if essai == 3:
                    raise
                await asyncio.sleep(2)

        if not isinstance(contrat, dict) or not contrat.get("numeroContrat"):
            raise EauGpsError("Aucun contrat rattaché à ce compte")
        self._contrat_defaut = contrat

        # 5. Cookie de contexte attendu par le portail sur les appels suivants.
        self._session.cookie_jar.update_cookies(
            {
                "aelToken": self._ael_token,
                "AEL_CONTEXT": quote(
                    json.dumps({"type": "contrat", "object": contrat}),
                    safe="",
                ),
            },
            response_url=URL(BASE_URL),
        )
        return contrat

    async def _get_authenticated(self, path: str) -> Any:
        """GET authentifié, avec une seule ré-authentification si la session a expiré."""
        if not self._ael_token:
            await self.authenticate()
        try:
            return await self._request("GET", path)
        except EauGpsAuthError:
            await self.authenticate()
            return await self._request("GET", path)

    # ------------------------------------------------------------------
    # Données
    # ------------------------------------------------------------------

    async def contrat_par_defaut(self) -> dict[str, Any]:
        if self._contrat_defaut is None:
            await self.authenticate()
        assert self._contrat_defaut is not None
        return self._contrat_defaut

    async def est_telereleve(self, contrat: str) -> bool:
        return bool(await self._get_authenticated(f"Consommation/isContratTelereleve/{contrat}"))

    async def dernier_releve(self, contrat: str) -> dict[str, Any]:
        data = await self._get_authenticated(
            f"Consommation/getDerniereConsommationRelevee/{contrat}"
        )
        if not isinstance(data, dict):
            raise EauGpsError("Dernier relevé illisible")
        return data

    async def releves_journaliers(self, contrat: str) -> list[dict[str, Any]]:
        """Historique journalier, du plus ancien au plus récent."""
        data = await self._get_authenticated(
            f"Facturation/listeConsommationsFacturees/{contrat}"
        )
        if not isinstance(data, dict):
            raise EauGpsError("Historique illisible")
        releves = [
            r
            for r in data.get("resultats", [])
            if isinstance(r.get("valeurIndex"), (int, float))
            and isinstance(r.get("volumeConsoEnLitres"), (int, float))
            and r.get("dateReleve")
        ]
        releves.sort(key=lambda r: r["dateReleve"])
        return releves
