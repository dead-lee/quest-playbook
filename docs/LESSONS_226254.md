# LESSONS 226254 (OMS MySQL deadlock) — durable only
Passed: fix16 commit `2f52fd99a9af` · R1 93.66 · Oracle 1.000 · T1 0/0 · R2 80.78 · submitted 质检/待领取
Baselines for selftest: `baselines/226254-run6-fix16/` · `baselines/225736-run8-fix8r/`

## 必须
1. 保存并检测前：`presubmit_gate.py <pkg>` PASS + 输出进 LOG；产出修复的同一看门轮次绝不提交。
2. `presubmit_gate.py --selftest` 必须 PASS；新规则若让历史通过基线 FAIL → 只能 WARN，不得硬 FAIL。
3. 从冻结基线复制再改；一次只改一条失分点；提交前与基线完整 diff 写 LOG。
4. test.sh / solution 的 shell **禁止** runuser/setpriv/su/sudo 等切 UID（硬门禁 03）。harness.py 里列表参数 `runuser -u nobody -- mvn …` 可过（fix8/fix16）。
5. 候选构建：harness 以 nobody 在独占副本构建（私有 HOME/m2）；test.sh 不直接 `mvn`；提前退出 `fail0()` 显式写 0；禁止 `cat "$REWARD_FILE"`。
6. 题面写的时限/数值必须测：45s → secs>45 或 late 请求判失败；并发 edit/reprice 按时间线精确值集合，无重叠即唯一值。
7. 过 R1/Oracle 的版本整包冻进 `baselines/<task>-<run>/`；状态页先 Ctrl+Shift+R。
8. 已授权自主推进时过门禁即交，不自设「等确认」。

## 不要
- 在失败版上叠补；把单次失败泛化成「任何地方禁切 UID」。
- 一次改 3–6 个文件；忽略 R1 同码可差 ~21 分（先判评审方差）。
- 构建前 `export TESTS_DIR`；test.sh 后台 `&`；环境镜像里塞与 tests 同字节验证文件。
- 把 G16/G17 升硬失败（会弄坏 fix8r 自测；见下）。

## 基线门禁
- 硬门禁：结构 / shell 切 UID(G3) / 超时 / 本地分(G10) 等 → FAIL 禁交。
- G5*、G11–G17（含 G16a/b 构建隔离、G17a/b 时限与精确值）= **advisory WARN**。
- **不升 G16/G17**：fix8r（R1 86.67）无 fail0/nobody-build/45s-exact，升硬失败会破 `--selftest`。新包仍应对齐 fix16；WARN 未清要心里有数。
- Selftest 锚点：fix8r PASS · fix16 PASS · run10/fix11 必须被 G3c 抓到。
