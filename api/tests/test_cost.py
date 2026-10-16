from datetime import date
from decimal import Decimal as D

import pytest

from neura1.engine.cost import CostError, Demand, OneTimeCost, Quote, price_change_scenario

AS_OF = date(2026, 10, 16)
Q099 = Quote("Q-099", D(230), "INR", 100, date(2026, 1, 1), date(2026, 6, 30))
Q101 = Quote("Q-101", D(250), "INR", 100, date(2026, 7, 1), date(2026, 12, 31))
DEMAND = [Demand("BO-0412", "VC-200-C", 100, 3), Demand("BO-0421", "VC-200-C", 40, 3),
          Demand("BO-0415", "VG-50-A", 60, 1)]
REQUAL = OneTimeCost("TP-PSU-07 requalification", D(8000), "INR", "docs/TP-PSU-07_test_procedure.md")


def test_voltline_ground_truth():
    s = price_change_scenario(DEMAND, 180, 120, [Q099, Q101], D(320), "INR", AS_OF, [REQUAL])
    assert s.gross_need == 480
    assert s.free_stock == 60
    assert s.net_need == 420
    assert s.baseline_quote == "Q-101"          # Q-099 is cheaper but expired
    assert s.material_delta == D(29400)        # 420 x 70
    assert s.total_delta == D(37400)
    assert any("Q-099 ignored" in a for a in s.assumptions)


def test_moq_rounds_purchase_up():
    s = price_change_scenario([Demand("B", "R", 10, 1)], 0, 0, [Q101], D(320), "INR", AS_OF)
    assert s.purchase_qty == 100
    assert s.material_delta == D(7000)


def test_stock_covers_demand():
    s = price_change_scenario([Demand("B", "R", 10, 1)], 50, 0, [Q101], D(320), "INR", AS_OF)
    assert s.purchase_qty == 0 and s.total_delta == 0


def test_missing_price_and_expired_quotes_and_currency_are_refused():
    with pytest.raises(CostError):
        price_change_scenario(DEMAND, 0, 0, [Q101], None, "INR", AS_OF)
    with pytest.raises(CostError):
        price_change_scenario(DEMAND, 0, 0, [Q099], D(320), "INR", AS_OF)
    with pytest.raises(CostError):
        price_change_scenario(DEMAND, 0, 0, [Q101], D(4), "USD", AS_OF)
