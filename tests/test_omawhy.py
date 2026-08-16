import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from omawhy import (
    action_command,
    build_remembered_rules,
    inspect_window_at_cursor,
    normalize_window,
    remember_window,
    undo_last_change,
    window_at_cursor,
)


class NormalizeWindowTests(unittest.TestCase):
    def test_exposes_hyprland_window_fields_without_guessing(self):
        raw = {
            "address": "0xabc",
            "class": "firefox",
            "initialClass": "firefox",
            "title": "YouTube",
            "workspace": {"id": 3, "name": "3"},
            "monitor": 1,
            "floating": False,
            "fullscreen": 0,
            "pinned": False,
            "pid": 8421,
            "at": [90, 120],
            "size": [1280, 720],
            "xwayland": False,
        }

        window = normalize_window(raw)

        self.assertEqual(
            window,
            {
                "address": "0xabc",
                "app_id": "firefox",
                "class": "",
                "identifier": "firefox",
                "identifier_kind": "app_id",
                "title": "YouTube",
                "workspace": 3,
                "monitor": 1,
                "floating": False,
                "fullscreen": False,
                "pinned": False,
                "pid": 8421,
                "at": [90, 120],
                "size": [1280, 720],
            },
        )

    def test_builds_anchored_rules_and_only_persists_geometry_when_floating(self):
        rules = build_remembered_rules(
            {
                "identifier": "org.mozilla.firefox",
                "identifier_kind": "app_id",
                "title": "YouTube",
                "workspace": 3,
                "monitor": "HDMI-A-1",
                "floating": True,
                "fullscreen": False,
                "pinned": False,
                "at": [90, 120],
                "size": [1280, 720],
            }
        )

        self.assertEqual(
            rules,
            [
                "# OmaWhy: YouTube [app_id=org.mozilla.firefox]",
                "windowrule = workspace 3 silent, match:class ^(org\\.mozilla\\.firefox)$",
                "windowrule = monitor HDMI-A-1, match:class ^(org\\.mozilla\\.firefox)$",
                "windowrule = float on, match:class ^(org\\.mozilla\\.firefox)$",
                "windowrule = size 1280 720, match:class ^(org\\.mozilla\\.firefox)$",
                "windowrule = move 90 120, match:class ^(org\\.mozilla\\.firefox)$",
            ],
        )

    def test_picks_the_visible_client_under_the_pointer(self):
        clients = [
            {"address": "0xhidden", "hidden": True, "at": [0, 0], "size": [800, 600]},
            {"address": "0xone", "at": [20, 40], "size": [400, 300]},
            {"address": "0xtwo", "at": [800, 40], "size": [400, 300]},
        ]

        self.assertEqual(window_at_cursor(clients, 99, 100)["address"], "0xone")
        self.assertIsNone(window_at_cursor(clients, 500, 100))

    def test_remember_writes_a_scoped_rule_with_backup_and_undo_restores_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            apps_file = home / ".config" / "hypr" / "apps.conf"
            apps_file.parent.mkdir(parents=True)
            apps_file.write_text("# Existing user rules\n", encoding="utf-8")
            window = {
                "identifier": "firefox",
                "identifier_kind": "app_id",
                "title": "YouTube",
                "workspace": 3,
                "monitor": "HDMI-A-1",
                "floating": False,
                "fullscreen": False,
                "pinned": False,
                "at": [0, 0],
                "size": [0, 0],
            }

            result = remember_window(window, home=home, reload_hyprland=False)
            rule_file = home / ".config" / "hypr" / "apps" / "omawhy.conf"

            self.assertTrue(result["backup"].exists())
            self.assertIn("source = " + str(rule_file), apps_file.read_text(encoding="utf-8"))
            self.assertIn("windowrule = workspace 3 silent", rule_file.read_text(encoding="utf-8"))
            self.assertTrue(undo_last_change(home=home, reload_hyprland=False))
            self.assertEqual(apps_file.read_text(encoding="utf-8"), "# Existing user rules\n")
            self.assertFalse(rule_file.exists())

    def test_inspection_resolves_the_human_monitor_name(self):
        selected = inspect_window_at_cursor(
            [
                {
                    "address": "0xabc",
                    "class": "firefox",
                    "title": "YouTube",
                    "workspace": {"id": 3},
                    "monitor": 1,
                    "at": [20, 40],
                    "size": [400, 300],
                    "pid": 8421,
                }
            ],
            {"x": 30, "y": 50},
            [{"id": 1, "name": "HDMI-A-1"}],
        )

        self.assertEqual(selected["monitor"], "HDMI-A-1")
        self.assertEqual(selected["app_id"], "firefox")

    def test_window_actions_target_only_the_selected_address(self):
        window = {"address": "0xabc", "identifier": "firefox", "title": "YouTube"}

        self.assertEqual(
            action_command("move-current", window),
            ["hyprctl", "dispatch", "movetoworkspace", "current,address:0xabc"],
        )
        self.assertEqual(
            action_command("toggle-floating", window),
            ["hyprctl", "dispatch", "togglefloating", "address:0xabc"],
        )
        self.assertEqual(
            action_command("toggle-fullscreen", window),
            ["hyprctl", "dispatch", "fullscreen", "0,address:0xabc"],
        )
        self.assertEqual(action_command("copy-app-id", window), ["wl-copy", "firefox"])

    def test_setup_adds_a_single_hotkey_and_removal_leaves_user_bindings_intact(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            config = home / ".config" / "hypr"
            config.mkdir(parents=True)
            bindings = config / "bindings.conf"
            bindings.write_text("# My own binding\n", encoding="utf-8")
            env = os.environ | {"HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config")}

            installed = subprocess.run(["bash", "setup.sh"], cwd=Path(__file__).parents[1], env=env, text=True, capture_output=True)
            self.assertEqual(installed.returncode, 0, installed.stderr)
            self.assertEqual(bindings.read_text(encoding="utf-8").count("OmaWhy: begin"), 1)

            removed = subprocess.run(["bash", "setup.sh", "--remove"], cwd=Path(__file__).parents[1], env=env, text=True, capture_output=True)
            self.assertEqual(removed.returncode, 0, removed.stderr)
            self.assertEqual(bindings.read_text(encoding="utf-8"), "# My own binding\n")


if __name__ == "__main__":
    unittest.main()
