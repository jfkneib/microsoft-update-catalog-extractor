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
import io
import json
import re
import shutil
import sys
import urllib.parse
import urllib.request
from typing import Dict, List


SEARCH_URL = "https://www.catalog.update.microsoft.com/Search.aspx"
DOWNLOAD_DIALOG_URL = "https://www.catalog.update.microsoft.com/DownloadDialog.aspx"
DEFAULT_OUTPUT_CSV = "/home/jfk/catalog_windows_security_platform.csv"
DEFAULT_OUTPUT_JSON = "/home/jfk/catalog_windows_security_platform.json"


MANUAL_TEXT = """\
NOM
    extraction.py - Extrait des resultats du Microsoft Update Catalog vers CSV

DESCRIPTION
    Cet utilitaire recupere une page de resultats du Microsoft Update Catalog,
    extrait les colonnes utiles, applique des filtres optionnels, puis exporte
    un fichier CSV.

    Colonnes exportees:
        - titre
        - produit
        - classification
        - derniere_mise_a_jour
        - version
        - taille
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
        Valeurs: titre, produit, classification, derniere_mise_a_jour, version, taille, update_id

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

    --save-html fichier.html
        Sauvegarde le HTML recupere.

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
"""


def debug_log(enabled: bool, message: str) -> None:
    """Affiche un message de debug sur stderr si le mode debug est actif."""
    if enabled:
        print(f"[DEBUG] {message}", file=sys.stderr)


def clean_text(raw: str) -> str:
    """Nettoie un fragment HTML en texte lisible sur une seule ligne."""
    # Supprime les balises HTML puis normalise les espaces.
    text = re.sub(r"<[^>]+>", "", raw, flags=re.S)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_rows(page_html: str) -> List[Dict[str, str]]:
    """Extrait les lignes de resultats depuis le HTML de la page catalogue."""
    row_re = re.compile(r'<tr id="([0-9a-f\-]+)_R\d+">(.*?)</tr>', re.S | re.I)

    def extract_cell(row_uid: str, col: int, row_html: str) -> str:
        """Recupere le contenu texte d'une cellule de colonne donnee."""
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
        size_m = re.search(
            rf'<span id="{re.escape(uid)}_size">(.*?)</span>',
            row_html,
            re.S | re.I,
        )

        # Construit un enregistrement normalise pour le CSV final.
        record = {
            "update_id": uid,
            "titre": extract_cell(uid, 1, row_html),
            "produit": extract_cell(uid, 2, row_html),
            "classification": extract_cell(uid, 3, row_html),
            "derniere_mise_a_jour": extract_cell(uid, 4, row_html),
            "version": extract_cell(uid, 5, row_html),
            "taille": clean_text(size_m.group(1)) if size_m else extract_cell(uid, 6, row_html),
        }

        if record["titre"]:
            rows.append(record)

    return rows


def fetch_search_html(query: str, timeout: int = 30) -> str:
    """Telecharge la page de recherche via requete HTTP simple (sans lynx)."""
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
    """Telecharge la page de recherche en passant par lynx."""
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
    """Recupere le premier lien de telechargement direct pour une mise a jour."""
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
    """Filtre les lignes dont le champ produit contient un texte (insensible a la casse)."""
    needle = product_name.strip().lower()
    return [r for r in rows if needle in r.get("produit", "").strip().lower()]


def filter_rows_regex(rows: List[Dict[str, str]], pattern: str, field: str = "produit") -> List[Dict[str, str]]:
    """Filtre les lignes avec une regex appliquee sur un champ donne."""
    regex = re.compile(pattern, re.I)
    return [r for r in rows if regex.search(r.get(field, "") or "")]


def filter_rows_uuid(rows: List[Dict[str, str]], uuid_value: str) -> List[Dict[str, str]]:
    """Filtre les lignes sur un UUID exact (champ update_id)."""
    needle = uuid_value.strip().lower()
    return [r for r in rows if (r.get("update_id", "") or "").strip().lower() == needle]


def parse_catalog_date(raw_date: str) -> datetime.date:
    """Convertit une date catalogue en objet date."""
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
    """Conserve les lignes dont la date est comprise dans l'intervalle demande."""
    filtered_rows: List[Dict[str, str]] = []
    for row in rows:
        try:
            row_date = parse_catalog_date(row.get("derniere_mise_a_jour", ""))
        except (ValueError, TypeError):
            continue

        if from_date and row_date < from_date:
            continue
        if to_date and row_date > to_date:
            continue
        filtered_rows.append(row)

    return filtered_rows


def select_latest_row(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Retourne uniquement la ligne avec la date la plus recente."""
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
    """Trie les lignes par date decroissante; les dates invalides sont en fin."""
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
    """Ajoute un lien de telechargement direct pour chaque ligne."""
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


def write_csv(rows: List[Dict[str, str]], output_path: str) -> None:
    """Ecrit les resultats dans un CSV avec un ordre de colonnes stable."""
    csv_content = render_csv(rows)
    with open(output_path, "w", newline="", encoding="utf-8") as handle:
        handle.write(csv_content)


def render_csv(rows: List[Dict[str, str]]) -> str:
    """Construit le rendu CSV en texte pour reutilisation (fichier/console)."""
    fields = [
        "titre",
        "produit",
        "classification",
        "derniere_mise_a_jour",
        "version",
        "taille",
        "update_id",
        "lien_telechargement",
    ]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def write_json(rows: List[Dict[str, str]], output_path: str) -> None:
    """Ecrit les resultats dans un JSON lisible (pretty print)."""
    with open(output_path, "w", encoding="utf-8") as handle:
        handle.write(render_json(rows))


def render_json(rows: List[Dict[str, str]]) -> str:
    """Construit le rendu JSON en texte pour reutilisation (fichier/console)."""
    return json.dumps(rows, ensure_ascii=False, indent=2) + "\n"


def print_results(rows: List[Dict[str, str]], as_json: bool) -> None:
    """Affiche les resultats dans la console au format choisi."""
    print("--- RESULTATS ---")
    if as_json:
        print(render_json(rows), end="")
    else:
        print(render_csv(rows), end="")


def print_results_raw(rows: List[Dict[str, str]], as_json: bool) -> None:
    """Affiche uniquement les donnees de resultat, sans texte annexe."""
    if as_json:
        print(render_json(rows), end="")
    else:
        print(render_csv(rows), end="")


def write_output(rows: List[Dict[str, str]], as_json: bool, output_path: str) -> None:
    """Ecrit les resultats au format CSV ou JSON selon les options."""
    if as_json:
        write_json(rows, output_path)
    else:
        write_csv(rows, output_path)


def apply_regex_filter_option(
    rows: List[Dict[str, str]],
    pattern: str | None,
    field: str,
    label: str,
    stdout_only: bool,
    debug_enabled: bool,
) -> List[Dict[str, str]]:
    """Applique un filtre regex optionnel avec gestion des erreurs et logs."""
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
    """Point d'entree CLI: lit les options, extrait, filtre et exporte le CSV."""
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
            "  python3 extraction.py \"Windows Security platform\" --filter-product \"Windows Security platform\" --last --print-results --output search_last.csv --no-links\n"
            "  python3 extraction.py \"Windows Security platform\" --save-html search_lynx.html"
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
        choices=["titre", "produit", "classification", "derniere_mise_a_jour", "version", "taille", "update_id"],
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
    parser.add_argument("--output", default=DEFAULT_OUTPUT_CSV, help="Chemin du fichier de sortie (CSV ou JSON)")
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
    args = parser.parse_args()

    if args.man:
        print(MANUAL_TEXT)
        return 0

    if not args.query:
        if not args.stdout_only:
            print("Argument manquant: fournir le texte de recherche en premier parametre.", file=sys.stderr)
        return -1

    stdout_only = args.stdout_only
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
    page_html = fetch_search_html_with_lynx(args.query)
    if args.save_html:
        with open(args.save_html, "w", encoding="utf-8") as handle:
            handle.write(page_html)

    rows = parse_rows(page_html)
    debug_log(args.debug, f"Lignes parsees avant filtres: {len(rows)}")
    if not rows:
        if not stdout_only:
            print("Aucune ligne de resultat detectee.", file=sys.stderr)
        return -1

    if args.filter_product:
        rows = filter_rows(rows, args.filter_product)
        if not rows:
            if not stdout_only:
                print(f"Aucune ligne ne correspond au produit: {args.filter_product}", file=sys.stderr)
            return -1
        if not stdout_only:
            print(f"[*] Filtre applique: {len(rows)} ligne(s) conservee(s)", file=sys.stderr)
        debug_log(args.debug, f"Filtre produit applique avec motif: {args.filter_product}")

    if args.filter_regex:
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

    if not args.no_links:
        enrich_with_links(rows)

    output_path = args.output
    if args.json and output_path == DEFAULT_OUTPUT_CSV:
        output_path = DEFAULT_OUTPUT_JSON

    write_output(rows, args.json, output_path)
    debug_log(args.debug, f"Fichier ecrit: {output_path}")

    if args.print_results:
        if stdout_only:
            print_results_raw(rows, args.json)
        else:
            print_results(rows, args.json)
        debug_log(args.debug, "Affichage console des resultats termine")

    if not stdout_only:
        print(f"Extraction terminee: {len(rows)} ligne(s) -> {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
