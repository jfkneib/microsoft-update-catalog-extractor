import tempfile
import unittest
import os
import shutil
from pathlib import Path
from unittest import mock
from io import StringIO
import json

import extraction


SAMPLE_HTML = '''
<table>
  <tr id="11111111-1111-1111-1111-111111111111_R1">
    <td id="11111111-1111-1111-1111-111111111111_C1_R1">Security Intelligence Update</td>
    <td id="11111111-1111-1111-1111-111111111111_C2_R1">Windows Security platform and Defender</td>
    <td id="11111111-1111-1111-1111-111111111111_C3_R1">Definition Updates</td>
    <td id="11111111-1111-1111-1111-111111111111_C4_R1">2026-04-02</td>
    <td id="11111111-1111-1111-1111-111111111111_C5_R1">1.0</td>
    <td id="11111111-1111-1111-1111-111111111111_C6_R1">123 MB</td>
  </tr>
  <tr id="22222222-2222-2222-2222-222222222222_R1">
    <td id="22222222-2222-2222-2222-222222222222_C1_R1">Other Update</td>
    <td id="22222222-2222-2222-2222-222222222222_C2_R1">Windows 11</td>
    <td id="22222222-2222-2222-2222-222222222222_C3_R1">Security Updates</td>
    <td id="22222222-2222-2222-2222-222222222222_C4_R1">2026-04-01</td>
    <td id="22222222-2222-2222-2222-222222222222_C5_R1">2.0</td>
    <td id="22222222-2222-2222-2222-222222222222_C6_R1">456 MB</td>
  </tr>
</table>
'''

SAMPLE_HTML_UNSORTED_DATES = '''
<table>
    <tr id="aaaaaaaa-1111-1111-1111-111111111111_R1">
        <td id="aaaaaaaa-1111-1111-1111-111111111111_C1_R1">Older Update</td>
        <td id="aaaaaaaa-1111-1111-1111-111111111111_C2_R1">Windows Security platform</td>
        <td id="aaaaaaaa-1111-1111-1111-111111111111_C3_R1">Definition Updates</td>
        <td id="aaaaaaaa-1111-1111-1111-111111111111_C4_R1">1/8/2025</td>
        <td id="aaaaaaaa-1111-1111-1111-111111111111_C5_R1">n/a</td>
        <td id="aaaaaaaa-1111-1111-1111-111111111111_C6_R1">37.6 MB</td>
    </tr>
    <tr id="bbbbbbbb-2222-2222-2222-222222222222_R1">
        <td id="bbbbbbbb-2222-2222-2222-222222222222_C1_R1">Newest Update</td>
        <td id="bbbbbbbb-2222-2222-2222-222222222222_C2_R1">Windows Security platform</td>
        <td id="bbbbbbbb-2222-2222-2222-222222222222_C3_R1">Definition Updates</td>
        <td id="bbbbbbbb-2222-2222-2222-222222222222_C4_R1">2/26/2026</td>
        <td id="bbbbbbbb-2222-2222-2222-222222222222_C5_R1">n/a</td>
        <td id="bbbbbbbb-2222-2222-2222-222222222222_C6_R1">44.0 MB</td>
    </tr>
</table>
'''


class ExtractionTests(unittest.TestCase):
    def test_main_man_option_prints_manual(self):
        """Verifie que --man affiche le manuel detaille et quitte avec succes."""
        argv = ["extraction.py", "--man"]
        with mock.patch("sys.argv", argv):
            with mock.patch("sys.stdout", new_callable=StringIO) as fake_out:
                exit_code = extraction.main()

        self.assertEqual(exit_code, 0)
        manual = fake_out.getvalue()
        self.assertIn("NOM", manual)
        self.assertIn("EXEMPLES", manual)

    def test_filter_rows_contains_case_insensitive(self):
        """Verifie que le filtre produit fonctionne en mode contient sans casse."""
        rows = [
            {"produit": "Windows Security platform and Defender", "titre": "a", "update_id": "1"},
            {"produit": "Windows 11", "titre": "b", "update_id": "2"},
        ]

        filtered = extraction.filter_rows(rows, "windows security platform")

        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["update_id"], "1")

    def test_main_search_with_lynx_and_filter_product_contains(self):
        """Teste le flux CLI lynx + filtre produit contient + generation CSV."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "result.csv"
            argv = [
                "extraction.py",
                "Windows Security platform",
                "--filter-product",
                "Windows Security platform",
                "--output",
                str(output_path),
                "--no-links",
            ]

            # Mock pour eviter les appels reseau pendant les tests.
            with mock.patch("sys.argv", argv):
                with mock.patch("shutil.which", return_value="/usr/bin/lynx"):
                    with mock.patch.object(extraction, "fetch_search_html_with_lynx", return_value=SAMPLE_HTML):
                        exit_code = extraction.main()

            self.assertEqual(exit_code, 0)
            self.assertTrue(output_path.exists())

            content = output_path.read_text(encoding="utf-8")
            self.assertIn("Security Intelligence Update", content)
            self.assertIn("Windows Security platform and Defender", content)
            self.assertNotIn("Other Update", content)

    def test_filter_rows_regex_on_product(self):
        """Verifie que le filtre regex selectionne uniquement les lignes attendues."""
        rows = [
            {"produit": "Windows Security platform and Defender", "titre": "a", "update_id": "1"},
            {"produit": "Windows 11", "titre": "b", "update_id": "2"},
        ]

        filtered = extraction.filter_rows_regex(rows, r"security\s+platform|defender", "produit")

        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["update_id"], "1")

    def test_filter_rows_uuid_exact(self):
        """Verifie le filtre exact sur l'UUID."""
        rows = [
            {"update_id": "11111111-1111-1111-1111-111111111111", "titre": "a"},
            {"update_id": "22222222-2222-2222-2222-222222222222", "titre": "b"},
        ]

        filtered = extraction.filter_rows_uuid(rows, "11111111-1111-1111-1111-111111111111")

        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["update_id"], "11111111-1111-1111-1111-111111111111")

    def test_select_latest_row(self):
        """Verifie la selection de la ligne la plus recente sur la date catalogue."""
        rows = [
            {"derniere_mise_a_jour": "1/8/2025", "update_id": "old", "titre": "Old"},
            {"derniere_mise_a_jour": "2/26/2026", "update_id": "new", "titre": "New"},
        ]

        latest = extraction.select_latest_row(rows)

        self.assertEqual(len(latest), 1)
        self.assertEqual(latest[0]["update_id"], "new")

    def test_parse_catalog_date_accepts_iso_and_us_formats(self):
        """Verifie que le parsing accepte les formats ISO et US."""
        self.assertEqual(str(extraction.parse_catalog_date("2026-04-02")), "2026-04-02")
        self.assertEqual(str(extraction.parse_catalog_date("2/26/2026")), "2026-02-26")

    def test_filter_rows_by_date_range(self):
        """Verifie le filtrage par intervalle de dates."""
        rows = [
            {"derniere_mise_a_jour": "2026-04-02", "update_id": "new", "titre": "New"},
            {"derniere_mise_a_jour": "2026-04-01", "update_id": "old", "titre": "Old"},
        ]

        filtered = extraction.filter_rows_by_date_range(
            rows,
            extraction.parse_catalog_date("2026-04-02"),
            extraction.parse_catalog_date("2026-04-02"),
        )

        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["update_id"], "new")

    def test_sort_rows_by_date_desc(self):
        """Verifie le tri decroissant sur la date de mise a jour."""
        rows = [
            {"derniere_mise_a_jour": "2026-04-01", "update_id": "old", "titre": "Old"},
            {"derniere_mise_a_jour": "2026-04-02", "update_id": "new", "titre": "New"},
        ]

        sorted_rows = extraction.sort_rows_by_date_desc(rows)

        self.assertEqual(sorted_rows[0]["update_id"], "new")
        self.assertEqual(sorted_rows[1]["update_id"], "old")

    def test_main_search_with_lynx_and_filter_regex(self):
        """Teste le flux CLI lynx + filtre regex sur le champ produit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "result_regex.csv"
            argv = [
                "extraction.py",
                "Windows Security platform",
                "--filter-regex",
                r"Windows Security platform|Defender",
                "--filter-field",
                "produit",
                "--output",
                str(output_path),
                "--no-links",
            ]

            # Mock pour verifier la logique de filtrage sans dependre du site.
            with mock.patch("sys.argv", argv):
                with mock.patch("shutil.which", return_value="/usr/bin/lynx"):
                    with mock.patch.object(extraction, "fetch_search_html_with_lynx", return_value=SAMPLE_HTML):
                        exit_code = extraction.main()

            self.assertEqual(exit_code, 0)
            content = output_path.read_text(encoding="utf-8")
            self.assertIn("Security Intelligence Update", content)
            self.assertNotIn("Other Update", content)

    def test_main_search_with_last_keeps_only_latest(self):
        """Teste que --last conserve uniquement la ligne avec la date la plus recente."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "result_last.csv"
            argv = [
                "extraction.py",
                "Windows Security platform",
                "--filter-product",
                "Windows Security platform",
                "--last",
                "--output",
                str(output_path),
                "--no-links",
            ]

            with mock.patch("sys.argv", argv):
                with mock.patch("shutil.which", return_value="/usr/bin/lynx"):
                    with mock.patch.object(extraction, "fetch_search_html_with_lynx", return_value=SAMPLE_HTML_UNSORTED_DATES):
                        exit_code = extraction.main()

            self.assertEqual(exit_code, 0)
            content = output_path.read_text(encoding="utf-8")
            self.assertIn("Newest Update", content)
            self.assertNotIn("Older Update", content)
            self.assertEqual(len(content.strip().splitlines()), 2)

    def test_main_search_with_lastdate_alias_keeps_only_latest(self):
        """Teste que --lastdate agit comme alias de --last."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "result_lastdate.csv"
            argv = [
                "extraction.py",
                "Windows Security platform",
                "--filter-product",
                "Windows Security platform",
                "--lastdate",
                "--output",
                str(output_path),
                "--no-links",
            ]

            with mock.patch("sys.argv", argv):
                with mock.patch("shutil.which", return_value="/usr/bin/lynx"):
                    with mock.patch.object(extraction, "fetch_search_html_with_lynx", return_value=SAMPLE_HTML_UNSORTED_DATES):
                        exit_code = extraction.main()

            self.assertEqual(exit_code, 0)
            content = output_path.read_text(encoding="utf-8")
            self.assertIn("Newest Update", content)
            self.assertNotIn("Older Update", content)

    def test_main_search_with_fromdate_and_todate_filters_rows(self):
        """Teste le filtrage CLI par plage de dates."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "result_daterange.csv"
            argv = [
                "extraction.py",
                "Windows Security platform",
                "--fromdate",
                "2026-04-02",
                "--todate",
                "2026-04-02",
                "--output",
                str(output_path),
                "--no-links",
            ]

            with mock.patch("sys.argv", argv):
                with mock.patch("shutil.which", return_value="/usr/bin/lynx"):
                    with mock.patch.object(extraction, "fetch_search_html_with_lynx", return_value=SAMPLE_HTML):
                        exit_code = extraction.main()

            self.assertEqual(exit_code, 0)
            content = output_path.read_text(encoding="utf-8")
            self.assertIn("Security Intelligence Update", content)
            self.assertNotIn("Other Update", content)

    def test_main_search_with_title_regex_filters_rows(self):
        """Teste le filtre regex dedie sur le titre."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "result_title.csv"
            argv = [
                "extraction.py",
                "Windows Security platform",
                "--title-regex",
                "Security Intelligence",
                "--output",
                str(output_path),
                "--no-links",
            ]

            with mock.patch("sys.argv", argv):
                with mock.patch("shutil.which", return_value="/usr/bin/lynx"):
                    with mock.patch.object(extraction, "fetch_search_html_with_lynx", return_value=SAMPLE_HTML):
                        exit_code = extraction.main()

            self.assertEqual(exit_code, 0)
            content = output_path.read_text(encoding="utf-8")
            self.assertIn("Security Intelligence Update", content)
            self.assertNotIn("Other Update", content)

    def test_main_search_with_classification_regex_filters_rows(self):
        """Teste le filtre regex dedie sur la classification."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "result_classification.csv"
            argv = [
                "extraction.py",
                "Windows Security platform",
                "--classification-regex",
                "Definition Updates",
                "--output",
                str(output_path),
                "--no-links",
            ]

            with mock.patch("sys.argv", argv):
                with mock.patch("shutil.which", return_value="/usr/bin/lynx"):
                    with mock.patch.object(extraction, "fetch_search_html_with_lynx", return_value=SAMPLE_HTML):
                        exit_code = extraction.main()

            self.assertEqual(exit_code, 0)
            content = output_path.read_text(encoding="utf-8")
            self.assertIn("Security Intelligence Update", content)
            self.assertNotIn("Other Update", content)

    def test_main_search_with_uuid_regex_filters_rows(self):
        """Teste le filtre regex dedie sur l'UUID."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "result_uuid.csv"
            argv = [
                "extraction.py",
                "Windows Security platform",
                "--uuid-regex",
                r"^11111111-1111-1111-1111-111111111111$",
                "--output",
                str(output_path),
                "--no-links",
            ]

            with mock.patch("sys.argv", argv):
                with mock.patch("shutil.which", return_value="/usr/bin/lynx"):
                    with mock.patch.object(extraction, "fetch_search_html_with_lynx", return_value=SAMPLE_HTML):
                        exit_code = extraction.main()

            self.assertEqual(exit_code, 0)
            content = output_path.read_text(encoding="utf-8")
            self.assertIn("11111111-1111-1111-1111-111111111111", content)
            self.assertNotIn("22222222-2222-2222-2222-222222222222", content)

    def test_main_search_with_uuid_exact_filters_rows(self):
        """Teste le filtre exact dedie sur l'UUID."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "result_uuid_exact.csv"
            argv = [
                "extraction.py",
                "Windows Security platform",
                "--uuid",
                "11111111-1111-1111-1111-111111111111",
                "--output",
                str(output_path),
                "--no-links",
            ]

            with mock.patch("sys.argv", argv):
                with mock.patch("shutil.which", return_value="/usr/bin/lynx"):
                    with mock.patch.object(extraction, "fetch_search_html_with_lynx", return_value=SAMPLE_HTML):
                        exit_code = extraction.main()

            self.assertEqual(exit_code, 0)
            content = output_path.read_text(encoding="utf-8")
            self.assertIn("11111111-1111-1111-1111-111111111111", content)
            self.assertNotIn("22222222-2222-2222-2222-222222222222", content)

    def test_main_output_is_sorted_by_date_desc(self):
        """Teste que la sortie est triee par date decroissante avant export."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "result_sorted.csv"
            argv = [
                "extraction.py",
                "Windows Security platform",
                "--output",
                str(output_path),
                "--no-links",
            ]

            with mock.patch("sys.argv", argv):
                with mock.patch("shutil.which", return_value="/usr/bin/lynx"):
                    with mock.patch.object(extraction, "fetch_search_html_with_lynx", return_value=SAMPLE_HTML_UNSORTED_DATES):
                        exit_code = extraction.main()

            self.assertEqual(exit_code, 0)
            lines = output_path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 3)
            self.assertIn("Newest Update", lines[1])
            self.assertIn("Older Update", lines[2])

    def test_main_limit_keeps_desired_number_of_results(self):
        """Teste que --limit conserve le nombre de resultats demande."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "result_limit.csv"
            argv = [
                "extraction.py",
                "Windows Security platform",
                "--limit",
                "1",
                "--output",
                str(output_path),
                "--no-links",
            ]

            with mock.patch("sys.argv", argv):
                with mock.patch("shutil.which", return_value="/usr/bin/lynx"):
                    with mock.patch.object(extraction, "fetch_search_html_with_lynx", return_value=SAMPLE_HTML_UNSORTED_DATES):
                        exit_code = extraction.main()

            self.assertEqual(exit_code, 0)
            lines = output_path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 2)
            self.assertIn("Newest Update", lines[1])

    def test_main_limit_invalid_returns_minus_one(self):
        """Verifie qu'une valeur <= 0 pour --limit retourne -1."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "result_limit_invalid.csv"
            argv = [
                "extraction.py",
                "Windows Security platform",
                "--limit",
                "0",
                "--output",
                str(output_path),
                "--no-links",
            ]

            with mock.patch("sys.argv", argv):
                with mock.patch("shutil.which", return_value="/usr/bin/lynx"):
                    with mock.patch.object(extraction, "fetch_search_html_with_lynx", return_value=SAMPLE_HTML):
                        exit_code = extraction.main()

            self.assertEqual(exit_code, -1)

    def test_main_invalid_fromdate_returns_minus_one(self):
        """Verifie qu'une date invalide retourne -1."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "result_invalid_date.csv"
            argv = [
                "extraction.py",
                "Windows Security platform",
                "--fromdate",
                "2026/04/02",
                "--output",
                str(output_path),
                "--no-links",
            ]

            with mock.patch("sys.argv", argv):
                with mock.patch("shutil.which", return_value="/usr/bin/lynx"):
                    with mock.patch.object(extraction, "fetch_search_html_with_lynx", return_value=SAMPLE_HTML):
                        exit_code = extraction.main()

            self.assertEqual(exit_code, -1)

    def test_main_search_with_json_output(self):
        """Teste l'export JSON formate avec l'option --json."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "result.json"
            argv = [
                "extraction.py",
                "Windows Security platform",
                "--filter-product",
                "Windows Security platform",
                "--json",
                "--output",
                str(output_path),
                "--no-links",
            ]

            with mock.patch("sys.argv", argv):
                with mock.patch("shutil.which", return_value="/usr/bin/lynx"):
                    with mock.patch.object(extraction, "fetch_search_html_with_lynx", return_value=SAMPLE_HTML):
                        exit_code = extraction.main()

            self.assertEqual(exit_code, 0)
            raw = output_path.read_text(encoding="utf-8")
            self.assertIn("\n  {", raw)
            payload = json.loads(raw)
            self.assertEqual(len(payload), 1)
            self.assertEqual(payload[0]["produit"], "Windows Security platform and Defender")

    def test_main_print_results_outputs_csv_to_console(self):
        """Verifie que --print-results affiche les donnees CSV dans la console."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "result.csv"
            argv = [
                "extraction.py",
                "Windows Security platform",
                "--filter-product",
                "Windows Security platform",
                "--print-results",
                "--output",
                str(output_path),
                "--no-links",
            ]

            with mock.patch("sys.argv", argv):
                with mock.patch("shutil.which", return_value="/usr/bin/lynx"):
                    with mock.patch.object(extraction, "fetch_search_html_with_lynx", return_value=SAMPLE_HTML):
                        with mock.patch("sys.stdout", new_callable=StringIO) as fake_out:
                                exit_code = extraction.main()

            self.assertEqual(exit_code, 0)
            console = fake_out.getvalue()
            self.assertIn("--- RESULTATS ---", console)
            self.assertIn("titre,produit,classification", console)
            self.assertIn("Windows Security platform and Defender", console)

    def test_main_debug_prints_debug_lines(self):
        """Verifie que -d affiche des informations de debug sur stderr."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "result.csv"
            argv = [
                "extraction.py",
                "-d",
                "Windows Security platform",
                "--filter-product",
                "Windows Security platform",
                "--output",
                str(output_path),
                "--no-links",
            ]

            with mock.patch("sys.argv", argv):
                with mock.patch("shutil.which", return_value="/usr/bin/lynx"):
                    with mock.patch.object(extraction, "fetch_search_html_with_lynx", return_value=SAMPLE_HTML):
                        with mock.patch("sys.stderr", new_callable=StringIO) as fake_err:
                                exit_code = extraction.main()

            self.assertEqual(exit_code, 0)
            err = fake_err.getvalue()
            self.assertIn("[DEBUG]", err)
            self.assertIn("Mode recherche selectionne: lynx", err)

    def test_main_stdout_only_prints_only_payload(self):
        """Verifie que --stdout-only n'affiche que les donnees de resultat."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "result.csv"
            argv = [
                "extraction.py",
                "Windows Security platform",
                "--filter-product",
                "Windows Security platform",
                "--stdout-only",
                "--output",
                str(output_path),
                "--no-links",
            ]

            with mock.patch("sys.argv", argv):
                with mock.patch("shutil.which", return_value="/usr/bin/lynx"):
                    with mock.patch.object(extraction, "fetch_search_html_with_lynx", return_value=SAMPLE_HTML):
                        with mock.patch("sys.stdout", new_callable=StringIO) as fake_out:
                            with mock.patch("sys.stderr", new_callable=StringIO) as fake_err:
                                exit_code = extraction.main()

            self.assertEqual(exit_code, 0)
            self.assertEqual(fake_err.getvalue(), "")
            out = fake_out.getvalue()
            self.assertIn("titre,produit,classification", out)
            self.assertIn("Windows Security platform and Defender", out)
            self.assertNotIn("--- RESULTATS ---", out)
            self.assertNotIn("Extraction terminee", out)

    def test_main_invalid_regex_returns_minus_one(self):
        """Verifie qu'une regex invalide retourne -1."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "result.csv"
            argv = [
                "extraction.py",
                "Windows Security platform",
                "--filter-regex",
                "(invalid",
                "--output",
                str(output_path),
                "--no-links",
            ]

            with mock.patch("sys.argv", argv):
                with mock.patch("shutil.which", return_value="/usr/bin/lynx"):
                    with mock.patch.object(extraction, "fetch_search_html_with_lynx", return_value=SAMPLE_HTML):
                        exit_code = extraction.main()

            self.assertEqual(exit_code, -1)

    def test_main_requires_query_argument(self):
        """Verifie que l'argument positionnel de recherche est obligatoire."""
        argv = [
            "extraction.py",
            "--no-links",
        ]

        with mock.patch("sys.argv", argv):
            with mock.patch("sys.stderr", new_callable=StringIO) as fake_err:
                exit_code = extraction.main()

        self.assertEqual(exit_code, -1)
        self.assertIn("Argument manquant", fake_err.getvalue())

    def test_main_requires_lynx_installed(self):
        """Verifie qu'une absence de lynx est bloquante."""
        argv = [
            "extraction.py",
            "Windows Security platform",
            "--no-links",
        ]

        with mock.patch("sys.argv", argv):
            with mock.patch("shutil.which", return_value=None):
                with mock.patch("sys.stderr", new_callable=StringIO) as fake_err:
                    exit_code = extraction.main()

            self.assertEqual(exit_code, -1)
            self.assertIn("Prerequis manquant", fake_err.getvalue())


@unittest.skipUnless(
    os.getenv("RUN_INTEGRATION_TESTS") == "1",
    "Set RUN_INTEGRATION_TESTS=1 to run integration tests.",
)
class ExtractionIntegrationTests(unittest.TestCase):
    REAL_UPDATE_CASES = [
        {"uuid": "0a9269d1-df26-4ba0-bb32-bfd66bf757d6", "kb": "5066835"},
        {"uuid": "15af37fd-f46c-4524-8354-1781437c82ee", "kb": "5068861"},
        {"uuid": "1aeb2be2-332e-4950-834f-256e9c75dee9", "kb": "5043080"},
        {"uuid": "22053fe8-307c-47b5-a555-8da7504fba6a", "kb": "5062553"},
        {"uuid": "228b85fe-66e2-4275-ae78-15286bee570b", "kb": "5044284"},
        {"uuid": "289bda65-76ed-4cfa-bcd7-c527201cce35", "kb": "5046617"},
        {"uuid": "30129e59-e337-4f94-81bc-8381d60c67a8", "kb": "5065426"},
        {"uuid": "316f203d-4a46-49c9-a393-cb2601829dbe", "kb": "5063878"},
        {"uuid": "3905e2b3-c431-4caf-81e9-ae3fb4425ed9", "kb": "5050009"},
        {"uuid": "5a198e6e-901a-451a-8ed4-eaf976d04470", "kb": "5053598"},
        {"uuid": "6195095d-cdaa-4dea-b370-0e47cf0d4991", "kb": "5074109"},
        {"uuid": "82080fc5-05ce-4083-bf79-d2359dcae6a4", "kb": "5077181"},
        {"uuid": "8f9b7ab8-5a4d-426d-8371-122b27447a0e", "kb": "5060842"},
        {"uuid": "916b960f-8cde-4b62-ba8a-3beba5b7559b", "kb": "5041571"},
        {"uuid": "98e2ba2f-494e-4449-9e17-390cb89e8290", "kb": "5039239"},
        {"uuid": "9d24a965-8f52-4930-888a-7a54796e3012", "kb": "5072033"},
        {"uuid": "c5c17f20-cf2a-41db-9176-15abdc1f931f", "kb": "5079473"},
        {"uuid": "d293841f-7bad-4148-9703-e457ab2e3535", "kb": "5055523"},
        {"uuid": "de002081-6cd0-47c4-839a-47ed9556834c", "kb": "5048667"},
        {"uuid": "e6a5d4f1-f84b-4579-bb50-e238fae3f1f9", "kb": "5051987"},
        {"uuid": "e90ded07-5246-4e91-a25d-4f7ead8facde", "kb": "5040435"},
        {"uuid": "ee07c0af-2005-4824-854f-3701e2e4b44d", "kb": "5058411"},
    ]

    def _run_real_catalog_query(self, kb):
        """Execute le script en conditions reelles pour un KB catalogue donne."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "integration_real_catalog.csv"
            argv = [
                "extraction.py",
                f"KB{kb}",
                "--filter-product",
                "Windows 11",
                "--classification-regex",
                "^security updates$",
                "--title-regex",
                f"KB{kb}",
                "--limit",
                "1",
                "--output",
                str(output_path),
                "--no-links",
            ]

            with mock.patch("sys.argv", argv):
                exit_code = extraction.main()

            self.assertEqual(exit_code, 0)
            self.assertTrue(output_path.exists())
            return output_path.read_text(encoding="utf-8")

    def test_end_to_end_real_catalog_query(self):
        """Teste un cas reel contre le Microsoft Update Catalog (reseau + lynx)."""
        if shutil.which("lynx") is None:
            self.skipTest("lynx non installe sur cette machine")

        smoke_case = self.REAL_UPDATE_CASES[0]
        content = self._run_real_catalog_query(smoke_case["kb"])
        self.assertIn("titre,produit,classification", content)
        self.assertIn(f"KB{smoke_case['kb']}", content)
        self.assertIn("windows 11", content.lower())
        self.assertIn("security updates", content.lower())

    def test_real_catalog_known_uuids(self):
        """Valide la liste d'UUID reels fournis pour Windows 11 24H2."""
        if shutil.which("lynx") is None:
            self.skipTest("lynx non installe sur cette machine")

        for case in self.REAL_UPDATE_CASES:
            with self.subTest(uuid=case["uuid"], kb=case["kb"]):
                content = self._run_real_catalog_query(case["kb"])
                self.assertIn("titre,produit,classification", content)
                self.assertIn(f"KB{case['kb']}", content)
                self.assertIn("windows 11", content.lower())
                self.assertIn("security updates", content.lower())


if __name__ == "__main__":
    unittest.main()
