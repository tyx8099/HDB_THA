import pandas as pd
import pytest

from transform import block_component, transform


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
    assert result["resale_identifier"].tolist() == [
        "S0192301201A", "S0192301201A", "S4564001202B",
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


@pytest.mark.parametrize(("column", "value", "message"), [
    ("month", "2012/01", "YYYY-MM"),
    ("month", "2012-13", "YYYY-MM"),
    ("resale_price", "0", "positive"),
    ("resale_price", "not-a-number", "positive"),
    ("town", "", "nonblank"),
    ("flat_type", "", "nonblank"),
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
    assert "resale_identifier" in result.columns
