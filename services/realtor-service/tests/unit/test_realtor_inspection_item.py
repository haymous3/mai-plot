"""Unit tests for the realtor-portal inspection item (SCRUM-204).

The masking here is the only thing standing between `user_pii.phone` and the
browser, so it is tested directly rather than through the route.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from app.repositories.inspection_repo import RealtorInspectionRow
from app.schemas.inspection import RealtorInspectionItem, mask_phone


def _row(**overrides: object) -> RealtorInspectionRow:
    now = datetime.now(UTC)
    fields: dict[str, object] = {
        "inspection_id": uuid4(),
        "transaction_id": uuid4(),
        "status": "accepted",
        "proposed_date": now + timedelta(days=1),
        "confirmed_date": now + timedelta(days=1),
        "assignment_expires_at": now + timedelta(hours=2),
        "created_at": now,
        "report_submitted_at": None,
        "buyer_id": uuid4(),
        "property_title": "2 Plots of Land",
        "address_text": "1 Admiralty Way",
        "lga": "Eti-Osa",
        "state": "Lagos",
        "property_type": "land",
        "sale_type": "distress",
        "size_sqm": Decimal("1000.00"),
        "asking_price_kobo": 1_500_000_000,
        "cover_photo_url": "https://cdn.maiplot.ng/a.jpg",
        "seller_authority_type": "owner",
        "seller_name": "Mr. Adebayo",
        "seller_phone": "+2348012345824",
    }
    fields.update(overrides)
    return RealtorInspectionRow(**fields)  # type: ignore[arg-type]


def test_masks_phone_to_dialling_code_and_last_three() -> None:
    assert mask_phone("+2348012345824") == "+234 *** **** 824"


def test_masks_local_format_without_plus() -> None:
    assert mask_phone("08012345824") == "080 *** **** 824"


def test_masks_ignoring_separators() -> None:
    assert mask_phone("+234 801 234 5824") == "+234 *** **** 824"


def test_no_phone_masks_to_none() -> None:
    assert mask_phone(None) is None


def test_too_short_to_mask_returns_none_rather_than_leaking() -> None:
    # A 6-digit value would surface half of itself — refuse instead.
    assert mask_phone("123456") is None


def test_item_never_carries_the_raw_phone() -> None:
    item = RealtorInspectionItem.from_row(_row())
    assert item.seller_phone_masked == "+234 *** **** 824"
    assert "8012345824" not in item.model_dump_json()


def test_buyer_and_inspection_refs_are_short_and_never_the_full_id() -> None:
    row = _row()
    item = RealtorInspectionItem.from_row(row)

    assert item.buyer_ref == str(row.buyer_id)[:8]
    assert item.inspection_ref == str(row.inspection_id)[:8]
    assert len(item.buyer_ref) == 8
    assert str(row.buyer_id) not in item.buyer_ref


def test_property_context_fields_pass_through() -> None:
    item = RealtorInspectionItem.from_row(_row())

    assert item.property_type == "land"
    assert item.sale_type == "distress"
    assert item.size_sqm == 1000.0
    assert item.asking_price_kobo == 1_500_000_000
    assert item.cover_photo_url == "https://cdn.maiplot.ng/a.jpg"
    assert item.seller_authority_type == "owner"
    assert item.seller_name == "Mr. Adebayo"


def test_listing_without_media_or_seller_pii_degrades_to_none() -> None:
    item = RealtorInspectionItem.from_row(
        _row(cover_photo_url=None, size_sqm=None, seller_name=None, seller_phone=None)
    )

    assert item.cover_photo_url is None
    assert item.size_sqm is None
    assert item.seller_name is None
    assert item.seller_phone_masked is None
