# APPLY15 — 226254 attempt 5 = fix8r + test.sh build-order fix + instruction 45s sentence (NOT pushed / NOT submitted)
Base: repo 2c62046 (fix8r). Changed files ONLY: tests/test.sh, instruction.md (diff: db/fix15.diff).
## IDE terminal (repo root /home/workspace/project)
Upload db/fix15.tgz, then:
sha256sum fix15.tgz | cut -c1-12      # expect f2ec05bbef11
tar xzf fix15.tgz -C . --no-same-owner && rm fix15.tgz && chmod +x tests/test.sh
sha256sum tests/test.sh instruction.md tests/harness.py environment/Dockerfile | cut -c1-12
#   bc4dda75f13f instruction 5ca7424d1109  harness f6adf85cf57f  Dockerfile 1ef4bb15e1d9 (unchanged)
bash -n tests/test.sh && echo SYNTAX_OK
git status --short    # expect only M instruction.md, M tests/test.sh
git commit -qam "fix15: copy+hash verifier tests before build, build without TESTS_DIR/OMS_RUN, re-verify before scoring; state 45s phase limit" && git push
git diff --stat HEAD~1 HEAD
## Form
Only 测试思路: replace with db/form226254/测试思路.fix15.txt (664 chars). Others unchanged.
Edit vs fix8r: 「离线构建被测工程，再把测试目录复制到 root 私有的临时目录里运行 pytest；」 ->
「先把测试目录复制到 root 私有的临时目录并记下 sha256 清单，再离线构建被测工程（构建时不暴露测试路径），构建后和打分前各核对一次清单，不一致即 0 分，然后在该目录里运行 pytest；」
## Gate: runs/gate_selftest15.out PASS; runs/gate_fix15.out 125 passed 0 failed RESULT PASS.
## Local: ref 1.0 x3 (46/44/45s), DeepSeek 0.0 (25s), original 0.0 (578s).
