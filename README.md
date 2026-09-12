# Personal Automation Platform

Une base Python simple, modulaire et portable pour toutes les automatisations personnelles.
Cash Converters Belgique est le premier module, pas le projet entier.

## Ce que fait la V1

- surveille les PC fixes ainsi que des recherches ciblées Ryzen/RTX/Radeon/Gaming ;
- utilise uniquement HTTP + HTML (aucun navigateur et aucun LLM) ;
- reconnaît les produits par l'ID stable Cash Converters ;
- initialise silencieusement l'état au premier lancement ;
- enrichit seulement les nouvelles fiches pour limiter les requêtes ;
- calcule un score déterministe configurable ;
- envoie les résultats pertinents via une interface commune (console ou Telegram) ;
- conserve les exécutions, produits et notifications dans SQLite ;
- refuse un résultat vide ou une chute anormale au lieu d'effacer l'état connu.

## Architecture

```text
src/
├── automation_platform/
│   ├── core/                 # configuration, HTTP, logs, DB, scheduler
│   │   ├── ai_gateway/       # interface stable, désactivée en V1
│   │   ├── database/         # contrat + adaptateur SQLite
│   │   └── notifications/    # contrat + sortie console
│   └── integrations/         # Telegram, puis Discord/Google/etc.
└── automations/
    └── cashconverters/       # scraping, parsing, scoring et commande
```

La logique Cash Converters ne dépend ni de Telegram, ni de GitHub Actions, ni d'un fournisseur
d'IA. Les services cloud ne font que lancer la même commande locale.

## Installation locale

Prérequis : Python 3.11 ou 3.12.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows PowerShell : .venv\Scripts\Activate.ps1
pip install -e '.[dev]'
cp .env.example .env
python -m automations.cashconverters.run
```

Au premier succès, les annonces présentes deviennent la référence et aucune notification n'est
envoyée. Les exécutions suivantes signalent uniquement les nouveaux IDs.

## Configuration

Les sources, mots-clés, pondérations, seuils, magasins et prix maximum sont dans
`src/automations/cashconverters/config.yaml`.

Variables d'environnement :

| Variable | Défaut | Rôle |
| --- | --- | --- |
| `AUTOMATION_DB_URL` | `sqlite:///storage/automation.db` | stockage V1 |
| `AUTOMATION_LOG_LEVEL` | `INFO` | niveau des logs JSON |
| `NOTIFICATION_BACKEND` | `console` | `console` ou `telegram` |
| `TELEGRAM_BOT_TOKEN` | vide | secret fourni par BotFather |
| `TELEGRAM_CHAT_ID` | vide | conversation destinataire |

Ne jamais remplir `.env.example`. Créer `.env` localement ; il est ignoré par Git.

## Telegram

1. Dans Telegram, parler à `@BotFather`, créer un bot et conserver le token.
2. Envoyer un message au nouveau bot.
3. Récupérer le `chat_id` via `https://api.telegram.org/bot<TOKEN>/getUpdates`.
4. Placer les deux valeurs dans `.env` localement ou dans les secrets GitHub.
5. Définir `NOTIFICATION_BACKEND=telegram`.

## Docker et homelab

Un scan unique :

```bash
docker compose run --rm cashconverters-once
```

Surveillance continue selon `SCAN_INTERVAL_MINUTES` :

```bash
docker compose up -d cashconverters
```

Le volume `./storage:/app/storage` garde SQLite. Sur Proxmox ou un mini-PC, il suffit de déplacer
le dépôt et ce volume. Aucun changement de logique n'est requis.

## Déploiement cloud gratuit

Le workflow `.github/workflows/cashconverters.yml` exécute la commande toutes les 15 minutes et
peut aussi être lancé manuellement. SQLite est restauré/sauvegardé dans un cache Actions dédié ;
un verrou empêche deux scans simultanés.

Pour un fonctionnement 15 minutes sans facture, utiliser un dépôt **public** avec un runner
GitHub standard : GitHub indique que ces exécutions sont gratuites. Dans un dépôt privé GitHub
Free, le quota est de 2 000 minutes/mois ; réduire la fréquence à 30–45 minutes ou accepter que
le workflow s'arrête lorsque le quota est atteint, sans moyen de paiement configuré.

Secrets du dépôt (`Settings > Secrets and variables > Actions`) :

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

La couche cloud est remplaçable : cron, systemd, Kubernetes CronJob ou un scheduler cloud peut
lancer `python -m automations.cashconverters.run`.

## Tests

```bash
pytest -m 'not live'
pytest -m live tests/test_live_cashconverters.py
ruff check .
python scripts/check_secrets.py
```

Les tests couvrent le parsing, le stockage, le bootstrap silencieux, une nouvelle annonce,
l'absence de doublon, la panne réseau, la page vide, le changement de structure et la chute
anormale du nombre de produits.

## Ajouter une automatisation

1. Créer `src/automations/<nom>/` avec `config.py`, la logique et `run.py`.
2. Réutiliser `HttpClient`, `ListingRepository`, `Notifier` et les logs du cœur.
3. Ajouter les seules tables réellement nécessaires via l'adaptateur de données.
4. Exposer une commande `python -m automations.<nom>.run`.
5. Ajouter ensuite un lanceur cron/cloud, sans logique métier dans ce lanceur.

## IA future

`core/ai_gateway` définit déjà `AIRequest`, `AIResult` et `AIGateway`. Aucun module ne doit appeler
OpenAI, Gemini, Claude ou un modèle local directement. Un futur routeur pourra implémenter ce
contrat et appliquer budgets, modèles autorisés, coût, tokens, fallbacks et arrêt d'urgence.
LiteLLM ou LangGraph ne sont pas installés tant qu'ils n'apportent aucune valeur concrète.

## PostgreSQL plus tard

Le code métier dépend de `ListingRepository`, pas de `sqlite3`. La migration consistera à ajouter
un adaptateur PostgreSQL et à changer `AUTOMATION_DB_URL`, sans réécrire les automatisations.
