"""Map an OcrResult to the business fields a title document must yield.

Extracts: property_address, plot_number, date, issuing_authority.

Strategy: prefer Textract FORMS key/values (matched by keyword aliases);
fall back to regex over the raw text for the date and plot number, which are
the most regular. Returns only the fields it found — a missing field is simply
absent, so the caller can tell "OCR read nothing usable" from "OCR read some".
Pure + dependency-free so it is fully unit-tested without AWS.
"""

from __future__ import annotations

import re

from app.adapters.ocr import OcrResult

# Form-key aliases (lower-cased) for each target field, most specific first.
_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "property_address": ("property address", "address", "location", "situate at"),
    "plot_number": ("plot number", "plot no", "plot", "parcel number", "survey number"),
    "date": ("date", "date issued", "issue date", "dated"),
    "issuing_authority": ("issuing authority", "authority", "issued by", "registry"),
}

# Regex fallbacks for the regular fields.
_DATE_RE = re.compile(
    r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"
    r"|\d{1,2}\s+[A-Za-z]+\s+\d{4})\b"
)
_PLOT_RE = re.compile(r"\bplot\s*(?:no\.?|number|#)?\s*[:\-]?\s*([A-Za-z0-9/\-]+)", re.IGNORECASE)


def parse_fields(result: OcrResult) -> dict[str, str]:
    """Return the subset of {property_address, plot_number, date,
    issuing_authority} that could be extracted."""
    fields: dict[str, str] = {}

    for field_name, aliases in _FIELD_ALIASES.items():
        value = _from_key_values(result.key_values, aliases)
        if value:
            fields[field_name] = value

    # Regex fallbacks only where FORMS gave us nothing.
    if "date" not in fields:
        match = _DATE_RE.search(result.raw_text)
        if match:
            fields["date"] = match.group(1)
    if "plot_number" not in fields:
        match = _PLOT_RE.search(result.raw_text)
        if match:
            fields["plot_number"] = match.group(1)

    return fields


def _from_key_values(key_values: dict[str, str], aliases: tuple[str, ...]) -> str | None:
    """First non-empty value whose key contains one of the aliases. Exact
    matches win over substring matches so 'date' doesn't shadow 'issue date'."""
    for alias in aliases:
        if alias in key_values and key_values[alias].strip():
            return key_values[alias].strip()
    for alias in aliases:
        for key, value in key_values.items():
            if alias in key and value.strip():
                return value.strip()
    return None
