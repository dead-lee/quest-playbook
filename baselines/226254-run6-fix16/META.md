# Baseline: 226254-run6-fix16

Frozen: 2026-10-13 12:18 CST (Asia/Shanghai)
Rule: TalentsAI FULL backup on any R1/Oracle pass (2026-10-13)

## Platform
- Task: 226254
- Attempt: 6/10 (fix16)
- Commit: 2f52fd99a9afcb5db630d6bacb55ffbc649262bb
- R1 score: 93.66/100 PASS (≥80)
- R1 txn: 5926c72c… 12:04:55→12:10:35 CST (340.6s)
- Oracle: still running at freeze time (txn 1cb874e6 since 12:10:35); T1/R2 pending
- Screenshots (no r1_run6 text report yet): screenshots/1213_eval.webp, screenshots/1213_exec.webp
  (also under /workspace/talents/status/)

## Package file sha256 (first 12) — verified match
- tests/test.sh          7fcb257e04f4
- tests/harness.py       791b23772196
- tests/workload.py      4141117eaef1
- tests/test_outputs.py  444272745a66
- instruction.md         5ca7424d1109 (unchanged from fix15)

## Artifacts
- fix16_pkg/   complete task package (identical to /workspace/talents/db/fix16_pkg)
- fix16.tgz    sha256 16739087388f
- fix16.diff   sha256 072e9e5c8f8d
- APPLY16.md   apply notes
- 测试思路.fix16.txt  form path db/form226254/测试思路.fix16.txt (= db/测试思路.fix16.txt); sha256 d43d8f8f7404; ~760 chars

## Lineage
- Base: fix15 commit e88416c (run5 R1 65.67 FAIL)
- Changed vs fix15: only the 4 test files above (instruction/task.toml/Dockerfile/solution unchanged)
- Local gate before push: selftest 7/7 PASS; gate 130/0 PASS PKG=fdde007c0a6e; ref 1.0×3, ds 0, orig 0

## Use
Frozen regression-gate baseline for any later attempt that must not regress R1 93.66 / these hashes.

## Oracle (added 12:48 CST)
- PASS: NOP 0.000 ≤ 0.100; Oracle 1.000 = 1.000
- txn 1cb874e6 12:10:35→12:26:37 CST (962.2s)
- T1 started 12:26:37, still running at note time

## T1 + R2 (added 14:34 CST)
- T1 PASS: model1 0.000, model2 0.000 (≤0.700); txn d9c11836 12:26:37→14:13:21 (6403.9s)
- R2 PASS 80.78/100 (≥80); txn b7abc836 14:13:21→14:22:36 (554.7s)
- Progress 4/4; banner: 四步检测已全部通过，可以提交题目
- Watchdog deleted after full pass; final 提交 pending parent

## Final submit (14:37 CST)
- Submitted yes; status 质检/待领取; 流转中 badge 质检中
