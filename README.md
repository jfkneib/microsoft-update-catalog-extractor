# Extraction Microsoft Update Catalog

Ce projet contient un script Python pour extraire les resultats du Microsoft Update Catalog et les exporter en CSV ou JSON.

## Utilitaires a installer

### Obligatoires

- python3
  Necessaire pour executer le script.

- lynx
  Prerequis indispensable. Le script s'execute uniquement en mode lynx.

### Optionnels mais utiles

- column
  Permet d'afficher proprement le CSV dans le terminal.

- sed
  Sert dans les exemples pour limiter le nombre de lignes affichees.

## Installation rapide

Sous Debian/Ubuntu:

```bash
sudo apt update
sudo apt install -y python3 lynx bsdextrautils sed
```

Remarque:

- bsdextrautils fournit la commande column sur de nombreuses distributions Debian/Ubuntu.
- Le script refuse l'execution si l'argument de recherche positionnel n'est pas fourni.
- Le script refuse l'execution si lynx n'est pas installe.

## Utilisation rapide

1. Donner la requete de recherche en premier argument positionnel.
2. Ajouter les filtres necessaires (produit, regex, date, UUID, limite).
3. Choisir un fichier de sortie avec --output.
4. Ajouter --no-links si vous voulez un traitement plus rapide.

## Cas concret demande

Objectif:

- Requete: Cumulative Update for Windows 11 Version 24H2 for x64-based Systems
- Produit contient: Windows 11
- Classification: Updates (majuscule/minuscule acceptees)
- Nombre maximum de resultats: 4

Commande:

```bash
python3 extraction.py "Cumulative Update for Windows 11 Version 24H2 for x64-based Systems" \
  --filter-product "Windows 11" \
  --classification-regex "^updates$" \
  --limit 4 \
  --output windows11_24h2_top4.csv \
  --no-links
```

## Exemples de commandes

Recherche avec filtre produit:

```bash
python3 extraction.py "Windows Security platform" \
  --filter-product "Windows Security platform" \
  --output search_filtered.csv \
  --no-links
```

Recherche avec regex generique sur un champ:

```bash
python3 extraction.py "Windows Security platform" \
  --filter-regex "Windows Security platform|Defender" \
  --filter-field produit \
  --output search_filtered_regex.csv \
  --no-links
```

Filtrer le titre avec une regex:

```bash
python3 extraction.py "Windows Security platform" \
  --title-regex "Security Intelligence|Platform" \
  --output title_filtered.csv \
  --no-links
```

Filtrer la classification avec une regex (insensible a la casse):

```bash
python3 extraction.py "Windows Security platform" \
  --classification-regex "definition updates|security updates" \
  --output class_filtered.csv \
  --no-links
```

Filtrer un UUID avec regex:

```bash
python3 extraction.py "Windows Security platform" \
  --uuid-regex "^[a-f0-9\-]{36}$" \
  --output uuid_filtered.csv \
  --no-links
```

Filtrer un UUID exact:

```bash
python3 extraction.py "Windows Security platform" \
  --filter-product "Windows Security platform" \
  --uuid "a32ca1d0-ddd4-486b-b708-d941db4f1081" \
  --output uuid_exact_found.csv \
  --no-links
```

Cas UUID exact sans resultat (comportement attendu: message d'erreur et code retour != 0):

```bash
python3 extraction.py "Windows Security platform" \
  --filter-product "Windows Security platform" \
  --uuid "00000000-0000-0000-0000-000000000000" \
  --output uuid_exact_not_found.csv \
  --no-links
```

Filtrer sur une plage de dates:

```bash
python3 extraction.py "Windows Security platform" \
  --fromdate 2026-01-01 \
  --todate 2026-12-31 \
  --output date_filtered.csv \
  --no-links
```

Limiter le nombre de resultats (top 5):

```bash
python3 extraction.py "Windows Security platform" \
  --filter-product "Windows Security platform" \
  --limit 5 \
  --output top5.csv \
  --no-links
```

Conserver uniquement le resultat le plus recent:

```bash
python3 extraction.py "Windows Security platform" \
  --filter-product "Windows Security platform" \
  --last \
  --output search_last.csv \
  --no-links
```

Exporter en JSON:

```bash
python3 extraction.py "Windows Security platform" \
  --filter-product "Windows Security platform" \
  --json \
  --output search_filtered.json \
  --no-links
```

Afficher les resultats dans le terminal:

```bash
python3 extraction.py "Windows Security platform" \
  --filter-product "Windows Security platform" \
  --last \
  --print-results \
  --output search_last.csv \
  --no-links
```

Afficher uniquement les donnees dans stdout:

```bash
python3 extraction.py "Windows Security platform" \
  --filter-product "Windows Security platform" \
  --stdout-only \
  --no-links
```

Affichage pratique du CSV (20 premieres lignes):

```bash
column -s, -t < search_filtered.csv | sed -n '1,20p'
```

## Notes

- Le mode de recherche est uniquement via lynx.
- La requete de recherche se passe en premier argument positionnel.
- Les options --fromdate et --todate acceptent les formats YYYY-MM-DD et M/J/AAAA.
- L'option --lastdate est disponible comme alias de --last.
- L'option --uuid permet un filtre exact sur update_id.
- L'option --limit permet de choisir le nombre de resultats final.
- Les resultats sont tries par date decroissante avant l'export.
- Les filtres regex dedies s'appliquent apres la recherche generale, sur le resultat deja extrait.
- Les tests unitaires n'ont pas de dependance externe supplementaire.

## Tests

Tests unitaires (par defaut):

```bash
SETUPTOOLS_USE_DISTUTILS=stdlib /usr/bin/python3 -m unittest -v
```

Tests d'integration (reels, reseau + lynx):

```bash
SETUPTOOLS_USE_DISTUTILS=stdlib RUN_INTEGRATION_TESTS=1 /usr/bin/python3 -m unittest -v test_extraction.ExtractionIntegrationTests.test_real_catalog_known_uuids
```

Important sur UUID/KB en integration:

- Le jeu de cas stocke un uuid par ligne (vos UUID de reference).
- La validation reelle interroge le catalogue par KB (ex: KB5079473), puis verifie titre/produit/classification.
- Cette approche est plus stable dans le temps: l'update_id retourne dans les resultats peut varier, mais le KB reste le pivot fonctionnel.

## Exemple pret a l'emploi

Commande complete pour votre recherche "Windows Security platform" avec filtre produit,
plage de dates, tri decroissant (automatique) et export CSV:

```bash
python3 extraction.py "Windows Security platform" \
  --filter-product "Windows Security platform" \
  --fromdate 2026-01-01 \
  --todate 2026-12-31 \
  --limit 10 \
  --output search_filtered.csv \
  --no-links
```