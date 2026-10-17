import hashlib
import hmac

import pandas as pd
import pytest

from hash_identifiers import hash_identifiers, load_pepper
from transform import block_component, transform


TEST_PEPPER = "test-only-pepper-with-at-least-32-characters"


@pytest.mark.parametrize(("block", "expected"), [
    ("7", "007"),
    ("19A", "019"),
    ("12A3", "123"),
    ("12345", "123"),
])
def test_block_component_removes_non_digits_and_pads(block, expected):
    assert block_component(block) == expected


def test_block_component_rejects_a_block_without_digits():
    with pytest.raises(ValueError, match="no digits"):
        block_component("ABC")


def test_identifier_uses_group_average_and_yymm():
    frame = pd.DataFrame([
        {"month": "2012-01", "town": "ANG MO KIO", "flat_type": "2 ROOM",
         "block": "19A", "resale_price": "230000", "source_file": "a.csv",
         "source_record_number": "1"},
        {"month": "2012-01", "town": "ANG MO KIO", "flat_type": "2 ROOM",
         "block": "19B", "resale_price": "231000", "source_file": "a.csv",
         "source_record_number": "2"},
        {"month": "2012-02", "town": "BEDOK", "flat_type": "3 ROOM",
         "block": "456", "resale_price": "400000", "source_file": "a.csv",
         "source_record_number": "3"},
    ])
    result = transform(frame)
    assert result["resale_identifier_base"].tolist() == [
        "S0192301201A", "S0192301201A", "S4564001202B",
    ]
    assert result["resale_identifier"].tolist() == [
        "S0192301201A", "S0192301201A-002", "S4564001202B",
    ]


def test_identifier_grouping_does_not_cross_month_town_or_flat_type():
    frame = pd.DataFrame([
        {"month": "2012-01", "town": "ANG MO KIO", "flat_type": "2 ROOM",
         "block": "101", "resale_price": "200000", "source_file": "a.csv",
         "source_record_number": "1"},
        {"month": "2012-01", "town": "ANG MO KIO", "flat_type": "3 ROOM",
         "block": "102", "resale_price": "300000", "source_file": "a.csv",
         "source_record_number": "2"},
        {"month": "2012-02", "town": "BEDOK", "flat_type": "2 ROOM",
         "block": "103", "resale_price": "400000", "source_file": "a.csv",
         "source_record_number": "3"},
    ])
    assert transform(frame)["resale_identifier"].tolist() == [
        "S1012001201A", "S1023001201A", "S1034001202B",
    ]


def test_collision_sequence_uses_source_lineage_not_input_order():
    frame = pd.DataFrame([
        {"month": "2012-01", "town": "ANG MO KIO", "flat_type": "2 ROOM",
         "block": "19A", "resale_price": "230000", "source_file": "a.csv",
         "source_record_number": "2"},
        {"month": "2012-01", "town": "ANG MO KIO", "flat_type": "2 ROOM",
         "block": "19B", "resale_price": "230000", "source_file": "a.csv",
         "source_record_number": "1"},
        {"month": "2012-01", "town": "ANG MO KIO", "flat_type": "2 ROOM",
         "block": "19C", "resale_price": "230000", "source_file": "a.csv",
         "source_record_number": "3"},
    ])
    result = transform(frame)
    assert result["resale_identifier"].tolist() == [
        "S0192301201A-002", "S0192301201A", "S0192301201A-003",
    ]
    assert result["resale_identifier"].is_unique


@pytest.mark.parametrize(("column", "value", "message"), [
    ("month", "2012/01", "YYYY-MM"),
    ("month", "2012-13", "YYYY-MM"),
    ("resale_price", "0", "positive"),
    ("resale_price", "not-a-number", "positive"),
    ("town", "", "nonblank"),
    ("flat_type", "", "nonblank"),
    ("source_file", "", "Source lineage"),
    ("source_record_number", "0", "Source lineage"),
])
def test_transform_rejects_invalid_input(column, value, message):
    frame = pd.DataFrame([{
        "month": "2012-01", "town": "ANG MO KIO", "flat_type": "2 ROOM",
        "block": "19", "resale_price": "230000", "source_file": "a.csv",
        "source_record_number": "1",
    }])
    frame.loc[0, column] = value
    with pytest.raises(ValueError, match=message):
        transform(frame)


def test_transform_does_not_change_the_input_frame():
    frame = pd.DataFrame([{
        "month": "2012-01", "town": "ANG MO KIO", "flat_type": "2 ROOM",
        "block": "19", "resale_price": "230000", "source_file": "a.csv",
        "source_record_number": "1",
    }])
    original = frame.copy(deep=True)
    result = transform(frame)
    pd.testing.assert_frame_equal(frame, original)
    assert "resale_identifier_base" in result.columns
    assert "resale_identifier" in result.columns


def transformed_rows():
    return pd.DataFrame([
        {"month": "2012-01", "resale_price": "230000",
         "resale_identifier_base": "S0192301201A",
         "resale_identifier": "S0192301201A"},
        {"month": "2012-01", "resale_price": "231000",
         "resale_identifier_base": "S0192301201A",
         "resale_identifier": "S0192301201A-002"},
    ])


def test_hashes_are_deterministic_unique_and_keyed():
    result = hash_identifiers(transformed_rows(), TEST_PEPPER)
    expected = hmac.new(
        TEST_PEPPER.encode(), b"S0192301201A", hashlib.sha256
    ).hexdigest()
    assert result.loc[0, "hashed_resale_identifier"] == expected
    assert result["hashed_resale_identifier"].is_unique
    assert hash_identifiers(transformed_rows(), TEST_PEPPER).equals(result)


def test_hashed_output_removes_readable_identifiers_and_preserves_other_values():
    result = hash_identifiers(transformed_rows(), TEST_PEPPER)
    assert "resale_identifier" not in result.columns
    assert "resale_identifier_base" not in result.columns
    assert result[["month", "resale_price"]].to_dict("records") == [
        {"month": "2012-01", "resale_price": "230000"},
        {"month": "2012-01", "resale_price": "231000"},
    ]


def test_hashing_rejects_duplicate_readable_identifiers():
    frame = transformed_rows()
    frame.loc[1, "resale_identifier"] = frame.loc[0, "resale_identifier"]
    with pytest.raises(ValueError, match="unique before hashing"):
        hash_identifiers(frame, TEST_PEPPER)


def test_hashing_rejects_a_weak_pepper():
    with pytest.raises(ValueError, match="at least 32"):
        hash_identifiers(transformed_rows(), "too-short")


def test_pepper_must_be_supplied_through_the_environment(monkeypatch):
    monkeypatch.delenv("HDB_IDENTIFIER_PEPPER", raising=False)
    with pytest.raises(ValueError, match="HDB_IDENTIFIER_PEPPER"):
        load_pepper()
