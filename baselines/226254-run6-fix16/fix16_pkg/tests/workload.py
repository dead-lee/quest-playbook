"""Trusted concurrent workload + verifier for the OMS services (stdlib + pymysql only).

All operations are generated here at run time from an OS random source; deadlocks and lock
wait timeouts are read from the MySQL server's own InnoDB counters, not from the services.
"""
import json
import random
import threading
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from decimal import Decimal

import pymysql

ORDER = "http://127.0.0.1:8081"
ITEM = "http://127.0.0.1:8082"
N_PRODUCTS = 20


def db(sock):
    return pymysql.connect(unix_socket=sock, user="root", database="oms", autocommit=True)


def metrics(sock):
    c = db(sock)
    with c.cursor() as cur:
        cur.execute("SELECT name, count FROM information_schema.INNODB_METRICS "
                    "WHERE name IN ('lock_deadlocks','lock_timeouts')")
        m = dict(cur.fetchall())
    c.close()
    return m


# Concurrency is counted only from oms_app transactions that currently hold (or wait for)
# InnoDB row locks on the workload tables (performance_schema.data_locks); idle or lock-free transactions
# do not count.
LOCKING_TRX_SQL = (
    "SELECT COUNT(DISTINCT l.ENGINE_TRANSACTION_ID) FROM performance_schema.data_locks l "
    "JOIN performance_schema.threads t ON t.THREAD_ID = l.THREAD_ID "
    "WHERE t.PROCESSLIST_USER = 'oms_app' AND l.LOCK_TYPE = 'RECORD' "
    "AND l.OBJECT_SCHEMA = 'oms' AND l.OBJECT_NAME IN ('orders','order_items','inventory')")


def call(base, path, body=None):
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(base + path, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"null")
        except Exception:
            return e.code, None
    except Exception as e:  # connection reset, timeout ...
        return 599, {"error": repr(e)}


def get(base, path):
    try:
        with urllib.request.urlopen(base + path, timeout=30) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception as e:
        return 599, {"error": repr(e)}


class Op:
    def __init__(self, kind, order=None, lines=None, rng=None):
        self.kind, self.order, self.lines, self.rng = kind, order, lines, rng
        self.status = None
        self.body = None
        self.t_send = self.t_recv = None

    def run(self):
        self.t_send = time.monotonic()
        try:
            return self._run()
        finally:
            self.t_recv = time.monotonic()

    def _run(self):
        if self.kind == "edit":
            self.status, self.body = call(ORDER, f"/orders/{self.order}/edit", {"lines": self.lines})
        elif self.kind == "cancel":
            self.status, self.body = call(ORDER, f"/orders/{self.order}/cancel")
        elif self.kind == "confirm":
            self.status, self.body = call(ITEM, f"/items/{self.order}/confirm")
        elif self.kind == "reprice":
            a, b, d = self.rng
            self.status, self.body = call(ITEM, "/items/reprice",
                                  {"fromProductId": a, "toProductId": b, "delta": str(d)})
        return self.status


def gen_ops(rng, kinds, orders, n):
    ops = []
    cancellable = list(orders)
    rng.shuffle(cancellable)
    cancel_budget = set(cancellable[: max(1, len(orders) // 4)]) if "cancel" in kinds else set()
    cancelled = []
    for _ in range(n):
        k = rng.choice(kinds)
        o = rng.choice(orders)
        if k == "edit":
            ps = rng.sample(range(1, N_PRODUCTS + 1), rng.randint(2, 4))
            ops.append(Op("edit", o, [{"productId": p, "qty": rng.randint(1, 5)} for p in ps]))
        elif k == "cancel":
            if cancel_budget:
                cancelled.append(cancel_budget.pop())
                ops.append(Op("cancel", cancelled[-1]))
            elif rng.random() < 0.3:  # duplicate cancel of an order already being cancelled
                ops.append(Op("cancel", rng.choice(cancelled)))
            else:
                ops.append(Op("confirm", o))
        elif k == "confirm":
            ops.append(Op("confirm", o))
        else:
            a = rng.randint(1, N_PRODUCTS - 3)
            ops.append(Op("reprice", rng=(a, a + rng.randint(1, 3), Decimal(rng.randint(1, 50)) / 100)))
    return ops


def run_phase(sock, ops, threads, max_secs=45):
    before = metrics(sock)
    it = iter(ops)
    lock = threading.Lock()
    peak = [0]
    iso = set()
    stop = threading.Event()
    deadline = time.monotonic() + max_secs

    def sampler():
        c = db(sock)
        with c.cursor() as cur:
            while not stop.is_set():
                cur.execute(LOCKING_TRX_SQL)
                peak[0] = max(peak[0], cur.fetchone()[0])
                cur.execute("SELECT DISTINCT v.VARIABLE_VALUE FROM performance_schema.variables_by_thread v "
                            "JOIN performance_schema.threads t ON t.THREAD_ID = v.THREAD_ID "
                            "WHERE t.PROCESSLIST_USER = 'oms_app' AND v.VARIABLE_NAME = 'transaction_isolation'")
                iso.update(r[0] for r in cur.fetchall())
                time.sleep(0.02)
        c.close()

    def worker():
        while True:
            with lock:
                op = next(it, None)
            if op is None:
                return
            if time.monotonic() > deadline:
                op.status = 598  # not executed: phase ran out of time
                continue
            op.run()
            if op.t_recv > deadline:
                op.late = True   # started in time but finished after the phase limit -> failure

    st = threading.Thread(target=sampler)
    st.start()
    t0 = time.time()
    ws = [threading.Thread(target=worker) for _ in range(threads)]
    for w in ws:
        w.start()
    for w in ws:
        w.join()
    stop.set()
    st.join()
    after = metrics(sock)
    return {
        "deadlocks": after["lock_deadlocks"] - before["lock_deadlocks"],
        "lock_timeouts": after["lock_timeouts"] - before["lock_timeouts"],
        "status": dict(Counter(op.status for op in ops)),
        "peak_trx": peak[0],
        "isolation": sorted(iso),
        "secs": round(time.time() - t0, 1),
        "late": sum(1 for op in ops if getattr(op, "late", False) or op.status == 598),
        "max_secs": max_secs,
    }


def snapshot(sock):
    c = db(sock)
    with c.cursor(pymysql.cursors.DictCursor) as cur:
        cur.execute("SELECT * FROM orders")
        orders = {r["id"]: r for r in cur.fetchall()}
        cur.execute("SELECT * FROM order_items")
        items = cur.fetchall()
        cur.execute("SELECT * FROM inventory")
        inv = {r["product_id"]: r for r in cur.fetchall()}
    c.close()
    return orders, items, inv


def check_consistency(sock, init, ops):
    """Return list of problems (empty = consistent)."""
    io, ii, iinv = init
    orders, items, inv = snapshot(sock)
    probs = []
    by_order = defaultdict(list)
    for it in items:
        by_order[it["order_id"]].append(it)
    for oid, o in orders.items():
        its = by_order.get(oid, [])
        tot = sum((Decimal(i["qty"]) * i["unit_price"] for i in its), Decimal("0"))
        if o["status"] == "CANCELLED":
            if its or o["total_amount"] != 0 or o["item_count"] != 0 or o["confirmed_count"] != 0:
                probs.append(f"order {oid} cancelled but has lines/amount/counts")
            continue
        if o["total_amount"] != tot:
            probs.append(f"order {oid} total {o['total_amount']} != lines {tot}")
        if o["item_count"] != len(its):
            probs.append(f"order {oid} item_count {o['item_count']} != {len(its)}")
        if o["confirmed_count"] != sum(1 for i in its if i["status"] == "CONFIRMED"):
            probs.append(f"order {oid} confirmed_count mismatch")
    reserved = Counter()
    for it in items:
        reserved[it["product_id"]] += it["qty"]
    price_delta = defaultdict(Decimal)
    edits = defaultdict(list)
    for op in ops:
        if op.kind == "reprice" and op.status == 200:
            a, b, d = op.rng
            for p in range(a, b + 1):
                price_delta[p] += d
        if op.kind == "edit" and op.status == 200:
            edits[op.order].append(sorted((l["productId"], l["qty"]) for l in op.lines))
        if op.status not in (200, 409):
            probs.append(f"{op.kind} {op.order or op.rng} failed with HTTP {op.status}")
    probs += check_status_timeline(ops, orders)
    probs += check_bodies(ops, init, orders, price_delta)
    for it in items:  # every line carries the product's current price (reprices reach every line)
        if it["unit_price"] != inv[it["product_id"]]["unit_price"]:
            probs.append(f"line {it['id']} price {it['unit_price']} != product {it['product_id']} "
                         f"price {inv[it['product_id']]['unit_price']}")
    for name, v in [(f"order {o['id']} total", o["total_amount"]) for o in orders.values()] + \
            [(f"line {i['id']} price", i["unit_price"]) for i in items] + \
            [(f"product {p} price", r["unit_price"]) for p, r in inv.items()]:
        if not _cents(v):
            probs.append(f"{name} {v} is not an exact cent amount")
    for p, r in inv.items():
        if r["reserved"] != reserved[p]:
            probs.append(f"product {p} reserved {r['reserved']} != lines {reserved[p]}")
        if r["stock"] != iinv[p]["stock"]:
            probs.append(f"product {p} stock changed")
        if r["unit_price"] != iinv[p]["unit_price"] + price_delta[p]:
            probs.append(f"product {p} price {r['unit_price']} != expected")
    init_lines = defaultdict(list)
    for it in ii:
        init_lines[it["order_id"]].append((it["product_id"], it["qty"]))
    for oid, o in orders.items():
        if o["status"] != "OPEN":
            continue
        cur = sorted((i["product_id"], i["qty"]) for i in by_order.get(oid, []))
        allowed = edits.get(oid) or [sorted(init_lines[oid])]
        if cur not in allowed:
            probs.append(f"order {oid} lines {cur} match no accepted edit")
    if set(orders) != set(io):
        probs.append("orders rows added/removed")
    return probs


def _cents(v):
    try:
        d = Decimal(str(v))
    except Exception:
        return False
    return d.is_finite() and d == d.quantize(Decimal("0.01"))


def _amount(v):
    if isinstance(v, bool) or not isinstance(v, (int, float, str)) or not _cents(v):
        raise ValueError(f"amount {v!r} is not an exact cent number")
    return Decimal(str(v)).quantize(Decimal("0.01"))


def check_bodies(ops, init, orders, price_delta):
    """Response bodies, field by field, under the same contract as the single-thread tests.
    Bodies describe the state committed by that very request (read in its own transaction)."""
    io, ii, iinv = init
    probs = []
    for op in ops:
        b, tag = op.body, f"{op.kind} {op.order or op.rng}"
        try:
            if op.status == 409:
                assert isinstance(b, dict) and "error" in b and b.get("mysqlError") == 0, f"409 body {b!r}"
                continue
            if op.status != 200:
                continue
            assert isinstance(b, dict), f"body {b!r}"
            if op.kind in ("edit", "cancel"):
                row = orders[op.order]
                assert set(b) >= {"id", "orderNo", "customerId", "status", "totalAmount", "itemCount",
                                  "confirmedCount", "version"}, f"fields {sorted(b)}"
                assert (b["id"], b["orderNo"], b["customerId"]) == (row["id"], row["order_no"], row["customer_id"]), "ids"
                tot = _amount(b["totalAmount"])
                if op.kind == "cancel":
                    assert b["status"] == "CANCELLED" and tot == 0 and b["itemCount"] == 0 \
                        and b["confirmedCount"] == 0, f"cancel body {b}"
                else:
                    assert b["status"] == "OPEN" and b["itemCount"] == len(op.lines) \
                        and b["confirmedCount"] == 0, f"edit body {b}"
                    exp = _edit_totals(op, ops, iinv)
                    assert tot in exp, f"edit total {tot} not in exact commit-time values {sorted(exp)[:6]}"
            elif op.kind == "confirm":
                assert set(b) >= {"total", "itemCount", "confirmedCount"}, f"fields {sorted(b)}"
                tot = _amount(b["total"])
                if (tot, b["itemCount"], b["confirmedCount"]) != (0, 0, 0):
                    assert orders[op.order]["status"] in ("OPEN", "CANCELLED")
                    assert b["confirmedCount"] == b["itemCount"] and 2 <= b["itemCount"] <= 4 and tot > 0, \
                        f"confirm body {b}"
            else:
                n = b.get("orders")
                lo, hi = _reprice_counts(op, ops, init)
                assert isinstance(n, int) and not isinstance(n, bool) and lo <= n <= hi, \
                    f"reprice body {b}: expected {lo}" + (f"..{hi} (overlapping writes)" if hi != lo else "")
        except (AssertionError, ValueError, KeyError, TypeError) as e:
            probs.append(f"{tag} response body wrong: {e}")
    return probs


def _overlaps(a, b):
    """a and b ran concurrently (neither finished before the other was sent)."""
    return not (a.t_recv < b.t_send or b.t_recv < a.t_send)


def _edit_totals(op, ops, iinv):
    """Exact totals an edit may return: qty x the price committed when the edit committed.
    Reprices finished before the edit was sent are included, reprices sent after it finished
    are not; only reprices that overlapped the edit may fall on either side of its commit."""
    base = sum((Decimal(l["qty"]) * iinv[l["productId"]]["unit_price"] for l in op.lines), Decimal("0"))
    def part(r):
        a, b, d = r.rng
        return sum((Decimal(l["qty"]) * d for l in op.lines if a <= l["productId"] <= b), Decimal("0"))
    vals = {base}
    for r in ops:
        if r.kind != "reprice" or r.status != 200 or r.t_send is None:
            continue
        c = part(r)
        if not c:
            continue
        if r.t_recv < op.t_send:
            vals = {v + c for v in vals}
        elif _overlaps(r, op):
            vals |= {v + c for v in vals}
    return vals


def _reprice_counts(rp, ops, init):
    """Exact number of non-cancelled orders with a line in [a, b] at the reprice's commit.
    Per order, the state at commit is the state after its last committed edit/cancel; an
    edit/cancel finished before the reprice was sent is settled, one overlapping it may land on
    either side. Returns (min, max); min == max whenever no write on the range overlapped."""
    io, ii, iinv = init
    a, b = rp.rng[0], rp.rng[1]
    hit = lambda prods: any(a <= p <= b for p in prods)
    init_prods = defaultdict(list)
    for it in ii:
        init_prods[it["order_id"]].append(it["product_id"])
    writes = defaultdict(list)
    for op in ops:
        if op.kind in ("edit", "cancel") and op.status == 200 and op.t_send is not None:
            writes[op.order].append(op)
    lo = hi = 0
    for oid, o in io.items():
        if o["status"] == "CANCELLED":
            continue
        cand = []
        ws = [w for w in writes.get(oid, []) if w.t_send < rp.t_recv]
        settled = [w for w in ws if w.t_recv < rp.t_send]
        # candidates for "last write committed before the reprice": not definitely followed by
        # another settled write
        for w in ws:
            if not any(w.t_recv < y.t_send and y.t_recv < rp.t_send for y in settled if y is not w):
                cand.append(False if w.kind == "cancel" else hit([l["productId"] for l in w.lines]))
        if not settled:
            cand.append(hit(init_prods[oid]))
        if any(w.kind == "cancel" for w in settled):
            cand = [False]
        lo += all(cand)
        hi += any(cand)
    return lo, hi


def check_status_timeline(ops, orders):
    """409 semantics judged on the request timeline, not on the final state.
    Let C be the (single) cancel of order X that returned 200, [C.send, C.recv] its interval.
    * An edit/cancel on X that was sent after C.recv (strictly after) must get 409.
    * An edit/cancel on X that got 409 is valid only if C exists and C.send < op.recv
      (C completed before, or overlapped with, the request). With no successful cancel
      of X, or a cancel that started only after the op finished, a 409 is a failure.
    * Requests overlapping C may get 200 or 409; data must be consistent either way.
    * confirm and reprice never return 409 (confirm on a cancelled order is a 200 no-op).
    * An order whose final status is CANCELLED has exactly one successful cancel; an order
      that is still OPEN has none; every other cancel of X must return 409."""
    probs = []
    ok_cancel = defaultdict(list)
    for op in ops:
        if op.kind == "cancel" and op.status == 200:
            ok_cancel[op.order].append(op)
    for oid, o in orders.items():
        n = len(ok_cancel.get(oid, []))
        if o["status"] == "CANCELLED" and n != 1:
            probs.append(f"order {oid} is CANCELLED but {n} cancel requests returned 200")
        if o["status"] != "CANCELLED" and n:
            probs.append(f"order {oid} cancel returned 200 but order is {o['status']}")
    for op in ops:
        if op.status not in (200, 409):
            continue
        if op.kind in ("confirm", "reprice"):
            if op.status == 409:
                probs.append(f"{op.kind} {op.order or op.rng} returned 409")
            continue
        cs = [c for c in ok_cancel.get(op.order, []) if c is not op]
        c = cs[0] if cs else None
        if op.status == 409:
            if c is None or not (c.t_send < op.t_recv):
                probs.append(f"{op.kind} {op.order} rejected (409) but the order was not cancelled before/while it ran")
        elif c is not None and c.t_recv < op.t_send:
            probs.append(f"{op.kind} {op.order} returned 200 although the cancel had already completed")
    return probs
