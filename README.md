# Eau Grand Paris Sud — intégration Home Assistant

Intégration non officielle pour le portail abonné **[Eau de Grand Paris Sud](https://abonne-eau.grandparissud.fr)**
(régie de l'agglomération Grand Paris Sud Seine-Essonne-Sénart, 91/77).

Elle récupère les relevés du compteur télérelevé — un index par nuit — et les
expose en capteurs, plus une statistique historique branchable sur le tableau
de bord **Énergie**.

> Le portail tourne sur la suite **SOMEI Wat.erp « Agence en ligne »**, utilisée
> par de nombreuses régies d'eau françaises. Le code est donc adaptable à une
> autre régie en changeant trois constantes — voir [Adapter à une autre régie](#adapter-à-une-autre-régie).

## Ce que ça installe

Un appareil par contrat, avec quatre capteurs :

| Capteur | Unité | Détail |
|---|---|---|
| Index compteur d'eau | m³ | `device_class: water` + `total_increasing` → utilisable comme source d'eau du tableau de bord Énergie |
| Consommation d'eau du jour | L | dernier relevé nocturne |
| Consommation d'eau moyenne 30 jours | L | moyenne glissante |
| Dernier relevé d'eau | horodatage | quand le portail a relevé |

Plus une **statistique externe** `eau_gps:consommation_<contrat>` qui porte tout
l'historique disponible sur le portail (plusieurs centaines de relevés), à
afficher en barres avec une carte `statistics-graph` (`stat_types: [change]`).

## Installation

### HACS (dépôt personnalisé)

1. HACS → menu ⋮ → **Dépôts personnalisés**
2. Dépôt : `https://github.com/momo3362/ha-eau-grand-paris-sud`, catégorie **Intégration**
3. Installer **Eau Grand Paris Sud**, puis **redémarrer Home Assistant**

### Manuelle

Copier `custom_components/eau_gps` dans le dossier `custom_components` de votre
configuration, puis redémarrer Home Assistant.

### Configuration

**Paramètres → Appareils et services → Ajouter une intégration → Eau Grand Paris Sud**,
puis l'identifiant (adresse e-mail) et le mot de passe de l'espace abonné. Le
numéro de contrat est détecté tout seul.

## Ce qu'il faut savoir avant d'ouvrir un ticket

Ces quatre comportements viennent du portail, pas de l'intégration — ils ont
coûté une journée de diagnostic, autant qu'ils servent :

- **Le mot de passe expire.** Le portail répond alors `HTTP 412 — « Pour des
  raisons de sécurité, votre mot de passe doit être changé »` et **refuse toute
  connexion par l'API**, alors qu'une session déjà ouverte dans un navigateur
  continue de fonctionner. C'est trompeur : le site marche, l'intégration non.
  Renouvelez le mot de passe sur le portail, Home Assistant vous le redemandera
  (étape de réauthentification, l'historique est conservé).
- **Le compte se bloque au bout de 5 échecs.** L'intégration s'arrête net dès
  que le portail annonce « il vous reste N essais » et ne réessaie jamais.
- **« Session Inconnue » (HTTP 400) est aléatoire**, environ une fois sur trois :
  c'est le répartiteur de charge F5 du portail, pas vos identifiants, et cela
  n'entame pas le compteur d'essais. L'intégration repart d'une session neuve et
  retente jusqu'à six fois.
- **Le portail répond 200 avec une page HTML** quand une route n'existe pas. Le
  code de retour seul ne veut rien dire, le contenu est vérifié à chaque appel.

Le relevé n'arrive qu'une fois par nuit (vers 00h46) : l'intégration interroge
le portail toutes les 6 heures, inutile de descendre plus bas.

## Adapter à une autre régie

Si votre régie utilise aussi une « Agence en ligne » SOMEI (l'URL du portail
sert une application Angular et les appels partent vers `/webapi/...`), trois
constantes de `custom_components/eau_gps/const.py` suffisent :

```python
BASE_URL = "https://abonne-eau.<votre-regie>.fr"
WS_APPLICATION_LOGIN = "AEL-TOKEN-XXX-PRD"
WS_APPLICATION_PWD = "..."
```

Les deux identifiants d'application ne sont pas des secrets : ils sont servis en
clair dans le bundle JavaScript du portail (constante `configuration.AEL_WEBAPI`)
et n'autorisent que l'appel à `/Acces/generateToken`. Ouvrez les outils de
développement du navigateur, onglet Réseau, et lisez-les dans la requête.

Attention, les routes de consommation diffèrent d'une instance à l'autre : ici
elles exigent le numéro de contrat dans le chemin
(`Consommation/isContratTelereleve/<contrat>`). Une pull request ajoutant votre
régie est la bienvenue.

## Comment l'authentification fonctionne

1. `GET /` — prend le cookie d'affinité du répartiteur
2. `POST /webapi/Acces/generateToken` — échange les identifiants d'application contre un jeton à usage unique
3. `POST /webapi/Utilisateur/authentification` — échange identifiant + mot de passe contre un `tokenAuthentique`
4. **Le jeton est posé en COOKIE `aelToken`** — et non en en-tête, c'est le point qui bloque toute réécriture naïve : l'en-tête seul renvoie 401
5. `GET /webapi/Abonnement/getContratParDefaut/` — récupère le contrat

Le cookie `AEL_CONTEXT` posé ensuite est décoratif : les routes de données
répondent sans lui. Le jeton de session vit **2 heures**.

## Avertissement

Projet personnel, sans aucun lien avec Eau de Grand Paris Sud ni SOMEI. Il
reproduit les appels que fait le portail dans votre navigateur, avec votre
compte. Les identifiants d'application embarqués peuvent changer sans préavis :
l'authentification cesserait alors de fonctionner, ouvrez un ticket.

Licence MIT.

---

## English summary

Unofficial Home Assistant integration for the **Eau de Grand Paris Sud** water
utility customer portal (France, Essonne/Seine-et-Marne). Exposes the nightly
smart-meter reading as four sensors plus a backfilled external statistic that
plugs into the Energy dashboard as a water source.

The portal runs on the **SOMEI Wat.erp "Agence en ligne"** stack shared by many
French water utilities, so it can be pointed at another one by changing three
constants in `const.py` (see above). Install via HACS custom repository, then
add the integration with your portal email and password — the contract number is
discovered automatically.

Known portal quirks: passwords expire and the API then returns **HTTP 412 while
the website still works**; the account locks after 5 failed attempts; the F5 load
balancer randomly answers "Session Inconnue" (HTTP 400, harmless, retried); and
unknown routes return **HTML with a 200 status**.
