# Extraction Microsoft Update Catalog

Ce projet contient un script Python pour extraire les resultats du Microsoft Update Catalog et les exporter en CSV, JSON ou MariaDB.

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

- PyMySQL
  Necessaire uniquement pour l'export MariaDB et le test de connexion base.

## Installation rapide

Sous Debian/Ubuntu:

```bash
sudo apt update
sudo apt install -y python3 lynx bsdextrautils sed
```

Dependance Python optionnelle pour MariaDB:

```bash
python3 -m pip install -r requirements.txt
```

Remarque:

- bsdextrautils fournit la commande column sur de nombreuses distributions Debian/Ubuntu.
- Le script refuse l'execution si l'argument de recherche positionnel n'est pas fourni.
- Le script refuse l'execution si lynx n'est pas installe.
- Pour un fichier de configuration client MySQL/MariaDB, le nom standard est .my.cnf, pas .my.cf.

## Fichier .my.cnf pour les tests

Pour le developpement local, la pratique recommandee est la suivante:

- versionner un modele sans secret;
- garder le vrai fichier local ignore par Git;
- utiliser un compte SQL dedie aux tests, avec des droits limites a la base de test.

Un modele est fourni dans [.my.cnf.example](.my.cnf.example).

Creation locale:

```bash
cp .my.cnf.example .my.cnf
chmod 600 .my.cnf
```

Points importants:

- ne jamais committer un vrai mot de passe dans .my.cnf;
- utiliser de preference un utilisateur de test, pas root;
- limiter ce compte a la base de test, par exemple xmppmaster si c'est votre base de validation.

Exemple de test de connexion avec le client MariaDB:

```bash
mariadb --defaults-file=.my.cnf -e "SELECT 1;"
```

Exemple de verification supplementaire:

```bash
mysqladmin --defaults-file=.my.cnf ping
```

Note:

- le script extraction.py ne lit pas automatiquement .my.cnf aujourd'hui;
- ce fichier sert surtout a tester la connexion avec le client MariaDB sans repasser le mot de passe en ligne de commande;
- une evolution possible consiste a ajouter une option du type --db-defaults-file pour que le script lise aussi ce fichier.

## Utilisation rapide

1. Donner la requete de recherche en premier argument positionnel.
2. Ajouter les filtres necessaires (produit, regex, date, UUID, limite).
3. Choisir un fichier de sortie avec --output.
4. Ou choisir une sortie MariaDB avec --output-mariadb et les options de connexion.
5. Ajouter --no-links si vous voulez un traitement plus rapide.
6. Ajouter --test-db-connection si vous voulez verifier la connexion avant l'extraction.

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

Tester uniquement la connexion MariaDB:

```bash
python3 extraction.py \
  --output-mariadb \
  --db-host 127.0.0.1 \
  --db-port 3306 \
  --db-user root \
  --db-password secret \
  --db-name catalog \
  --db-table extraction_results \
  --test-db-connection
```

Tester la connexion MariaDB puis poursuivre l'extraction:

```bash
python3 extraction.py "Windows Security platform" \
  --filter-product "Windows Security platform" \
  --output-mariadb \
  --db-host 127.0.0.1 \
  --db-port 3306 \
  --db-user root \
  --db-password secret \
  --db-name xmppmaster \
  --db-table extraction_results \
  --test-db-connection \
  --no-links
```

Exporter vers MariaDB:

```bash
python3 extraction.py "Windows Security platform" \
  --filter-product "Windows Security platform" \
  --output-mariadb \
  --db-host 127.0.0.1 \
  --db-port 3306 \
  --db-user root \
  --db-password secret \
  --db-name catalog \
  --db-table extraction_results \
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
- L'option --output-mariadb remplace la table cible si elle existe deja et si son schema correspond a la table d'extraction attendue.
- Si la table existe avec un autre schema, le script retourne une erreur au lieu de la detruire.
- L'option --test-db-connection permet de valider la connexion MariaDB avant tout export.
- Si --test-db-connection est utilisee sans requete, le script quitte apres le test de connexion.
- Si --test-db-connection est utilisee avec une requete, le script teste la connexion puis poursuit l'extraction.
- Un fichier local .my.cnf peut etre utilise pour les tests manuels du client MariaDB, mais il n'est pas encore consomme directement par le script.
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