# Analyse du site Cash Converters Belgique — 12 septembre 2026

## Résultat

Le catalogue est un PrestaShop rendu côté serveur. Un client HTTP suffit ; Playwright n'est pas
nécessaire. Selon les en-têtes, une même URL peut renvoyer soit la page HTML complète, soit une
réponse JSON PrestaShop contenant le fragment HTML `rendered_products`; les deux sont supportés.

## Contrat observé

- Catégorie informatique : `/fr/134-informatique` (7 261 produits observés).
- Ordinateurs de bureau : `/fr/164-ordinateurs-de-bureau` (343 produits, 21/page).
- Pagination : paramètre `page=2`, lien HTML `rel="next"`.
- Tri récent accepté : `order=product.date_add.desc`.
- Recherche : `/fr/recherche?controller=search&s=<terme>&order=product.date_add.desc`.
- Carte produit : `article.product-miniature[data-id-product]`.
- Champs liste : titre, URL, prix, magasin, image, drapeaux dont `Nouveau`.
- Fiche produit : `#product-details[data-product]` contient du JSON encodé avec titre complet,
  prix, catégorie, référence, date d'ajout, caractéristiques, magasin et images.

## Stratégie retenue

Deux pages récentes de la catégorie PC fixe et de quatre recherches ciblées sont lues toutes les
15 minutes. Les doublons entre flux sont fusionnés par ID. Seules les nouvelles fiches sont
ouvertes pour obtenir les détails complets, avec une limite configurable.

Cette stratégie évite de relire les centaines de pages du catalogue à chaque scan. Le premier
scan constitue l'état initial silencieux. Une absence du conteneur/cartes attendus, moins de dix
produits uniques ou une chute sous 25 % du volume précédent devient une panne explicite et ne
modifie pas les annonces connues.

## Limites connues

- La date fournie par PrestaShop est interprétée dans le fuseau `Europe/Brussels`.
- Un changement de sélecteurs provoquera volontairement `PARSER_FAILURE`.
- Les recherches ciblées complètent la catégorie PC fixe mais ne prétendent pas indexer les
  7 000+ articles informatiques à chaque passage.
- Aucun CAPTCHA ou mécanisme anti-bot n'est contourné.
