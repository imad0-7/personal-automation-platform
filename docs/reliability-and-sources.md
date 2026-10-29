# Fiabilité et extension des sources — 29 octobre 2026

## Diagnostic réel

Le scan cloud 40866623413 a lu 271 annonces, découvert 0 nouvel ID et effectué 44
requêtes. Deux fiches (1272417 et 1271745) ont échoué par ReadTimeout. Le catalogue
était lisible ; « Contrôle partiel » ne signifiait pas que la détection était arrêtée.
Le scan 40822929612 avait échoué au chargement du catalogue (ReadTimeout).
Les cinq premiers produits du catalogue officiel ont été retrouvés dans le dashboard.

## Politique appliquée

- Nouveautés : deux premières pages, avec rattrapage si aucune frontière connue.
- Prix et réservation : toutes les 120 minutes, sur les 100 premières annonces.
  Hors de cette fenêtre, le dernier état de réservation connu est conservé.
  Une annonce nouvelle reçoit immédiatement son premier état observé.
- Recensement complet : une fois par jour pour conserver les statistiques de disparitions.
  Les pages non visitées lors d'un scan partiel ne deviennent jamais « disparues ».
- Maximum cinq fiches détaillées par passage, délai de 12 secondes par fiche.
- Erreur de fiche : reprise après 30 min, 1 h, 2 h… au maximum 24 h ; données
  conservées. Les analyses ambiguës réussies sont relues au plus une fois par semaine.
- Pas de demandes automatiques de correction sur Telegram. L'onglet À clarifier reste.
- Une erreur de commandes Telegram reste dans les journaux, sans fausse alerte catalogue.
- Alerte catalogue après deux scans consécutifs en échec ; une notification par
  incident et une notification de reprise si l'incident avait été annoncé.
- Alerte détails : au moins trois fiches en échec répété depuis plus d'une heure,
  au maximum un message par 24 heures. Les erreurs isolées restent dans les journaux.
- HTTP : erreurs d'accès/permanentes sans répétition ; reprise bornée pour erreurs
  réseau/serveur. Aucun contournement d'un blocage d'accès.

Les intervalles et limites sont dans `src/automations/cashconverters/config.yaml`.
GitHub Actions vise un passage toutes les 15 minutes ; ses délais de planification
peuvent allonger cet intervalle. Le calendrier de réservation est temporel (120 min),
pas un compteur d'exécutions, pour résister aux scans retardés ou manuels.

## 2ememain : inspection effectuée, collecte récurrente non activée

La page publique catégorie Ordinateurs de bureau est accessible sans compte et
contient des annonces en HTML. La présence de publicités en tête impose de traiter
séparément position, date affichée et première détection ; une remontée ne doit pas
être prise pour un nouvel ID. Les annonces françaises et néerlandaises doivent être
dédupliquées par identifiant, pas par URL ou titre.

Cependant, `https://www.2ememain.be/robots.txt` exclut explicitement les endpoints
`/lrp/api/search*` et `/lp/api/listings*`. Les conditions générales (§7.1 et §7.3)
encadrent copie, republication et extractions répétées, avec une exception limitée
mentionnant l'usage personnel/RSS. Cette exception ne suffit pas à conclure que
notre surveillance destinée à l'achat-revente et sa republication publique sont autorisées.

Sources officielles :
- https://www.2ememain.be/robots.txt
- https://aide.2ememain.be/s/article/i-conditions-generales?language=fr
- https://www.2ememain.be/l/informatique-logiciels/ordinateurs-de-bureau/

Aucun endpoint exclu n'a été appelé. Aucun flux RSS exploitable documenté n'a été
identifié pendant l'inspection. Ne pas confondre les pages de recherche du mot « RSS »
avec un véritable flux.

Voie à finaliser avant activation : flux officiellement proposé pour cet usage,
accès partenaire/autorisation, ou ingestion privée des alertes natives reçues par
l'utilisateur (avec connexion au compte et consentement, sans crawler la recherche).
Ne pas publier automatiquement les données 2ememain sur le dashboard public.

## Roadmap conservée, hors de ce changement

Watchlist par utilisateur, archivage après une période sans interaction (proposition
14 jours), conservation de l'historique, administration authentifiée et hébergement
homelab, fréquence adaptative et analyse IA via la gateway indépendante des fournisseurs.
