#!/bin/bash
# Verifier for the OMS deadlock task.
# - A fresh MySQL 8 instance is initialised from the verifier's own my.cnf (REPEATABLE READ,
#   InnoDB defaults); schema, seed data, the DML-only service account and round setup/teardown
#   come from tests/db, not from the candidate.
# - The candidate project in /app is built offline and its two services run as the
#   unprivileged user "nobody" (started by harness.py); they only reach MySQL through the oms_app account.
# - Workloads are generated at verification time; deadlocks/lock timeouts are read from the
#   server's INNODB_METRICS counters, consistency is recomputed from the database itself.
REWARD_FILE="/logs/verifier/reward.txt"
mkdir -p /logs/verifier
echo "0" > "$REWARD_FILE"
export TESTS_DIR="$(cd "$(dirname "$0")" && pwd)"
export OMS_RUN="${OMS_RUN:-/tmp/oms-verify}"
export RUN_AS="${RUN_AS-nobody}"
rm -rf "$OMS_RUN"; mkdir -p "$OMS_RUN"
trap 'rm -rf "${WORK:-}" "${BUILD:-}"' EXIT

BUILD="$(mktemp -d)"
cp -r "${APP_DIR:-/app}/." "$BUILD/"
rm -rf "$BUILD"/*/target
( cd "$BUILD" && mvn -o -q -B package -DskipTests ) > "$OMS_RUN/build.log" 2>&1 || { echo "build failed"; tail -30 "$OMS_RUN/build.log"; cat "$REWARD_FILE"; exit 0; }
JARS="$OMS_RUN/jars"; mkdir -p "$JARS"
cp "$BUILD"/order-service/target/order-service.jar "$BUILD"/item-service/target/item-service.jar "$JARS"/ || { cat "$REWARD_FILE"; exit 0; }
chmod -R a+rX "$JARS"

# Run from a private copy of the verifier (root-owned when run as root); nothing is read from
# /opt/oms or the candidate tree except the app sources built above.
WORK="$(mktemp -d)"; chmod 700 "$WORK"
cp -r "$TESTS_DIR/." "$WORK/"
export TESTS_DIR="$WORK"
cd "$WORK"
OMS_SOCK="$OMS_RUN/mysql.sock" OMS_JARS="$JARS" timeout 1080 python3 -m pytest -q -s -p no:cacheprovider \
    --junitxml="$WORK/junit.xml" test_outputs.py
echo "deadlock reports logged by services: $(grep -c LOCK_CONFLICT "$OMS_RUN"/svclog/*.log 2>/dev/null | tr '\n' ' ')"
python3 - "$WORK/junit.xml" <<'PY'
import sys
import xml.etree.ElementTree as ET
# Gates (any failure -> 0): single-threaded business behaviour, schema/isolation unchanged.
# Weighted concurrent phases (sum 1.0); each passes only with 0 deadlocks, 0 lock wait
# timeouts, real concurrency, REPEATABLE READ sessions and fully consistent data.
weights = {"test_concurrent_edit_and_confirm": 0.20, "test_concurrent_edit_and_cancel": 0.20,
           "test_concurrent_reprice_and_edit": 0.20, "test_concurrent_after_cancel": 0.10,
           "test_concurrent_mixed": 0.30}
gates = ["test_single_thread_functional", "test_schema_and_isolation_unchanged",
         "test_query_endpoints", "test_conflict_status_codes"]
score = 0.0
try:
    root = ET.parse(sys.argv[1]).getroot()
    passed = {tc.get("name") for tc in root.iter("testcase")
              if not any(ch.tag in ("failure", "error", "skipped") for ch in tc)}
    if all(g in passed for g in gates):
        score = sum(wt for name, wt in weights.items() if name in passed)
except Exception:
    score = 0.0
open("/logs/verifier/reward.txt", "w").write(f"{score:.4f}\n")
print("reward", round(score, 4))
PY
cat "$REWARD_FILE"
rm -rf "$WORK" "$BUILD"
exit 0
