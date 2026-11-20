"""Generate tests/fixtures/large/handbook.md: a large, synthetic markdown document.

The handbook describes a fictional delivery network ("Lanternfish") and is
built from a hand-written skeleton plus seeded filler, so the output is the
same every run. The generated file is committed; tests never run this script.

It deliberately contains everything mdpeek must cope with: front matter, a
preamble, headings six levels deep, duplicate and self-numbered titles, '/'
in titles, setext headings, fenced code with '#' lines, HTML blocks, nested
lists, blockquotes, footnote-style text, small inline tables, a wide table
(24 columns), a deep table (320 rows) and a ragged table. It also plants
specific facts that the efficiency eval (evals/scenarios.toml) asks about.

    uv run python scripts/gen_handbook.py            # rewrite the fixture
    uv run python scripts/gen_handbook.py --check    # fail if it is stale
"""

from __future__ import annotations

import argparse
import random
import sys
import textwrap
from pathlib import Path

OUTPUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "large" / "handbook.md"
SEED = 20261120

WORDS = [
    "lantern",
    "route",
    "depot",
    "parcel",
    "courier",
    "ledger",
    "beacon",
    "harbour",
    "signal",
    "relay",
    "window",
    "manifest",
    "schedule",
    "dispatch",
    "tide",
    "current",
    "buoy",
    "cargo",
    "crate",
    "pallet",
    "sensor",
    "channel",
    "reading",
    "offset",
    "network",
    "node",
    "uplink",
    "batch",
    "queue",
    "retry",
    "backoff",
    "window",
    "threshold",
    "region",
    "zone",
    "corridor",
    "audit",
    "trace",
    "record",
    "checkpoint",
    "shift",
    "crew",
    "handover",
    "vessel",
    "dock",
    "berth",
    "crane",
    "gauge",
    "calibrate",
    "verify",
    "confirm",
    "reconcile",
    "escalate",
    "archive",
    "rotate",
    "renew",
    "provision",
    "retire",
    "quietly",
    "reliably",
    "promptly",
    "carefully",
    "steadily",
    "usually",
    "rarely",
    "always",
    "nightly",
    "hourly",
]

CITIES = [
    "Port Avalon",
    "Glenmere",
    "Saltby",
    "Corran Bay",
    "Northwick",
    "Elderford",
    "Marrow Point",
    "Dunhallow",
    "Kestrel Ford",
    "Brightwater",
    "Ashcombe",
    "Tidewell",
    "Ravenholt",
    "Larkspur",
    "Fenmouth",
    "Stonehaven",
]
REGIONS = ["North", "South", "East", "West", "Central", "Islands"]
FIRST = [
    "Ada",
    "Bram",
    "Cleo",
    "Dov",
    "Esme",
    "Finn",
    "Gia",
    "Hal",
    "Ines",
    "Joss",
    "Kai",
    "Lior",
    "Mira",
    "Nox",
    "Oren",
    "Pia",
]
LAST = [
    "Vale",
    "Thorn",
    "Reed",
    "Marsh",
    "Holt",
    "Crane",
    "Wren",
    "Frost",
    "Lark",
    "Moss",
    "Pike",
    "Rook",
    "Sage",
    "Teal",
]


class Writer:
    def __init__(self, seed: int) -> None:
        self.rng = random.Random(seed)
        self.lines: list[str] = []

    def add(self, *lines: str) -> None:
        self.lines.extend(lines)

    def blank(self) -> None:
        if self.lines and self.lines[-1] != "":
            self.lines.append("")

    def heading(self, level: int, title: str) -> None:
        self.blank()
        self.add("#" * level + " " + title, "")

    def sentence(self) -> str:
        words = self.rng.sample(WORDS, self.rng.randint(7, 14))
        return " ".join(words).capitalize() + "."

    def paragraph(self, sentences: tuple[int, int] = (2, 5)) -> None:
        text = " ".join(self.sentence() for _ in range(self.rng.randint(*sentences)))
        self.add(*textwrap.wrap(text, width=80))
        self.blank()

    def paragraphs(self, count: tuple[int, int] = (1, 3)) -> None:
        for _ in range(self.rng.randint(*count)):
            self.paragraph()

    def bullets(self, items: int = 4, nested: bool = False) -> None:
        for _ in range(items):
            self.add(f"- {self.sentence()}")
            if nested and self.rng.random() < 0.5:
                self.add(f"  - {self.sentence()}", f"    - {self.sentence()}")
        self.blank()

    def table(self, headers: list[str], rows: list[list[str]]) -> None:
        self.blank()
        self.add("| " + " | ".join(headers) + " |", "|" + "---|" * len(headers))
        self.add(*("| " + " | ".join(row) + " |" for row in rows))
        self.blank()

    def text(self) -> str:
        return "\n".join(self.lines).rstrip("\n") + "\n"


def front_matter(w: Writer) -> None:
    w.add(
        "---",
        "title: Lanternfish Operations Handbook",
        "version: 4.2",
        "audience: [operators, integrators]",
        "---",
        "",
        "This handbook describes how the Lanternfish delivery network is installed,",
        "configured and operated. It is long on purpose: read it with mdpeek.",
        "",
    )


def introduction(w: Writer) -> None:
    w.heading(1, "Introduction")
    w.paragraphs((2, 3))
    w.heading(2, "Overview")
    w.paragraphs()
    w.heading(2, "Audience / Scope")
    w.paragraphs()
    w.bullets(5)
    w.heading(2, "Conventions")
    w.paragraph()
    w.table(
        ["Marker", "Meaning"],
        [["**Note**", "Helpful context"], ["**Warning**", "Risk of data loss"]],
    )


def getting_started(w: Writer) -> None:
    w.heading(1, "Getting Started")
    w.paragraph()
    w.heading(2, "Overview")
    w.paragraphs()
    w.heading(2, "Installation")
    w.paragraph()
    w.add(
        "```bash",
        "# Install the command line tools",
        "pip install lanternfish",
        "## This is a comment, not a heading",
        "lantern init --region north",
        "```",
    )
    w.blank()
    w.paragraph()
    w.heading(3, "Verifying the install")
    w.paragraphs()
    w.add("    # indented code is not a heading either", "    lantern doctor")
    w.blank()
    w.heading(2, "First Dispatch")
    w.paragraphs((2, 3))
    w.bullets(4, nested=True)


def architecture(w: Writer) -> None:
    w.heading(1, "Architecture / Design")
    w.paragraph()
    w.heading(2, "Overview")
    w.paragraphs()
    for name in ["Beacons", "Relays", "Ledger"]:
        w.heading(2, name)
        w.paragraphs((2, 4))
        for sub in ["Lifecycle", "Failure modes"]:
            w.heading(3, sub)
            w.paragraphs()
    # No blank lines inside: CommonMark ends an HTML block at a blank line,
    # after which a '#' line really is a heading.
    w.add(
        "<details>",
        "<summary>Internal notes</summary>",
        "# This line is inside an HTML block, not a heading",
        "</details>",
    )
    w.blank()


def configuration(w: Writer) -> None:
    w.heading(1, "Configuration")
    w.paragraph()
    w.heading(2, "Overview")
    w.paragraphs()
    w.heading(2, "Networking")
    w.paragraphs()
    w.heading(3, "Timeouts")
    w.paragraphs()
    w.heading(4, "Retries")
    w.paragraph()
    w.add(
        "The default retry limit is 7 attempts, with an exponential backoff that",
        "starts at 250 ms. Set `network.retry_limit` to change it.",
    )
    w.blank()
    w.paragraph()
    w.heading(3, "Proxies")
    w.paragraphs()
    w.heading(2, "Storage")
    w.paragraphs((2, 3))
    w.table(
        ["Setting", "Default", "Description"],
        [
            ["storage.path", "/var/lib/lantern", "Where ledgers are kept"],
            ["storage.max_gb", "500", "Disk budget before archiving"],
            ["storage.archive_after_days", "90", "Age at which ledgers are archived"],
        ],
    )


def operations(w: Writer) -> None:
    w.heading(1, "Operations")
    w.paragraph()
    w.heading(2, "Overview")
    w.paragraphs()
    w.heading(2, "Regional depots")
    w.paragraph()
    rows = []
    for i in range(1, 321):
        city = w.rng.choice(CITIES)
        capacity = str(w.rng.randint(500, 9000))
        if i == 217:
            city, capacity = "Port Avalon", "4120"
        rows.append(
            [
                f"D-{i:04d}",
                city,
                w.rng.choice(REGIONS),
                capacity,
                str(w.rng.randint(2009, 2026)),
                f"{w.rng.choice(FIRST)} {w.rng.choice(LAST)}",
            ]
        )
    w.table(["Depot ID", "City", "Region", "Capacity (t)", "Opened", "Manager"], rows)
    w.heading(2, "Shift handover")
    w.paragraphs()
    w.add("> **Warning**", "> Never hand over a shift with an open manifest.")
    w.blank()
    w.bullets(6, nested=True)


def hardware(w: Writer) -> None:
    w.heading(1, "Hardware")
    w.paragraph()
    w.heading(2, "Overview")
    w.paragraphs()
    w.heading(2, "Sensors")
    w.paragraphs()
    w.heading(3, "Calibration")
    w.paragraph()
    channels = [f"Ch {c:02d}" for c in range(1, 23)]
    rows = []
    for s in range(1, 41):
        values = [f"{w.rng.uniform(-0.5, 0.5):.3f}" for _ in channels]
        if s == 14:
            values[8] = "0.137"
        rows.append([f"S-{s:02d}", *values, w.rng.choice(["ok", "drift", "replace"])])
    w.table(["Sensor", *channels, "Status"], rows)
    w.heading(3, "Mounting")
    w.paragraphs()


def security(w: Writer) -> None:
    w.heading(1, "Security")
    w.paragraph()
    w.heading(2, "Overview")
    w.paragraphs()
    w.heading(2, "Key management")
    w.paragraph()
    w.heading(3, "Rotating API keys")
    w.add(
        "1. Run `lantern keys rotate --all` from an operator workstation.",
        "2. Confirm each relay reports the new key fingerprint.",
        "3. Revoke the old keys with `lantern keys revoke --older-than 1d`.",
    )
    w.blank()
    w.paragraph()
    w.heading(3, "Storing keys")
    w.paragraphs()
    w.heading(2, "Audit logging")
    w.paragraphs((2, 3))


def troubleshooting(w: Writer) -> None:
    w.heading(1, "Troubleshooting")
    w.paragraph()
    w.heading(2, "Overview")
    w.paragraphs()
    w.heading(2, "Error codes")
    w.table(
        ["Code", "Meaning", "Action"],
        [
            ["E101", "Beacon unreachable", "Check the uplink"],
            ["E104", "Depot sync timeout", "Raise network.retry_limit"],
            ["E220", "Ledger checksum mismatch", "Run lantern ledger verify"],
            ["E305", "Sensor out of range", "Recalibrate the sensor"],
        ],
    )
    w.heading(2, "Known issues")
    w.paragraph()
    w.add(
        "| Issue | Affects | Workaround |",
        "|---|---|---|",
        "| Slow uplink | 4.1 |",
        "| Clock skew | 4.0, 4.1 | Sync NTP | Restart relay |",
        "| Duplicate manifests | 4.2 | Re-run dispatch |",
    )
    w.blank()
    w.paragraph()


def api_reference(w: Writer) -> None:
    w.heading(1, "API Reference")
    w.paragraph()
    w.heading(2, "Overview")
    w.paragraphs()
    w.heading(2, "Endpoints")
    for resource in ["Depots", "Manifests", "Beacons"]:
        w.heading(3, resource)
        w.paragraph()
        for method in ["GET", "POST"]:
            w.heading(4, f"{method} /{resource.lower()}/{{id}}")
            w.paragraph()
            w.heading(5, "Parameters")
            w.paragraph()
            w.heading(6, "Query string")
            w.bullets(3)
            w.heading(6, "Body")
            w.paragraph()


def release_notes(w: Writer) -> None:
    w.heading(1, "Release Notes")
    w.paragraph()
    for version in ["4.2", "4.1", "4.0"]:
        w.heading(2, f"{version} Release")
        w.paragraph()
        w.heading(3, "1. Changes")
        w.bullets(3)
        w.heading(3, "2. Fixes / Workarounds")
        w.bullets(3)
    w.add("Version 4.0 dropped support for v2 beacons.[^1]", "", "[^1]: See the migration guide.")
    w.blank()


def appendix(w: Writer) -> None:
    w.blank()
    w.add("Appendix", "========", "")
    w.paragraph()
    w.add("Glossary", "--------", "")
    for term in ["Beacon", "Depot", "Ledger", "Manifest", "Relay"]:
        w.add(f"**{term}**: {w.sentence()}")
        w.blank()


def filler_chapters(w: Writer) -> None:
    """Long narrative chapters, so the handbook is realistically large."""
    for chapter in ["Field Guide", "Regional Playbooks", "Case Studies"]:
        w.heading(1, chapter)
        w.paragraph()
        for region in REGIONS:
            w.heading(2, f"{region} region")
            w.paragraphs((2, 3))
            for topic in ["Routes", "Depots", "Seasonal notes", "Incidents"]:
                w.heading(3, topic)
                w.paragraphs((4, 7))
                w.bullets(w.rng.randint(3, 6), nested=True)


def build() -> str:
    w = Writer(SEED)
    for part in (
        front_matter,
        introduction,
        getting_started,
        architecture,
        configuration,
        operations,
        hardware,
        security,
        troubleshooting,
        api_reference,
        filler_chapters,
        release_notes,
        appendix,
    ):
        part(w)
    return w.text()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail if the fixture is stale")
    args = parser.parse_args()
    text = build()
    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != text:
            print(f"{OUTPUT} is stale; run scripts/gen_handbook.py", file=sys.stderr)
            return 1
        return 0
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT} ({len(text.splitlines())} lines, {len(text)} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
