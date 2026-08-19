import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from omawhy import (
    action_command,
    build_remembered_rules,
    desktop_status,
    diagnose_shortcut,
    explain_window_rules,
    inspect_window_at_cursor,
    normalize_window,
    remember_window,
    scan_problems,
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

            hyprland_lua = home / ".config" / "hypr" / "hyprland.lua"
            hyprland_lua.write_text('require("default.hypr.omarchy")\n', encoding="utf-8")
            lua_result = remember_window(window, home=home, reload_hyprland=False)
            lua_rules = home / ".config" / "hypr" / "omawhy.lua"
            self.assertEqual(lua_result["rules_file"], lua_rules)
            self.assertIn('require("hypr.omawhy")', hyprland_lua.read_text(encoding="utf-8"))
            self.assertIn('o.window("^firefox$"', lua_rules.read_text(encoding="utf-8"))
            self.assertTrue(undo_last_change(home=home, reload_hyprland=False))
            self.assertEqual(hyprland_lua.read_text(encoding="utf-8"), 'require("default.hypr.omarchy")\n')
            self.assertFalse(lua_rules.exists())

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
            action_command("move-current", window, current_workspace=3),
            ["hyprctl", "dispatch", 'hl.dsp.window.move({ workspace = "3", window = "address:0xabc" })'],
        )
        self.assertEqual(
            action_command("toggle-floating", window),
            ["hyprctl", "dispatch", 'hl.dsp.window.float({ action = "toggle", window = "address:0xabc" })'],
        )
        self.assertEqual(
            action_command("toggle-fullscreen", window),
            ["hyprctl", "dispatch", 'hl.dsp.window.fullscreen({ mode = "fullscreen", action = "toggle", window = "address:0xabc" })'],
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

            (config / "hyprland.lua").write_text('require("hypr.bindings")\n', encoding="utf-8")
            lua_bindings = config / "bindings.lua"
            lua_bindings.write_text("-- My own Lua binding\n", encoding="utf-8")
            installed_lua = subprocess.run(["bash", "setup.sh"], cwd=Path(__file__).parents[1], env=env, text=True, capture_output=True)
            self.assertEqual(installed_lua.returncode, 0, installed_lua.stderr)
            self.assertIn('o.bind("SUPER + SHIFT + I", "OmaWhy"', lua_bindings.read_text(encoding="utf-8"))

            removed_lua = subprocess.run(["bash", "setup.sh", "--remove"], cwd=Path(__file__).parents[1], env=env, text=True, capture_output=True)
            self.assertEqual(removed_lua.returncode, 0, removed_lua.stderr)
            self.assertEqual(lua_bindings.read_text(encoding="utf-8"), "-- My own Lua binding\n")

    def test_explains_a_matching_omarchy_lua_placement_rule_with_source_and_line(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            hypr = home / ".config" / "hypr"
            hypr.mkdir(parents=True)
            (hypr / "hyprland.lua").write_text('require("hypr.rules")\n', encoding="utf-8")
            (hypr / "rules.lua").write_text(
                'o.window("firefox", { workspace = "3", float = true })\n'
                'o.window("firefox", { opacity = "1.0 0.9" })\n',
                encoding="utf-8",
            )

            explanation = explain_window_rules(
                {"identifier": "firefox", "workspace": 3, "floating": True, "monitor": "HDMI-A-1"},
                home=home,
                omarchy_root=home / "missing-omarchy",
            )

            self.assertEqual(explanation["verdict"], "placement-rule")
            self.assertEqual(len(explanation["matches"]), 2)
            placement = explanation["matches"][0]
            self.assertEqual(placement["path"], str(hypr / "rules.lua"))
            self.assertEqual(placement["line"], 1)
            self.assertEqual(placement["effects"], {"workspace": "3", "float": True})
            self.assertEqual(placement["state"], {"workspace": "matches", "float": "matches"})
            self.assertIn("workspace 3", explanation["message"])

    def test_explains_matching_legacy_conf_rules_from_sourced_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            hypr = home / ".config" / "hypr"
            rules = hypr / "apps" / "browser.conf"
            rules.parent.mkdir(parents=True)
            (hypr / "hyprland.conf").write_text("source = ~/.config/hypr/apps.conf\n", encoding="utf-8")
            (hypr / "apps.conf").write_text("source = " + str(rules) + "\n", encoding="utf-8")
            rules.write_text("windowrule = float on, match:class ^(firefox)$\n", encoding="utf-8")

            explanation = explain_window_rules(
                {"identifier": "firefox", "workspace": 1, "floating": True, "monitor": "HDMI-A-1"},
                home=home,
                omarchy_root=home / "missing-omarchy",
            )

            self.assertEqual(explanation["verdict"], "placement-rule")
            self.assertEqual(explanation["matches"][0]["format"], "conf")
            self.assertEqual(explanation["matches"][0]["effects"], {"float": True})
            self.assertEqual(explanation["matches"][0]["state"], {"float": "matches"})

    def test_follows_lua_require_order_before_claiming_a_tag_rule_applies(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            hypr = home / ".config" / "hypr"
            hypr.mkdir(parents=True)
            (hypr / "hyprland.lua").write_text(
                'o.window("firefox", { tag = "+chosen" })\n'
                'require("hypr.rules")\n'
                'o.window({ tag = "chosen" }, { workspace = "7" })\n',
                encoding="utf-8",
            )
            (hypr / "rules.lua").write_text('o.window({ tag = "chosen" }, { tag = "-chosen" })\n', encoding="utf-8")

            explanation = explain_window_rules(
                {"identifier": "firefox", "workspace": 1, "floating": False, "monitor": "HDMI-A-1"},
                home=home,
                omarchy_root=home / "missing-omarchy",
            )

            self.assertEqual(explanation["verdict"], "style-rule")
            self.assertFalse(any("workspace" in match["effects"] for match in explanation["matches"]))

    def test_finds_an_active_lua_shortcut_and_its_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            bindings = home / ".config" / "hypr" / "bindings.lua"
            bindings.parent.mkdir(parents=True)
            bindings.write_text('o.bind("SUPER + SHIFT + I", "OmaWhy", "omarchy-shell shell toggle io.github.brm-src.omawhy \'{}\'")\n', encoding="utf-8")

            diagnosis = diagnose_shortcut("Super Shift I", home=home, omarchy_root=home / "missing-omarchy")

            self.assertEqual(diagnosis["verdict"], "bound")
            self.assertEqual(diagnosis["binding"]["label"], "OmaWhy")
            self.assertEqual(diagnosis["binding"]["path"], str(bindings))
            self.assertEqual(diagnosis["binding"]["line"], 1)

    def test_desktop_status_reports_active_config_shell_and_omawhy_binding(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            hypr = home / ".config" / "hypr"
            hypr.mkdir(parents=True)
            (hypr / "hyprland.lua").write_text('require("hypr.bindings")\n', encoding="utf-8")
            (hypr / "bindings.lua").write_text('o.bind("SUPER + SHIFT + I", "OmaWhy", "omarchy-shell shell toggle io.github.brm-src.omawhy \'{}\'")\n', encoding="utf-8")

            status = desktop_status(home=home, omarchy_root=home / "missing-omarchy", check_command=lambda command: True)

            self.assertEqual(status["config"], "lua")
            self.assertEqual([item["state"] for item in status["checks"]], ["ok", "ok", "ok"])
            self.assertIn("listo", status["message"])

    def test_reports_a_shortcut_disabled_by_user_configuration(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            bindings = home / ".config" / "hypr" / "bindings.lua"
            bindings.parent.mkdir(parents=True)
            bindings.write_text('hl.unbind("SUPER + SHIFT + I")\n', encoding="utf-8")

            diagnosis = diagnose_shortcut("Super Shift I", home=home, omarchy_root=home / "missing-omarchy")

            self.assertEqual(diagnosis["verdict"], "disabled")
            self.assertEqual(diagnosis["events"][0]["line"], 1)

    def test_scan_reports_missing_binary_duplicate_shortcut_and_broken_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            hypr = home / ".config" / "hypr"
            hypr.mkdir(parents=True)
            (hypr / "hyprland.conf").write_text(
                'source = ~/.local/share/omarchy/default/hypr/autostart.conf\n',
                encoding="utf-8",
            )
            bindings = hypr / "bindings.conf"
            bindings.write_text(
                'bindd = SUPER SHIFT, R, launch-terminal, exec, alacritty\n'
                'bindd = SUPER SHIFT, R, launch-file-manager, exec, nemo\n',
                encoding="utf-8",
            )

            result = scan_problems(
                home=home,
                omarchy_root=home / "missing-omarchy",
                which_command=lambda binary: binary == "nemo",
                check_command=lambda command: False,
            )

            titles = [problem["title"] for problem in result["problems"]]
            self.assertIn("Comando apunta a un ejecutable que no existe", titles)
            self.assertIn("Atajo definido más de una vez", titles)
            self.assertIn("Source a un archivo que no existe", titles)
            missing = next(p for p in result["problems"] if p["title"].startswith("Comando"))
            self.assertIn("alacritty", missing["detail"])
            self.assertEqual(missing["path"], str(bindings))
            self.assertEqual(missing["line"], 1)

    def test_scan_returns_empty_for_a_clean_config(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            hypr = home / ".config" / "hypr"
            hypr.mkdir(parents=True)
            (hypr / "hyprland.conf").write_text('bindd = SUPER SHIFT, I, test, exec, nemo\n', encoding="utf-8")

            result = scan_problems(
                home=home,
                omarchy_root=home / "missing-omarchy",
                which_command=lambda binary: True,
                check_command=lambda command: True,
            )

            self.assertEqual(result["total"], 0)
            self.assertEqual(result["message"], "No encontré problemas evidentes.")

    def test_scan_reports_broken_lua_require(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            hypr = home / ".config" / "hypr"
            hypr.mkdir(parents=True)
            (hypr / "hyprland.lua").write_text('require("hypr.ghost")\n', encoding="utf-8")

            result = scan_problems(
                home=home,
                omarchy_root=home / "missing-omarchy",
                which_command=lambda binary: True,
                check_command=lambda command: True,
            )

            self.assertEqual(result["total"], 1)
            self.assertIn("Require a un archivo que no existe", result["problems"][0]["title"])
            self.assertIn("ghost.lua", result["problems"][0]["detail"])


if __name__ == "__main__":
    unittest.main()
