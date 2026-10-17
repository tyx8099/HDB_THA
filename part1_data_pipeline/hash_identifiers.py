"""Create a de-identified dataset using keyed identifier hashes."""

import argparse
import hashlib
import hmac
import os
from pathlib import Path

import pandas as pd

from transform import DEFAULT_OUTPUT as DEFAULT_TRANSFORMED


PART1 = Path(__file__).parent
DEFAULT_OUTPUT = PART1 / "data" / "hashed" / "resale_hashed_2012_2017.csv"
PEPPER_ENV = "HDB_IDENTIFIER_PEPPER"
MINIMUM_PEPPER_LENGTH = 32
IDENTIFIER_COLUMNS = ("resale_identifier_base", "resale_identifier")


def load_pepper():
    pepper = os.environ.get(PEPPER_ENV, "")
    if len(pepper) < MINIMUM_PEPPER_LENGTH:
        raise ValueError(
            f"{PEPPER_ENV} must be set to a secret of at least {MINIMUM_PEPPER_LENGTH} characters"
        )
    return pepper


def hash_identifier(identifier, pepper):
    return hmac.new(
        pepper.encode("utf-8"), identifier.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def hash_identifiers(frame, pepper):
    """Replace readable unique identifiers with deterministic HMAC-SHA-256 values."""
    missing = set(IDENTIFIER_COLUMNS).difference(frame.columns)
    if missing:
        raise ValueError(f"Transformed input is missing identifier columns: {sorted(missing)}")
    if len(pepper) < MINIMUM_PEPPER_LENGTH:
        raise ValueError(f"Pepper must contain at least {MINIMUM_PEPPER_LENGTH} characters")
    if frame["resale_identifier"].eq("").any():
        raise ValueError("Readable identifiers must be nonblank")
    if not frame["resale_identifier"].is_unique:
        raise ValueError("Readable identifiers must be unique before hashing")

    result = frame.drop(columns=list(IDENTIFIER_COLUMNS)).copy()
    result["hashed_resale_identifier"] = frame["resale_identifier"].map(
        lambda identifier: hash_identifier(identifier, pepper)
    )
    if not result["hashed_resale_identifier"].is_unique:
        raise ValueError("Hashed identifiers are not unique")
    return result


def build_hashed(input_path=DEFAULT_TRANSFORMED, output_path=DEFAULT_OUTPUT, pepper=None):
    frame = pd.read_csv(input_path, dtype=str, keep_default_na=False)
    result = hash_identifiers(frame, pepper or load_pepper())
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
    parser.add_argument("--input", type=Path, default=DEFAULT_TRANSFORMED)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = build_hashed(args.input, args.output)
    print(f"Wrote {len(result):,} hashed records to {args.output}")
    print("Readable resale identifiers are excluded from the hashed output")


if __name__ == "__main__":
    main()
