# HDB resale data profiling report

## Scope and method

This report profiles the original files from the [HDB resale collection](https://data.gov.sg/collections/189/view), restricted to January 2012–December 2017, and the current master and quarantine outputs. Run `python3 part1_data_pipeline/combine.py` before regenerating this report with `python3 part1_data_pipeline/profile.py`. Source CSVs are never edited. The master is the set that passes the four exact January 2012 category checks; the quarantine contains failed records with reasons. Further transformations and hashing are pending.

## 1. Source inventory

| Original CSV | All rows | 2012–2017 rows | Columns | First month | Last month |
| --- | --- | --- | --- | --- | --- |
| ResaleFlatPricesBasedonApprovalDate2000Feb2012.csv | 369,651 | 3,188 | 10 | 2000-01 | 2012-02 |
| ResaleFlatPricesBasedonRegistrationDateFromMar2012toDec2014.csv | 52,203 | 52,203 | 10 | 2012-03 | 2014-12 |
| ResaleFlatPricesBasedonRegistrationDateFromJan2015toDec2016.csv | 37,153 | 37,153 | 11 | 2015-01 | 2016-12 |
| ResaleflatpricesbasedonregistrationdatefromJan2017onwards.csv | 242,454 | 20,509 | 11 | 2017-01 | 2026-10 |

The selected raw data contains **113,053 records** over **72 months**. The first and last files include records outside the assessment period; they remain intact in `data/raw/`. The 2015–2016 and 2017-onward files add `remaining_lease`, giving them 11 columns instead of 10. The publication changes from approval date to registration date in March 2012, so trends across that boundary require care.

## 2. Raw completeness and cardinality

| Field | Blank rows | Blank share | Distinct nonblank values |
| --- | --- | --- | --- |
| month | 0 | 0.0% | 72 |
| town | 0 | 0.0% | 26 |
| flat_type | 0 | 0.0% | 7 |
| block | 0 | 0.0% | 2,193 |
| street_name | 0 | 0.0% | 526 |
| storey_range | 0 | 0.0% | 25 |
| floor_area_sqm | 0 | 0.0% | 169 |
| flat_model | 0 | 0.0% | 20 |
| lease_commence_date | 0 | 0.0% | 50 |
| resale_price | 0 | 0.0% | 2,865 |
| remaining_lease | 55,391 | 49.0% | 631 |

The ten common source fields have **no blank values** in the selected period. `remaining_lease` is blank for **55,391 records** because their source files do not supply that column; this is schema absence, not an observed blank inside those files.

Across the ten common fields, **902 rows** occur in repeated attribute patterns (**451 rows** beyond the first occurrence). The source has no transaction ID, so matching published attributes alone cannot establish duplicate transactions.

## 3. January 2012 authoritative values

The reference month has **1,559 records**. These exact values, with no case or spacing normalization, are the allowlists used by the current merge step:

| Field | Allowed values | Values |
| --- | --- | --- |
| town | 26 | ANG MO KIO, BEDOK, BISHAN, BUKIT BATOK, BUKIT MERAH, BUKIT PANJANG, BUKIT TIMAH, CENTRAL AREA, CHOA CHU KANG, CLEMENTI, GEYLANG, HOUGANG, JURONG EAST, JURONG WEST, KALLANG/WHAMPOA, MARINE PARADE, PASIR RIS, PUNGGOL, QUEENSTOWN, SEMBAWANG, SENGKANG, SERANGOON, TAMPINES, TOA PAYOH, WOODLANDS, YISHUN |
| flat_type | 7 | 1 ROOM, 2 ROOM, 3 ROOM, 4 ROOM, 5 ROOM, EXECUTIVE, MULTI-GENERATION |
| flat_model | 13 | Adjoined flat, Apartment, Improved, Maisonette, Model A, Model A-Maisonette, Model A2, Multi Generation, New Generation, Premium Apartment, Simplified, Standard, Terrace |
| storey_range | 12 | 01 TO 03, 04 TO 06, 07 TO 09, 10 TO 12, 13 TO 15, 16 TO 18, 19 TO 21, 22 TO 24, 25 TO 27, 28 TO 30, 31 TO 33, 34 TO 36 |

| Field | Rows outside reference | New values | Most frequent new values |
| --- | --- | --- | --- |
| town | 0 | 0 | None |
| flat_type | 0 | 0 | None |
| flat_model | 870 | 7 | DBSS (583), Type S1 (179), Type S2 (78), Improved-Maisonette (15), Premium Maisonette (8), Premium Apartment Loft (6) |
| storey_range | 7,050 | 13 | 01 TO 05 (2,700), 06 TO 10 (2,474), 11 TO 15 (1,259), 16 TO 20 (265), 37 TO 39 (125), 21 TO 25 (92) |

## 4. Lifecycle reconciliation

| Output | Records | Share of selected raw |
| --- | --- | --- |
| Selected raw | 113,053 | 100.0% |
| Master | 105,225 | 93.1% |
| Quarantined | 7,828 | 6.9% |

Every selected raw record appears exactly once across master and quarantine, based on source file and source record number. The two outputs have no overlapping lineage keys, and all source field values match the original CSV records.

| Source file | Selected raw | Master | Quarantined | Quarantine share |
| --- | --- | --- | --- | --- |
| ResaleFlatPricesBasedonApprovalDate2000Feb2012.csv | 3,188 | 3,187 | 1 | <0.1% |
| ResaleFlatPricesBasedonRegistrationDateFromMar2012toDec2014.csv | 52,203 | 45,245 | 6,958 | 13.3% |
| ResaleFlatPricesBasedonRegistrationDateFromJan2015toDec2016.csv | 37,153 | 36,701 | 452 | 1.2% |
| ResaleflatpricesbasedonregistrationdatefromJan2017onwards.csv | 20,509 | 20,092 | 417 | 2.0% |

| Year | Selected raw | Master | Quarantined | Quarantine share |
| --- | --- | --- | --- | --- |
| 2012 | 23,198 | 16,344 | 6,854 | 29.5% |
| 2013 | 16,097 | 16,081 | 16 | <0.1% |
| 2014 | 16,096 | 16,007 | 89 | 0.6% |
| 2015 | 17,780 | 17,602 | 178 | 1.0% |
| 2016 | 19,373 | 19,099 | 274 | 1.4% |
| 2017 | 20,509 | 20,092 | 417 | 2.0% |

## 5. Quarantine profile

| Failed rule | Rows |
| --- | --- |
| invalid_storey_range | 7,050 |
| invalid_flat_model | 870 |

A row may fail more than one rule, so the rule counts can sum to more than the number of quarantined records. Distinct reason combinations are:

| Reason combination | Rows |
| --- | --- |
| invalid_storey_range | 6,958 |
| invalid_flat_model | 778 |
| invalid_flat_model\|invalid_storey_range | 92 |

**Months with no accepted records:** 2012-03, 2012-04, 2012-05. In March–May 2012, the registration-date source uses storey bands such as `01 TO 05` and `06 TO 10`; January 2012 uses `01 TO 03`, `04 TO 06`, and similar three-floor bands. The strict reference rule therefore quarantines every record in those three months. Quarantine means a rule failed; it does not prove the sale or source value is erroneous.

## 6. Numeric behaviour

| Measure | Invalid or unavailable rows | Minimum | Median | 99th percentile | Maximum |
| --- | --- | --- | --- | --- | --- |
| Raw resale price (SGD) | 0 | 175,000 | 425,000 | 860,000 | 1,180,000 |
| Raw floor area (sqm) | 0 | 31.00 | 96.00 | 151.00 | 280.00 |
| Raw price per sqm (SGD) | 0 | 2,375 | 4,512 | 8,292 | 10,645 |

| Bucket | Median resale price (SGD) | Median price per sqm (SGD) |
| --- | --- | --- |
| Master | 422,000 | 4,493 |
| Quarantined | 455,000 | 4,774 |

Lease commencement years range from **1966** to **2015**. There are **0** non-numeric commencement years or years later than their transaction year.

The numeric summaries are descriptive. No price-anomaly heuristic has been applied yet; an unusually high price should be evaluated against comparable town, flat type, time, and area rather than a single global threshold.

## 7. Monthly reconciliation

| Month | Selected raw | Master | Quarantined | Quarantine share |
| --- | --- | --- | --- | --- |
| 2012-01 | 1,559 | 1,559 | 0 | 0.0% |
| 2012-02 | 1,629 | 1,628 | 1 | <0.1% |
| 2012-03 | 2,360 | 0 | 2,360 | 100.0% |
| 2012-04 | 2,155 | 0 | 2,155 | 100.0% |
| 2012-05 | 2,323 | 0 | 2,323 | 100.0% |
| 2012-06 | 1,993 | 1,991 | 2 | 0.1% |
| 2012-07 | 2,179 | 2,177 | 2 | <0.1% |
| 2012-08 | 2,075 | 2,072 | 3 | 0.1% |
| 2012-09 | 1,760 | 1,759 | 1 | <0.1% |
| 2012-10 | 1,937 | 1,932 | 5 | 0.3% |
| 2012-11 | 1,735 | 1,735 | 0 | 0.0% |
| 2012-12 | 1,493 | 1,491 | 2 | 0.1% |
| 2013-01 | 1,633 | 1,632 | 1 | <0.1% |
| 2013-02 | 886 | 886 | 0 | 0.0% |
| 2013-03 | 1,306 | 1,302 | 4 | 0.3% |
| 2013-04 | 1,692 | 1,691 | 1 | <0.1% |
| 2013-05 | 1,605 | 1,604 | 1 | <0.1% |
| 2013-06 | 1,317 | 1,315 | 2 | 0.2% |
| 2013-07 | 1,484 | 1,483 | 1 | <0.1% |
| 2013-08 | 1,354 | 1,352 | 2 | 0.1% |
| 2013-09 | 1,212 | 1,212 | 0 | 0.0% |
| 2013-10 | 1,391 | 1,389 | 2 | 0.1% |
| 2013-11 | 1,209 | 1,208 | 1 | <0.1% |
| 2013-12 | 1,008 | 1,007 | 1 | <0.1% |
| 2014-01 | 1,098 | 1,098 | 0 | 0.0% |
| 2014-02 | 959 | 959 | 0 | 0.0% |
| 2014-03 | 1,444 | 1,437 | 7 | 0.5% |
| 2014-04 | 1,557 | 1,544 | 13 | 0.8% |
| 2014-05 | 1,447 | 1,438 | 9 | 0.6% |
| 2014-06 | 1,223 | 1,216 | 7 | 0.6% |
| 2014-07 | 1,352 | 1,341 | 11 | 0.8% |
| 2014-08 | 1,329 | 1,319 | 10 | 0.8% |
| 2014-09 | 1,472 | 1,464 | 8 | 0.5% |
| 2014-10 | 1,560 | 1,547 | 13 | 0.8% |
| 2014-11 | 1,351 | 1,345 | 6 | 0.4% |
| 2014-12 | 1,304 | 1,299 | 5 | 0.4% |
| 2015-01 | 1,250 | 1,237 | 13 | 1.0% |
| 2015-02 | 1,151 | 1,130 | 21 | 1.8% |
| 2015-03 | 1,348 | 1,334 | 14 | 1.0% |
| 2015-04 | 1,630 | 1,612 | 18 | 1.1% |
| 2015-05 | 1,567 | 1,548 | 19 | 1.2% |
| 2015-06 | 1,706 | 1,689 | 17 | 1.0% |
| 2015-07 | 1,551 | 1,542 | 9 | 0.6% |
| 2015-08 | 1,449 | 1,434 | 15 | 1.0% |
| 2015-09 | 1,498 | 1,484 | 14 | 0.9% |
| 2015-10 | 1,748 | 1,733 | 15 | 0.9% |
| 2015-11 | 1,470 | 1,456 | 14 | 1.0% |
| 2015-12 | 1,412 | 1,403 | 9 | 0.6% |
| 2016-01 | 1,280 | 1,274 | 6 | 0.5% |
| 2016-02 | 1,200 | 1,186 | 14 | 1.2% |
| 2016-03 | 1,655 | 1,635 | 20 | 1.2% |
| 2016-04 | 1,824 | 1,801 | 23 | 1.3% |
| 2016-05 | 1,829 | 1,800 | 29 | 1.6% |
| 2016-06 | 1,827 | 1,803 | 24 | 1.3% |
| 2016-07 | 1,572 | 1,552 | 20 | 1.3% |
| 2016-08 | 1,882 | 1,857 | 25 | 1.3% |
| 2016-09 | 1,668 | 1,635 | 33 | 2.0% |
| 2016-10 | 1,678 | 1,648 | 30 | 1.8% |
| 2016-11 | 1,580 | 1,552 | 28 | 1.8% |
| 2016-12 | 1,378 | 1,356 | 22 | 1.6% |
| 2017-01 | 1,185 | 1,170 | 15 | 1.3% |
| 2017-02 | 1,085 | 1,070 | 15 | 1.4% |
| 2017-03 | 1,903 | 1,865 | 38 | 2.0% |
| 2017-04 | 1,839 | 1,811 | 28 | 1.5% |
| 2017-05 | 1,980 | 1,938 | 42 | 2.1% |
| 2017-06 | 1,747 | 1,709 | 38 | 2.2% |
| 2017-07 | 1,780 | 1,749 | 31 | 1.7% |
| 2017-08 | 1,960 | 1,914 | 46 | 2.3% |
| 2017-09 | 1,680 | 1,638 | 42 | 2.5% |
| 2017-10 | 1,785 | 1,739 | 46 | 2.6% |
| 2017-11 | 1,980 | 1,941 | 39 | 2.0% |
| 2017-12 | 1,585 | 1,548 | 37 | 2.3% |

## Assumptions and follow-up

- January 2012 observed values are used as exact allowlists because the assessment calls them strictly authoritative. Newly introduced but plausible later values are quarantined.
- The 2015-onward source `remaining_lease` is measured at the resale application, not as of 1 January 2027. The requested new value still needs a consistent calculation.
- Repeated attribute patterns are not removed pending a defensible duplicate rule.
- This is the raw-to-master profile. Extend it after producing cleaned, transformed, and hashed outputs so the final report covers the complete pipeline lifecycle.
