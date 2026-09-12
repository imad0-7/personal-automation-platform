# Personal Automation Platform

Une base Python simple, modulaire et portable pour toutes les automatisations personnelles.
Cash Converters Belgique est le premier module, pas le projet entier.

## Ce que fait la V2

- surveille tous les PC fixes, triés par ajout récent ;
- utilise uniquement HTTP + HTML (aucun navigateur et aucun LLM) ;
- reconnaît les produits par l'ID stable Cash Converters ;
- initialise silencieusement l'état au premier lancement ;
- enrichit progressivement les fiches utiles pour limiter les requêtes ;
- extrait CPU, plateforme, RAM, GPU et stockage sans LLM, avec niveaux de confiance ;
- applique des règles Offre explicites et configurables, sans score ;
- suit les prix des 100 PC récents toutes les deux heures ;
- suit l'état du bouton Réserver quand une fiche est contrôlée ;
- accepte des commandes Telegram et prépare des préférences par utilisateur ;
- génère une petite page de consultation statique ;
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
    └── cashconverters/       # scraping, extraction, règles et commande
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

Au premier succès V2, les 17 pages (343 PC lors de la dernière inspection) deviennent la référence
et aucune notification produit n'est envoyée. Les scans ordinaires lisent les deux pages récentes.

## Configuration

Le rythme et la source sont dans `config.yaml`. Le référentiel AM4/AM5 et les règles Offre sont
dans `hardware.yaml`. Les règles initiales sont : AM5 ≤ 1 200 €, AM4 ≤ 500 €, et AM4 avec RTX 5060
strictement sous 700 €. Les configurations plus chères ne sont pas déclarées Offre sans règle.

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

Commandes (traitées au prochain scan, donc sous environ 15 minutes) :

- `/mode tous`, `/mode offres`, `/mode resume`, `/mode pause` ;
- `/rapport on` ou `/rapport off` ;
- `/test`, `/status`, `/help` ;
- `/corriger ID ram_gb=32 ram_type=DDR5` corrige uniquement l'annonce indiquée.

Le mode initial est `resume` avec compte rendu à chaque scan. Les Offres sont immédiates et les
autres nouveaux PC sont regroupés. Les cas ambigus (maximum cinq) sont demandés une fois par jour
au premier passage après midi, heure de Bruxelles. Les commandes d'autres chats sont ignorées.

Une panne du site ou du parseur produit une alerte technique dédupliquée. La répétition est évitée
pendant la même panne, puis un message confirme le rétablissement.

Un test cloud manuel reste disponible dans Actions > `Telegram notification test`.

## Petite page

`python scripts/generate_dashboard.py` génère `public/index.html` avec les 100 PC récents, les
informations matérielles, les Offres et l'état de réservation connu. Aucune clé ni préférence
privée n'y apparaît. Le workflow manuel `Dashboard` peut la publier sur GitHub Pages. Pages doit
d'abord être activé avec la source **GitHub Actions** dans les paramètres du dépôt ; la fréquence
de deux heures sera activée après cette étape pour ne pas créer d'exécutions en échec.

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

Les tests couvrent aussi l'extraction matérielle, les règles AM4/AM5, le suivi de prix,
la réservation, les commandes, le dashboard et les alertes techniques.

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
