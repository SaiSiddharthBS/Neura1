"""Validate a company's CSV exports before anything touches the graph.

Each record type has a spec: required columns, value types, and references to other records.
Validation reports every problem with file, row, and column, so a non-technical owner of the
spreadsheet can fix it. Nothing is written unless validation passes with zero errors.
"""

import csv
import io
from dataclasses import dataclass, field
from datetime import date

from neura1.ingest.structured import BomCycleError, check_bom_cycles


@dataclass(frozen=True)
class Spec:
    name: str
    title: str
    columns: tuple[str, ...]
    required: tuple[str, ...]
    key: str | None = "id"
    ints: tuple[str, ...] = ()
    positive: tuple[str, ...] = ()
    dates: tuple[str, ...] = ()
    enums: dict = field(default_factory=dict)
    refs: dict = field(default_factory=dict)  # column -> record type it must reference
    example: tuple[str, ...] = ()
    help: str = ""


SPECS: dict[str, Spec] = {s.name: s for s in [
    Spec("teams", "Teams", ("id", "name"), ("id", "name"), example=("T-HW", "Hardware Engineering")),
    Spec("people", "People", ("id", "name", "role", "team_id"), ("id", "name", "team_id"),
         refs={"team_id": "teams"}, example=("P-PRIYA", "Priya Nair", "Power Hardware Lead", "T-HW")),
    Spec("items", "Items (products, assemblies, parts, firmware, tests)",
         ("id", "kind", "name", "mpn", "manufacturer"), ("id", "kind", "name"),
         enums={"kind": {"product", "assembly", "part", "firmware", "test"}},
         example=("NB54360", "part", "Buck regulator 3.3V 3A", "NB54360", "Northbridge Semi"),
         help="One row per thing you design, buy, or maintain. mpn is the manufacturer part number."),
    Spec("revisions", "Revisions", ("id", "item_id", "rev", "status", "effective_from"),
         ("id", "item_id", "rev", "status"), dates=("effective_from",),
         enums={"status": {"draft", "released", "obsolete"}}, refs={"item_id": "items"},
         example=("PSU-24-2", "PSU-24", "2", "released", "2025-04-20")),
    Spec("bom", "Bill of materials lines", ("parent_rev", "child_item", "child_rev", "qty", "uom", "refdes"),
         ("parent_rev", "child_item", "qty", "uom"), key=None, ints=("qty",), positive=("qty",),
         refs={"parent_rev": "revisions", "child_item": "items", "child_rev": "revisions"},
         example=("PSU-24-2", "NB54360", "", "1", "ea", "U3"),
         help="child_rev is required when the child is an assembly: it pins which revision is built in."),
    Spec("alternates", "Alternate parts", ("item_id", "alt_item_id", "basis", "note"), ("item_id", "alt_item_id", "basis"),
         key=None, refs={"item_id": "items", "alt_item_id": "items"},
         example=("NB54360", "NB54361-L", "manufacturer_crossref", "Pin-compatible per datasheet")),
    Spec("dependencies", "Dependencies (firmware, tests, docs on parts)", ("from_item", "to_item", "note"),
         ("from_item", "to_item"), key=None, refs={"from_item": "items", "to_item": "items"},
         example=("FW-PMIC-SEQ", "NB54360", "Power-good timing assumes 4 ms soft-start")),
    Spec("ownership", "Ownership", ("person_id", "target_id"), ("person_id", "target_id"), key=None,
         refs={"person_id": "people", "target_id": "*"}, example=("P-PRIYA", "PSU-24")),
    Spec("suppliers", "Suppliers", ("id", "name"), ("id", "name"), example=("S-DECCAN", "Deccan Components")),
    Spec("quotes", "Supplier quotes", ("id", "supplier_id", "item_id", "unit_price", "currency", "moq", "lead_weeks",
                                       "valid_from", "valid_until"),
         ("id", "supplier_id", "item_id", "unit_price", "currency", "valid_from", "valid_until"),
         ints=("moq", "lead_weeks"), dates=("valid_from", "valid_until"),
         refs={"supplier_id": "suppliers", "item_id": "items"},
         example=("Q-101", "S-DECCAN", "NB54360", "250", "INR", "100", "6", "2026-07-01", "2026-12-31")),
    Spec("stock", "Stock", ("item_id", "on_hand", "allocated"), ("item_id", "on_hand"), key="item_id",
         ints=("on_hand", "allocated"), refs={"item_id": "items"}, example=("NB54360", "180", "120")),
    Spec("customers", "Customers", ("id", "name"), ("id", "name"), example=("C-KAVERI", "Kaveri Water Utilities")),
    Spec("builds", "Planned builds", ("id", "rev_id", "qty", "planned_date", "status"), ("id", "rev_id", "qty", "planned_date"),
         ints=("qty",), positive=("qty",), dates=("planned_date",), refs={"rev_id": "revisions"},
         example=("BO-0412", "VC-200-C", "100", "2026-11-03", "planned")),
    Spec("orders", "Customer orders", ("id", "customer_id", "build_id", "qty", "due_date", "penalty_note"),
         ("id", "customer_id", "qty", "due_date"), ints=("qty",), positive=("qty",), dates=("due_date",),
         refs={"customer_id": "customers", "build_id": "builds"},
         example=("SO-881", "C-KAVERI", "BO-0412", "80", "2026-11-20", "Penalty per clause 9.2")),
    Spec("shipments", "Shipped units", ("id", "customer_id", "rev_id", "qty", "shipped_on"),
         ("id", "customer_id", "rev_id", "qty"), ints=("qty",), dates=("shipped_on",),
         refs={"customer_id": "customers", "rev_id": "revisions"},
         example=("SH-2024-07", "C-KAVERI", "VC-200-B", "220", "2024-07-18")),
]}

NOUN = {"teams": "team", "people": "person", "items": "item", "revisions": "revision", "suppliers": "supplier",
        "quotes": "quote", "customers": "customer", "builds": "build", "orders": "order", "shipments": "shipment"}

# Load order respects references.
ORDER = ["teams", "people", "items", "revisions", "bom", "alternates", "dependencies", "suppliers", "quotes",
         "stock", "customers", "builds", "orders", "shipments", "ownership"]


def template_csv(name: str) -> str:
    s = SPECS[name]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(s.columns)
    w.writerow(s.example)
    return buf.getvalue()


# Common column names from ERP/PLM/EDA exports, normalised (lowercase, letters and digits only).
ALIASES = {
    "quantity": "qty", "qtyperboard": "qty", "qtyper": "qty",
    "reference": "refdes", "references": "refdes", "designator": "refdes", "designators": "refdes",
    "refdesignator": "refdes", "referencedesignator": "refdes",
    "manufacturerpartnumber": "mpn", "mfrpartnumber": "mpn", "mfrpn": "mpn", "mfgpartnumber": "mpn",
    "mfgpartno": "mpn", "manufacturerpn": "mpn", "partnumber": "mpn", "mpn1": "mpn",
    "mfr": "manufacturer", "mfg": "manufacturer", "manufacturername": "manufacturer", "manufacturer1": "manufacturer",
    "description": "name", "value": "name", "comment": "name",
    "duedate": "due_date", "planneddate": "planned_date", "unitprice": "unit_price", "leadtime": "lead_weeks",
    "leadtimeweeks": "lead_weeks", "validfrom": "valid_from", "validuntil": "valid_until", "validto": "valid_until",
    "onhand": "on_hand", "itemid": "item_id", "partid": "item_id", "internalpn": "item_id",
}


def canonical(col: str) -> str:
    key = "".join(ch for ch in col.lower() if ch.isalnum())
    if key in ALIASES:
        return ALIASES[key]
    return "_".join(col.strip().lower().replace("-", " ").split())


def eda_bom_to_records(data: list[dict], parent_rev: str, known_mpn: dict[str, str],
                       known_ids: set[str] = frozenset()) -> tuple[list[dict], list[dict]]:
    """Turn a KiCad/Altium-style BOM (one row per part, designators listed) into items and BOM lines.

    A part already in the graph is matched by manufacturer part number; otherwise it is created with the MPN as id.
    """
    items, bom = [], []
    for r in data:
        mpn = r.get("mpn", "").strip()
        refdes = r.get("refdes", "").strip()
        qty = r.get("qty", "").strip() or str(len([d for d in refdes.replace(";", ",").split(",") if d.strip()]))
        upper_ids = {i.upper(): i for i in known_ids}
        item_id = (r.get("item_id", "").strip() or known_mpn.get(mpn.upper()) or upper_ids.get(mpn.upper()) or mpn)
        if item_id and item_id not in known_ids and item_id not in known_mpn.values() \
                and all(i["id"] != item_id for i in items):
            items.append({"id": item_id, "kind": "part", "name": r.get("name", "") or mpn, "mpn": mpn,
                          "manufacturer": r.get("manufacturer", "")})
        bom.append({"parent_rev": parent_rev, "child_item": item_id, "child_rev": "", "qty": qty, "uom": "ea",
                    "refdes": refdes})
    return items, bom


def detect(filename: str, header: list[str]) -> str | None:
    stem = filename.rsplit("/", 1)[-1].rsplit(".", 1)[0].lower()
    if stem in SPECS:
        return stem
    cols = set(header)
    matches = [s.name for s in SPECS.values() if set(s.required) <= cols]
    # Prefer the spec that explains the most columns
    return max(matches, key=lambda n: len(set(SPECS[n].columns) & cols), default=None)


@dataclass
class Issue:
    level: str  # error | warning
    file: str
    row: int | None
    column: str | None
    message: str


def is_eda_bom(header: list[str]) -> bool:
    cols = set(header)
    return {"refdes", "mpn"} <= cols and "parent_rev" not in cols


def parse(text: str) -> tuple[list[str], list[dict]]:
    sample = text.lstrip("\ufeff")
    try:
        dialect = csv.Sniffer().sniff(sample[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(sample), dialect=dialect)
    header = [canonical(h) for h in (reader.fieldnames or [])]
    reader.fieldnames = header
    return header, [{k: (v or "").strip() for k, v in r.items() if k is not None} for r in reader]


def validate(files: dict[str, str], existing: dict[str, set[str]] | None = None,
             eda_parent_rev: str | None = None) -> dict:
    """files: filename -> CSV text. existing: record type -> ids already in the graph.

    eda_parent_rev: the revision an EDA-style BOM export (Reference/Qty/MPN columns) belongs to.
    """
    existing = existing or {}
    issues: list[Issue] = []
    parsed: dict[str, tuple[str, list[dict]]] = {}
    converted: list[str] = []

    for fname, text in files.items():
        header, data = parse(text)
        if is_eda_bom(header):
            if not eda_parent_rev:
                issues.append(Issue("error", fname, None, None,
                                    "This looks like a BOM exported from a CAD tool. Say which revision it belongs to "
                                    "(e.g. VC-200-C) so its lines can be attached."))
                continue
            items, bom = eda_bom_to_records(data, eda_parent_rev, existing.get("_mpn", {}),
                                            existing.get("items", set()))
            for kind, rows_ in (("items", items), ("bom", bom)):
                prev = parsed.get(kind, (fname, []))[1]
                parsed[kind] = (fname, prev + rows_)
            converted.append(f"{fname}: {len(bom)} BOM lines for {eda_parent_rev}, {len(items)} new parts")
            continue
        kind = detect(fname, header)
        if kind is None:
            issues.append(Issue("error", fname, None, None,
                                "Could not recognise this file. Rename it after a template (e.g. bom.csv) "
                                "or use the template's column names."))
            continue
        spec = SPECS[kind]
        missing = [c for c in spec.required if c not in header]
        if missing:
            issues.append(Issue("error", fname, None, None, f"Missing required columns: {', '.join(missing)}"))
            continue
        extra = [c for c in header if c not in spec.columns]
        if extra:
            issues.append(Issue("warning", fname, None, None, f"Ignoring unknown columns: {', '.join(extra)}"))
        for r in data:
            for c in spec.columns:
                r.setdefault(c, "")
        parsed[kind] = (fname, data)

    ids = {k: set(v) for k, v in existing.items()}
    for kind, (fname, data) in parsed.items():
        if SPECS[kind].key:
            ids.setdefault(kind, set()).update(r[SPECS[kind].key] for r in data if r[SPECS[kind].key])
    all_ids = set().union(*ids.values()) if ids else set()
    item_kind = {r["id"]: r["kind"] for r in parsed.get("items", ("", []))[1]} | existing.get("_item_kind", {})
    rev_item = {r["id"]: r["item_id"] for r in parsed.get("revisions", ("", []))[1]} | existing.get("_rev_item", {})

    for kind, (fname, data) in parsed.items():
        spec = SPECS[kind]
        seen: set[str] = set()
        for i, r in enumerate(data, start=2):  # row 1 is the header
            def err(col, msg, level="error"):
                issues.append(Issue(level, fname, i, col, msg))

            for c in spec.required:
                if not r[c]:
                    err(c, "is empty")
            if spec.key and r[spec.key]:
                if r[spec.key] in seen:
                    err(spec.key, f"duplicate id {r[spec.key]}")
                seen.add(r[spec.key])
            for c in spec.ints:
                if r[c]:
                    try:
                        v = int(r[c])
                        if v < 0 or (c in spec.positive and v == 0):
                            err(c, f"must be {'positive' if c in spec.positive else 'zero or more'}, got {r[c]}")
                    except ValueError:
                        err(c, f"must be a whole number, got {r[c]!r}")
            if kind == "quotes" and r["unit_price"]:
                try:
                    if float(r["unit_price"]) <= 0:
                        err("unit_price", "must be positive")
                except ValueError:
                    err("unit_price", f"must be a number, got {r['unit_price']!r}")
            for c in spec.dates:
                if r[c]:
                    try:
                        date.fromisoformat(r[c])
                    except ValueError:
                        err(c, f"must be a date like 2026-11-03, got {r[c]!r}")
            for c, allowed in spec.enums.items():
                if r[c] and r[c] not in allowed:
                    err(c, f"must be one of {', '.join(sorted(allowed))}, got {r[c]!r}")
            for c, target in spec.refs.items():
                v = r[c]
                if not v:
                    continue
                pool = all_ids if target == "*" else ids.get(target, set())
                if v not in pool:
                    err(c, f"{v} is not a known {'record' if target == '*' else NOUN.get(target, target)}")
            if kind == "bom" and r["parent_rev"] in existing.get("revisions", set()) \
                    and existing.get("_rev_status", {}).get(r["parent_rev"]) == "released":
                err("parent_rev", f"changes released revision {r['parent_rev']}. Released revisions normally "
                                  "change only through a new revision", "warning")
            if kind == "bom" and r["child_item"]:
                ck = item_kind.get(r["child_item"])
                if ck == "assembly" and not r["child_rev"]:
                    err("child_rev", f"{r['child_item']} is an assembly, so child_rev must say which revision")
                if r["child_rev"] and rev_item.get(r["child_rev"], r["child_item"]) != r["child_item"]:
                    err("child_rev", f"{r['child_rev']} is a revision of {rev_item.get(r['child_rev'])}, "
                                     f"not {r['child_item']}")
                if r["uom"] and r["uom"] != "ea":
                    err("uom", f"unit {r['uom']!r} is stored but cost roll-ups only handle 'ea' today", "warning")
            if kind == "quotes" and r["valid_from"] and r["valid_until"] and r["valid_until"] < r["valid_from"]:
                err("valid_until", "is before valid_from")
            if kind == "stock" and r["allocated"].isdigit() and r["on_hand"].isdigit() \
                    and int(r["allocated"]) > int(r["on_hand"]):
                err("allocated", "is more than on_hand", "warning")

    if "bom" in parsed:
        try:
            check_bom_cycles(parsed["bom"][1])
        except BomCycleError as exc:
            issues.append(Issue("error", parsed["bom"][0], None, None, f"BOM contains itself: {exc}"))

    errors = [x for x in issues if x.level == "error"]
    return {
        "ok": not errors,
        "files": [{"file": f, "type": k, "title": SPECS[k].title, "rows": len(d)} for k, (f, d) in parsed.items()],
        "issues": [x.__dict__ for x in issues],
        "errors": len(errors),
        "warnings": len(issues) - len(errors),
        "converted": converted,
        "_parsed": {k: d for k, (_, d) in parsed.items()},
    }
