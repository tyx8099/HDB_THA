"""Focused checks for the January reference rule and row preservation."""

import csv
import tempfile
import unittest
from datetime import date
from pathlib import Path

from combine import combine


class CombineTest(unittest.TestCase):
    def test_reference_values_quarantine_only_unseen_categories(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "raw"
            raw.mkdir()
            columns = [
                "month", "town", "flat_type", "flat_model", "storey_range", "resale_price"
            ]
            with (raw / "early.csv").open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=columns)
                writer.writeheader()
                writer.writerow(dict(zip(columns, ["2012-01", "A", "3 ROOM", "Model A", "01 TO 03", "230000"])))
                writer.writerow(dict(zip(columns, ["2012-02", "A", "3 ROOM", "Model A", "01 TO 03", "240000"])))
            with (raw / "later.csv").open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=columns + ["remaining_lease"])
                writer.writeheader()
                writer.writerow(dict(zip(columns + ["remaining_lease"], ["2012-03", "A", "3 ROOM", "Model A", "01 TO 03", "250000", "80"])))
                writer.writerow(dict(zip(columns + ["remaining_lease"], ["2012-03", "A", "3 ROOM", "New Model", "01 TO 05", "260000", "79"])))

            master = root / "master.csv"
            quarantine = root / "quarantine.csv"
            counts = combine(raw, master, quarantine, date(2012, 1, 1), date(2012, 3, 1))
            with master.open(newline="", encoding="utf-8") as handle:
                accepted = list(csv.DictReader(handle))
            with quarantine.open(newline="", encoding="utf-8") as handle:
                rejected = list(csv.DictReader(handle))

            self.assertEqual(counts, {"accepted": 3, "quarantined": 1})
            self.assertEqual([row["resale_price"] for row in accepted], ["230000", "240000", "250000"])
            self.assertEqual(accepted[0]["remaining_lease"], "")
            self.assertEqual(accepted[2]["remaining_lease"], "80")
            self.assertEqual(rejected[0]["quarantine_reasons"], "invalid_flat_model|invalid_storey_range")
            self.assertEqual((rejected[0]["source_file"], rejected[0]["source_record_number"]), ("later.csv", "2"))


if __name__ == "__main__":
    unittest.main()
