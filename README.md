# HDB resale data pipeline

This repository contains a Python pipeline for HDB resale transactions from
January 2012 through December 2017. It combines the original files, validates
records against January 2012, profiles data quality, calculates remaining
lease, flags potential price anomalies, creates unique resale identifiers, and
produces a de-identified output.

The source files come from the
[HDB Resale Flat Prices collection](https://data.gov.sg/collections/189/view).

## Repository structure

```text
part1_data_pipeline/
├── data/
│   ├── raw/
│   ├── master/
│   ├── cleaned/
│   ├── transformed/
│   ├── quarantined/
│   └── hashed/
├── notebooks/
│   ├── 01_eda.ipynb
│   └── 02_transformation.ipynb
├── combine.py
├── lease.py
├── price_anomalies.py
├── transform.py
├── hash_identifiers.py
├── profile.py
├── test_transform.py
├── DATA_PROFILING_REPORT.md
└── README.md

part2_architecture/
```

The [Part 1 guide](part1_data_pipeline/README.md) describes each pipeline step
in detail. The
[profiling report](part1_data_pipeline/DATA_PROFILING_REPORT.md) contains the
data findings, assumptions, quarantine analysis, and lifecycle reconciliation.

## Setup

Python 3.10 or newer is required. From the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r part1_data_pipeline/requirements.txt
```

## Run the pipeline

Run the scripts in this order:

```sh
.venv/bin/python part1_data_pipeline/combine.py
.venv/bin/python part1_data_pipeline/lease.py
.venv/bin/python part1_data_pipeline/price_anomalies.py
.venv/bin/python part1_data_pipeline/transform.py
export HDB_IDENTIFIER_PEPPER="replace-with-a-private-random-value"
.venv/bin/python part1_data_pipeline/hash_identifiers.py
.venv/bin/python part1_data_pipeline/profile.py
```

`HDB_IDENTIFIER_PEPPER` must contain at least 32 characters. The value in
`.env.example` is for demonstration only. A real pepper must remain private and
outside source control. Hashes generated with different peppers will differ by
design.

## Output groups

| Output | Description |
| --- | --- |
| Raw | Four original source CSVs, stored unchanged |
| Master | All in-scope records before the validation split |
| Cleaned | Records passing the January 2012 validation, with lease and anomaly fields |
| Transformed | Cleaned records with unique readable resale identifiers |
| Quarantined | Records failing one or more authoritative-value checks, with reasons |
| Hashed | Cleaned fields with a unique HMAC-SHA-256 identifier and no readable identifier |

The selected raw data contains 113,053 records. Validation produces 105,225
cleaned records and 7,828 quarantined records. Master and quarantine reconcile
to every in-scope source row using `source_file` and `source_record_number`.

## Notebooks

Start Jupyter Lab with:

```sh
.venv/bin/jupyter lab part1_data_pipeline/notebooks/
```

Run the notebooks in order:

1. `01_eda.ipynb` explores the raw data, applies validation, calculates lease,
   and flags potential price anomalies.
2. `02_transformation.ipynb` creates unique identifiers, produces the hashed
   output, and generates the final profiling report.

Both notebooks include saved cell outputs. The second notebook requires
`HDB_IDENTIFIER_PEPPER` in the environment before Jupyter is started.

## Tests

Run the transformation and hashing tests with:

```sh
.venv/bin/python -m pytest part1_data_pipeline/test_transform.py
```

## Main assumptions

- January 2012 observed values are exact allowlists for `town`, `flat_type`,
  `flat_model`, and `storey_range`.
- The source provides only a lease commencement year. The 99-year lease is
  assumed to start on 1 January of that year when calculating the balance on
  1 January 2027.
- Price anomalies are review flags based on robust peer-group comparisons;
  flagged records remain in the cleaned output.
- Repeated base identifiers are resolved deterministically using source lineage
  and suffixes such as `-002` and `-003`. No records are dropped.
- HMAC-SHA-256 with a private pepper protects the predictable identifier format
  against straightforward dictionary attacks.

Part 2 will add the AWS ingestion and data-exploitation architecture diagrams
under `part2_architecture/`.
