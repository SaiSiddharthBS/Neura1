"""Deterministic cost scenario for a component price change.

Inputs come from graph queries; nothing here is estimated by a model. Every number in the
output can be traced to a build, a BOM quantity, a stock record, or a quote.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


class CostError(ValueError):
    pass


@dataclass(frozen=True)
class Demand:
    build_id: str
    revision: str
    build_qty: int
    qty_per_unit: int

    @property
    def parts(self) -> int:
        return self.build_qty * self.qty_per_unit


@dataclass(frozen=True)
class Quote:
    id: str
    unit_price: Decimal
    currency: str
    moq: int
    valid_from: date
    valid_until: date
    lead_weeks: int | None = None

    def valid_on(self, day: date) -> bool:
        return self.valid_from <= day <= self.valid_until


@dataclass(frozen=True)
class OneTimeCost:
    label: str
    amount: Decimal
    currency: str
    source: str


@dataclass
class Scenario:
    currency: str
    gross_need: int
    free_stock: int
    net_need: int
    purchase_qty: int
    baseline_quote: str
    baseline_unit_price: Decimal
    new_unit_price: Decimal
    material_delta: Decimal
    one_time_total: Decimal
    total_delta: Decimal
    demand: list[Demand]
    one_time: list[OneTimeCost]
    formula: str
    assumptions: list[str] = field(default_factory=list)
    excluded: list[str] = field(default_factory=list)


EXCLUDED = ["freight", "taxes and duties", "FX movement", "scrap and yield loss", "assembly labour",
            "tooling", "other BOM lines (assumed unchanged)"]


def pick_baseline(quotes: list[Quote], as_of: date) -> tuple[Quote, list[str]]:
    """The baseline is the lowest-priced quote valid on `as_of`. Expired quotes are reported, never used."""
    notes = [f"Quote {q.id} ignored: valid {q.valid_from}..{q.valid_until}, not on {as_of}"
             for q in quotes if not q.valid_on(as_of)]
    valid = [q for q in quotes if q.valid_on(as_of)]
    if not valid:
        raise CostError(f"No quote valid on {as_of}; the baseline price is unknown")
    return min(valid, key=lambda q: q.unit_price), notes


def price_change_scenario(
    demand: list[Demand],
    on_hand: int,
    allocated: int,
    quotes: list[Quote],
    new_unit_price: Decimal | None,
    new_currency: str,
    as_of: date,
    one_time: list[OneTimeCost] = (),
) -> Scenario:
    if new_unit_price is None:
        raise CostError("New unit price is missing; refusing to assume one")
    baseline, notes = pick_baseline(quotes, as_of)
    if baseline.currency != new_currency or any(c.currency != new_currency for c in one_time):
        raise CostError("Mixed currencies and no FX rate supplied")

    gross = sum(d.parts for d in demand)
    free = max(on_hand - allocated, 0)
    net = max(gross - free, 0)
    purchase = max(net, baseline.moq) if net > 0 else 0

    unit_delta = new_unit_price - baseline.unit_price
    material = purchase * unit_delta
    one_time_total = sum((c.amount for c in one_time), Decimal(0))

    assumptions = notes + [
        f"Unallocated stock ({free}) covers demand first and was bought at the old price",
        "All demand is purchased at the new price (no orders confirmed before the effective date)",
    ]
    if purchase > net:
        assumptions.append(f"Purchase rounded up from {net} to MOQ {baseline.moq}")

    return Scenario(
        currency=new_currency,
        gross_need=gross,
        free_stock=free,
        net_need=net,
        purchase_qty=purchase,
        baseline_quote=baseline.id,
        baseline_unit_price=baseline.unit_price,
        new_unit_price=new_unit_price,
        material_delta=material,
        one_time_total=one_time_total,
        total_delta=material + one_time_total,
        demand=list(demand),
        one_time=list(one_time),
        formula=f"{purchase} x ({new_unit_price} - {baseline.unit_price}) + {one_time_total}",
        assumptions=assumptions,
        excluded=EXCLUDED,
    )
