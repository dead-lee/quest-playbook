"""Verifier-owned process harness: fresh MySQL instance, round setup/teardown and the two
services. All children are foreground-supervised Popen objects with bounded waits and are
always terminated/killed and reaped (finally + atexit). No shell backgrounding is used."""
import atexit
import os
import random
import subprocess
import time
import urllib.request

TESTS_DIR = os.environ.get("TESTS_DIR", os.path.dirname(os.path.abspath(__file__)))
OMS_RUN = os.environ.get("OMS_RUN", "/tmp/oms-verify")
MYSQLD = os.environ.get("MYSQLD", "mysqld")
MYSQL = os.environ.get("MYSQL", "mysql")
JAVA = os.environ.get("JAVA", "java")
BASEDIR = os.environ.get("MYSQL_BASEDIR", "")
RUN_AS = os.environ.get("RUN_AS", "nobody")
SOCK = os.path.join(OMS_RUN, "mysql.sock")
_procs = []
N_PRODUCTS = 20          # product ids 1..20 (documented in the instruction)
_RNG = random.SystemRandom()
N_ORDERS = _RNG.randint(100, 140)   # fresh, random fixture for every verification run


def _gen_seed():
    rng = _RNG
    price = {p: rng.randint(100, 800) * 5 / 100 for p in range(1, N_PRODUCTS + 1)}
    reserved = {p: 0 for p in price}
    orders, items = [], []
    for o in range(1, N_ORDERS + 1):
        tot = 0
        for p in rng.sample(range(1, N_PRODUCTS + 1), 3):
            q = rng.randint(1, 5)
            reserved[p] += q
            tot += round(price[p] * 100) * q
            items.append(f"({o},{p},{q},{price[p]:.2f})")
        orders.append(f"({o},'SO{o:08d}',{rng.randint(1000, 9999)},'OPEN',{tot / 100:.2f},3,0)")
    inv = [f"({p},'SKU-{p:04d}',{price[p]:.2f},{rng.randint(50000, 150000)},{reserved[p]})"
           for p in price]
    return ("USE oms;\nINSERT INTO inventory (product_id, sku, unit_price, stock, reserved) VALUES\n"
            + ",\n".join(inv) + ";\nINSERT INTO orders (id, order_no, customer_id, status, "
            "total_amount, item_count, confirmed_count) VALUES\n" + ",\n".join(orders)
            + ";\nINSERT INTO order_items (order_id, product_id, qty, unit_price) VALUES\n"
            + ",\n".join(items) + ";\n")


SEED_SQL = _gen_seed()


def _mysqld_args():
    a = [MYSQLD, "--defaults-file=" + os.path.join(TESTS_DIR, "my.cnf")]
    if BASEDIR:
        a.append("--basedir=" + BASEDIR)
    if os.geteuid() == 0:
        a.append("--user=root")
    return a + ["--datadir=" + os.path.join(OMS_RUN, "data")]


def mysql_root(sql_file, extra=""):
    with open(sql_file) as f:
        sql = f.read()
    return subprocess.run([MYSQL, "--protocol=socket", "-S", SOCK, "-uroot"],
                          input=sql + extra, text=True, cwd=TESTS_DIR, timeout=300).returncode


def _ping():
    return subprocess.run([MYSQL, "--protocol=socket", "-S", SOCK, "-uroot", "-e", "SELECT 1"],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                          timeout=10).returncode == 0


def _spawn(args, out, env=None):
    p = subprocess.Popen(args, stdout=open(out, "w"), stderr=subprocess.STDOUT, env=env)
    _procs.append(p)
    return p


def db_start():
    os.makedirs(os.path.join(OMS_RUN, "log"), exist_ok=True)
    subprocess.run(["rm", "-rf", os.path.join(OMS_RUN, "data")], check=True)
    with open(os.path.join(OMS_RUN, "log", "init.log"), "w") as lg:
        subprocess.run(_mysqld_args() + ["--initialize-insecure"], stdout=lg,
                       stderr=subprocess.STDOUT, timeout=300, check=True)
    p = _spawn(_mysqld_args() + ["--socket=" + SOCK,
                                 "--pid-file=" + os.path.join(OMS_RUN, "mysqld.pid"),
                                 "--log-error=" + os.path.join(OMS_RUN, "log", "mysqld.err")],
               os.path.join(OMS_RUN, "log", "mysqld.stdout"))
    for _ in range(60):
        if p.poll() is not None:
            break
        if _ping():
            return
        time.sleep(1)
    raise RuntimeError("mysql failed to start")


def round_setup():
    if mysql_root(os.path.join(TESTS_DIR, "db", "setup.sql"), SEED_SQL) != 0:
        raise RuntimeError("round setup failed")


def round_teardown():
    mysql_root(os.path.join(TESTS_DIR, "db", "teardown.sql"))


def _up(url):
    try:
        with urllib.request.urlopen(url, timeout=2) as r:
            return 200 <= r.status < 300
    except Exception:
        return False


def svc_start(jars):
    logdir = os.path.join(OMS_RUN, "svclog")
    os.makedirs(logdir, exist_ok=True)
    os.chmod(logdir, 0o777)
    env = dict(os.environ, OMS_LOG_DIR=logdir, DB_HOST="127.0.0.1", DB_PORT="3306")
    runner = ["runuser", "-u", RUN_AS, "--"] if RUN_AS else []
    for s in ("order", "item"):
        _spawn(runner + [JAVA, "-Xmx512m", "-jar", os.path.join(jars, s + "-service.jar")],
               os.path.join(logdir, s + ".stdout"), env)
    for _ in range(120):
        if _up("http://localhost:8081/orders/1") and _up("http://localhost:8082/items/1"):
            return
        time.sleep(1)
    raise RuntimeError("services failed to start")


def stop_all():
    while _procs:
        p = _procs.pop()
        try:
            p.terminate()
            p.wait(timeout=15)
        except Exception:
            p.kill()
            p.wait(timeout=15)


atexit.register(stop_all)


def start_all(jars):
    try:
        os.makedirs(OMS_RUN, exist_ok=True)
        db_start()
        round_setup()
        svc_start(jars)
    except BaseException:
        stop_all()
        raise
