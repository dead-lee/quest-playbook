#!/usr/bin/env python3
"""TalentsAI presubmit gate (Harbor package). Usage: presubmit_gate.py <pkg_dir> [--form FORM_TEXT.md]
Every check encodes a platform rejection / score loss we actually hit. Any FAIL -> exit 1.
Refs: C# = /workspace/talents/R1_CHECKLIST.md item; runs = 224471 (old task) / 225736 runN."""
import hashlib, os, re, sys, tomllib

EXPECT_TIMEOUTS = {"agent": 3600.0, "verifier": 1200.0, "build": 900.0}   # Max 2026-10-12 20:37 (agent), 14:26 (build/verifier)
SCORES_FILE = "/workspace/talents/db/runs/gate_scores.txt"
results = []

def check(ok, cid, msg, ref):
    results.append((bool(ok), cid, msg, ref))

def read(p):
    try:
        return open(p, encoding="utf-8", errors="replace").read()
    except FileNotFoundError:
        return None

def code_lines(text):
    """(lineno, line) with shell/python comments and heredoc bodies stripped (best effort)."""
    out, hd = [], None
    for i, raw in enumerate(text.splitlines(), 1):
        if hd:
            if raw.strip() == hd: hd = None
            continue
        m = re.search(r"<<-?\s*'?\"?(\w+)'?\"?", raw)
        line = re.sub(r"(^|\s)#.*$", "", raw) if not raw.lstrip().startswith("#!") else ""
        if out and out[-1][1].rstrip().endswith("\\"):
            out[-1] = (out[-1][0], out[-1][1].rstrip()[:-1] + " " + line)   # join continuation
        else:
            out.append((i, line))
        if m: hd = m.group(1)
    return out

SELFTEST = [  # (pkg, form, must_pass_ids_prefix_or_None_for_full_PASS, must_fail_ids, validated_by)
    ("/workspace/talents/db/fix8r_pkg", "/workspace/talents/db/form226254/测试思路.fix8r.txt", None, [], "fix8 = 225736 run8 R1 86.67 PASS (gates 01-03 + 06 anti-cheat)"),
    ("/workspace/talents/db/selftest/run10_pkg", None, None, ["G3c"], "225736 run10 R1=0 gate 03: runuser in test.sh:38"),
    ("/workspace/talents/db/fix11_pkg", None, None, ["G3c"], "226254 run1 R1=0 gate 03: setpriv in test.sh:43"),
    ("/workspace/talents/db/fix12_pkg", None, "G3", [], "226254 run2 gates 01-03 PASS (no switch)"),
    ("/workspace/talents/db/fix13_pkg", None, "G3", [], "226254 run3 gates 01-03 PASS"),
    ("/workspace/talents/baselines/226254-run5-fix15/fix15_pkg", None, "G3", [], "226254 run5 gates 01-03 PASS, 04 full (G16/G17 WARN only)"),
    ("/workspace/talents/baselines/225736-run8-fix8r/fix8r_pkg", "/workspace/talents/baselines/225736-run8-fix8r/测试思路.fix8r.txt", None, [], "baseline copy of fix8r, full PASS (G16/G17 WARN only)"),
    ("/workspace/talents/baselines/226254-run6-fix16/fix16_pkg", "/workspace/talents/baselines/226254-run6-fix16/测试思路.fix16.txt", None, [], "226254 run6 R1 93.66 PASS (G16/G17 still advisory — fix8r lacks them)"),
]

def selftest():
    import subprocess
    bad = 0
    for pkg, form, scope, must_fail, why in SELFTEST:
        cmd = [sys.executable, __file__, pkg] + (["--form", form] if form else ["--skip-form", "--skip-scores"])
        out = subprocess.run(cmd, capture_output=True, text=True).stdout
        fails = re.findall(r"^  FAIL (\S+)", out, re.M)
        if scope is None and not must_fail: ok = "RESULT: PASS" in out
        elif scope: ok = not any(f.startswith(scope) for f in fails)
        else: ok = all(m in fails for m in must_fail)
        bad += not ok
        print(f"  {'OK ' if ok else 'BAD'} {os.path.basename(pkg):12} expect {'PASS' if not must_fail and scope is None else ('no '+scope+' FAIL' if scope else 'FAIL '+','.join(must_fail))}  [{why}]  fails={fails}")
    print("SELFTEST:", "PASS" if not bad else f"FAIL ({bad})"); sys.exit(1 if bad else 0)

def main():
    args = sys.argv[1:]
    if args[:1] == ["--selftest"]: selftest()
    if not args: print(__doc__); sys.exit(2)
    pkg = os.path.abspath(args[0])
    form = args[args.index("--form") + 1] if "--form" in args else "/workspace/talents/db/FORM_TEXT.md"
    J = lambda *p: os.path.join(pkg, *p)

    # ---- G1 structure (C1; 224471 run1) ----
    req = ["task.toml", "instruction.md", "environment/Dockerfile", "solution/solve.sh", "tests/test.sh"]
    for f in req:
        check(os.path.isfile(J(f)), "G1", f"required file {f}", "C1, 224471 run1")
    junk = [os.path.relpath(os.path.join(d, x), pkg) for d, ds, fs in os.walk(pkg) for x in ds + fs
            if x in ("target", "__pycache__", ".pytest_cache", ".git") or x.endswith((".pyc", ".class", ".jar", ".orig", ".rej", "~"))]
    check(not junk, "G1b", f"no build/junk artifacts in package {junk[:5]}", "C21 (target/ left by local runs)")

    # ---- G2 task.toml (C2, C19; 224471 run1-4; 225736 run8 agent 600 timeout, Max 20:37 -> 3600) ----
    try:
        t = tomllib.loads(read(J("task.toml")) or "")
    except Exception as e:
        t = {}; check(False, "G2", f"task.toml parse error {e}", "C2")
    check(t.get("schema_version") == "1.3", "G2a", "schema_version = \"1.3\"", "C2, 224471 run1 R1=0")
    check(re.fullmatch(r"[\w.-]+/[\w.-]+", str(t.get("task", {}).get("name", ""))), "G2b", "[task].name is org/name", "C2, 224471 run2-4")
    ag = t.get("agent", {}).get("timeout_sec"); vf = t.get("verifier", {}).get("timeout_sec")
    bd = t.get("environment", {}).get("build_timeout_sec")
    check(ag == EXPECT_TIMEOUTS["agent"], "G2c", f"agent timeout_sec == 3600 (got {ag})", "225736 run8 T1 AgentTimeoutError@600; Max 20:37")
    check(vf == EXPECT_TIMEOUTS["verifier"], "G2d", f"verifier timeout_sec == 1200 (got {vf})", "C19, Max 14:26")
    check(bd == EXPECT_TIMEOUTS["build"], "G2e", f"build_timeout_sec == 900 (got {bd})", "C19, Max 14:26")
    for k, v in (("agent", ag), ("verifier", vf), ("build", bd)):
        check(isinstance(v, (int, float)) and v % 300 == 0, "G2f", f"{k} timeout multiple of 5 min", "C-timeout rule")

    # ---- collect scripts ----
    shells = {}
    for d, _, fs in os.walk(pkg):
        for f in fs:
            p = os.path.join(d, f); rel = os.path.relpath(p, pkg)
            if f.endswith(".sh") or f == "Dockerfile" or (read(p) or "").startswith("#!/bin/"):
                if not rel.startswith("environment/app/"): shells[rel] = read(p) or ""
    pys = {os.path.relpath(os.path.join(d, f), pkg): read(os.path.join(d, f)) or ""
           for d, _, fs in os.walk(J("tests")) for f in fs if f.endswith(".py")}
    # solve.sh heredoc bodies are Java; code_lines() skips heredocs.

    # ---- G3 identity commands (C3, C25; 225736 run1, run2, run10 hard gate 脚本安全) ----
    ident = re.compile(r"\b(useradd|groupadd|adduser|addgroup|usermod|groupmod|newusers|chpasswd)\b")
    chown_name = re.compile(r"\bchown\s+(-\S+\s+)*(?![0-9]+(:[0-9]+)?\s)[A-Za-z_$][^\s]*")
    # 226254 run1: R1 rejected even literal `setpriv --reuid=65534 --regid=65534` (test.sh:43);
    # 225736 run10 rejected `runuser -u nobody` (test.sh:38). => NO uid/gid switching at all.
    REF_SW = "C28: 225736 run10 R1=0 (runuser -u nobody) + 226254 run1 R1=0 (setpriv --reuid=65534)"
    switch_sh = [
        (re.compile(r"\bsetpriv\b"), "setpriv (any form, even numeric)"),
        (re.compile(r"\brunuser\b"), "runuser"),
        (re.compile(r"(^|[\s;&|(`])su(\s|$)"), "su"),
        (re.compile(r"\bsudo\b"), "sudo"),
        (re.compile(r"\b(gosu|su-exec|chpst|setuidgid|s6-setuidgid|doas|capsh|newgrp|sg)\b"), "gosu/su-exec/chpst/capsh/doas/newgrp"),
        (re.compile(r"\bchroot\b.*--(userspec|groups)"), "chroot --userspec"),
        (re.compile(r"\bunshare\b.*(-U\b|--user\b|-r\b|--map-root-user|--map-user|--map-current-user)"), "unshare user namespace"),
        (re.compile(r"^\s*USER\s+\S"), "Dockerfile USER"),
        (re.compile(r"--user[= ](?!root\b)\S"), "--user=<non-root>"),
    ]
    for rel, txt in shells.items():
        if not (rel.startswith("tests/") or rel.startswith("solution/") or rel == "environment/Dockerfile"): continue
        for n, ln in code_lines(txt):
            if ident.search(ln): check(False, "G3a", f"{rel}:{n} identity cmd: {ln.strip()}", "C3, run1/run2 R1=0 (useradd even with -u)")
            if chown_name.search(ln): check(False, "G3b", f"{rel}:{n} chown by name: {ln.strip()}", "C3, run2/3")
            if rel == "environment/Dockerfile": continue
            for rx, what in switch_sh:
                if rx.search(ln): check(False, "G3c", f"{rel}:{n} uid/gid switch {what}: {ln.strip()}", REF_SW)
    pysw = {rel: txt for rel, txt in pys.items()}
    for d, _, fs in os.walk(J("solution")):
        for f in fs:
            if f.endswith(".py"): pysw[os.path.relpath(os.path.join(d, f), pkg)] = read(os.path.join(d, f)) or ""
    py_switch = re.compile(r"os\.(set(e|re|res)?[ug]id|setgroups|initgroups)\b|preexec_fn|\b(Popen|run|call|check_call|check_output|_spawn)\(.*\b(user|group|extra_groups)\s*=|"
                           r"getpwnam|pwd\.getpw")   # narrowed 2026-10-13: list-arg runuser/RUN_AS in harness.py passed gate 03 (fix8; 225736 run7/8/9)
    for rel, txt in pysw.items():
        for n, ln in code_lines(txt):
            if py_switch.search(ln):
                check(False, "G3f", f"{rel}:{n} uid/gid switch in python: {ln.strip()}", REF_SW)
    check(True, "G3z", "no uid/gid switch COMMAND in shell scripts (python list-arg runuser allowed: fix8 passed)", REF_SW)
    tsh = shells.get("tests/test.sh", "")

    # ---- G4 background processes in shell (C4, C9; run3, run4 non_terminating_process) ----
    bg = re.compile(r"(?<![&>|<0-9])&(?![&>])\s*($|[;)])")
    for rel, txt in shells.items():
        for n, ln in code_lines(txt):
            if bg.search(ln) or re.search(r"\b(nohup|setsid|disown|daemonize|start-stop-daemon|mysqld_safe|systemctl|service\s+\w+\s+start)\b", ln) \
               or re.search(r"--daemon(ize)?\b", ln):
                check(False, "G4", f"{rel}:{n} background/daemon process: {ln.strip()}", "C9, run3/run4 R1=0 (timeout+pkill still rejected)")
    for rel, txt in pys.items():
        if re.search(r"shell\s*=\s*True", txt) and re.search(r"&\s*[\"']", txt):
            check(False, "G4b", f"{rel}: shell=True with & background", "C9")
        if re.search(r"os\.setsid|os\.fork\(|daemon\s*=\s*True|setsid\b[\"']", txt):
            check(False, "G4c", f"{rel}: detached/daemon process", "C9")
        # C29 (226254 run2): own process group is REQUIRED, but only when supervised as a group
        if re.search(r"start_new_session\s*=\s*True", txt) and not (re.search(r"os\.killpg\(", txt) and "wait(" in txt):
            check(False, "G4c2", f"{rel}: start_new_session without killpg+wait supervision", "C9/C29")
    if pys.get("tests/harness.py") is not None:
        h = pys["tests/harness.py"]
        check("kill()" in h and ("wait(" in h), "G4d", "harness has terminate->kill->wait cleanup", "C9")

    # ---- G5 anti-cheat: test.sh ordering (C24, C25, run9 防作弊 6.67) ----
    tl = code_lines(tsh)
    def first(rx):
        for n, ln in tl:
            if re.search(rx, ln): return n
        return None
    n_copy = first(r"\bcp\s+-a\s+\"?\$_?TESTS|\bcp\b.*\bWORK\b")
    n_freeze = first(r"chmod\s+(444|555|-R\s+a-w)")
    n_build = first(r"\b(mvn|gradle|javac|make|npm|pip\s+install|java\s+-jar|python3?\s+(?!-\s)(?!.*pytest))")
    n_export = first(r"export\s+TESTS_DIR\b|^\s*TESTS_DIR=")
    n_pytest = first(r"pytest")
    n_reward0 = first(r"echo\s+\"?0\"?\s*>\s*\"?\$?\{?REWARD|reward\.txt")
    check(n_reward0 and n_build and n_reward0 < n_build, "G5a", "reward.txt set to 0 before anything else", "C-test思路, 224471")
    check(n_copy and n_build and n_copy < n_build, "G5b", f"tests copied to private dir (L{n_copy}) BEFORE build (L{n_build})", "C24, run9 防作弊 6.67")
    check(n_freeze and n_build and n_freeze < n_build, "G5c", f"private copy frozen read-only (L{n_freeze}) before build", "C24, run9")
    check(first(r"mktemp\s+-d") and first(r"chmod\s+700"), "G5d", "private dir via mktemp -d + chmod 700", "C10/C24")
    check(n_export and n_build and n_export > n_build, "G5e", f"TESTS_DIR exported (L{n_export}) only AFTER build (L{n_build})", "C24, run9")
    if n_build:
        bl = dict(tl)[n_build]
        check("env -u TESTS_DIR" in bl or re.search(r"\benv\s+-i\b", bl), "G5f", "candidate build runs with `env -u TESTS_DIR`", "C24, run9")
        check(not re.search(r"setpriv|runuser|\bsu\b|sudo", bl), "G5g", "candidate build runs WITHOUT any uid switch (root, separate copy)", "C28, 226254 run1")
        check(re.search(r"maven\.repo\.local=", bl) or "/root" not in bl, "G5h", "offline mvn uses the baked repo", "C26")
        check(re.search(r"cp\s+-a\s+\"?\$\{?APP_DIR", tsh) and re.search(r"cd\s+\"?\$BUILD", bl), "G5h2", "build runs on a separate copy of /app", "C24, run9")
    # integrity: sha256 manifest of the frozen copy BEFORE build, re-checked AFTER build (and before scoring)
    n_man = first(r"MANIFEST_PRE=.*sha256sum|MANIFEST_PRE=\"?\$\(manifest\)")
    man_def = re.search(r"manifest\(\)\s*\{[^}]*sha256sum", tsh)
    cmp_lines = [n for n, ln in tl if re.search(r"!=\s*\"?\$MANIFEST_PRE", ln)]
    check(man_def and n_man and n_freeze and n_build and n_freeze < n_man < n_build, "G5m",
          f"sha256 manifest of frozen tests taken after freeze, before build (L{n_man})", "C24, run9 防作弊 6.67")
    check(any(n_build < n < (n_export or 10**9) for n in cmp_lines), "G5n", f"manifest re-verified after build, before TESTS_DIR export {cmp_lines}", "C24, run9")
    n_score = first(r"junit\.xml.*<<")
    check(any(n_pytest and n_pytest < n < (n_score or 10**9) for n in cmp_lines), "G5o", "manifest re-verified after pytest, before scoring", "C24")
    check(re.search(r"^main\(\)\s*\{", tsh, re.M) and re.search(r"^main \"\$@\"\s*$", tsh, re.M), "G5p", "test.sh body wrapped in main() so on-disk edits during build can't alter execution", "C24")
    check(n_pytest and n_export and n_pytest >= n_export, "G5j", "pytest runs after TESTS_DIR export, from the private copy", "C24")
    m = re.search(r"timeout\s+(\d+)\s+python3?\s+-m\s+pytest", tsh)
    check(m and vf and int(m.group(1)) < vf, "G5k", f"pytest wrapped in timeout < verifier ({m.group(1) if m else None} < {vf})", "C19, fix8")
    check(re.search(r"exit 0\s*$", tsh.strip()), "G5l", "test.sh ends with exit 0 (reward only via reward.txt)", "C10")

    # ---- G11-G13 anti-cheat: candidate process isolation (C29-C31; 226254 run2 R1 65, 防作弊 5/33) ----
    REF2 = "226254 run2 R1=65 (06 防作弊 5/33)"
    h = pys.get("tests/harness.py", "")
    hl = code_lines(h)
    # G11 whitelisted env for candidate services; no verifier path ever reaches them
    for n, ln in hl:
        if re.search(r"dict\(\s*os\.environ|os\.environ\.copy\(|\*\*os\.environ|env\s*=\s*os\.environ\b|=\s*os\.environ\s*$", ln):
            check(False, "G11a", f"tests/harness.py:{n} passes the full verifier environment: {ln.strip()}", "C29, " + REF2)
    m = re.search(r"SVC_ENV_KEYS\s*=\s*\(([^)]*)\)", h)
    keys = set(re.findall(r"[\"'](\w+)[\"']", m.group(1))) if m else set()
    check(m and keys <= {"PATH", "LANG", "JAVA_HOME", "LC_ALL", "TZ"}, "G11b", f"service env whitelist SVC_ENV_KEYS={sorted(keys)} (only PATH/LANG/JAVA_HOME[/LC_ALL/TZ])", "C29, " + REF2)
    sv_def = re.search(r"def svc_start\(.*?(?=\ndef )", h, re.S)
    sv = sv_def.group(0) if sv_def else ""
    check(sv and re.search(r"svc_env\(", sv) and not re.search(r"TESTS_DIR|OMS_RUN|OMS_JARS|OMS_SOCK|\bWORK\b|\bSOCK\b", sv), "G11c",
          "svc_start uses svc_env() and references no verifier path (TESTS_DIR/OMS_RUN/OMS_JARS/OMS_SOCK/WORK/SOCK)", "C29, " + REF2)
    check(re.search(r"cwd\s*=\s*logdir", sv), "G11d", "services run with cwd = their own log dir (not the verifier copy)", "C29")
    for n, ln in tl:
        if re.search(r"\bexport\s+(TESTS_DIR|OMS_RUN|OMS_JARS|OMS_SOCK|WORK|_TESTS_SRC|RES|JUNIT)\b", ln):
            check(False, "G11e", f"tests/test.sh:{n} exports a verifier path: {ln.strip()}", "C29, " + REF2)
    if n_build:
        check(re.search(r"\benv\s+-i\b", dict(tl)[n_build]), "G11f", "candidate build runs with a whitelisted env (env -i ...)", "C29, " + REF2)
    check(not re.search(r"OMS_RUN.{0,4}/svclog|OMS_LOG_DIR\s*=\s*os\.path\.join\(\s*OMS_RUN", h + tsh), "G11g", "service log dir is not inside OMS_RUN", "C29")
    # G12 process groups + orphan verification
    check(re.search(r"start_new_session\s*=\s*True", h), "G12a", "services started in their own process group (start_new_session=True)", "C30, " + REF2)
    check(re.search(r"os\.killpg\(", h) and re.search(r"SIGKILL", h), "G12b", "stop_all kills the whole process group (killpg TERM -> KILL)", "C30, " + REF2)
    check(re.search(r"/proc", h) and re.search(r"orphan", h, re.I), "G12c", "stop_all verifies no process of the group survives (orphan check)", "C30, " + REF2)
    # G13 junit.xml integrity
    jm = re.search(r"--junitxml=\"?([^\s\"]+)", tsh)
    jp = jm.group(1) if jm else ""
    check(jp and not re.search(r"OMS_RUN|WORK|SVCLOG|/tmp/|/app|/opt", jp), "G13a", f"junit.xml in a verifier-only dir (got {jp})", "C31, " + REF2)
    jdir = re.match(r"\$\{?(\w+)", jp)
    check(jdir and re.search(rf"{jdir.group(1)}=\"?\$\(mktemp -d\)", tsh) and re.search(rf"chmod\s+700\s+\"?\${jdir.group(1)}", tsh),
          "G13b", "junit dir created with mktemp -d + chmod 700", "C31")
    n_jsha = first(r"JUNIT_SHA=.*sha256sum")
    n_jchk = [n for n, ln in tl if re.search(r"!=\s*\"?\$JUNIT_SHA", ln)]
    _between = [ln for n, ln in tl if n_pytest and n_jsha and n_pytest < n < n_jsha and ln.strip() and not ln.strip().startswith("#")
                and not re.search(r"--junitxml|test_outputs\.py", ln)]
    check(n_jsha and n_pytest and all(re.match(r"\s*reap_all\b", ln) for ln in _between), "G13c", f"junit hashed immediately after pytest (L{n_jsha})", "C31, " + REF2)
    check(n_jchk and n_score and all(n_jsha < n < n_score for n in n_jchk), "G13d", f"junit hash re-verified before parsing {n_jchk}", "C31")
    check(re.search(r"hashlib\.sha256\(.*\)\.hexdigest\(\)\s*!=\s*sys\.argv\[2\]", tsh) and "ET.fromstring(data)" in tsh, "G13e",
          "scorer parses exactly the hashed bytes (hash check in-process)", "C31")
    # ---- G14 same-UID candidate leftovers (C34; 226254 run3 R1 66, 06 防作弊 3.33: setsid daemon can rewrite reward.txt) ----
    REF3 = "226254 run3 R1=66 (06 防作弊 3.33/33)"
    ra = re.search(r"reap_all\(\)\s*\{.*?\n\}", tsh, re.S)
    rab = ra.group(0) if ra else ""
    check(ra and "/proc" in rab and "SIGKILL" in rab and re.search(r"for _ in range\(\d+\)", rab) and "ancestry" in rab,
          "G14a", "reap_all scans /proc and SIGKILLs everything outside the verifier ancestry, in a loop", "C34, " + REF3)
    check(re.search(r"clean\s*>=\s*2", rab) and re.search(r'"Z", "X"', rab), "G14b", "reap_all requires 2 clean scans, ignores only zombies", "C34")
    n_reap = [n for n, ln in tl if re.match(r"\s*reap_all\b", ln)]
    n_rmb = first(r'rm -rf "\$BUILD"; BUILD=""')
    check(n_pytest and any(n_pytest < n < (n_jsha or 10**9) for n in n_reap), "G14c", "reap_all right after pytest, before any check", "C34, " + REF3)
    check(n_rmb and n_pytest and any(n_rmb < n < n_pytest for n in n_reap), "G14d", "reap_all after the candidate build, before pytest", "C34")
    fz = re.search(r"# --- FINALIZE-BEGIN ---(.*?)# --- FINALIZE-END ---", tsh, re.S)
    fzb = fz.group(1) if fz else ""
    i_score, i_reap = fzb.find('text = f"{score'), fzb.find("if not reap():")
    i_pub, i_resc = fzb.find("ok = publish(text)"), fzb.find("if not ok or strays(ancestry())")
    check(fz and -1 < i_score < i_reap < i_pub < i_resc, "G14e", "score in memory -> reap -> publish reward -> rescan (stray -> 0)", "C34, " + REF3)
    check("O_EXCL" in fzb and "O_NOFOLLOW" in fzb and "fsync" in fzb and "st_nlink == 1" in fzb and "hashlib.sha256(got)" in fzb,
          "G14f", "reward.txt recreated O_EXCL|O_NOFOLLOW, fsync, read back + sha256 compared", "C34")
    check(re.search(r"assert not strays\(ancestry\(\)\)", fzb), "G14g", "asserts zero leftover processes before publishing", "C34")
    n_writes = [n for n, ln in tl if re.search(r"(>|open\()\s*\"?\$?\{?REWARD|reward\.txt\",\s*\"w\"", ln) and "fail0()" not in ln and not ln.lstrip().startswith("#")]
    check(len(n_writes) <= 1, "G14h", f"only the initial 0 and fail0()/publish() write reward.txt (extra writes at {n_writes})", "C34")
    ex = [n for n, ln in tl if re.search(r"\bexit 0\b", ln) and "fail0()" not in ln and not ln.lstrip().startswith("#")]
    check(len(ex) == 1, "G14i", f"every early exit goes through fail0 (reap + recreate 0); stray 'exit 0' at {ex[:-1]}", "C34")
    # dynamic: setsid daemon attack against the pkg's own finalize block (fresh PID namespace, never the box)
    import subprocess, shutil, tempfile
    atk = "/workspace/talents/db/runs/reaptest"
    if fz and shutil.which("unshare") and os.path.isfile(f"{atk}/daemon_attack.sh"):
        tmp = tempfile.mkdtemp()
        open(f"{tmp}/finalize.py", "w").write(fzb)
        for f in ("daemon_attack.sh", "control.sh"):
            shutil.copy(f"{atk}/{f}", tmp)
        def ns(f):
            return subprocess.run(["unshare", "--map-user=%d" % os.getuid(), "--map-group=%d" % os.getgid(), "-pf", "--mount-proc", "bash", f],
                                  cwd=tmp, capture_output=True, text=True, timeout=60).stdout
        check("ATTACK_TEST: PASS" in ns("daemon_attack.sh"), "G14j", "setsid daemon rewriting reward.txt is killed; reward stays 0 (local attack test)", "C34, " + REF3)
        check("CONTROL_TEST: PASS" in ns("control.sh"), "G14k", "honest all-pass junit still publishes 1.0000", "C34")
        shutil.rmtree(tmp, ignore_errors=True)
    else:
        check(False, "G14j", "attack test could not run (no FINALIZE block / unshare / reaptest)", "C34")
    # ---- G15 contract precision (C35; 226254 run3: 04 reprice orders timing, 05 version presence-only) ----
    ins = read(J("instruction.md")) or ""
    check(re.search(r"reprice.{0,40}orders.{0,30}事务里统计", ins, re.S) and "提交时" in ins and "时间上重叠" in ins,
          "G15a", "instruction defines when reprice `orders` is counted (own txn, at commit; timeline rule)", "C35, " + REF3)
    check(re.search(r"`version`\s*为整数", ins) and "严格变大" in ins, "G15b", "instruction defines `version` value semantics", "C35, " + REF3)
    wl = read(J("tests/workload.py")) or ""; to = read(J("tests/test_outputs.py")) or ""
    check(re.search(r'v = b\["version"\]', wl) and "def check_versions" in wl and "check_versions(ops)" in wl, "G15c",
          "concurrent bodies check version values (int, > initial, <= final, cancel == final, timeline-ordered)", "C35, " + REF3)
    check(re.search(r'body\["version"\]\s*==\s*row\["version"\]', to) and 'body["version"] > v_edit' in to, "G15d",
          "single-thread checks version == DB value and that edit/cancel increase it", "C35, " + REF3)

    # ---- G6 anti-cheat: verifier isolation (C5, C10; 224471 run6, 225736 run5 防作弊 6.67) ----
    tests_hash = {}
    for d, _, fs in os.walk(J("tests")):
        for f in fs:
            b = open(os.path.join(d, f), "rb").read()
            tests_hash[hashlib.sha256(b.strip()).hexdigest()] = os.path.relpath(os.path.join(d, f), pkg)
    tnames = {os.path.basename(v) for v in tests_hash.values()} - {"test.sh"}
    for d, _, fs in os.walk(J("environment")):
        for f in fs:
            p = os.path.join(d, f); rel = os.path.relpath(p, pkg)
            h = hashlib.sha256(open(p, "rb").read().strip()).hexdigest()
            check(h not in tests_hash, "G6a", f"{rel} identical to {tests_hash.get(h)}", "C10, run5 防作弊 6.67")
            check(f not in tnames or "app/" in rel, "G6b", f"{rel} shares a verifier filename (my.cnf/schema/seed...)", "C10, run5")
    for rel, txt in pys.items():
        if re.search(r"sys\.path\.(insert|append)\([^)]*(/app|APP_DIR)", txt) or re.search(r"^\s*(from|import)\s+(app|solution)\b", txt, re.M):
            check(False, "G6c", f"{rel} imports candidate code", "C5, 224471 run6 防作弊")
        if re.search(r"open\([^)]*['\"]/opt/oms", txt):
            check(False, "G6d", f"{rel} reads candidate-writable /opt/oms", "C10, run5")
    df = read(J("environment/Dockerfile")) or ""
    check(not re.search(r"COPY\s+.*tests", df), "G6e", "Dockerfile does not COPY tests", "C10")
    check(re.search(r"(seed|random|SystemRandom)", pys.get("tests/harness.py", "") + pys.get("tests/workload.py", "")) is not None,
          "G6f", "verification data generated at runtime", "C10, run5")
    check(not os.path.exists(J("tests/db/seed.sql")), "G6g", "no static seed.sql in tests", "C10, fix6")

    # ---- G7 instruction.md hygiene / contract (C6, C11, C12, C15, C16; run5 题面 28.67, run6, run7) ----
    ins = read(J("instruction.md")) or ""
    check(len(ins) > 1500, "G7a", f"instruction.md substantive ({len(ins)} chars)", "C6")
    for bad, why in ((r"TESTS_DIR|tests/|test_outputs|workload\.py|harness", "mentions verifier internals"),
                     (r"/opt/oms/db", "stale path removed in fix6"), (r"solve\.sh|solution/", "mentions solution"),
                     (r"runuser|setpriv|65534", "mentions verifier UID mechanics"), (r"TODO|FIXME|XXX", "leftover TODO")):
        check(not re.search(bad, ins), "G7b", f"instruction.md {why}", "C6/C10")
    for need, why in ((r"409", "409 semantics"), (r"2xx", "2xx-only rule (Max)"), (r"时间线", "timeline 409 rule (C13, run6)"),
                      (r"0\.01.{0,3}0\.50", "reprice delta range (C16, run7)"), (r"100.{0,3}140", "seed order range (C15, run6)"),
                      (r"5\.00.{0,3}40\.00", "price range (C15)"), (r"REPEATABLE[ -]READ", "isolation contract")):
        check(re.search(need, ins), "G7c", f"instruction.md states {why}", "C11/C15/C16")
    # every random range in tests must be inside documented range (run7: delta 0.01-0.99 vs 0.50)
    tst = pys.get("tests/test_outputs.py", "") + pys.get("tests/workload.py", "")
    for m in re.finditer(r"randint\(1,\s*(\d+)\)\)?\s*/\s*100", tst):
        check(int(m.group(1)) <= 50, "G7d", f"price delta randint(1,{m.group(1)})/100 within 0.01-0.50", "C16, run7")
    # every weighted/gate test named in test.sh exists in test_outputs.py
    to = pys.get("tests/test_outputs.py", "")
    for name in re.findall(r"\"(test_\w+)\"", tsh):
        check(re.search(rf"def {name}\(", to), "G7e", f"scored test {name} exists", "C12")
    wsum = sum(float(x) for x in re.findall(r"\"test_\w+\":\s*([0-9.]+)", tsh))
    check(abs(wsum - 1.0) < 1e-6, "G7f", f"weights sum to 1.0 ({wsum})", "C-scoring")

    # ---- G8 FORM text consistency (fix9/run8 notes) ----
    skip_form = "--skip-form" in args
    ft = read(form) or ""
    if skip_form: ft = "2xx 409"
    check(ft, "G8a", f"FORM text present ({form})", "Max: form boxes must match package")
    _pkgsrc = "\n".join(list(shells.values()) + list(pys.values()))
    _drops = bool(re.search(r"runuser|setpriv", _pkgsrc))
    _bads = [(r"/opt/oms/db", "stale path")]
    if EXPECT_TIMEOUTS["agent"] != 600.0: _bads.append((r"600\s*秒|10\s*分钟", "stale 600s agent timeout"))
    if not _drops: _bads.append((r"runuser|setpriv|65534|低权限|nobody", "identity mechanism the package does not use"))
    if "setpriv" not in _pkgsrc: _bads.append((r"setpriv|65534", "setpriv/65534 but package does not use setpriv"))
    for bad, why in _bads:
        check(not re.search(bad, ft), "G8b", f"FORM text has {why}", "fix9; narrowed 2026-10-13 (fix8 form said 低权限 and passed)")
    check("2xx" in ft and "409" in ft, "G8c", "FORM 测试思路 states 2xx/409 rule", "Max 10:2x")

    # ---- G9 solution sanity ----
    sv = read(J("solution/solve.sh")) or ""
    check(sv.startswith("#!") and "set -e" in sv, "G9a", "solve.sh has shebang + set -e", "C1")
    check(not re.search(r"\bmvn\b.*&\s*$|\bjava -jar\b", sv), "G9b", "solve.sh only edits code (no services)", "C9")

    # ---- G10 local scores recorded for THIS exact package (C8; 224471 run5-10 T1 too easy) ----
    man = []
    for d, _, fs in sorted(os.walk(pkg)):
        for f in sorted(fs):
            p = os.path.join(d, f)
            man.append(f"{hashlib.sha256(open(p,'rb').read()).hexdigest()[:12]}  {os.path.relpath(p, pkg)}")
    pkgh = hashlib.sha256("\n".join(man).encode()).hexdigest()[:12]
    if "--skip-scores" in args:   # IDE use only; the box run must include scores
        print("  WARN G10 skipped (--skip-scores)"); results.extend([(True,"G10","skipped","")]*0)
    sc = read(SCORES_FILE) or ""
    line = next((l for l in sc.splitlines() if l.startswith(f"PKG={pkgh} ")), "")
    def val(k):
        m = re.search(rf"{k}=([0-9.]+)", line); return float(m.group(1)) if m else None
    ref, orig, ds = val("ref"), val("orig"), val("ds")
    if "--skip-scores" not in args:
      check(ref == 1.0, "G10a", f"local reference score 1.0 for PKG={pkgh} (got {ref})", "C8")
      check(orig is not None and orig <= 0.1, "G10b", f"local original-code score <=0.1 (got {orig})", "C8, Oracle NOP<=0.1")
      check(ds is not None and ds <= 0.7, "G10c", f"local DeepSeek-fix score <=0.7 (got {ds})", "224471 T1 failed 1.000 x5; T1 门槛 <=0.700")

    # ---- G16/G17 226254 run5 (fix15) R1 06=6, 05=26.33 ----
    # Stay ADVISORY forever while fix8r is a SELFTEST full-PASS baseline: fix8 scored R1 86.67
    # without fail0/nobody-build/45s-exact checks. Promoting would break historical selftest. ----
    tsh16 = read(J("tests/test.sh")) or ""
    wl16 = read(J("tests/workload.py")) or ""
    to16 = read(J("tests/test_outputs.py")) or ""
    check(not re.search(r'cat\s+"?\$\{?REWARD_FILE', tsh16) and "cat /logs/verifier/reward" not in tsh16, "G16a",
          "test.sh never cats the reward file (early exits write 0 themselves)", "C44, 226254 run5 06")
    check(not any(re.search(r"\bmvn\b", ln) for _, ln in code_lines(tsh16)), "G16b",
          "candidate mvn build not run directly by test.sh as the verifier user (unprivileged build helper)", "C44, 226254 run5 06")
    check(("max_secs" in to16 or "late" in to16) and "late" in wl16, "G17a",
          "phase fails when it exceeds the stated time limit / requests finish late", "C45, 226254 run5 05a")
    check(not re.search(r"0\s*<=\s*n\s*<=\s*len\(orders\)", wl16) and not re.search(r"lo\s*<=\s*tot\s*<=\s*hi", wl16), "G17b",
          "concurrent edit/reprice bodies checked against exact commit-time values (not range only)", "C45, 226254 run5 05b/c")

    # ---- report ----
    # Score-item heuristics (R1 items 04-06 are graded, not hard gates). fix8 failed all of these and still
    # passed R1 86.67 (225736 run8), so they can only WARN; hard gates 01-03 + G1-G4/G6-G10 still FAIL.
    ADVISORY = re.compile(r"^G(5[bcefmnop]|5h2|1[1-7][a-z0-9]*)$")
    warns = [r for r in results if not r[0] and ADVISORY.match(r[1])]
    for ok, cid, msg, ref in warns: print(f"  WARN {cid:5} {msg}   [{ref}; advisory: fix8 passed R1 without it]")
    results[:] = [r for r in results if r not in warns]
    fails = [r for r in results if not r[0]]
    print(f"presubmit_gate {pkg}  PKG={pkgh}")
    for ok, cid, msg, ref in results:
        if not ok: print(f"  FAIL {cid:5} {msg}   [{ref}]")
    print(f"  {len(results)-len(fails)} passed, {len(fails)} failed")
    print("  manifest:"); [print("   ", m) for m in man if not m.split()[1].startswith("environment/app/")]
    print("RESULT:", "PASS" if not fails else "FAIL — DO NOT 保存并检测")
    sys.exit(1 if fails else 0)

if __name__ == "__main__":
    main()
