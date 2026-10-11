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

## Explore the data in Jupyter

From the repository root, install the notebook dependencies and open
`notebooks/01_eda.ipynb`:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r part1_data_pipeline/requirements.txt
.venv/bin/jupyter lab part1_data_pipeline/notebooks/01_eda.ipynb
```

Run all cells in order. The notebook reads the committed raw CSVs, invokes the
same merge, lease, and anomaly functions, profiles the raw, master, cleaned, and
quarantined records, and recreates the output CSVs and
`DATA_PROFILING_REPORT.md`. Its saved cell outputs are included for review.

To regenerate the profiling report without opening Jupyter, run:

```sh
.venv/bin/python part1_data_pipeline/profile.py
```

The report checks row-level reconciliation, source-value preservation, and the
lease and price anomaly calculations before writing its tables and findings. It will be extended
as transformed and hashed output groups are implemented.

This strict rule quarantines all March–May 2012 records: their source file uses
different storey-range bands from January 2012. That consequence is retained
and is described in the profiling report. Further transformations are
subsequent pipeline steps.
