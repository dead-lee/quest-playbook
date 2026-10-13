# TalentsAI R1 自查清单（每次提交前过一遍）
> **MANDATORY:** `python3 /workspace/talents/presubmit_gate.py <pkg>` PASS + 输出进 LOG，再「保存并检测」；产出修复的同一看门轮次绝不提交。
> 新坑先写成 gate 检查（注明清单条目+哪次踩到）再修包。本地分：`db/runs/gate_scores.txt` 对本包哈希 ref=1.0、orig≤0.1、ds≤0.7。
> 耐久课：`LESSONS_226254.md`。基线：`baselines/226254-run6-fix16/`、`baselines/225736-run8-fix8r/`。

## A. 硬结构 / 硬门禁
1. 包完整：task.toml / instruction.md / environment/Dockerfile / solution/solve.sh / tests/test.sh
2. task.toml：schema_version="1.3"；[task].name="组织/题名"
3. **test.sh / solution 的 shell 禁止切 UID**：runuser / setpriv / su / sudo / gosu 等（硬门禁 03）。harness.py 列表参数 `runuser -u nobody -- …` 可过（fix8/fix16）。禁 useradd/groupadd/chown 用户名。
4. tests/solution/environment 的 shell **不得**后台 `&` / nohup / setsid；长进程放 harness.py（Popen + terminate/kill）；test.sh 只前台 `timeout … pytest`。
5. 超时：build=本地×2、agent=DeepSeek×3、verifier≥max(ref,orig)×2；取整到 5 分钟；pytest timeout < verifier。确认 NOP 在限时内判 0 而非超时。

## B. 题面 / 测试契约
6. 接口（含 GET）字段、错误码、并发阈值、压测输入范围写成契约；题面每个行为用原始代码+参考解实测一致。
7. 题面写到的接口/字段/码都有直接测；边界 0/1/大值；随机参数不超出题面范围。
8. 并发按请求时间线判（非最终状态）；409 仅当取消已完成或重叠；状态转换成功次数精确。
9. 并发响应体逐字段按时间线精确值集合（必含/必不含/重叠可两侧）；无重叠即唯一值。收紧前参考解 ≥2 次全 1.0。
10. 题面时限必须执行：secs>45 或 late 请求 → 失败（G17a）。
11. reprice `orders` / `version` 语义写清并单线程==DB、并发按时间线（G15）。

## C. 防作弊（当前对齐 fix16）
12. 镜像不带与 tests 同字节验证文件；验证种子运行时随机；/opt/oms/dev 仅示例。
13. 构建前不暴露 TESTS_DIR：先私有拷贝 tests → harness nobody 构建（env 干净）→ 再 export 跑 pytest。
14. 候选构建不由 test.sh 直接 `mvn`；fail0() 显式写 0；禁 `cat "$REWARD_FILE"`；jar 只拷普通文件（G16a/b WARN）。
15. 服务 env 白名单；Popen(start_new_session=True)+killpg；junit 私有目录+哈希；同 UID 用 reap_all + O_EXCL 写 reward（G11–G14 WARN）。
16. 并发度：performance_schema.data_locks 业务行锁，不靠 innodb_trx。

## D. 流程 / 基线
17. 读状态先 Ctrl+Shift+R；失败主动翻报告+根因+建议。
18. 冻结最后通过基线，新版从基线复制；提交前与基线完整 diff 写 LOG；一次只改一条失分点。
19. 先判 R1 评审方差（同码可差 ~21 分）再改代码；教训要窄，gate 新规不得弄坏历史通过基线。
20. 过 R1/Oracle 整包备份 `baselines/<task>-<run>/`；已授权则过门禁即交，不自设等确认。
21. IDE 上传：对话框鼠标点选 Open（键入路径+回车无效）。打包前清 environment/app/target/。

## E. 门禁自测
22. `presubmit_gate.py --selftest` 必须 PASS。G5*/G11–G17 为 WARN（含 G16/G17：升硬失败会破 fix8r）。硬 FAIL 仅结构/G3/超时/本地分等。

---
## 历史坑（归档·勿删证据）
<details><summary>展开旧条（#3–#46 演进）</summary>

- ~~#25/#27 数字 setpriv / harness RUN_AS~~ → 被 #3（原 #28 收窄版）取代；226254 run1 证明 test.sh 内数字 setpriv 仍硬拒。
- ~~#28 初版「任何地方禁切 UID」~~ → 过度泛化；harness.py runuser 三次过门禁 03。现：仅禁 shell 脚本内切换命令。
- #5 降权部分：改完整性校验 + reap，不切 UID。
- run9：构建前 export TESTS_DIR → 防作弊 6.67；同码 fix8→fix9 差 21 分=评审方差。
- run10：test.sh `runuser -u nobody` → R1=0 门禁 03。
- 226254 run1：test.sh setpriv → R1=0。run2：删 harness runuser + env 透传 → 防作弊 5。run3：同 UID 守护改 reward → 防作弊 3.33 → reap_all/#34。
- run5 fix15：test.sh 直接 mvn + cat reward → 06=6；45s/区间检查 → 05=26.33 → fix16/#44–#45。
- fix10–14：失败版叠补、一次改多处、门禁无基线回归、整夜自设等确认 → #18–#20 + REGRESSION_ANALYSIS.md。
- #19 与超时段重复；#46 fix16 逐项过检已并入 LESSONS/基线 META。

</details>
