# Part 1: Data pipeline

## Combine the source files

Run from the repository root with Python 3.10 or newer:

```sh
python3 part1_data_pipeline/combine.py
```

The command reads every CSV in `data/raw/`, selects records from January 2012
through December 2017, and writes two files:

- `data/master/resale_master_2012_2017.csv`: records whose `town`, `flat_type`,
  `flat_model`, and `storey_range` values all occur in January 2012.
- `data/quarantined/resale_quarantined_2012_2017.csv`: records with at least one
  value outside those January 2012 sets. `quarantine_reasons` lists each failed
  field.

The allowed values are derived from the January 2012 records on every run;
they are not hardcoded. Matching is exact, including case and spacing. Blank
values fail validation. Every selected source record appears in exactly one of
the two output files. The original downloads are left intact.

The output column order begins with the January 2012 source schema. Columns
introduced by later files are appended; `remaining_lease` is blank for records
from files that do not contain it. Two further columns, `source_file` and
`source_record_number`, identify each record's original file and its 1-based
position after that file's header. No source field values are changed.

The command fails if any month in the requested period is missing from the
sources, a source CSV row is malformed, or the starting month occurs in multiple
source files. Use `--raw-dir`, `--output`, `--quarantine-output`, `--start`, and
`--end` to change the defaults.

## Compute remaining lease

After combining, run:

```sh
python3 part1_data_pipeline/lease.py
```

This writes `data/cleaned/resale_cleaned_2012_2017.csv` with the same accepted
records as master and three new columns: full years, remaining months, and a
readable value as of **1 January 2027**. The 99-year lease is assumed to start
on 1 January of `lease_commence_date`, because the source supplies only a year.
The calculated month component is therefore zero for these records. The
source's `remaining_lease` column remains unchanged.

## Flag potential resale price anomalies

After computing remaining lease, run:

```sh
.venv/bin/python part1_data_pipeline/price_anomalies.py
```

This adds `price_per_sqm`, a peer count, a robust score, a review flag, and a
status to the cleaned CSV. For each record, it compares log(SGD per sqm) against
sales in the same transaction year, town, and flat type. Scores beyond ±3.5
are flagged when the peer group has at least 30 records and nonzero median
absolute deviation. Small or constant groups are marked unassessed. All rows
remain in cleaned output; unusual prices may reflect real property differences.

## Transform resale identifiers

Run after the cleaning steps:

```sh
.venv/bin/python part1_data_pipeline/transform.py
```

This writes `data/transformed/resale_transformed_2012_2017.csv`. It adds a
readable `resale_identifier`: `S`, the first three numeric block
characters (left-padded), the first three digits of the grouped average resale
price, `YYMM`, and the town's first character. The implementation follows the
brief's `2012-01` → `1201` example for the four-digit date component.

`resale_identifier_base` records the value assembled from those parts. When a
base identifier repeats, records are ordered by `source_file` and
`source_record_number`; the first retains the base identifier and later records
receive `-002`, `-003`, and so on. This makes `resale_identifier` unique without
dropping records.

## Hash resale identifiers

Set a private pepper of at least 32 characters, then run:

```sh
export HDB_IDENTIFIER_PEPPER="replace-with-a-private-random-value"
.venv/bin/python part1_data_pipeline/hash_identifiers.py
```

`.env.example` contains a demonstration value for reference. Replace it before
running the hashing step; a committed example value does not protect against
dictionary attacks.

This writes `data/hashed/resale_hashed_2012_2017.csv`. The script applies
HMAC-SHA-256 to each unique `resale_identifier`. The secret pepper prevents an
attacker from reproducing hashes from guessed identifiers. The hashed output
contains `hashed_resale_identifier` and excludes both readable identifier
columns. `.env.example` documents the required variable; the real pepper and
`.env` remain outside source control.

Run the transformation tests with:

```sh
.venv/bin/python -m pytest part1_data_pipeline/test_transform.py
```

## Explore the data in Jupyter

From the repository root, install the notebook dependencies:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r part1_data_pipeline/requirements.txt
.venv/bin/jupyter lab part1_data_pipeline/notebooks/
```

Run `01_eda.ipynb` first. It reads the committed raw CSVs, explores their
behaviour, applies the January 2012 validation, and creates the cleaned output
with lease and anomaly fields.

Then run `02_transformation.ipynb` with `HDB_IDENTIFIER_PEPPER` set. It creates
the unique readable identifiers, writes the hashed output, and regenerates
`DATA_PROFILING_REPORT.md` across all five output groups. Both notebooks include
saved cell outputs for review.

To regenerate the profiling report without opening Jupyter, run:

```sh
.venv/bin/python part1_data_pipeline/profile.py
```

The report checks row-level reconciliation, source-value preservation, lease and
price anomaly calculations, identifier uniqueness, and hashed output before
writing its tables and findings.

This strict rule quarantines all March–May 2012 records: their source file uses
different storey-range bands from January 2012. That consequence is retained
and is described in the profiling report.
