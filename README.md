# HDB resale data pipeline

This repository contains two related deliverables for HDB resale transactions
from January 2012 to December 2017:

1. A Python pipeline for profiling, validating, transforming, and
   de-identifying the data.
2. An AWS architecture for scheduled ingestion and private Tableau access.

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
├── hdb_aws_architecture.png
└── README.md
```

## Part 1: data pipeline

The pipeline uses the values observed in January 2012 as strict allowlists for
`town`, `flat_type`, `flat_model`, and `storey_range`. Records with later values
outside those sets are retained in quarantine with their failure reasons.

### Setup

Python 3.10 or newer is required. From the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r part1_data_pipeline/requirements.txt
```

### Run

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
`.env.example` is only an example; the real secret must remain outside source
control.

### Outputs

| Output | Description |
| --- | --- |
| Raw | Four unchanged source CSVs |
| Master | In-scope records that pass the strict January 2012 validation |
| Quarantined | Records that fail one or more authoritative-value checks, with reasons |
| Cleaned | Master records with remaining-lease and price-anomaly fields |
| Transformed | Cleaned records with deterministic unique resale identifiers |
| Hashed | Cleaned fields with unique HMAC-SHA-256 identifiers and no readable identifiers |

The four source files contain 113,053 in-scope records. Strict validation
produces 105,225 master records and 7,828 quarantined records. Together, those
outputs preserve every in-scope source row and retain its source file and row
number.

### Notebooks and tests

The executed notebooks contain saved cell outputs:

1. `01_eda.ipynb` covers profiling, validation, lease calculation, and anomaly
   detection.
2. `02_transformation.ipynb` creates unique identifiers and the de-identified
   output.

Set `HDB_IDENTIFIER_PEPPER` before starting Jupyter to run the second notebook.

Open them with:

```sh
.venv/bin/jupyter lab part1_data_pipeline/notebooks/
```

Run the transformation and hashing tests with:

```sh
.venv/bin/python -m pytest part1_data_pipeline/test_transform.py
```

See the [Part 1 guide](part1_data_pipeline/README.md) for the processing rules
and the [data profiling report](part1_data_pipeline/DATA_PROFILING_REPORT.md)
for findings, assumptions, and quarantine analysis.

## Part 2: AWS architecture

The architecture covers:

1. A scheduled batch pipeline from data.gov.sg through Lambda and Glue into
   raw, curated, and quarantine S3 layers.
2. Private Tableau access through Site-to-Site VPN, an internal load balancer,
   and approved Athena views.

Lambda streams large downloads into S3 multipart uploads. Glue performs data
validation and transformation, writes versioned Parquet folders partitioned by
transaction year, and publishes validated output through the Glue Data Catalog.

See the [architecture diagram](part2_architecture/hdb_aws_architecture.png) and
the [Part 2 design notes](part2_architecture/README.md) for the complete flow,
security controls, assumptions, and trade-offs.

## Key assumptions

- A 99-year lease begins on 1 January of `lease_commence_date` because the
  source provides only the commencement year.
- Remaining lease is calculated as of 1 January 2027.
- Price anomaly flags are review indicators. Flagged records remain in the
  cleaned output.
- Repeated base identifiers receive deterministic rank suffixes; no records are
  dropped.
- HMAC-SHA-256 uses a private pepper to protect the predictable identifier from
  dictionary attacks.
