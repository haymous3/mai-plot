"""Weekly Railway cost check (SCRUM-250).

Pulls the last 7 days of memory + CPU for every service in one Railway
environment, turns the averages into a monthly cost at Railway's published
usage rates, and flags anything over budget.

Why this exists: from launch until SCRUM-249 the six Celery workers each idled
at 3.0-3.6 GB (prefork sized from the HOST's cpu_count) — ~75% of the bill —
and nothing told anyone, because nothing failed. This is the thing that tells.

Stdlib only, so the workflow needs no install step. Exit code is 0 either way;
the workflow decides what to do with the report. Writes:
  - a Markdown report to --report (the workflow posts it)
  - "flagged=true|false" to $GITHUB_OUTPUT when running in Actions

Offline run (no token): `--from-file fixture.json`, where the fixture is
{"services": {"<id>": "<name>"}, "metrics": <the GraphQL `metrics` list>}.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

API_URL = "https://backboard.railway.com/graphql/v2"

# Railway usage pricing (docs.railway.com, checked 2026-10-21). Override via env
# if they change rather than editing the script.
MEMORY_USD_PER_GB_MONTH = float(os.environ.get("MEMORY_USD_PER_GB_MONTH", "10"))
CPU_USD_PER_VCPU_MONTH = float(os.environ.get("CPU_USD_PER_VCPU_MONTH", "20"))

_SERVICES_QUERY = """
query($id: String!) {
  project(id: $id) { services { edges { node { id name } } } }
}
"""

_METRICS_QUERY = """
query($projectId: String!, $environmentId: String!, $startDate: DateTime!) {
  metrics(
    projectId: $projectId
    environmentId: $environmentId
    startDate: $startDate
    measurements: [MEMORY_USAGE_GB, CPU_USAGE]
    groupBy: [SERVICE_ID]
    sampleRateSeconds: 3600
  ) {
    measurement
    tags { serviceId }
    values { ts value }
  }
}
"""


@dataclass(frozen=True)
class ServiceCost:
    name: str
    memory_gb: float
    vcpu: float
    memory_limit_gb: float

    @property
    def monthly_usd(self) -> float:
        return self.memory_gb * MEMORY_USD_PER_GB_MONTH + self.vcpu * CPU_USD_PER_VCPU_MONTH

    @property
    def over_limit(self) -> bool:
        return self.memory_gb > self.memory_limit_gb


def _graphql(token: str, query: str, variables: dict[str, Any]) -> dict[str, Any]:
    # Project tokens and account/workspace tokens use DIFFERENT headers; send
    # the right one so either kind works as the RAILWAY_TOKEN secret.
    headers = {"Content-Type": "application/json", "User-Agent": "maiplot-cost-check"}
    if os.environ.get("RAILWAY_TOKEN_KIND", "project") == "project":
        headers["Project-Access-Token"] = token
    else:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        API_URL,
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        body: dict[str, Any] = json.load(resp)
    if body.get("errors"):
        raise RuntimeError(f"Railway API error: {body['errors']}")
    data: dict[str, Any] = body["data"]
    return data


def fetch(
    token: str, project_id: str, environment_id: str
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    project = _graphql(token, _SERVICES_QUERY, {"id": project_id})["project"]
    services = {e["node"]["id"]: e["node"]["name"] for e in project["services"]["edges"]}
    start = (datetime.now(UTC) - timedelta(days=7)).isoformat()
    metrics = _graphql(
        token,
        _METRICS_QUERY,
        {"projectId": project_id, "environmentId": environment_id, "startDate": start},
    )["metrics"]
    return services, metrics


def parse_limits(spec: str) -> dict[str, float]:
    """`elasticsearch=1.5,postgres=0.5` -> {"elasticsearch": 1.5, ...}."""
    out: dict[str, float] = {}
    for part in filter(None, (p.strip() for p in spec.split(","))):
        name, _, value = part.partition("=")
        out[name.strip()] = float(value)
    return out


def summarise(
    services: dict[str, str],
    metrics: list[dict[str, Any]],
    *,
    default_limit_gb: float,
    limits: dict[str, float],
) -> list[ServiceCost]:
    """Average each service's hourly samples. Billing is per minute of actual
    usage, so the AVERAGE (not the peak) is what the bill follows."""
    avg: dict[tuple[str, str], float] = {}
    for series in metrics:
        sid = (series.get("tags") or {}).get("serviceId")
        values = [v["value"] for v in series.get("values") or [] if v.get("value") is not None]
        if sid and values:
            avg[(sid, series["measurement"])] = sum(values) / len(values)

    rows = [
        ServiceCost(
            name=name,
            memory_gb=avg.get((sid, "MEMORY_USAGE_GB"), 0.0),
            vcpu=avg.get((sid, "CPU_USAGE"), 0.0),
            memory_limit_gb=limits.get(name, default_limit_gb),
        )
        for sid, name in services.items()
    ]
    return sorted(rows, key=lambda r: r.monthly_usd, reverse=True)


def render(rows: list[ServiceCost], *, budget_usd: float) -> tuple[str, bool]:
    total = sum(r.monthly_usd for r in rows)
    total_gb = sum(r.memory_gb for r in rows)
    over = [r for r in rows if r.over_limit]
    flagged = total > budget_usd or bool(over)

    lines = [
        "## Railway weekly cost check",
        "",
        f"**Estimated usage: ${total:,.2f}/month** (budget ${budget_usd:,.0f}) "
        f"— {total_gb:.2f} GB average memory across {len(rows)} services, "
        "7-day averages at "
        f"${MEMORY_USD_PER_GB_MONTH:g}/GB-month + ${CPU_USD_PER_VCPU_MONTH:g}/vCPU-month. "
        "Plan subscription fee not included.",
        "",
    ]
    if total > budget_usd:
        lines.append(f"🔴 **Over budget by ${total - budget_usd:,.2f}/month.**")
    for r in over:
        lines.append(
            f"🔴 **{r.name}** averages {r.memory_gb:.2f} GB "
            f"(limit {r.memory_limit_gb:g} GB) — ${r.monthly_usd:,.2f}/month."
        )
    if not flagged:
        lines.append("🟢 Within budget, no service over its memory limit.")
    lines += [
        "",
        "| Service | Avg memory (GB) | Avg vCPU | $/month |",
        "|---|---:|---:|---:|",
    ]
    for r in rows:
        mark = " 🔴" if r.over_limit else ""
        lines.append(
            f"| {r.name}{mark} | {r.memory_gb:.3f} | {r.vcpu:.4f} | {r.monthly_usd:,.2f} |"
        )
    lines += [
        "",
        "⚠️ A stopped service can keep reporting its last memory reading, so a "
        "non-zero figure does not prove it is running — check the Railway "
        "dashboard before acting on a single row.",
    ]
    return "\n".join(lines) + "\n", flagged


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--from-file", help="read a fixture instead of calling Railway")
    ap.add_argument("--report", default="railway-cost-report.md")
    args = ap.parse_args()

    if args.from_file:
        with open(args.from_file, encoding="utf-8") as fh:
            fixture = json.load(fh)
        services, metrics = fixture["services"], fixture["metrics"]
    else:
        token = os.environ.get("RAILWAY_TOKEN")
        if not token:
            print("RAILWAY_TOKEN is not set", file=sys.stderr)
            return 1
        services, metrics = fetch(
            token, os.environ["RAILWAY_PROJECT_ID"], os.environ["RAILWAY_ENVIRONMENT_ID"]
        )

    rows = summarise(
        services,
        metrics,
        default_limit_gb=float(os.environ.get("MEMORY_LIMIT_GB", "1.0")),
        limits=parse_limits(os.environ.get("MEMORY_LIMIT_OVERRIDES", "")),
    )
    report, flagged = render(rows, budget_usd=float(os.environ.get("BUDGET_USD", "80")))

    with open(args.report, "w", encoding="utf-8") as fh:
        fh.write(report)
    print(f"report written to {args.report} (flagged={flagged})")
    if gh_out := os.environ.get("GITHUB_OUTPUT"):
        with open(gh_out, "a", encoding="utf-8") as fh:
            fh.write(f"flagged={'true' if flagged else 'false'}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
