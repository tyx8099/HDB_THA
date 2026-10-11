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

Run the focused merge test with:

```sh
python3 part1_data_pipeline/test_combine.py
```

## Explore the data in Jupyter

From the repository root, install the notebook dependencies and open
`notebooks/01_eda.ipynb`:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r part1_data_pipeline/requirements.txt
.venv/bin/jupyter lab part1_data_pipeline/notebooks/01_eda.ipynb
```

Run all cells in order. The notebook reads the committed raw CSVs, invokes the
same merge function, profiles the raw, master, and quarantined records, and
recreates both output CSVs and `DATA_PROFILING_REPORT.md`. Its saved cell outputs
are included for review.

To regenerate the profiling report without opening Jupyter, run:

```sh
.venv/bin/python part1_data_pipeline/profile.py
```

The report checks row-level reconciliation and source-value preservation before
writing its tables and findings. It currently covers the raw-to-master stage;
the final report will be extended as later output groups are implemented.

This strict rule quarantines all March–May 2012 records: their source file uses
different storey-range bands from January 2012. That consequence is retained
and will be described in the profiling report. Further quality checks and
transformations are subsequent pipeline steps.
