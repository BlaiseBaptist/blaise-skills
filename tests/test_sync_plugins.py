import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "plugins/t3-fleet/skills/t3-fleet-onboard/scripts/sync-plugins.py"
spec = importlib.util.spec_from_file_location("sync_plugins", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SyncPluginsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)

    def old_links(self, links):
        skills = self.home / ".agents/skills"
        skills.mkdir(parents=True, exist_ok=True)
        for name, target in links.items():
            (skills / name).symlink_to(target)
        state = self.home / ".local/state/blaise-skills/shared-links.json"
        state.parent.mkdir(parents=True)
        state.write_text(json.dumps(links))

    def test_retires_only_links_the_old_sync_owns(self):
        self.old_links({"t3-fleet-delegate": "/cache/a/t3-fleet-delegate", "screenshot": "/cache/a/screenshot"})
        # The user repointed screenshot; it is theirs now.
        replaced = self.home / ".agents/skills/screenshot"
        replaced.unlink()
        replaced.symlink_to("/mine/screenshot")
        (self.home / ".agents/skills/docx").symlink_to("/synced/docx")
        module.retire_links(self.home)
        self.assertEqual(sorted(os.listdir(self.home / ".agents/skills")), ["docx", "screenshot"])
        self.assertFalse((self.home / ".local/state/blaise-skills/shared-links.json").exists())

    def test_retire_without_state_is_a_no_op(self):
        module.retire_links(self.home)

    def test_installs_runner_and_keeps_it_current(self):
        runner = self.home / ".local/bin/claude-skills-sync"
        source = Path(module.__file__).with_name("claude-skills-sync.sh")
        module.install_runner(self.home)
        self.assertEqual(runner.read_bytes(), source.read_bytes())
        self.assertTrue(os.access(runner, os.X_OK))
        runner.write_text("#!/bin/sh\n# stale\n")
        module.install_runner(self.home)
        self.assertEqual(runner.read_bytes(), source.read_bytes())

    def codex(self, installed, marketplaces=("blaise-skills",)):
        calls = []

        def run(command, **kwargs):
            calls.append(command)
            if command[:4] == ["codex", "plugin", "marketplace", "list"]:
                return mock.Mock(stdout=json.dumps({"marketplaces": [{"name": n} for n in marketplaces]}))
            return mock.Mock(stdout=json.dumps({"installed": installed, "available": []}))
        return calls, run

    def test_codex_waits_for_the_new_runner_to_add_the_marketplace(self):
        calls, run = self.codex([], marketplaces=("openai-curated",))
        with mock.patch.object(module.subprocess, "run", side_effect=run):
            self.assertEqual(module.update_codex(["t3-fleet"]), [])
        self.assertFalse(any("add" in call for call in calls))

    def test_codex_bootstraps_claudes_plugins(self):
        calls, run = self.codex([])
        with mock.patch.object(module.subprocess, "run", side_effect=run):
            self.assertEqual(module.update_codex(["t3-fleet", "desktop"]), ["t3-fleet", "desktop"])
        self.assertIn(["codex", "plugin", "add", "desktop@blaise-skills"], calls)

    def test_codex_defaults_to_t3_fleet(self):
        calls, run = self.codex([])
        with mock.patch.object(module.subprocess, "run", side_effect=run):
            self.assertEqual(module.update_codex([]), ["t3-fleet"])

    def test_codex_leaves_installed_plugins_to_the_upgrade(self):
        calls, run = self.codex([{"name": "t3-fleet", "marketplaceName": "blaise-skills"},
                                 {"name": "sites", "marketplaceName": "openai-curated"}])
        with mock.patch.object(module.subprocess, "run", side_effect=run):
            self.assertEqual(module.update_codex(["desktop"]), ["t3-fleet"])
        self.assertFalse(any("add" in call for call in calls))


if __name__ == "__main__":
    unittest.main()
