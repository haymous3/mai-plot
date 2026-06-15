"""parse_fields — FORMS key/values, regex fallback, missing-field handling."""

from __future__ import annotations

from app.adapters.ocr import OcrResult
from app.services.ocr_parser import parse_fields


def test_extracts_all_four_fields_from_form_key_values() -> None:
    result = OcrResult(
        raw_text="...",
        key_values={
            "property address": "12 Admiralty Way, Lekki, Lagos",
            "plot number": "LA-1234",
            "date issued": "2021-07-15",
            "issuing authority": "Lagos State Government",
        },
    )
    fields = parse_fields(result)
    assert fields == {
        "property_address": "12 Admiralty Way, Lekki, Lagos",
        "plot_number": "LA-1234",
        "date": "2021-07-15",
        "issuing_authority": "Lagos State Government",
    }


def test_regex_fallback_for_date_and_plot_when_no_forms() -> None:
    result = OcrResult(
        raw_text=(
            "CERTIFICATE OF OCCUPANCY\nGranted over Plot No: 47B at Ikoyi\nDated this 03/11/2020\n"
        ),
        key_values={},
    )
    fields = parse_fields(result)
    assert fields["plot_number"] == "47B"
    assert fields["date"] == "03/11/2020"
    # No address / authority available -> simply absent.
    assert "property_address" not in fields
    assert "issuing_authority" not in fields


def test_forms_value_wins_over_regex_fallback() -> None:
    result = OcrResult(
        raw_text="Plot No: 999 dated 01/01/2000",
        key_values={"plot number": "LA-1234", "date": "2021-07-15"},
    )
    fields = parse_fields(result)
    assert fields["plot_number"] == "LA-1234"
    assert fields["date"] == "2021-07-15"


def test_empty_result_yields_no_fields() -> None:
    assert parse_fields(OcrResult(raw_text="", key_values={})) == {}


def test_blank_form_values_are_ignored() -> None:
    result = OcrResult(raw_text="no usable text here", key_values={"address": "   "})
    assert parse_fields(result) == {}
