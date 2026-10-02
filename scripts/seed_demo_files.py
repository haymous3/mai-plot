# /// script
# requires-python = ">=3.11"
# dependencies = ["boto3>=1.34"]
# ///
"""Upload placeholder files for the demo seed's document rows (SCRUM-239).

`seed_demo_data.sql` inserts document ROWS whose `s3_key` never had an object
behind it, so every seed document 404s in the admin review modal ("File
missing"). This puts a small, clearly-labelled placeholder PDF at each of those
exact keys.

Deliberately a FIXED list of the seed's keys, not "every key with no object":
a real user's lost upload must keep showing "File missing" — a placeholder in
its place would look like a document a reviewer could approve.

⚠️ Keep SEED_FILES in step with seed_demo_data.sql if its documents change.

Usage (bucket credentials from Railway → bucket → Credentials):

    AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=... \\
    S3_ENDPOINT_URL=https://... S3_BUCKET=... S3_REGION=... \\
    uv run scripts/seed_demo_files.py            # add --dry-run to only list

Existing objects are left alone, so a re-run never overwrites a real file.
"""

from __future__ import annotations

import os
import sys

# (s3_key, label shown on the placeholder) — mirrors seed_demo_data.sql.
SEED_FILES: list[tuple[str, str]] = [
    # listing_documents
    ("docs/l1/cofo.pdf", "Certificate of Occupancy - demo listing 1"),
    ("docs/l3/deed.pdf", "Deed of Assignment - demo listing 3"),
    ("docs/l6/survey.pdf", "Survey Plan - demo listing 6"),
    ("docs/l9/cofo.pdf", "Certificate of Occupancy - demo listing 9"),
    # user_pii.poa_document_s3_key (auth-service PoA review)
    ("s3://demo/poa/emeka.pdf", "Power of Attorney - Emeka Nwosu (demo)"),
    ("s3://demo/poa/ibrahim.pdf", "Power of Attorney - Ibrahim Sani (demo)"),
]


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def placeholder_pdf(label: str) -> bytes:
    """A one-page A4 PDF with three lines of text. No dependencies."""
    lines = [
        ("F1", 22, 72, 760, "DEMO PLACEHOLDER"),
        ("F1", 14, 72, 725, label),
        ("F1", 11, 72, 700, "Seed data only - not a real document. Maihomme demo."),
    ]
    stream = "".join(
        f"BT /{font} {size} Tf {x} {y} Td ({_pdf_escape(text)}) Tj ET\n"
        for font, size, x, y, text in lines
    ).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % off for off in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    return bytes(out)


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    missing = [
        name
        for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "S3_ENDPOINT_URL", "S3_BUCKET")
        if not os.environ.get(name)
    ]
    if missing:
        print(f"Missing environment variables: {', '.join(missing)}", file=sys.stderr)
        return 2

    import boto3
    from botocore.exceptions import ClientError

    bucket = os.environ["S3_BUCKET"]
    client = boto3.client(
        "s3",
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        region_name=os.environ.get("S3_REGION") or "auto",
    )

    for key, label in SEED_FILES:
        try:
            client.head_object(Bucket=bucket, Key=key)
            print(f"exists   {key}")
            continue
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") not in ("404", "NoSuchKey", "NotFound"):
                raise
        if dry_run:
            print(f"would put {key}")
            continue
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=placeholder_pdf(label),
            ContentType="application/pdf",
        )
        print(f"put      {key}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
