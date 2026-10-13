# TalentsAI task notes (OMS MySQL deadlock)

Public notes from Max’s TalentsAI work on task **226254** (order-management system MySQL deadlock under RR isolation).

## What’s here

| Path | Purpose |
|---|---|
| `docs/LESSONS_226254.md` | Hard rules distilled after a full R1 → Oracle → T1 → R2 pass |
| `docs/R1_CHECKLIST.md` | Slim pre-submit checklist |
| `docs/NEXT_ACTION.md` | Final status snapshot (submitted / awaiting platform review) |
| `docs/REGRESSION_ANALYSIS.md` | Earlier regression notes |
| `docs/LOG_EXCERPT.md` | Recent trail from the working log |
| `tools/presubmit_gate.py` | Local gate + self-test used before platform submit |
| `baselines/` | Frozen packages that passed (fix16 = final submit baseline) |

## Task sketch

Two Spring Boot + MyBatis services (order + item) in one container talk over HTTP. Deadlocks come from inconsistent lock order on order/item tables plus gap locks from non-unique index range updates. Isolation level and schema must stay fixed; retries must not hide the bug. The reference fix unifies lock order and updates by primary key row-by-row.

## Hard rules (short)

1. Run gate + self-test before every platform submit.
2. Self-test must not break historical passers (advisory WARN beats false hard-fail).
3. Copy from a frozen baseline; one focused fix per attempt.
4. Do not switch UID inside `test.sh` shell (harness `runuser` is OK).
5. Build as `nobody` via harness; `fail0` must write score `0` on early exits.
6. Enforce the stated time limits and exact concurrent values.
7. Freeze every R1/Oracle passer as a full baseline under `baselines/`.
8. When authorized to submit, submit — don’t self-hold.

## Not included

Browser profiles, platform screenshots, local Docker worktrees, and credentials stay off this repo.

## License

Released under the MIT License — see `LICENSE`.
