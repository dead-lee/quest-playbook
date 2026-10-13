# APPLY16 — 226254 attempt 6 = fix15 (commit e88416c) + R1-run5 05/06 fixes only (NOT pushed / NOT submitted)
Base: repo e88416c (fix15). Changed files ONLY (diff: db/fix16.diff, 153 +/- lines):
- tests/test.sh (7fcb257e04f4): candidate build no longer runs `mvn` as verifier user; calls
  `python3 "$WORK/harness.py" build APP JARS LOG` (env -u TESTS_DIR/OMS_RUN/...). New `fail0()` writes "0"
  to reward.txt itself on every early exit (build fail / jars missing / manifest mismatch); all
  `cat "$REWARD_FILE"` removed; `chmod 755 /logs/verifier`; BUILD var/trap removed.
- tests/harness.py (791b23772196): new build_app(): private copy of /app + private HOME + copy of ~/.m2/repository,
  chown -R $RUN_AS (nobody), `runuser -u nobody -- mvn -o -q -B -Dmaven.repo.local=... package -DskipTests`
  with clean env (PATH/HOME/LANG/JAVA_HOME), timeout 900; copies only the 2 regular-file jars (symlink -> fail);
  `__main__` "build" entry. svc_start unchanged.
- tests/workload.py (4141117eaef1): run_phase uses monotonic deadline, marks requests finishing after 45s as late,
  returns late/max_secs; edit totals checked against exact commit-time value set (_edit_totals: reprices done
  before = included, overlapping = either side); reprice "orders" checked against exact count at commit
  (_reprice_counts; lo==hi when no overlapping edit/cancel on the range).
- tests/test_outputs.py (444272745a66): phase() fails if secs > 45 or any late request.
instruction.md, task.toml, Dockerfile, solution UNCHANGED.
## IDE terminal (repo root /home/workspace/project)
Upload db/fix16.tgz, then:
sha256sum fix16.tgz | cut -c1-12      # expect 16739087388f
tar xzf fix16.tgz -C . --no-same-owner && rm fix16.tgz && chmod +x tests/test.sh
sha256sum tests/test.sh tests/harness.py tests/workload.py tests/test_outputs.py instruction.md | cut -c1-12
#   7fcb257e04f4 791b23772196 4141117eaef1 444272745a66 instruction 5ca7424d1109 (unchanged)
bash -n tests/test.sh && python3 -m py_compile tests/harness.py tests/workload.py tests/test_outputs.py && echo SYNTAX_OK
git status --short    # expect only M tests/harness.py tests/test.sh tests/test_outputs.py tests/workload.py
git commit -qam "fix16: build candidate as nobody in private copy, early exits write 0; enforce 45s phase limit; exact concurrent edit/reprice values" && git push
git diff --stat HEAD~1 HEAD
(If upload is not possible, paste each of the 4 files from db/fix16_pkg/tests/ verbatim into the Web IDE.)
## Form
Only 测试思路: replace with db/form226254/测试思路.fix16.txt (760 chars). Others unchanged.
## Gate: runs/gate_selftest16.out SELFTEST PASS (7/7); runs/gate_fix16.out 130 passed 0 failed RESULT PASS, PKG=fdde007c0a6e.
## Local: ref 1.0 x3 (56/55/54s), DeepSeek 0.0 (27s), original 0.0 (529s); malicious pom (writes reward.txt=1.0 during
build + finalName broken) -> 0 (fix15 same input -> 1.0000, tamper survived).
