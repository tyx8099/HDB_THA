"""Flag unusual resale prices among comparable accepted transactions."""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from lease import DEFAULT_CLEANED


MIN_PEERS = 30
ROBUST_Z_THRESHOLD = 3.5
ANOMALY_COLUMNS = (
    "price_per_sqm", "price_anomaly_peer_count", "price_anomaly_robust_z",
    "price_anomaly_flag", "price_anomaly_status",
)


def score_prices(frame: pd.DataFrame) -> pd.DataFrame:
    """Compare log(SGD/sqm) within transaction year, town, and flat type.

    A peer group includes the transaction being scored. Small groups and groups
    with zero median absolute deviation are reported as unassessed.
    """
    required = {"month", "town", "flat_type", "resale_price", "floor_area_sqm"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Missing columns for price scoring: {sorted(missing)}")
    result = frame.drop(columns=list(ANOMALY_COLUMNS), errors="ignore").copy()
    price = pd.to_numeric(result["resale_price"], errors="coerce")
    area = pd.to_numeric(result["floor_area_sqm"], errors="coerce")
    valid = price.gt(0) & area.gt(0) & np.isfinite(price) & np.isfinite(area)
    ppsqm = (price / area).where(valid)
    valid &= np.isfinite(ppsqm) & ppsqm.gt(0)
    ppsqm = ppsqm.where(valid)

    peers = result.loc[valid, ["month", "town", "flat_type"]].copy()
    peers["year"] = peers["month"].str[:4]
    peers["log_ppsqm"] = np.log(ppsqm.loc[valid])
    group_keys = ["year", "town", "flat_type"]
    grouped = peers.groupby(group_keys, dropna=False)["log_ppsqm"]
    count = grouped.transform("size")
    median = grouped.transform("median")
    absolute_deviation = (peers["log_ppsqm"] - median).abs()
    mad = absolute_deviation.groupby(
        [peers[column] for column in group_keys], dropna=False
    ).transform("median")
    assessable = count.ge(MIN_PEERS) & mad.gt(0)
    robust_z = (0.6745 * (peers["log_ppsqm"] - median) / mad).where(assessable)

    status = pd.Series("invalid_numeric", index=result.index, dtype="object")
    status.loc[valid] = "normal"
    status.loc[count.index[count.lt(MIN_PEERS)]] = "insufficient_peers"
    status.loc[count.index[count.ge(MIN_PEERS) & mad.eq(0)]] = "zero_mad"
    status.loc[robust_z.index[robust_z.gt(ROBUST_Z_THRESHOLD)]] = "high"
    status.loc[robust_z.index[robust_z.lt(-ROBUST_Z_THRESHOLD)]] = "low"

    result["price_per_sqm"] = ppsqm.map(lambda value: f"{value:.2f}" if pd.notna(value) else "")
    result["price_anomaly_peer_count"] = count.reindex(result.index).fillna(0).astype(int).astype(str)
    result["price_anomaly_robust_z"] = robust_z.reindex(result.index).map(
        lambda value: f"{value:.3f}" if pd.notna(value) else ""
    )
    result["price_anomaly_flag"] = status.isin(["high", "low"]).map({True: "true", False: "false"})
    result["price_anomaly_status"] = status
    return result


def flag_prices(input_path: Path = DEFAULT_CLEANED, output_path: Path | None = None) -> pd.DataFrame:
    if output_path is None:
        output_path = input_path
    frame = pd.read_csv(input_path, dtype=str, keep_default_na=False)
    result = score_prices(frame)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".partial")
    try:
        result.to_csv(temporary, index=False, lineterminator="\n")
        temporary.replace(output_path)
    finally:
        temporary.unlink(missing_ok=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_CLEANED)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    result = flag_prices(args.input, args.output)
    counts = result["price_anomaly_status"].value_counts()
    print(f"Scored {len(result):,} records: {counts.get('high', 0):,} high, "
          f"{counts.get('low', 0):,} low, "
          f"{counts.get('insufficient_peers', 0):,} insufficient peers")


if __name__ == "__main__":
    main()
