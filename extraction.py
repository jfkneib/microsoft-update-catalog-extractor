#!/usr/bin/env python3
"""
Extraction automatique des mises a jour depuis un HTML du Microsoft Update Catalog.

Usage:
  python3 extraction.py
    python3 extraction.py "Windows Security platform" --output /home/jfk/catalog.csv
    python3 extraction.py "Windows Security platform" --filter-product "Windows Security platform"
    python3 extraction.py "Windows Security platform" --filter-regex "Windows Security platform|Defender" --filter-field produit
"""

import argparse
import csv
import datetime
import html
import importlib
import io
import json
import os
import re
import shutil
import sys
import urllib.parse
import urllib.request
from typing import Any, Dict, List


SEARCH_URL = "https://www.catalog.update.microsoft.com/Search.aspx"
DOWNLOAD_DIALOG_URL = "https://www.catalog.update.microsoft.com/DownloadDialog.aspx"
DETAILS_URL = "https://www.catalog.update.microsoft.com/ScopedViewInline.aspx"
DEFAULT_OUTPUT_CSV = "/home/jfk/catalog_windows_security_platform.csv"
DEFAULT_OUTPUT_JSON = "/home/jfk/catalog_windows_security_platform.json"
DEFAULT_DB_PORT = 3306
DB_COLUMNS = [
    "titre",
    "produit",
    "classification",
    "derniere_mise_a_jour",
    "version",
    "taille",
    "kb",
    "description",
    "msrc_number",
    "msrc_severity",
    "supersededby",
    "update_id",
    "lien_telechargement",
]
DETAIL_ENRICHED_FIELDS = {"description", "msrc_number", "msrc_severity", "supersededby"}


MANUAL_TEXT = """\
NOM
    extraction.py - Extrait des resultats du Microsoft Update Catalog vers CSV, JSON ou MariaDB

DESCRIPTION
    Cet utilitaire recupere une page de resultats du Microsoft Update Catalog,
    extrait les colonnes utiles, applique des filtres optionnels, puis exporte
    un fichier CSV, JSON ou une table MariaDB.

    Colonnes exportees:
        - titre
        - produit
        - classification
        - derniere_mise_a_jour
        - version
        - taille
        - kb
        - description
        - msrc_number
        - msrc_severity
        - supersededby
        - update_id
        - lien_telechargement

PREREQUIS
    Utilitaires et composants a prevoir:
        - python3
            Obligatoire pour executer le script.

        - lynx
            Prerequis indispensable.

        - acces reseau HTTPS
            Necessaire pour interroger le Microsoft Update Catalog.

    Utilitaires optionnels:
        - column
            Pratique pour afficher le CSV en tableau dans le terminal.

        - sed
            Utilise dans les exemples pour limiter l'affichage a quelques lignes.

    Exemples d'installation sous Debian/Ubuntu:
        sudo apt update
        sudo apt install -y python3 lynx bsdextrautils sed

MODES D'ENTREE
    1) "TEXTE" (argument positionnel)
         Lance une recherche catalogue via lynx.
         Remarque: lynx doit etre installe au prealable.

FILTRES
    --filter-product "TEXTE"
        Garde les lignes dont le champ produit contient TEXTE (insensible a la casse).

    --filter-regex "REGEX"
        Applique une expression reguliere (insensible a la casse).

    --filter-field CHAMP
        Choisit le champ cible de --filter-regex.
        Valeurs: titre, produit, classification, derniere_mise_a_jour, version, taille, kb, description, msrc_number, msrc_severity, supersededby, update_id

    --title-regex "REGEX"
        Filtre le champ titre avec une expression reguliere.

    --classification-regex "REGEX"
        Filtre le champ classification avec une expression reguliere.

    --uuid-regex "REGEX"
        Filtre le champ update_id (UUID) avec une expression reguliere.

    --uuid UUID
        Filtre exact sur le champ update_id (UUID).

    --fromdate DATE
        Conserve uniquement les lignes dont la date est superieure ou egale a DATE.

    --todate DATE
        Conserve uniquement les lignes dont la date est inferieure ou egale a DATE.

    --lastdate
        Alias de --last. Conserve uniquement la ligne la plus recente.

    --limit N
        Conserve uniquement les N premieres lignes apres tri et filtres.

    --last
        Conserve uniquement la ligne la plus recente selon la colonne
        derniere_mise_a_jour.

SORTIE
    --output fichier.csv
        Definit le chemin du CSV de sortie.

    --json
        Ecrit la sortie au format JSON formate (indentation 2 espaces).

    --print-results
        Affiche aussi les resultats dans la console.

    --stdout-only
        Affiche uniquement les resultats dans stdout (sans message annexe).
        Active implicitement --print-results.

    -d, --debug
        Active des logs detailles sur stderr (mode de recherche, filtres, compteurs).

    --no-links
        N'appelle pas DownloadDialog.aspx (plus rapide, colonne lien vide).

    --with-details
        Interroge la fiche detail de chaque mise a jour pour recuperer la
        description, le numero MSRC, la severite MSRC et confirmer le KB.

    --only-empty-supersededby
        Conserve uniquement les mises a jour dont le champ supersededby est
        vide. Cette option active implicitement la lecture de la fiche detail.

    --save-html fichier.html
        Sauvegarde le HTML recupere.

    --output-mariadb
        Ecrit les resultats dans une table MariaDB au lieu d'un fichier.

    --db-host, --db-port, --db-user, --db-password
        Parametres de connexion MariaDB.

    --db-name, --db-table
        Base et table cibles pour l'export MariaDB.

    --db-charset
        Jeu de caracteres de connexion (defaut: utf8mb4).

    --db-connect-timeout
        Timeout de connexion en secondes (defaut: 10).

    --test-db-connection
        Teste la connexion MariaDB. Sans requete, quitte apres le test.
        Avec une requete, poursuit ensuite l'extraction.

EXEMPLES
    Prerequis pour les exemples:
        lynx doit etre installe.

    1) Recherche principale + filtre produit contient
         python3 extraction.py "Windows Security platform" \\
             --filter-product "Windows Security platform" \\
             --output search_filtered.csv --no-links

    2) Recherche principale + filtre regex sur produit
         python3 extraction.py "Windows Security platform" \\
             --filter-regex "Windows Security platform|Defender" \\
             --filter-field produit \\
             --output search_filtered_regex.csv --no-links

    3) Filtrer le titre avec une regex
         python3 extraction.py "Windows Security platform" \
             --title-regex "Security Intelligence|Platform" \
             --output title_filtered.csv --no-links

    4) Filtrer la classification avec une regex
         python3 extraction.py "Windows Security platform" \
             --classification-regex "Definition Updates|Security Updates" \
             --output class_filtered.csv --no-links

    5) Filtrer l'UUID avec une regex
         python3 extraction.py "Windows Security platform" \
             --uuid-regex "^[a-f0-9\\-]{36}$" \
             --output uuid_filtered.csv --no-links

    6) Filtrer l'UUID exact
         python3 extraction.py "Windows Security platform" \
             --uuid "11111111-1111-1111-1111-111111111111" \
             --output uuid_exact.csv --no-links

    7) Filtrer par intervalle de dates
         python3 extraction.py "Windows Security platform" \
             --fromdate 2026-01-01 --todate 2026-12-31 \
             --output date_filtered.csv --no-links

    8) Limiter le nombre de resultats
         python3 extraction.py "Windows Security platform" \
             --filter-product "Windows Security platform" \
             --limit 5 --output top5.csv --no-links

        9) Conserver uniquement la mise a jour la plus recente
              python3 extraction.py "Windows Security platform" \
               --filter-product "Windows Security platform" --last \
               --output search_last.csv --no-links

           10) Exporter en JSON formate
               python3 extraction.py "Windows Security platform" \
                 --filter-product "Windows Security platform" --json \
                 --output search_filtered.json --no-links

           11) Afficher aussi les resultats dans la console
               python3 extraction.py "Windows Security platform" \
                 --filter-product "Windows Security platform" --last \
                 --print-results --output search_last.csv --no-links

           12) Afficher les 20 premieres lignes du CSV
         column -s, -t < search_filtered.csv | sed -n '1,20p'

                     13) Tester uniquement la connexion MariaDB
                             python3 extraction.py --output-mariadb --db-host localhost \
                                 --db-port 3306 --db-user root --db-password secret \
                                 --db-name catalog --db-table extraction_results \
                                 --test-db-connection

                     14) Tester la connexion puis lancer l'extraction
                             python3 extraction.py "Windows Security platform" \
                                 --filter-product "Windows Security platform" \
                                 --output-mariadb --db-host localhost --db-port 3306 \
                                 --db-user root --db-password secret --db-name catalog \
                                 --db-table extraction_results --test-db-connection --no-links

                     15) Exporter les resultats vers MariaDB
                             python3 extraction.py "Windows Security platform" \
                                 --filter-product "Windows Security platform" \
                                 --output-mariadb --db-host localhost --db-port 3306 \
                                 --db-user root --db-password secret --db-name catalog \
                                 --db-table extraction_results --no-links

                     16) Conserver uniquement les mises a jour non remplacees
                             python3 extraction.py "Windows 11" \
                                 --filter-product "Windows 11" \
                                 --only-empty-supersededby \
                                 --output not_superseded.csv --no-links
"""


def debug_log(enabled: bool, message: str) -> None:
    """Ecrit un message de debug sur stderr.

    Cette fonction centralise l'affichage des traces de debug pour eviter de
    disperser des tests sur le flag dans tout le code. Quand le mode debug est
    desactive, l'appel ne produit aucun effet.

    Args:
        enabled: Indique si le mode debug est actif.
        message: Texte a ecrire sur stderr.
    """
    if enabled:
        print(f"[DEBUG] {message}", file=sys.stderr)


def clean_text(raw: str) -> str:
    """Nettoie un fragment HTML pour obtenir un texte exploitable.

    Le HTML recupere depuis le catalogue contient des balises, des entites HTML
    et souvent des retours a la ligne ou espaces multiples. Cette fonction
    normalise ce contenu pour produire une valeur simple, stable et facile a
    comparer dans les filtres comme dans les exports.

    Args:
        raw: Fragment HTML ou texte brut a normaliser.

    Returns:
        Une chaine nettoyee, sans balises HTML et avec des espaces normalises.
    """
    # Supprime les balises HTML puis normalise les espaces pour obtenir une valeur plate.
    text = re.sub(r"<[^>]+>", "", raw, flags=re.S)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_kb_from_title(title: str) -> str:
    """Extrait le numero KB depuis le titre quand il est present.

    Le catalogue affiche souvent le KB directement dans le titre, par exemple
    sous la forme "(KB5086672)". Pour simplifier les exports et les filtres,
    on normalise cette information dans une colonne dediee et on ne conserve
    que la partie numerique.

    Args:
        title: Titre d'une mise a jour issu du catalogue.

    Returns:
        Le numero KB sans prefixe "KB", ou une chaine vide si aucun motif
        exploitable n'est present dans le titre.
    """
    match = re.search(r"\bKB\s*([0-9]{6,8})\b", title or "", re.I)
    if not match:
        return ""
    return match.group(1)


def fetch_update_details_html(update_id: str, timeout: int = 30) -> str:
    """Recupere la fiche detail HTML d'une mise a jour via ScopedViewInline.

    Args:
        update_id: UUID de la mise a jour.
        timeout: Timeout HTTP en secondes.

    Returns:
        Le HTML de la fiche detail.
    """
    params = urllib.parse.urlencode({"updateid": update_id})
    req = urllib.request.Request(
        f"{DETAILS_URL}?{params}",
        headers={"User-Agent": "Mozilla/5.0"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def parse_update_details_html(detail_html: str) -> Dict[str, str]:
    """Extrait les metadonnees utiles depuis la fiche detail d'une mise a jour.

    Args:
        detail_html: HTML de la fiche detail ScopedViewInline.

    Returns:
        Dictionnaire contenant description, kb, msrc_number et msrc_severity.
    """

    def extract_element_text(element_id: str) -> str:
        match = re.search(
            rf'id="{re.escape(element_id)}"[^>]*>(.*?)</[^>]+>',
            detail_html,
            re.S | re.I,
        )
        return clean_text(match.group(1)) if match else ""

    def extract_div_text(div_id: str, label: str) -> str:
        match = re.search(
            rf'<div id="{re.escape(div_id)}"[^>]*>(.*?)</div>',
            detail_html,
            re.S | re.I,
        )
        if not match:
            return ""
        text = clean_text(match.group(1))
        text = re.sub(rf'^{re.escape(label)}\s*', '', text, flags=re.I).strip()
        return text

    def extract_div_items(div_id: str) -> str:
        match = re.search(
            rf'<div id="{re.escape(div_id)}"[^>]*>(.*?)</div>',
            detail_html,
            re.S | re.I,
        )
        if not match:
            return ""
        block = match.group(1)
        items = re.findall(r'<div[^>]*>(.*?)</div>', block, re.S | re.I)
        if not items:
            text = clean_text(block)
            return "" if text.lower() == "n/a" else text
        cleaned_items = []
        for item in items:
            text = clean_text(item)
            if text and text.lower() != "n/a":
                cleaned_items.append(text)
        return " | ".join(cleaned_items)

    description = extract_element_text("ScopedViewHandler_desc")
    msrc_severity = extract_element_text("ScopedViewHandler_msrcSeverity") or "n/a"
    msrc_number = extract_div_text("securityBullitenDiv", "MSRC Number:") or "n/a"
    kb_text = extract_div_text("kbDiv", "KB article numbers:")
    kb_match = re.search(r'\b([0-9]{6,8})\b', kb_text)
    kb = kb_match.group(1) if kb_match else ""
    supersededby = extract_div_items("supersededbyInfo")

    return {
        "description": description,
        "kb": kb,
        "msrc_number": msrc_number,
        "msrc_severity": msrc_severity,
        "supersededby": "" if supersededby.lower() == "n/a" else supersededby,
    }


def fetch_update_details(update_id: str, timeout: int = 30) -> Dict[str, str]:
    """Recupere et parse la fiche detail d'une mise a jour.

    Args:
        update_id: UUID de la mise a jour.
        timeout: Timeout HTTP en secondes.

    Returns:
        Metadonnees detaillees de la mise a jour.
    """
    return parse_update_details_html(fetch_update_details_html(update_id, timeout=timeout))


def parse_rows(page_html: str) -> List[Dict[str, str]]:
    """Extrait les lignes de resultats depuis le HTML de la page catalogue.

    Le Microsoft Update Catalog ne fournit pas une API simple pour ces donnees.
    Le script travaille donc directement sur le HTML source et reconstruit un
    enregistrement par ligne du tableau de resultats.

    Args:
        page_html: HTML brut de la page de recherche du catalogue.

    Returns:
        Une liste de dictionnaires normalises selon les colonnes definies dans
        l'export final.
    """
    row_re = re.compile(r'<tr id="([0-9a-f\-]+)_R\d+">(.*?)</tr>', re.S | re.I)

    def extract_cell(row_uid: str, col: int, row_html: str) -> str:
        """Recupere et nettoie le contenu d'une cellule pour une colonne donnee.

        Args:
            row_uid: Identifiant unique de la ligne dans le tableau HTML.
            col: Numero de colonne a lire.
            row_html: HTML complet de la ligne en cours de traitement.

        Returns:
            Le texte nettoye de la cellule, ou une chaine vide si la cellule
            n'est pas retrouvee.
        """
        m = re.search(
            rf'id="{re.escape(row_uid)}_C{col}_R\d+"[^>]*>(.*?)</td>',
            row_html,
            re.S | re.I,
        )
        return clean_text(m.group(1)) if m else ""

    rows: List[Dict[str, str]] = []
    for match in row_re.finditer(page_html):
        uid = match.group(1)
        row_html = match.group(2)

        # La taille est parfois encapsulee dans un span dedie au lieu de la cellule standard.
        size_m = re.search(
            rf'<span id="{re.escape(uid)}_size">(.*?)</span>',
            row_html,
            re.S | re.I,
        )

        # Construit un enregistrement normalise pour tous les formats de sortie.
        record = {
            "update_id": uid,
            "titre": extract_cell(uid, 1, row_html),
            "produit": extract_cell(uid, 2, row_html),
            "classification": extract_cell(uid, 3, row_html),
            "derniere_mise_a_jour": extract_cell(uid, 4, row_html),
            "version": extract_cell(uid, 5, row_html),
            "taille": clean_text(size_m.group(1)) if size_m else extract_cell(uid, 6, row_html),
        }
        record["kb"] = extract_kb_from_title(record["titre"])
        record["description"] = ""
        record["msrc_number"] = "n/a"
        record["msrc_severity"] = "n/a"
        record["supersededby"] = ""

        if record["titre"]:
            rows.append(record)

    return rows


def fetch_search_html(query: str, timeout: int = 30) -> str:
    """Telecharge la page de recherche via HTTP direct.

    Cette fonction existe surtout comme alternative simple pour le debug ou des
    evolutions futures. Le flux principal du script s'appuie sur lynx, car le
    site renvoie parfois un HTML plus exploitable par ce biais.

    Args:
        query: Texte recherche dans le catalogue.
        timeout: Timeout HTTP en secondes.

    Returns:
        Le HTML de la page de recherche.
    """
    params = urllib.parse.urlencode({"q": query})
    url = f"{SEARCH_URL}?{params}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def fetch_search_html_with_lynx(query: str, timeout: int = 30) -> str:
    """Telecharge la page de recherche en utilisant lynx.

    Le site Microsoft Update Catalog repond de maniere plus stable pour ce
    script quand le HTML est recupere via lynx en mode source. Cette fonction
    encapsule cet appel systeme et remonte une erreur explicite si lynx echoue.

    Args:
        query: Texte recherche dans le catalogue.
        timeout: Timeout de l'appel subprocess en secondes.

    Returns:
        Le HTML brut renvoye par lynx.

    Raises:
        RuntimeError: Si lynx retourne un code d'erreur.
    """
    import subprocess

    # Lynx permet une extraction plus proche du rendu attendu par le site.
    params = urllib.parse.urlencode({"q": query})
    url = f"{SEARCH_URL}?{params}"
    result = subprocess.run(
        ["lynx", "-source", url],
        capture_output=True,
        timeout=timeout,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"lynx failed: {result.stderr}")
    return result.stdout


def fetch_download_link(update_id: str, timeout: int = 30) -> str:
    """Recupere le premier lien de telechargement direct pour une mise a jour.

    Le catalogue expose les liens de telechargement via DownloadDialog.aspx.
    Cette fonction reproduit la requete attendue puis extrait la premiere URL
    disponible dans la reponse HTML/JavaScript.

    Args:
        update_id: UUID de la mise a jour.
        timeout: Timeout HTTP en secondes.

    Returns:
        La premiere URL de telechargement trouvee, ou une chaine vide.
    """
    # Le endpoint DownloadDialog attend une structure JSON dans le formulaire.
    payload = json.dumps(
        [
            {
                "size": 0,
                "languages": "",
                "uidInfo": update_id,
                "updateID": update_id,
            }
        ]
    )

    form = {
        "updateIDs": payload,
        "updateIDsBlockedForImport": "",
        "wsusApiPresent": "",
        "contentImport": "",
        "sku": "",
        "serverName": "",
        "ssl": "",
        "portNumber": "",
    }

    body = urllib.parse.urlencode(form).encode("utf-8")
    req = urllib.request.Request(
        DOWNLOAD_DIALOG_URL,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Mozilla/5.0",
        },
    )

    with urllib.request.urlopen(req, timeout=timeout) as resp:
        dialog_html = resp.read().decode("utf-8", errors="ignore")

    urls = re.findall(
        r"downloadInformation\[0\]\.files\[\d+\]\.url\s*=\s*'([^']+)'",
        dialog_html,
    )
    return urls[0] if urls else ""


def filter_rows(rows: List[Dict[str, str]], product_name: str) -> List[Dict[str, str]]:
    """Filtre les lignes dont le champ produit contient un texte.

    Args:
        rows: Lignes candidates a filtrer.
        product_name: Texte a chercher dans la colonne produit.

    Returns:
        Les lignes dont le champ produit contient le texte recherche, sans
        distinction de casse.
    """
    needle = product_name.strip().lower()
    return [r for r in rows if needle in r.get("produit", "").strip().lower()]


def filter_rows_regex(rows: List[Dict[str, str]], pattern: str, field: str = "produit") -> List[Dict[str, str]]:
    """Filtre les lignes avec une expression reguliere appliquee sur un champ.

    Args:
        rows: Lignes a examiner.
        pattern: Expression reguliere a appliquer.
        field: Nom de la colonne cible.

    Returns:
        Les lignes dont le champ cible correspond a la regex.
    """
    regex = re.compile(pattern, re.I)
    return [r for r in rows if regex.search(r.get(field, "") or "")]


def filter_rows_uuid(rows: List[Dict[str, str]], uuid_value: str) -> List[Dict[str, str]]:
    """Filtre les lignes sur un UUID exact.

    Args:
        rows: Lignes a examiner.
        uuid_value: UUID attendu dans la colonne update_id.

    Returns:
        Les lignes dont update_id correspond exactement a la valeur demandee,
        sans distinction de casse.
    """
    needle = uuid_value.strip().lower()
    return [r for r in rows if (r.get("update_id", "") or "").strip().lower() == needle]


def filter_rows_empty_supersededby(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Conserve uniquement les lignes dont supersededby est vide.

    Cette fonction est utile pour ne garder que les mises a jour qui ne sont
    pas deja remplacees par une autre entree du catalogue.

    Args:
        rows: Lignes candidates a filtrer.

    Returns:
        Les lignes dont le champ supersededby est vide ou ne contient que des espaces.
    """
    return [r for r in rows if not (r.get("supersededby", "") or "").strip()]


def parse_catalog_date(raw_date: str) -> datetime.date:
    """Convertit une date du catalogue en objet date Python.

    Le catalogue retourne des dates dans plusieurs formats selon les pages ou
    le contexte. Le script accepte ici les deux formats observes et normalise le
    resultat en objet date pour permettre tri et filtrage.

    Args:
        raw_date: Date brute lue dans la colonne derniere_mise_a_jour.

    Returns:
        La date parsee.

    Raises:
        ValueError: Si la date est vide ou dans un format non supporte.
    """
    raw = raw_date.strip()
    if not raw:
        raise ValueError("date vide")

    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(raw, fmt).date()
        except ValueError:
            continue

    raise ValueError(f"format de date non supporte: {raw_date}")


def filter_rows_by_date_range(
    rows: List[Dict[str, str]],
    from_date: datetime.date | None = None,
    to_date: datetime.date | None = None,
) -> List[Dict[str, str]]:
    """Conserve les lignes dont la date est comprise dans l'intervalle demande.

    Args:
        rows: Lignes a filtrer.
        from_date: Borne basse inclusive, ou None.
        to_date: Borne haute inclusive, ou None.

    Returns:
        Les lignes dont la date est dans l'intervalle demande.
    """
    filtered_rows: List[Dict[str, str]] = []
    for row in rows:
        try:
            row_date = parse_catalog_date(row.get("derniere_mise_a_jour", ""))
        except (ValueError, TypeError):
            # Une date non exploitable ne peut pas etre comparee correctement: la ligne est ignoree.
            continue

        if from_date and row_date < from_date:
            continue
        if to_date and row_date > to_date:
            continue
        filtered_rows.append(row)

    return filtered_rows


def select_latest_row(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Retourne uniquement la ligne la plus recente.

    Args:
        rows: Lignes candidates.

    Returns:
        Une liste contenant zero ou une ligne. Le retour reste une liste pour
        conserver une interface uniforme avec les autres fonctions de filtrage.
    """
    dated_rows = []
    for row in rows:
        try:
            dated_rows.append((parse_catalog_date(row.get("derniere_mise_a_jour", "")), row))
        except (ValueError, TypeError):
            # Ignore les lignes sans date exploitable.
            continue

    if not dated_rows:
        return []

    # max() utilise la date comme cle et conserve la ligne la plus recente.
    latest = max(dated_rows, key=lambda item: item[0])[1]
    return [latest]


def sort_rows_by_date_desc(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Trie les lignes par date decroissante.

    Les lignes sans date valide sont preservees et placees en fin de resultat
    afin de ne pas perdre d'information tout en gardant un ordre coherent.

    Args:
        rows: Lignes a trier.

    Returns:
        Une nouvelle liste triee par date decroissante.
    """
    dated_rows: List[tuple[datetime.date, Dict[str, str]]] = []
    undated_rows: List[Dict[str, str]] = []
    for row in rows:
        try:
            dated_rows.append((parse_catalog_date(row.get("derniere_mise_a_jour", "")), row))
        except (ValueError, TypeError):
            undated_rows.append(row)

    dated_rows.sort(key=lambda item: item[0], reverse=True)
    return [row for _, row in dated_rows] + undated_rows


def enrich_with_links(rows: List[Dict[str, str]]) -> None:
    """Ajoute un lien de telechargement direct a chaque ligne.

    Cette etape effectue un appel supplementaire par mise a jour. Elle est donc
    potentiellement lente et peut etre desactivee via --no-links.

    Args:
        rows: Lignes a enrichir. La liste est modifiee en place.
    """
    for row in rows:
        try:
            row["lien_telechargement"] = fetch_download_link(row["update_id"])
        except Exception as exc:  # noqa: BLE001
            # On conserve la ligne meme si la resolution du lien echoue.
            row["lien_telechargement"] = ""
            print(
                f"[WARN] Echec de recuperation du lien pour {row['update_id']}: {exc}",
                file=sys.stderr,
            )


def enrich_with_details(rows: List[Dict[str, str]]) -> None:
    """Ajoute les metadonnees de la fiche detail a chaque ligne.

    Cette etape effectue un appel supplementaire par mise a jour vers la popup
    de details du catalogue. En cas d'echec, les valeurs par defaut sont
    conservees pour ne pas perdre la ligne principale.

    Args:
        rows: Lignes a enrichir. La liste est modifiee en place.
    """
    for row in rows:
        try:
            details = fetch_update_details(row["update_id"])
            row["description"] = details.get("description", "") or ""
            row["msrc_number"] = details.get("msrc_number", "n/a") or "n/a"
            row["msrc_severity"] = details.get("msrc_severity", "n/a") or "n/a"
            row["supersededby"] = details.get("supersededby", "") or ""
            detail_kb = details.get("kb", "") or ""
            if detail_kb:
                row["kb"] = detail_kb
        except Exception as exc:  # noqa: BLE001
            row.setdefault("description", "")
            row.setdefault("msrc_number", "n/a")
            row.setdefault("msrc_severity", "n/a")
            row.setdefault("supersededby", "")
            print(
                f"[WARN] Echec de recuperation des details pour {row['update_id']}: {exc}",
                file=sys.stderr,
            )


def write_csv(rows: List[Dict[str, str]], output_path: str) -> None:
    """Ecrit les resultats dans un fichier CSV.

    Args:
        rows: Lignes a exporter.
        output_path: Chemin du fichier CSV cible.
    """
    csv_content = render_csv(rows)
    with open(output_path, "w", newline="", encoding="utf-8") as handle:
        handle.write(csv_content)


def render_csv(rows: List[Dict[str, str]]) -> str:
    """Construit le rendu CSV en memoire.

    Le rendu texte est partage entre l'ecriture fichier et l'affichage console
    pour garantir un format identique dans les deux cas.

    Args:
        rows: Lignes a serialiser.

    Returns:
        Le contenu CSV complet sous forme de chaine.
    """
    buffer = io.StringIO()
    # L'ordre des colonnes doit rester stable entre CSV, JSON logique et table SQL.
    writer = csv.DictWriter(buffer, fieldnames=DB_COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def write_json(rows: List[Dict[str, str]], output_path: str) -> None:
    """Ecrit les resultats dans un fichier JSON formate.

    Args:
        rows: Lignes a exporter.
        output_path: Chemin du fichier JSON cible.
    """
    with open(output_path, "w", encoding="utf-8") as handle:
        handle.write(render_json(rows))


def render_json(rows: List[Dict[str, str]]) -> str:
    """Construit le rendu JSON en memoire.

    Args:
        rows: Lignes a serialiser.

    Returns:
        Une chaine JSON pretty-print terminee par un saut de ligne.
    """
    return json.dumps(rows, ensure_ascii=False, indent=2) + "\n"


def print_results(rows: List[Dict[str, str]], as_json: bool) -> None:
    """Affiche les resultats dans la console avec un en-tete lisible.

    Args:
        rows: Lignes a afficher.
        as_json: Indique si l'affichage doit etre en JSON ou en CSV.
    """
    print("--- RESULTATS ---")
    if as_json:
        print(render_json(rows), end="")
    else:
        print(render_csv(rows), end="")


def print_results_raw(rows: List[Dict[str, str]], as_json: bool) -> None:
    """Affiche uniquement les donnees de resultat, sans texte annexe.

    Ce mode est utile pour composer le script avec d'autres commandes shell.

    Args:
        rows: Lignes a afficher.
        as_json: Indique si l'affichage doit etre en JSON ou en CSV.
    """
    if as_json:
        print(render_json(rows), end="")
    else:
        print(render_csv(rows), end="")


def write_output(rows: List[Dict[str, str]], as_json: bool, output_path: str) -> None:
    """Route l'export vers le format fichier demande.

    Args:
        rows: Lignes a exporter.
        as_json: Indique si la sortie doit etre en JSON, sinon CSV.
        output_path: Fichier cible.
    """
    if as_json:
        write_json(rows, output_path)
    else:
        write_csv(rows, output_path)


def resolve_output_path(raw_output: str | None, as_json: bool) -> str:
    """Construit le chemin de sortie final.

    Si aucun chemin n'est fourni, le fichier par defaut est cree dans le
    repertoire courant afin d'eviter toute hypothese sur l'environnement.

    Args:
        raw_output: Valeur de l'option --output, ou None si absente.
        as_json: Indique si la sortie doit etre en JSON.

    Returns:
        Le chemin final a utiliser pour l'ecriture.
    """
    if raw_output:
        return raw_output

    filename = os.path.basename(DEFAULT_OUTPUT_JSON if as_json else DEFAULT_OUTPUT_CSV)
    return os.path.join(os.getcwd(), filename)


def sanitize_sql_identifier(identifier: str, label: str) -> str:
    """Valide un identifiant SQL simple.

    Les noms de base et de table ne peuvent pas etre passes comme parametres SQL
    prepares. Il faut donc les valider explicitement avant de les interpoler.

    Args:
        identifier: Identifiant SQL propose par l'utilisateur.
        label: Libelle a reutiliser dans les messages d'erreur.

    Returns:
        L'identifiant valide tel quel.

    Raises:
        ValueError: Si l'identifiant ne respecte pas le format autorise.
    """
    if not identifier or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", identifier):
        raise ValueError(f"{label} invalide: utiliser uniquement lettres, chiffres et underscore")
    return identifier


def load_mariadb_client() -> Any:
    """Charge le module client MariaDB/MySQL requis pour l'export SQL.

    Le chargement est volontairement paresseux pour ne pas imposer la
    dependance PyMySQL aux utilisateurs qui exportent seulement en CSV/JSON.

    Returns:
        Le module client importe dynamiquement.

    Raises:
        RuntimeError: Si le module PyMySQL n'est pas installe.
    """
    try:
        return importlib.import_module("pymysql")
    except ImportError as exc:
        raise RuntimeError(
            "Module Python manquant pour MariaDB: installez PyMySQL (pip install PyMySQL)."
        ) from exc


def build_db_config(args: argparse.Namespace) -> Dict[str, Any]:
    """Construit et valide la configuration MariaDB a partir des options CLI.

    Args:
        args: Namespace argparse issu du parsing CLI.

    Returns:
        Un dictionnaire de configuration pret a etre passe au client MariaDB.

    Raises:
        ValueError: Si une option obligatoire manque ou si une valeur est invalide.
    """
    required_fields = {
        "db_host": "--db-host",
        "db_user": "--db-user",
        "db_password": "--db-password",
        "db_name": "--db-name",
        "db_table": "--db-table",
    }
    missing_options = [option for attr, option in required_fields.items() if not getattr(args, attr)]
    if missing_options:
        raise ValueError(f"Options MariaDB manquantes: {', '.join(missing_options)}")

    if args.db_port <= 0:
        raise ValueError("Option MariaDB invalide: --db-port doit etre > 0")
    if args.db_connect_timeout <= 0:
        raise ValueError("Option MariaDB invalide: --db-connect-timeout doit etre > 0")

    return {
        "host": args.db_host,
        "port": args.db_port,
        "user": args.db_user,
        "password": args.db_password,
        "database": sanitize_sql_identifier(args.db_name, "Nom de base"),
        "table": sanitize_sql_identifier(args.db_table, "Nom de table"),
        "charset": args.db_charset,
        "connect_timeout": args.db_connect_timeout,
    }


def connect_to_mariadb(db_config: Dict[str, Any]) -> Any:
    """Ouvre une connexion MariaDB a partir de la configuration validee.

    Args:
        db_config: Parametres de connexion deja valides.

    Returns:
        Une connexion ouverte vers la base cible.
    """
    client = load_mariadb_client()
    return client.connect(
        host=db_config["host"],
        port=db_config["port"],
        user=db_config["user"],
        password=db_config["password"],
        database=db_config["database"],
        charset=db_config["charset"],
        connect_timeout=db_config["connect_timeout"],
        autocommit=False,
    )


def test_mariadb_connection(db_config: Dict[str, Any]) -> None:
    """Teste qu'une connexion MariaDB peut etre etablie.

    Cette fonction verifie a la fois l'ouverture de connexion et l'execution
    d'une requete triviale, afin d'eviter un faux positif sur une connexion
    partiellement ouverte ou mal configuree.

    Args:
        db_config: Parametres de connexion MariaDB.
    """
    connection = connect_to_mariadb(db_config)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    finally:
        connection.close()


def fetch_existing_table_columns(connection: Any, database_name: str, table_name: str) -> List[str]:
    """Retourne les colonnes d'une table existante dans l'ordre physique.

    Cette verification est utilisee avant destruction/recreation de la table
    pour s'assurer qu'on ne remplace pas accidentellement une table qui ne fait
    pas partie du schema d'export de ce script.

    Args:
        connection: Connexion SQL ouverte.
        database_name: Nom de la base cible.
        table_name: Nom de la table cible.

    Returns:
        La liste ordonnee des colonnes, ou une liste vide si la table n'existe
        pas.
    """
    query = (
        "SELECT COLUMN_NAME "
        "FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s "
        "ORDER BY ORDINAL_POSITION"
    )
    with connection.cursor() as cursor:
        cursor.execute(query, (database_name, table_name))
        rows = cursor.fetchall()
    return [row[0] for row in rows]


def ensure_replaceable_extraction_table(connection: Any, database_name: str, table_name: str) -> None:
    """Verifie que la table cible peut etre remplacee sans risque.

    Le comportement voulu est strict: si la table existe deja mais ne correspond
    pas exactement au schema d'extraction attendu, le script s'arrete avec une
    erreur au lieu de supprimer une table potentiellement metier.

    Args:
        connection: Connexion SQL ouverte.
        database_name: Nom de la base cible.
        table_name: Nom de la table cible.

    Raises:
        ValueError: Si la table existe avec un schema different.
    """
    existing_columns = fetch_existing_table_columns(connection, database_name, table_name)
    if not existing_columns:
        return

    if existing_columns != DB_COLUMNS:
        raise ValueError(
            f"La table existante {database_name}.{table_name} ne correspond pas au schema d'extraction attendu"
        )


def recreate_extraction_table(connection: Any, table_name: str) -> None:
    """Supprime puis recree la table d'extraction avec le schema attendu.

    Args:
        connection: Connexion SQL ouverte.
        table_name: Nom de la table a recreer.
    """
    create_sql = (
        f"CREATE TABLE `{table_name}` ("
        "`titre` TEXT NOT NULL, "
        "`produit` TEXT NOT NULL, "
        "`classification` TEXT NOT NULL, "
        "`derniere_mise_a_jour` VARCHAR(32) NOT NULL, "
        "`version` VARCHAR(255) NOT NULL, "
        "`taille` VARCHAR(255) NOT NULL, "
        "`kb` VARCHAR(16) NOT NULL, "
        "`description` TEXT NOT NULL, "
        "`msrc_number` VARCHAR(64) NOT NULL, "
        "`msrc_severity` VARCHAR(64) NOT NULL, "
        "`supersededby` TEXT NOT NULL, "
        "`update_id` VARCHAR(64) NOT NULL, "
        "`lien_telechargement` TEXT NOT NULL, "
        "PRIMARY KEY (`update_id`)"
        ") CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
    )
    with connection.cursor() as cursor:
        # La validation prealable du schema permet ici un DROP/CREATE volontaire et controle.
        cursor.execute(f"DROP TABLE IF EXISTS `{table_name}`")
        cursor.execute(create_sql)


def insert_rows_into_mariadb(connection: Any, table_name: str, rows: List[Dict[str, str]]) -> None:
    """Insere les resultats d'extraction dans la table MariaDB cible.

    Args:
        connection: Connexion SQL ouverte.
        table_name: Nom de la table dans laquelle inserer les lignes.
        rows: Lignes normalisees a inserer.
    """
    insert_sql = (
        f"INSERT INTO `{table_name}` ("
        "titre, produit, classification, derniere_mise_a_jour, version, taille, kb, description, msrc_number, msrc_severity, supersededby, update_id, lien_telechargement"
        ") VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
    )
    # La charge utile respecte exactement l'ordre defini dans DB_COLUMNS et dans le CREATE TABLE.
    payload = [tuple((row.get(column, "") or "") for column in DB_COLUMNS) for row in rows]
    with connection.cursor() as cursor:
        cursor.executemany(insert_sql, payload)


def write_output_to_mariadb(rows: List[Dict[str, str]], db_config: Dict[str, Any]) -> None:
    """Ecrit les resultats dans MariaDB apres validation stricte de la table cible.

    Le flux est volontairement transactionnel: validation du schema, recreation
    de la table, insertion des lignes, puis commit final. En cas d'erreur, un
    rollback est tente avant fermeture de la connexion.

    Args:
        rows: Lignes a inserer.
        db_config: Configuration de connexion et de destination SQL.
    """
    connection = connect_to_mariadb(db_config)
    try:
        ensure_replaceable_extraction_table(connection, db_config["database"], db_config["table"])
        recreate_extraction_table(connection, db_config["table"])
        insert_rows_into_mariadb(connection, db_config["table"], rows)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def apply_regex_filter_option(
    rows: List[Dict[str, str]],
    pattern: str | None,
    field: str,
    label: str,
    stdout_only: bool,
    debug_enabled: bool,
) -> List[Dict[str, str]]:
    """Applique un filtre regex optionnel avec gestion uniforme des erreurs.

    Cette fonction mutualise le comportement de plusieurs options CLI qui
    partagent la meme logique: ignorer si l'option est absente, remonter une
    erreur si la regex est invalide, et lever un echec si aucun resultat ne
    subsiste apres filtrage.

    Args:
        rows: Lignes a filtrer.
        pattern: Regex fournie par l'utilisateur, ou None.
        field: Champ cible sur lequel appliquer la regex.
        label: Libelle lisible a afficher dans les messages d'erreur.
        stdout_only: Indique si le script doit rester silencieux hors payload.
        debug_enabled: Indique si les logs debug sont actifs.

    Returns:
        Les lignes filtrees.

    Raises:
        ValueError: Si la regex est invalide.
        LookupError: Si aucune ligne ne correspond au filtre demande.
    """
    if not pattern:
        return rows

    try:
        filtered_rows = filter_rows_regex(rows, pattern, field)
    except re.error as exc:
        if not stdout_only:
            print(f"Regex invalide pour {label}: {exc}", file=sys.stderr)
        raise ValueError(label) from exc

    if not filtered_rows:
        if not stdout_only:
            print(f"Aucune ligne ne correspond a la regex '{pattern}' sur {label}", file=sys.stderr)
        raise LookupError(label)

    if not stdout_only:
        print(f"[*] Filtre regex applique sur {label}: {len(filtered_rows)} ligne(s) conservee(s)", file=sys.stderr)
    debug_log(debug_enabled, f"Regex utilisee sur {field}: {pattern}")
    return filtered_rows


def main() -> int:
    """Point d'entree CLI du script.

    Le flux principal suit quatre etapes:
    1. Validation des options et gestion des modes speciaux.
    2. Recuperation du HTML via lynx.
    3. Parsing puis application des filtres dans un ordre deterministe.
    4. Export final vers fichier ou MariaDB, avec affichage optionnel.

    Returns:
        0 en cas de succes, -1 en cas d'erreur fonctionnelle ou de validation.
    """
    parser = argparse.ArgumentParser(
        description="Extrait les informations de mises a jour depuis un export HTML du Microsoft Update Catalog.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(
            "Exemples:\n"
            "  python3 extraction.py \"Windows Security platform\" --filter-product \"Windows Security platform\" --output search_filtered.csv --no-links\n"
            "  python3 extraction.py \"Windows Security platform\" --filter-regex \"Windows Security platform|Defender\" --filter-field produit --output search_filtered.csv --no-links\n"
            "  python3 extraction.py \"Windows Security platform\" --title-regex \"Security Intelligence\" --output title_filtered.csv --no-links\n"
            "  python3 extraction.py \"Windows Security platform\" --classification-regex \"Definition Updates\" --output class_filtered.csv --no-links\n"
            "  python3 extraction.py \"Windows Security platform\" --uuid-regex \"^[a-f0-9\\-]{36}$\" --output uuid_filtered.csv --no-links\n"
            "  python3 extraction.py \"Windows Security platform\" --uuid \"11111111-1111-1111-1111-111111111111\" --output uuid_exact.csv --no-links\n"
            "  python3 extraction.py \"Windows Security platform\" --fromdate 2026-01-01 --todate 2026-12-31 --output date_filtered.csv --no-links\n"
            "  python3 extraction.py \"Windows Security platform\" --filter-product \"Windows Security platform\" --limit 5 --output top5.csv --no-links\n"
            "  python3 extraction.py \"Windows Security platform\" --filter-product \"Windows Security platform\" --last --output search_last.csv --no-links\n"
            "  python3 extraction.py \"Windows Security platform\" --filter-product \"Windows Security platform\" --json --output search_filtered.json --no-links\n"
            "  python3 extraction.py \"Windows Security platform\" --filter-product \"Windows Security platform\" --only-empty-supersededby --output not_superseded.csv --no-links\n"
            "  python3 extraction.py \"Windows Security platform\" --filter-product \"Windows Security platform\" --last --print-results --output search_last.csv --no-links\n"
            "  python3 extraction.py \"Windows Security platform\" --save-html search_lynx.html\n"
            "  python3 extraction.py --output-mariadb --db-host localhost --db-port 3306 --db-user root --db-password secret --db-name catalog --db-table extraction_results --test-db-connection\n"
            "  python3 extraction.py \"Windows Security platform\" --output-mariadb --db-host localhost --db-port 3306 --db-user root --db-password secret --db-name catalog --db-table extraction_results --no-links"
        ),
    )
    parser.add_argument("query", nargs="?", help="Texte a chercher dans le catalogue Microsoft (mode lynx)")
    parser.add_argument("--man", action="store_true", help="Affiche le manuel detaille puis quitte")
    parser.add_argument("-d", "--debug", action="store_true", help="Active les logs de debug sur stderr")
    parser.add_argument("--filter-product", help="Garder uniquement les lignes dont le produit contient ce texte")
    parser.add_argument("--filter-regex", help="Filtrer avec une expression reguliere (regex)")
    parser.add_argument("--title-regex", help="Filtrer le champ titre avec une expression reguliere")
    parser.add_argument("--classification-regex", help="Filtrer le champ classification avec une expression reguliere")
    parser.add_argument("--uuid-regex", help="Filtrer le champ update_id (UUID) avec une expression reguliere")
    parser.add_argument("--uuid", help="Filtrer sur un UUID exact (champ update_id)")
    parser.add_argument(
        "--filter-field",
        default="produit",
        choices=["titre", "produit", "classification", "derniere_mise_a_jour", "version", "taille", "kb", "description", "msrc_number", "msrc_severity", "supersededby", "update_id"],
        help="Champ cible pour --filter-regex (defaut: produit)",
    )
    parser.add_argument(
        "--fromdate",
        "--from-date",
        dest="fromdate",
        help="Date minimale inclusive pour 'derniere_mise_a_jour' (formats acceptes: YYYY-MM-DD ou M/J/AAAA)",
    )
    parser.add_argument(
        "--todate",
        "--to-date",
        dest="todate",
        help="Date maximale inclusive pour 'derniere_mise_a_jour' (formats acceptes: YYYY-MM-DD ou M/J/AAAA)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Nombre maximum de lignes a conserver apres tri et filtres",
    )
    parser.add_argument("--output", help="Chemin du fichier de sortie (CSV ou JSON); par defaut: repertoire courant")
    parser.add_argument(
        "--save-html",
        help="Chemin de sauvegarde du HTML recupere en mode lynx",
    )
    parser.add_argument(
        "--no-links",
        action="store_true",
        help="Ne pas appeler DownloadDialog.aspx (plus rapide, sans lien direct)",
    )
    parser.add_argument(
        "--with-details",
        action="store_true",
        help="Interroger la fiche detail de chaque mise a jour pour enrichir kb, description et metadonnees MSRC",
    )
    parser.add_argument(
        "--only-empty-supersededby",
        action="store_true",
        help="Garder uniquement les mises a jour dont supersededby est vide; active implicitement les details",
    )
    parser.add_argument(
        "--last",
        "--lastdate",
        action="store_true",
        help="Conserver uniquement la ligne la plus recente (colonne derniere_mise_a_jour)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Ecrire la sortie au format JSON formate (indent=2)",
    )
    parser.add_argument(
        "--print-results",
        action="store_true",
        help="Afficher aussi les resultats dans la console",
    )
    parser.add_argument(
        "--stdout-only",
        action="store_true",
        help="Afficher uniquement les resultats dans stdout (sans logs/messages)",
    )
    parser.add_argument(
        "--output-mariadb",
        action="store_true",
        help="Ecrire les resultats dans MariaDB au lieu d'un fichier CSV/JSON",
    )
    parser.add_argument("--db-host", help="Hote MariaDB")
    parser.add_argument("--db-port", type=int, default=DEFAULT_DB_PORT, help="Port MariaDB (defaut: 3306)")
    parser.add_argument("--db-user", help="Utilisateur MariaDB")
    parser.add_argument("--db-password", help="Mot de passe MariaDB")
    parser.add_argument("--db-name", help="Nom de la base MariaDB cible")
    parser.add_argument("--db-table", help="Nom de la table MariaDB cible")
    parser.add_argument("--db-charset", default="utf8mb4", help="Charset MariaDB (defaut: utf8mb4)")
    parser.add_argument(
        "--db-connect-timeout",
        type=int,
        default=10,
        help="Timeout de connexion MariaDB en secondes (defaut: 10)",
    )
    parser.add_argument(
        "--test-db-connection",
        action="store_true",
        help="Teste la connexion MariaDB; sans requete quitte, avec requete continue l'extraction",
    )
    args = parser.parse_args()
    stdout_only = args.stdout_only

    if args.man:
        print(MANUAL_TEXT)
        return 0

    # Les options SQL sont validees le plus tot possible, y compris pour le mode test.
    db_config = None
    if args.output_mariadb or args.test_db_connection:
        try:
            db_config = build_db_config(args)
        except ValueError as exc:
            if not args.stdout_only:
                print(str(exc), file=sys.stderr)
            return -1

    if args.test_db_connection:
        try:
            test_mariadb_connection(db_config)
        except Exception as exc:  # noqa: BLE001
            if not args.stdout_only:
                print(f"Connexion MariaDB impossible: {exc}", file=sys.stderr)
            return -1
        if args.stdout_only:
            print("OK")
        else:
            print("[*] Connexion MariaDB OK", file=sys.stderr)

        # Sans requete, ce mode sert uniquement de verification de connectivite.
        if not args.query:
            return 0

    if not args.query:
        if not args.stdout_only:
            print("Argument manquant: fournir le texte de recherche en premier parametre.", file=sys.stderr)
        return -1

    if stdout_only:
        args.print_results = True

    if shutil.which("lynx") is None:
        if not stdout_only:
            print("Prerequis manquant: 'lynx' n'est pas installe sur le systeme.", file=sys.stderr)
        return -1

    debug_log(args.debug, f"Options: json={args.json}, last={args.last}, no_links={args.no_links}")

    if not stdout_only:
        print(f"[*] Recherche via lynx: {args.query}", file=sys.stderr)
    debug_log(args.debug, "Mode recherche selectionne: lynx (obligatoire)")

    # 1. Recuperation du HTML source du catalogue.
    page_html = fetch_search_html_with_lynx(args.query)
    if args.save_html:
        with open(args.save_html, "w", encoding="utf-8") as handle:
            handle.write(page_html)

    # 2. Parsing HTML vers une liste de dictionnaires normalises.
    rows = parse_rows(page_html)
    debug_log(args.debug, f"Lignes parsees avant filtres: {len(rows)}")
    if not rows:
        if not stdout_only:
            print("Aucune ligne de resultat detectee.", file=sys.stderr)
        return -1

    filter_regex_on_detail_field = bool(args.filter_regex and args.filter_field in DETAIL_ENRICHED_FIELDS)
    details_loaded = False

    # 3. Application des filtres dans un ordre fixe pour garder un comportement previsible.
    if args.filter_product:
        rows = filter_rows(rows, args.filter_product)
        if not rows:
            if not stdout_only:
                print(f"Aucune ligne ne correspond au produit: {args.filter_product}", file=sys.stderr)
            return -1
        if not stdout_only:
            print(f"[*] Filtre applique: {len(rows)} ligne(s) conservee(s)", file=sys.stderr)
        debug_log(args.debug, f"Filtre produit applique avec motif: {args.filter_product}")

    if args.filter_regex and not filter_regex_on_detail_field:
        try:
            rows = apply_regex_filter_option(
                rows,
                args.filter_regex,
                args.filter_field,
                f"le champ '{args.filter_field}'",
                stdout_only,
                args.debug,
            )
        except (ValueError, LookupError):
            return -1

    for pattern, field, label in [
        (args.title_regex, "titre", "le titre"),
        (args.classification_regex, "classification", "la classification"),
        (args.uuid_regex, "update_id", "l'UUID"),
    ]:
        try:
            rows = apply_regex_filter_option(rows, pattern, field, label, stdout_only, args.debug)
        except (ValueError, LookupError):
            return -1

    if args.uuid:
        rows = filter_rows_uuid(rows, args.uuid)
        if not rows:
            if not stdout_only:
                print(f"Aucune ligne ne correspond a l'UUID exact: {args.uuid}", file=sys.stderr)
            return -1
        if not stdout_only:
            print(f"[*] Filtre UUID exact applique: {len(rows)} ligne(s) conservee(s)", file=sys.stderr)
        debug_log(args.debug, f"UUID exact utilise: {args.uuid}")

    if args.fromdate or args.todate:
        try:
            from_date = parse_catalog_date(args.fromdate) if args.fromdate else None
            to_date = parse_catalog_date(args.todate) if args.todate else None
        except ValueError as exc:
            if not stdout_only:
                print(f"Date invalide: {exc}", file=sys.stderr)
            return -1

        if from_date and to_date and from_date > to_date:
            if not stdout_only:
                print("Intervalle de dates invalide: fromdate est posterieure a todate.", file=sys.stderr)
            return -1

        rows = filter_rows_by_date_range(rows, from_date, to_date)
        if not rows:
            if not stdout_only:
                print("Aucune ligne ne correspond a l'intervalle de dates demande.", file=sys.stderr)
            return -1
        if not stdout_only:
            print(f"[*] Filtre de date applique: {len(rows)} ligne(s) conservee(s)", file=sys.stderr)
        debug_log(args.debug, f"Filtre date applique: from={args.fromdate}, to={args.todate}")

    if filter_regex_on_detail_field or args.only_empty_supersededby:
        enrich_with_details(rows)
        details_loaded = True
        debug_log(args.debug, "Enrichissement detail active avant filtrage sur champs detail")

    if args.filter_regex and filter_regex_on_detail_field:
        try:
            rows = apply_regex_filter_option(
                rows,
                args.filter_regex,
                args.filter_field,
                f"le champ '{args.filter_field}'",
                stdout_only,
                args.debug,
            )
        except (ValueError, LookupError):
            return -1

    if args.only_empty_supersededby:
        rows = filter_rows_empty_supersededby(rows)
        if not rows:
            if not stdout_only:
                print("Aucune ligne ne correspond a un supersededby vide.", file=sys.stderr)
            return -1
        if not stdout_only:
            print(
                f"[*] Filtre supersededby vide applique: {len(rows)} ligne(s) conservee(s)",
                file=sys.stderr,
            )
        debug_log(args.debug, "Filtre supersededby vide applique")

    if args.last:
        rows = select_latest_row(rows)
        if not rows:
            if not stdout_only:
                print(
                    "Impossible d'appliquer --last: aucune date exploitable dans 'derniere_mise_a_jour'.",
                    file=sys.stderr,
                )
            return -1
        if not stdout_only:
            print("[*] Option --last appliquee: 1 ligne conservee", file=sys.stderr)
        debug_log(args.debug, "Selection de la ligne la plus recente terminee")

    rows = sort_rows_by_date_desc(rows)
    debug_log(args.debug, "Tri par date decroissante applique avant export")

    if args.limit is not None:
        if args.limit <= 0:
            if not stdout_only:
                print("Valeur invalide pour --limit: utiliser un entier > 0.", file=sys.stderr)
            return -1
        rows = rows[: args.limit]
        if not rows:
            if not stdout_only:
                print("Aucune ligne restante apres application de --limit.", file=sys.stderr)
            return -1
        if not stdout_only:
            print(f"[*] Limite appliquee: {len(rows)} ligne(s) conservee(s)", file=sys.stderr)
        debug_log(args.debug, f"Limite demandee: {args.limit}")

    if args.with_details and not details_loaded:
        enrich_with_details(rows)
        details_loaded = True
        debug_log(args.debug, "Enrichissement via les fiches detail termine")

    if not args.no_links:
        # Cette etape est volontairement tardive pour eviter des appels reseau inutiles sur des lignes deja filtrees.
        enrich_with_links(rows)

    # 4. Export final vers base ou fichier.
    destination_label = ""
    if args.output_mariadb:
        try:
            write_output_to_mariadb(rows, db_config)
        except Exception as exc:  # noqa: BLE001
            if not stdout_only:
                print(f"Echec export MariaDB: {exc}", file=sys.stderr)
            return -1
        destination_label = f"{db_config['database']}.{db_config['table']}"
        debug_log(args.debug, f"Export MariaDB termine: {destination_label}")
    else:
        output_path = resolve_output_path(args.output, args.json)

        if stdout_only:
            destination_label = "stdout"
            debug_log(args.debug, "Mode stdout-only: aucune ecriture fichier")
        else:
            write_output(rows, args.json, output_path)
            destination_label = output_path
            debug_log(args.debug, f"Fichier ecrit: {output_path}")

    if args.print_results:
        if stdout_only:
            print_results_raw(rows, args.json)
        else:
            print_results(rows, args.json)
        debug_log(args.debug, "Affichage console des resultats termine")

    if not stdout_only:
        print(f"Extraction terminee: {len(rows)} ligne(s) -> {destination_label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
