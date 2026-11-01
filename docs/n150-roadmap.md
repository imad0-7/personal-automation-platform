# Feuille de route — hébergement N150 et accès partagés

Mise à jour : 1er novembre 2026.

## Contexte confirmé

- Machine disponible : mini-PC Firebat (modèle exact non précisé), Intel N150 avec 16 Go de RAM, actuellement sous Windows.
- L'utilisateur accepte d'installer Linux si cela apporte un avantage.
- Objectif : héberger le watcher Cash Converters en continu, avec une cadence locale régulière.
- Conserver les suivis et l'historique lors de la migration de la base SQLite.
- Basculer les scans et le polling Telegram vers un seul hébergement actif après validation locale.
- GitHub reste le dépôt de code et l'environnement de tests.

## Surveillance de pages à la manière de Visualping

- Retenir changedetection.io comme base à évaluer et installer, plutôt que développer d'emblée un moteur complet.
- Prévoir Docker et un navigateur pour les pages qui nécessitent JavaScript.
- Garder le watcher spécialisé pour la découverte des PC/GPU et ses règles métier.
- Commencer avec les interfaces existantes, puis intégrer les services à un tableau de bord commun.
- Dimensionner la concurrence des navigateurs après essais sur les sites réellement suivis.

## Tableau de bord commun envisagé

- Application web adaptée au PC et au téléphone.
- D'abord Cash Converters et changedetection.io, puis d'autres services du N150.
- État des services, dernier/prochain scan, journaux, erreurs et historique des alertes.
- Gestion des suivis, prix, règles, fréquences et actions de lancement/pause.
- Séparer le traitement réactif de Telegram de la fréquence des recherches.
- Ajouter ultérieurement une connexion ChatGPT pour piloter les réglages et les suivis.
- Prévoir distinctement l'accès de développement pour modifier, tester et déployer le code.
- La dictée de messages est le premier usage vocal envisagé ; ne pas présumer que le mode vocal continu dispose des mêmes outils.
- Le choix Windows/Linux reste à valider avant installation : Linux est envisagé pour le serveur dédié ; l'accès via l'application ChatGPT Windows dépend de la conservation d'un hôte Windows compatible.

## Accès partagé : piste discutée, non implémentée

- L'utilisateur souhaite pouvoir donner accès au watcher à d'autres personnes avec des comptes.
- Sa préférence exprimée est une connexion Google ; les modalités d'inscription restent à décider.
- Proposition initiale : Google Sign-In et accès sur invitation/approbation, sans mots de passe locaux.
- Créer un compte applicatif interne lié à l'identifiant stable du fournisseur après validation serveur.
- Distinguer l'identité Google des autorisations dans le watcher.
- Prévoir un propriétaire/administrateur et des utilisateurs qui ne gèrent que leurs propres suivis.
- Isoler suivis, règles, notifications et association Telegram pour chaque utilisateur.
- Les utilisateurs du watcher ne reçoivent pas un accès d'administration général au N150.
- Mutualiser les collectes et distribuer les événements aux abonnés selon leurs préférences.
- Prévoir une association Telegram propre à chaque compte avec un code à usage unique et limité dans le temps.
- Exposer le futur tableau de bord privé par un accès HTTPS authentifié ; l'accès extérieur reste à configurer.
- Ne pas assimiler le tableau de bord statique GitHub Pages à un portail privé avec contrôle serveur.
- Le bot actuel est limité à un destinataire autorisé : le multi-utilisateur exige une évolution réelle du backend et du routage des notifications.

## Ordre proposé, sans déploiement déjà réalisé

1. Valider l'OS et préparer l'hébergement N150.
2. Migrer le watcher et vérifier cadence, reprise et sauvegardes.
3. Installer changedetection.io et tester quelques surveillances.
4. Construire le portail commun et l'API de gestion.
5. Ajouter les comptes, invitations, connexion Google et Telegram par utilisateur.
6. Ajouter le pilotage ChatGPT/MCP et étendre progressivement aux autres services.

Références :
- https://github.com/dgtlmoon/changedetection.io
- https://developers.google.com/identity/gsi/web/guides/verify-google-id-token
- https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html


## Services homelab à garder pour la suite

- Pistes appréciées par l'utilisateur : Dockge, Uptime Kuma, Homepage, n8n, Paperless-ngx, Jellyfin, Immich, AdGuard Home, Syncthing et Vaultwarden ; installation et priorités à confirmer.
- Machine secondaire disponible : Dell OptiPlex 760, processeur annoncé comme Intel Core Duo (référence exacte à vérifier), 4 Go de RAM, SSD 128 Go. Rôles envisagés : tests, sauvegardes et surveillance légère ; compatibilité et consommation à vérifier avant usage permanent.
- Jellyfin et l'écosystème *arr sont à étudier : Sonarr pour les séries, Radarr pour les films, Prowlarr pour les indexeurs, un client de téléchargement comme qBittorrent, Bazarr pour les sous-titres.
- Comprendre le fonctionnement et les sources autorisées avant toute installation de cette chaîne. Aucun téléchargement ni configuration de sources n'a été demandé ou effectué.
- Prévoir les besoins de stockage multimédia et vérifier les capacités de lecture/transcodage du Firebat selon les usages.


## Diagnostic IA : piste retenue

- L'utilisateur souhaite pouvoir demander une aide IA depuis le N150 avec son abonnement ChatGPT Plus, sans clé API ni facturation API séparée.
- Voie retenue à étudier : Codex CLI sur la machine, connecté avec le compte ChatGPT ; les requêtes consomment les limites de l'abonnement.
- Lorsqu'un service rencontre un problème, préparer un diagnostic avec les erreurs et le contexte utiles, demander l'autorisation via Telegram ou le dashboard, puis lancer Codex.
- Distinguer l'autorisation de diagnostic de l'application d'une correction ; prévoir validation, tests et retour arrière.
- Prévoir un nombre limité de tentatives pour éviter les boucles et maîtriser l'usage.
- Open WebUI Computer est une interface complémentaire possible : sa documentation décrit des backends d'agents utilisant la connexion CLI existante. Compatibilité/version à valider lors de l'installation.
- Aucune connexion au compte ni installation sur le N150 n'a encore été réalisée.

## Améliorations proposées, à sélectionner

- Sauvegardes automatiques avec essais de restauration, copie secondaire sur le Dell et copie indépendante pour les données importantes.
- Contrôle du dernier scan effectivement terminé, du prochain scan attendu et des retards, en complément de la disponibilité HTTP.
- Environnement de test et déploiements réversibles avant modification des services utilisés par les deux comptes.
- Envoi d'un lien au bot Telegram puis choix du suivi au moyen de boutons.
- Centre d'activité commun : changements, notifications et erreurs ; préférences d'urgence et de regroupement par utilisateur.
- File de tâches avec reprise après redémarrage et tentatives bornées.
