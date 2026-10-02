#!/usr/bin/env python3
"""Regression tests: bring-loop hooks must run where only `python3` exists.

Run from the repo root: python3 -m unittest discover -s tests -v

Why: both hook commands once called bare `python`, which recent macOS doesn't
ship, so neither hook ran there. These tests guard the hook commands, every
other bare-`python` invocation in the repo's text files, and the behaviour of
the hooks with `python` absent from PATH.

Every fixture below is hand-written; none is produced by the code under test.
This file deliberately contains bare-`python` strings (the known-bad samples),
so the tree sweep excludes it by exact path.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
PLUGIN = os.path.join(REPO, "plugin")
HOOKS_DIR = os.path.join(PLUGIN, "hooks")
HOOKS_JSON = os.path.join(HOOKS_DIR, "hooks.json")
THIS_FILE = "tests/test_hooks_interpreter.py"

# The one allowed hook-command shape (contract: python3, quoted plugin-root path).
HOOK_CMD_RE = re.compile(r'python3 "\$\{CLAUDE_PLUGIN_ROOT\}/hooks/([A-Za-z0-9._-]+\.py)"')

# A bare-python invocation: the token `python` (not python3, not python.exe, not
# part of a path or word) followed by a quote, `$`, `-`, a path, or a file name.
# Case-sensitive on purpose, so prose like "Python stdlib" never matches.
BARE_INVOCATION_RE = re.compile(
    r"(?<![\w.\-])python(?![\w.])(?:[ \t]+(?:[\"'$\-<]|\S*/\S*|\w+\.\w+)|[ \t]*$)")
BARE_SHEBANG_RE = re.compile(r"^#!.*(?<![\w.\-])python(?![\w.])")
# List-form launch: subprocess.run(['python', CORE]), ["python", "x.py"], ['python']
BARE_LIST_TOKEN_RE = re.compile(r"[\"']python[\"']\s*[,\]]")

SWEEP_SUFFIXES = (".md", ".py", ".json", ".txt", ".sh", ".bash", ".zsh",
                  ".yaml", ".yml", ".toml")
SWEEP_SKIP_DIRS = {".git", "__pycache__", "node_modules"}

ROOT_VAR = '"${CLAUDE_PLUGIN_ROOT}/hooks/%s.py"'


# ---------------------------------------------------------------- pure checkers

def scan_hooks(json_text):
    """Walk hooks -> event -> [group] -> hooks -> [entry].

    Returns (commands, non_command_count) where commands is a list of
    (event, command). Raises ValueError on any shape it does not recognise, so a
    misread nesting can never look like "nothing to check".
    """
    doc = json.loads(json_text)
    hooks = doc.get("hooks") if isinstance(doc, dict) else None
    if not isinstance(hooks, dict):
        raise ValueError("top-level 'hooks' must be an object keyed by event")
    commands, others = [], 0
    for event, groups in hooks.items():
        if not isinstance(groups, list):
            raise ValueError("event %r must hold a list of groups" % event)
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                raise ValueError("a group under %r has no 'hooks' list" % event)
            for entry in group["hooks"]:
                if not isinstance(entry, dict):
                    raise ValueError("a hook entry under %r is not an object" % event)
                if entry.get("type") == "command":
                    commands.append((event, entry.get("command")))
                else:
                    others += 1
    return commands, others


def bad_hook_commands(json_text):
    """Every command that is not exactly the allowed python3 form."""
    commands, _ = scan_hooks(json_text)
    return [c for _, c in commands
            if not isinstance(c, str) or not HOOK_CMD_RE.fullmatch(c)]


def resolve_script(command, plugin_dir):
    """Path of the script a hook command runs, or None if it is not the allowed
    form or resolves outside <plugin>/hooks."""
    m = HOOK_CMD_RE.fullmatch(command) if isinstance(command, str) else None
    if not m:
        return None
    hooks_dir = os.path.realpath(os.path.join(plugin_dir, "hooks"))
    path = os.path.realpath(os.path.join(hooks_dir, m.group(1)))
    return path if os.path.dirname(path) == hooks_dir else None


def verify_hooks_doc(testcase, json_text):
    """The assertions the real hooks.json must satisfy. Fails on a vacuous doc."""
    commands, _ = scan_hooks(json_text)
    testcase.assertEqual(len(commands), 2, "expected exactly 2 command hooks, found %r" % commands)
    testcase.assertEqual(sorted(e for e, _ in commands), ["SessionStart", "Stop"])
    testcase.assertEqual(bad_hook_commands(json_text), [])


def line_is_bare_python(line):
    return bool(BARE_INVOCATION_RE.search(line) or BARE_SHEBANG_RE.match(line)
                or BARE_LIST_TOKEN_RE.search(line))


def find_bare_python(root, exclude=()):
    """Sweep text files under root. Returns (files_scanned, [(relpath, lineno)])."""
    scanned, hits = [], []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SWEEP_SKIP_DIRS)
        for name in sorted(filenames):
            if not name.endswith(SWEEP_SUFFIXES):
                continue
            rel = os.path.relpath(os.path.join(dirpath, name), root).replace(os.sep, "/")
            if rel in exclude:
                continue
            scanned.append(rel)
            with open(os.path.join(dirpath, name), encoding="utf-8", errors="replace") as f:
                for n, line in enumerate(f, 1):
                    if line_is_bare_python(line):
                        hits.append((rel, n))
    return scanned, hits


def _doc(command, event="SessionStart"):
    return json.dumps({"hooks": {event: [{"hooks": [{"type": "command", "command": command}]}]}})


def _env_without_python(plugin_dir):
    return {"PATH": "/usr/bin:/bin", "HOME": os.environ.get("HOME", "/"),
            "CLAUDE_PLUGIN_ROOT": plugin_dir}


def _run(command, cwd, stdin_text="{}"):
    return subprocess.run(["/bin/sh", "-c", command], cwd=cwd, input=stdin_text,
                          capture_output=True, text=True, timeout=10,
                          env=_env_without_python(PLUGIN))


def _system_python3_works():
    try:
        return subprocess.run(["/usr/bin/python3", "-c", "pass"], capture_output=True,
                              timeout=10).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


# ------------------------------------------------------------------ hooks.json

class TestHooksJson(unittest.TestCase):
    def setUp(self):
        with open(HOOKS_JSON, encoding="utf-8") as f:
            self.text = f.read()

    def test_every_hook_command_matches_contract_form(self):
        verify_hooks_doc(self, self.text)

    def test_referenced_scripts_equal_hooks_dir(self):
        commands, _ = scan_hooks(self.text)
        referenced = sorted(HOOK_CMD_RE.fullmatch(c).group(1) for _, c in commands)
        on_disk = sorted(n for n in os.listdir(HOOKS_DIR) if n.endswith(".py"))
        self.assertEqual(referenced, on_disk)

    def test_hook_scripts_exist(self):
        commands, _ = scan_hooks(self.text)
        self.assertTrue(commands)
        for _, command in commands:
            path = resolve_script(command, PLUGIN)
            self.assertIsNotNone(path, command)
            self.assertTrue(os.path.isfile(path), path)

    def test_resolve_script_rejects_escapes(self):
        for cmd in ('python3 "${CLAUDE_PLUGIN_ROOT}/hooks/../scripts/bring_core.py"',
                    'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/bring_core.py"',
                    'python3 "/abs/hooks/bring-injector.py"'):
            self.assertIsNone(resolve_script(cmd, PLUGIN), cmd)

    def test_plugin_json_version_matches_changelog(self):
        with open(os.path.join(PLUGIN, ".claude-plugin", "plugin.json"), encoding="utf-8") as f:
            version = json.load(f)["version"]
        with open(os.path.join(REPO, "CHANGELOG.md"), encoding="utf-8") as f:
            first = next(line for line in f if line.startswith("## "))
        m = re.search(r"\bv(\d+\.\d+\.\d+)\b", first)
        self.assertIsNotNone(m, first)
        self.assertEqual(version, m.group(1),
                         "plugin.json version and the newest CHANGELOG heading must agree "
                         "(the plugin cache is keyed by version)")
        self.assertGreaterEqual(tuple(int(p) for p in version.split(".")), (0, 1, 2))


class TestSkillsAndBrief(unittest.TestCase):
    def test_skill_descriptions_within_budget(self):
        skills_dir = os.path.join(PLUGIN, "skills")
        found = 0
        for name in sorted(os.listdir(skills_dir)):
            with open(os.path.join(skills_dir, name, "SKILL.md"), encoding="utf-8") as f:
                head = f.read().split("\n---", 2)[0]
            descs = [l[len("description:"):].strip() for l in head.split("\n")
                     if l.startswith("description:")]
            self.assertEqual(len(descs), 1, name)
            self.assertLessEqual(len(descs[0]), 250, name)
            self.assertNotIn(": ", descs[0].replace('"', ""), name + ": unquoted colon breaks YAML")
            found += 1
        self.assertGreaterEqual(found, 2)

    def test_brief_log_command_is_runnable_from_any_cwd(self):
        sys_path = os.path.join(PLUGIN, "scripts")
        env = {"PATH": "/usr/bin:/bin", "HOME": os.environ.get("HOME", "/")}
        with tempfile.TemporaryDirectory() as proj:
            os.makedirs(os.path.join(proj, "bring"))
            with open(os.path.join(proj, "bring", "actions.md"), "w", encoding="utf-8") as f:
                f.write("## Send it\nkind: send\nid: x1\n")
            r = subprocess.run(["/usr/bin/python3", os.path.join(sys_path, "bring_core.py"), "brief"],
                               cwd=proj, capture_output=True, text=True, timeout=10, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        m = re.search(r'`python3 "([^"]+bring_core\.py)" log ', r.stdout)
        self.assertIsNotNone(m, r.stdout)
        self.assertTrue(os.path.isabs(m.group(1)))
        self.assertTrue(os.path.isfile(m.group(1)), m.group(1))


class TestCheckerBites(unittest.TestCase):
    """The checker flags every known-bad shape and passes the real ones."""

    GOOD = [ROOT_VAR % "bring-injector", ROOT_VAR % "bring-stop-nudge"]

    def test_checker_flags_bypass_shapes(self):
        p = lambda s: "python " + s  # noqa: E731
        good = 'python3 ' + ROOT_VAR % "a"
        bad = [
            p(ROOT_VAR % "x"),
            "/usr/bin/python " + ROOT_VAR % "x",
            "/usr/bin/env python " + ROOT_VAR % "x",
            "env python " + ROOT_VAR % "x",
            "FOO=1 python " + ROOT_VAR % "x",
            "python2 " + ROOT_VAR % "x",
            "python.exe " + ROOT_VAR % "x",
            "  python " + ROOT_VAR % "x",
            " python3 " + ROOT_VAR % "x",
            good + " && python " + ROOT_VAR % "b",
            "true || python " + ROOT_VAR % "b",
            "cd x; python " + ROOT_VAR % "y",
            good + " | python " + ROOT_VAR % "b",
            "true && " + good,
            good + " --flag",
            "python3 " + ROOT_VAR % "a" + "\npython " + ROOT_VAR % "b",
        ]
        for cmd in bad:
            self.assertEqual(bad_hook_commands(_doc(cmd)), [cmd], "not flagged: %r" % cmd)

    def test_checker_flags_bare_python_in_second_matcher_group(self):
        text = json.dumps({"hooks": {
            "SessionStart": [{"hooks": [{"type": "command", "command": "python3 " + self.GOOD[0]}]}],
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "python3 " + self.GOOD[1]}]},
                {"matcher": "Edit", "hooks": [{"type": "command", "command": "python " + self.GOOD[1]}]},
            ]}})
        self.assertEqual(bad_hook_commands(text), ["python " + self.GOOD[1]])

    def test_checker_flags_non_string_command(self):
        text = json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": None}]}]}})
        self.assertEqual(bad_hook_commands(text), [None])

    def test_checker_passes_real_form(self):
        for g in self.GOOD:
            self.assertEqual(bad_hook_commands(_doc("python3 " + g)), [])

    def test_checker_not_vacuous(self):
        zero = json.dumps({"hooks": {}})
        prompt_only = json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "prompt", "prompt": "x"}]}]}})
        flat = json.dumps({"hooks": [{"type": "command", "command": "python x.py"}]})
        no_inner = json.dumps({"hooks": {"Stop": [{"matcher": ""}]}})
        misnamed = json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "commnad", "command": "python x.py"}]}]}})
        # zero command hooks: the real-file assertions must fail, not pass silently
        for doc in (zero, prompt_only, misnamed):
            with self.assertRaises(AssertionError):
                verify_hooks_doc(self, doc)
        # misnamed type is counted as "other", so it cannot hide a command
        self.assertEqual(scan_hooks(misnamed), ([], 1))
        # wrong nesting must raise, never report 0 found
        for doc in (flat, no_inner):
            with self.assertRaises(ValueError):
                scan_hooks(doc)

    def test_non_command_entries_are_counted_not_checked(self):
        text = json.dumps({"hooks": {"Stop": [{"hooks": [
            {"type": "prompt", "prompt": "python x.py"},
            {"type": "command", "command": "python3 " + self.GOOD[0]}]}]}})
        commands, others = scan_hooks(text)
        self.assertEqual((len(commands), others), (1, 1))
        self.assertEqual(bad_hook_commands(text), [])


# ----------------------------------------------------------------- tree sweep

class TestNoBarePythonInTree(unittest.TestCase):
    BAD_LINES = [
        "python plugin/scripts/bring_core.py init",
        "  python bring_core.py check",
        "Run: python tests/test_bring_core.py",
        "python -m unittest",
        'Run `python "${CLAUDE_PLUGIN_ROOT}/scripts/bring_core.py" brief`',
        "#!/usr/bin/env python",
        "#!/usr/bin/python",
        "cd x && python plugin/scripts/bring_core.py brief",
        "python <<EOF",
        "echo x | python",
        "run: python",
        "python3 x && python",
        "subprocess.run(['python', CORE, 'brief'])",
        'cmd = ["python", "x.py"]',
        "args = ['python']",
    ]
    GOOD_LINES = [
        "python3 plugin/scripts/bring_core.py init",
        "Python stdlib, no network",
        "python stdlib",
        "#!/usr/bin/env python3",
        "python3.9 -m unittest",
        "the python3 interpreter",
        "`python`",
        "subprocess.run(['python3', CORE])",
        'cmd = ["python3", "x.py"]',
    ]

    def test_regex_flags_known_bad_and_ignores_good(self):
        for line in self.BAD_LINES:
            self.assertTrue(line_is_bare_python(line), "not flagged: %r" % line)
        for line in self.GOOD_LINES:
            self.assertFalse(line_is_bare_python(line), "wrongly flagged: %r" % line)

    def test_sweep_sees_a_known_positive_and_honours_exclusion(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "docs"))
            os.makedirs(os.path.join(d, ".git"))
            with open(os.path.join(d, "docs", "a.md"), "w", encoding="utf-8") as f:
                f.write("fine line\nrun python plugin/x.py now\n")
            with open(os.path.join(d, "skip.md"), "w", encoding="utf-8") as f:
                f.write("python plugin/x.py\n")
            with open(os.path.join(d, ".git", "c.md"), "w", encoding="utf-8") as f:
                f.write("python plugin/x.py\n")
            with open(os.path.join(d, "run.sh"), "w", encoding="utf-8") as f:
                f.write("python plugin/scripts/bring_core.py brief\n")
            with open(os.path.join(d, "ci.yaml"), "w", encoding="utf-8") as f:
                f.write("run: python plugin/scripts/bring_core.py check\n")
            scanned, hits = find_bare_python(d)
            self.assertEqual(sorted(scanned), ["ci.yaml", "docs/a.md", "run.sh", "skip.md"])
            self.assertEqual(sorted(hits), [("ci.yaml", 1), ("docs/a.md", 2),
                                            ("run.sh", 1), ("skip.md", 1)])
            scanned, hits = find_bare_python(d, exclude=("skip.md",))
            self.assertEqual(sorted(scanned), ["ci.yaml", "docs/a.md", "run.sh"])
            self.assertNotIn(("skip.md", 1), hits)

    def test_no_bare_python_invocations_in_tree(self):
        scanned, hits = find_bare_python(REPO, exclude=(THIS_FILE,))
        self.assertGreater(len(scanned), 0)
        for must in ("plugin/hooks/hooks.json", "README.md", "llms.txt",
                     "plugin/skills/bring/SKILL.md", "plugin/scripts/bring_core.py"):
            self.assertIn(must, scanned)
        self.assertNotIn(THIS_FILE, scanned)
        self.assertEqual(hits, [], "bare `python` invocations (file, line)")


# ------------------------------------------------------------------ behaviour

@unittest.skipUnless(_system_python3_works(), "/usr/bin/python3 not usable here")
class TestHooksRunWithoutBarePython(unittest.TestCase):
    """Run the real hook commands under PATH=/usr/bin:/bin, the way a hook runner would."""

    # Hand-written fixture: one open item; NOT produced by bring_core.py init.
    ACTIONS = "## Send the pilot invite\nkind: send\nid: pilot-invite\nnote: hand-written fixture\n"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.proj = self._tmp.name
        os.makedirs(os.path.join(self.proj, "bring"))
        with open(os.path.join(self.proj, "bring", "actions.md"), "w", encoding="utf-8") as f:
            f.write(self.ACTIONS)
        with open(HOOKS_JSON, encoding="utf-8") as f:
            commands, _ = scan_hooks(f.read())
        self.cmd = {event: command for event, command in commands}

    def test_injector_emits_session_start_context(self):
        r = _run(self.cmd["SessionStart"], self.proj)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "SessionStart")
        self.assertIn("python3", out["additionalContext"])
        self.assertIn("pilot-invite", out["additionalContext"])

    def test_stop_nudge_runs_and_keeps_stdout_empty(self):
        r = _run(self.cmd["Stop"], self.proj)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "")
        self.assertIn("went untouched", r.stderr)  # it ran and found today's bring

    def test_fail_open_without_bring_dir(self):
        with tempfile.TemporaryDirectory() as empty:
            for stdin_text in ("{}", "", "not json {{{"):
                for command in self.cmd.values():
                    r = _run(command, empty, stdin_text)
                    self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""), command)

    def test_garbage_stdin_still_exits_zero(self):
        for command in self.cmd.values():
            r = _run(command, self.proj, "\x00\xff not json")
            self.assertEqual(r.returncode, 0, command)

    def test_old_bare_python_command_fails_where_python_is_absent(self):
        if shutil.which("python", path="/usr/bin:/bin") is not None:
            self.skipTest("a bare `python` exists on /usr/bin:/bin here; the old bug cannot show")
        old = 'python "${CLAUDE_PLUGIN_ROOT}/hooks/bring-injector.py"'
        r = _run(old, self.proj)
        self.assertEqual(r.returncode, 127)
        self.assertEqual(r.stdout, "")


if __name__ == "__main__":
    unittest.main()
