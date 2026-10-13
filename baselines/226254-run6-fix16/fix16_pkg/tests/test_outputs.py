"""Verifier for the OMS deadlock task. MySQL and the services are started by harness.py; every test
starts from the same freshly generated (random per run) seed (round setup) and all workloads are generated here."""
import os
import random
import subprocess
from decimal import Decimal

import pytest

import harness
import workload as w

SOCK = os.environ["OMS_SOCK"]
THREADS = int(os.environ.get("OMS_THREADS", "50"))
OPS = int(os.environ.get("OMS_OPS", "400"))
SYS = random.SystemRandom()


round_setup = harness.round_setup
round_teardown = harness.round_teardown


@pytest.fixture(scope="session", autouse=True)
def services():
    harness.start_all(os.environ["OMS_JARS"])
    try:
        yield
    finally:
        harness.stop_all()


def phase(kinds, orders, reps=2, pre=None):
    """Run the concurrent workload `reps` times from a fresh seed; return the failures."""
    failures = []
    for rep in range(reps):
        round_setup()
        try:
            done, extra = pre() if pre else ([], [])
            init = w.snapshot(SOCK)
            ops = extra + w.gen_ops(random.Random(SYS.random()), kinds, orders, OPS)
            r = w.run_phase(SOCK, ops, THREADS)
            ops = done + ops
            print(kinds, rep, r)
            if r["deadlocks"]:
                failures.append(f"{r['deadlocks']} deadlocks (MySQL error 1213)")
            if r["lock_timeouts"]:
                failures.append(f"{r['lock_timeouts']} lock wait timeouts (MySQL error 1205)")
            if r["isolation"] and r["isolation"] != ["REPEATABLE-READ"]:
                failures.append(f"service sessions use isolation {r['isolation']}")
            if r["secs"] > r["max_secs"] or r["late"]:
                failures.append(f"phase took {r['secs']}s, {r['late']} requests not finished within "
                                f"the {r['max_secs']}s limit")
            if r["peak_trx"] < 4:
                failures.append(f"only {r['peak_trx']} concurrent transactions observed (work is serialized)")
            failures += w.check_consistency(SOCK, init, ops)[:5]
        finally:
            round_teardown()
        if failures:
            break
    assert not failures, "; ".join(failures[:8])


def adjacent_block(n):
    start = SYS.randint(1, harness.N_ORDERS - n)
    return list(range(start, start + n))


def test_single_thread_functional():
    """Gate: the business behaviour of every endpoint, one request at a time."""
    round_setup()
    try:
        _, items0, inv0 = w.snapshot(SOCK)
        price = {p: r["unit_price"] for p, r in inv0.items()}
        reserved = {p: r["reserved"] for p, r in inv0.items()}
        o = SYS.randint(1, 60)
        lines = [{"productId": p, "qty": SYS.randint(1, 5)} for p in SYS.sample(range(1, 21), 3)]
        st, body = w.call(w.ORDER, f"/orders/{o}/edit", {"lines": lines})
        assert st == 200, (st, body)
        for it in items0:
            if it["order_id"] == o:
                reserved[it["product_id"]] -= it["qty"]
        for l in lines:
            reserved[l["productId"]] += l["qty"]
        exp_total = sum(Decimal(l["qty"]) * price[l["productId"]] for l in lines)
        assert Decimal(str(body["totalAmount"])) == exp_total and body["itemCount"] == 3
        orders, _, _ = w.snapshot(SOCK)
        _check_order_json(body, orders[o])
        assert body["status"] == "OPEN" and body["confirmedCount"] == 0
        st, body = w.call(w.ITEM, f"/items/{o}/confirm")
        assert st == 200, (st, body)
        orders, items, inv = w.snapshot(SOCK)
        assert orders[o]["confirmed_count"] == 3
        _check_summary_json(body, orders[o])
        assert all(i["status"] == "CONFIRMED" for i in items if i["order_id"] == o)
        assert {p: r["reserved"] for p, r in inv.items()} == reserved
        a = SYS.randint(1, 17)
        b = a + 2
        d = Decimal(SYS.randint(1, 50)) / 100  # instruction: delta 0.01-0.50, span 1-3
        exp_n = _affected_open_orders(a, b)
        st, body = w.call(w.ITEM, "/items/reprice", {"fromProductId": a, "toProductId": b, "delta": str(d)})
        assert st == 200 and body["orders"] == exp_n, (st, body, exp_n)
        orders, items, inv = w.snapshot(SOCK)
        for p in range(a, b + 1):
            assert inv[p]["unit_price"] == price[p] + d
        for it in items:
            base = next((x["unit_price"] for x in items0 if x["id"] == it["id"]), None)
            if base is not None:
                assert it["unit_price"] == base + (d if a <= it["product_id"] <= b else 0)
        exp_total = sum(Decimal(l["qty"]) * (price[l["productId"]] + (d if a <= l["productId"] <= b else 0))
                        for l in lines)
        assert orders[o]["total_amount"] == exp_total
        st, body = w.call(w.ORDER, f"/orders/{o}/cancel")
        assert st == 200 and body["status"] == "CANCELLED", (st, body)
        for l in lines:
            reserved[l["productId"]] -= l["qty"]
        orders, items, inv = w.snapshot(SOCK)
        _check_order_json(body, orders[o])
        assert (orders[o]["total_amount"], orders[o]["item_count"], orders[o]["confirmed_count"]) == (0, 0, 0)
        assert not [i for i in items if i["order_id"] == o]
        assert {p: r["reserved"] for p, r in inv.items()} == reserved
        assert w.call(w.ORDER, f"/orders/{o}/edit", {"lines": lines})[0] == 409
        assert w.call(w.ORDER, f"/orders/{o}/cancel")[0] == 409
    finally:
        round_teardown()


def _check_order_json(body, row):
    assert body["id"] == row["id"] and body["orderNo"] == row["order_no"]
    assert body["customerId"] == row["customer_id"] and body["status"] == row["status"]
    assert Decimal(str(body["totalAmount"])) == row["total_amount"]
    assert body["itemCount"] == row["item_count"] and body["confirmedCount"] == row["confirmed_count"]


def _check_summary_json(body, row):
    assert Decimal(str(body["total"])) == row["total_amount"]
    assert body["itemCount"] == row["item_count"] and body["confirmedCount"] == row["confirmed_count"]


def _affected_open_orders(a, b):
    orders, items, _ = w.snapshot(SOCK)
    return len({i["order_id"] for i in items
                if a <= i["product_id"] <= b and orders[i["order_id"]]["status"] == "OPEN"})


def test_query_endpoints():
    """Gate: GET :8081/orders/{id} and GET :8082/items/{id} return the documented fields."""
    round_setup()
    try:
        orders, items, _ = w.snapshot(SOCK)
        for o in SYS.sample(sorted(orders), 5):
            st, body = w.get(w.ORDER, f"/orders/{o}")
            assert st == 200, (st, body)
            _check_order_json(body, orders[o])
            st, lines = w.get(w.ITEM, f"/items/{o}")
            assert st == 200 and isinstance(lines, list), (st, lines)
            exp = {i["id"]: i for i in items if i["order_id"] == o}
            assert sorted(l["id"] for l in lines) == sorted(exp)
            for l in lines:
                e = exp[l["id"]]
                assert l["orderId"] == o and l["productId"] == e["product_id"] and l["qty"] == e["qty"]
                assert Decimal(str(l["unitPrice"])) == e["unit_price"] and l["status"] == e["status"]
        o = SYS.choice(sorted(orders))
        st, body = w.call(w.ITEM, f"/items/{o}/confirm")
        assert st == 200, (st, body)
        orders, items, _ = w.snapshot(SOCK)
        _check_summary_json(body, orders[o])
        assert body["itemCount"] == 3 and body["confirmedCount"] == 3
        st, body = w.get(w.ORDER, f"/orders/{o}")
        assert st == 200
        _check_order_json(body, orders[o])
        a = SYS.randint(1, 18)
        exp_n = _affected_open_orders(a, a + 2)
        st, body = w.call(w.ITEM, "/items/reprice", {"fromProductId": a, "toProductId": a + 2, "delta": "0.05"})
        assert st == 200 and body["orders"] == exp_n, (st, body, exp_n)
    finally:
        round_teardown()


def test_conflict_status_codes():
    """Gate: 409 only for cancelled orders; open orders are never rejected."""
    round_setup()
    try:
        o, other = SYS.sample(range(1, harness.N_ORDERS + 1), 2)
        lines = [{"productId": p, "qty": SYS.randint(1, 5)} for p in SYS.sample(range(1, 21), 2)]
        for _ in range(3):  # repeated edits/confirms of an open order are normal business
            assert w.call(w.ORDER, f"/orders/{o}/edit", {"lines": lines})[0] == 200
            assert w.call(w.ITEM, f"/items/{o}/confirm")[0] == 200
        st, body = w.call(w.ORDER, f"/orders/{o}/cancel")
        assert st == 200 and body["status"] == "CANCELLED" and body["itemCount"] == 0
        assert Decimal(str(body["totalAmount"])) == 0
        assert w.call(w.ORDER, f"/orders/{o}/edit", {"lines": lines})[0] == 409
        assert w.call(w.ORDER, f"/orders/{o}/cancel")[0] == 409
        st, body = w.call(w.ITEM, f"/items/{o}/confirm")  # confirm of a cancelled order: 200 no-op
        assert st == 200, (st, body)
        assert (Decimal(str(body["total"])), body["itemCount"], body["confirmedCount"]) == (0, 0, 0)
        st, body = w.call(w.ORDER, f"/orders/{other}/edit", {"lines": lines})
        assert st == 200, (st, body)
        st, body2 = w.call(w.ITEM, f"/items/{other}/confirm")
        assert st == 200, (st, body2)
        orders, items, _ = w.snapshot(SOCK)
        _check_summary_json(body2, orders[other])
        assert orders[o]["status"] == "CANCELLED" and orders[other]["status"] == "OPEN"
        assert (orders[o]["total_amount"], orders[o]["item_count"], orders[o]["confirmed_count"]) == (0, 0, 0)
        assert not [i for i in items if i["order_id"] == o]
        st, body = w.get(w.ORDER, f"/orders/{o}")
        assert st == 200
        _check_order_json(body, orders[o])
        assert w.get(w.ITEM, f"/items/{o}") == (200, [])
    finally:
        round_teardown()


def test_schema_and_isolation_unchanged():
    """Gate: server isolation level and schema stay as shipped."""
    round_setup()
    try:
        c = w.db(SOCK)
        with c.cursor() as cur:
            cur.execute("SELECT @@GLOBAL.transaction_isolation")
            assert cur.fetchone()[0] == "REPEATABLE-READ"
            cur.execute("SELECT table_name, column_name, column_type, column_key, extra FROM information_schema.columns "
                        "WHERE table_schema='oms' ORDER BY table_name, ordinal_position")
            cols = cur.fetchall()
        c.close()
        assert ("orders", "id", "bigint", "PRI", "auto_increment") in cols
        assert ("order_items", "id", "bigint", "PRI", "auto_increment") in cols
    finally:
        round_teardown()


def test_concurrent_edit_and_confirm():
    """Customer edits vs warehouse confirmations on the same orders (header/lines order)."""
    phase(["edit", "confirm"], adjacent_block(10))


def test_concurrent_edit_and_cancel():
    """Edits and cancellations on adjacent orders (line delete/insert gaps, inventory)."""
    phase(["edit", "edit", "cancel"], adjacent_block(16))


def test_concurrent_reprice_and_edit():
    """Price campaigns over product ranges while customers edit and the warehouse confirms."""
    phase(["reprice", "edit", "edit", "confirm", "confirm"], adjacent_block(12))


def test_concurrent_after_cancel():
    """A cancelled order in the middle of a block: its neighbours keep working (200, consistent)."""
    block = adjacent_block(12)
    victim = block[len(block) // 2]

    def pre():
        c = w.Op("cancel", victim)
        st = c.run()
        assert st == 200, st
        rng = random.Random(SYS.random())
        late = [w.Op("edit", victim, [{"productId": p, "qty": 1} for p in rng.sample(range(1, 21), 2)])
                for _ in range(8)] + [w.Op("cancel", victim), w.Op("confirm", victim)]
        return [c], late

    phase(["edit", "confirm"], block, pre=pre)


def test_concurrent_mixed():
    """All business paths at once."""
    phase(["edit", "confirm", "cancel", "reprice"], adjacent_block(30), reps=3)
