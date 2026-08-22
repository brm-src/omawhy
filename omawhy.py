#!/usr/bin/env python3
"""Safe Hyprland window inspection and rule persistence for OmaWhy."""

import hashlib
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

LANG = "es"


def _t(es, en):
    """Return the user-facing string for the active language (default: Spanish)."""
    return es if LANG == "es" else en


def _matcher(window):
    identifier = str(window.get("identifier") or "")
    if not identifier:
        raise ValueError(_t("La ventana no expone app_id/class; no es seguro crear una regla.", "The window does not expose app_id/class; it is not safe to create a rule."))
    return "match:class ^(" + re.escape(identifier) + ")$"


def build_remembered_rules(window):
    """Generate current Hyprland window rules without matching titles loosely."""
    matcher = _matcher(window)
    title = str(window.get("title") or "Ventana").replace("\n", " ")
    kind = str(window.get("identifier_kind") or "app_id")
    identifier = str(window.get("identifier") or "")
    rules = [f"# OmaWhy: {title} [{kind}={identifier}]"]
    workspace = int(window.get("workspace") or 0)
    monitor = str(window.get("monitor") or "")
    if workspace > 0:
        rules.append(f"windowrule = workspace {workspace} silent, {matcher}")
    if monitor:
        rules.append(f"windowrule = monitor {monitor}, {matcher}")
    if window.get("fullscreen"):
        rules.append(f"windowrule = fullscreen on, {matcher}")
    else:
        rules.append(f"windowrule = float {'on' if window.get('floating') else 'off'}, {matcher}")
        if window.get("floating"):
            size = list(window.get("size") or [0, 0])
            at = list(window.get("at") or [0, 0])
            if len(size) == 2 and all(int(value) > 0 for value in size):
                rules.append(f"windowrule = size {int(size[0])} {int(size[1])}, {matcher}")
            if len(at) == 2 and all(int(value) >= 0 for value in at):
                rules.append(f"windowrule = move {int(at[0])} {int(at[1])}, {matcher}")
    if window.get("pinned"):
        rules.append(f"windowrule = pin on, {matcher}")
    return rules


def build_remembered_lua_rule(window):
    """Generate a Lua rule using only documented Omarchy rule properties."""
    identifier = str(window.get("identifier") or "")
    if not identifier:
        raise ValueError(_t("La ventana no expone app_id/class; no es seguro crear una regla.", "The window does not expose app_id/class; it is not safe to create a rule."))
    matcher = ("^" + re.escape(identifier) + "$").replace("\\", "\\\\").replace('"', '\\"')
    effects = []
    workspace = int(window.get("workspace") or 0)
    monitor = str(window.get("monitor") or "")
    if workspace > 0:
        effects.append('workspace = "' + str(workspace) + '"')
    if monitor:
        effects.append('monitor = "' + monitor.replace("\\", "\\\\").replace('"', '\\"') + '"')
    if window.get("fullscreen"):
        effects.append("fullscreen = true")
    else:
        effects.append("float = " + ("true" if window.get("floating") else "false"))
    if window.get("pinned"):
        effects.append("pin = true")
    return 'o.window("' + matcher + '", { ' + ", ".join(effects) + " })"


def window_at_cursor(clients, x, y):
    """Return the top-most visible client covering a global cursor point."""
    for client in reversed(clients):
        if client.get("hidden"):
            continue
        at = list(client.get("at") or [])
        size = list(client.get("size") or [])
        if len(at) != 2 or len(size) != 2:
            continue
        left, top = at
        width, height = size
        if left <= x < left + width and top <= y < top + height:
            return client
    return None


def _normalize_shortcut(keys):
    return " + ".join(piece for piece in re.split(r"\s*(?:\+|,)\s*|\s+", str(keys).upper().strip()) if piece)


def _shortcut_events(path):
    text = path.read_text(encoding="utf-8", errors="replace")
    # Drop Lua comment lines (-- ...) so commented-out example binds are not
    # reported as real shortcut problems.
    active_text = "\n".join("" if line.lstrip().startswith("--") else line for line in text.splitlines())
    events = []
    lua_bind = re.compile(r"o\.bind\(\s*[\"'](?P<keys>[^\"']+)[\"']\s*,\s*(?P<label>nil|[\"'][^\"']*[\"'])\s*,\s*(?P<command>[\"'][^\"']*[\"']|\{)")
    for match in lua_bind.finditer(active_text):
        label = match.group("label")
        command = match.group("command")
        events.append((match.start(), {"action": "bind", "keys": _normalize_shortcut(match.group("keys")), "label": "" if label == "nil" else label[1:-1], "command": "comando compuesto" if command == "{" else command[1:-1], "path": str(path), "line": active_text.count("\n", 0, match.start()) + 1}))
    for match in re.finditer(r"hl\.unbind\(\s*[\"']([^\"']+)[\"']\s*\)", active_text):
        events.append((match.start(), {"action": "unbind", "keys": _normalize_shortcut(match.group(1)), "path": str(path), "line": active_text.count("\n", 0, match.start()) + 1}))
    for number, line in enumerate(text.splitlines(), 1):
        match = re.match(r"\s*bindd?\s*=\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*(.+)$", line)
        if match:
            events.append((number * 1000000, {"action": "bind", "keys": _normalize_shortcut(match.group(1) + " " + match.group(2)), "label": match.group(3).strip(), "command": match.group(5).strip(), "path": str(path), "line": number}))
    return [event for _, event in sorted(events, key=lambda item: item[0])]


def diagnose_shortcut(keys, home=None, omarchy_root=None):
    """Tell the user whether a Hyprland shortcut is bound, disabled, or absent."""
    wanted = _normalize_shortcut(keys)
    home = Path(home or Path.home())
    omarchy_root = Path(omarchy_root or os.getenv("OMARCHY_PATH", "/usr/share/omarchy"))
    candidates = [
        omarchy_root / "default" / "hypr" / "bindings.lua",
        omarchy_root / "default" / "hypr" / "bindings.conf",
        home / ".config" / "hypr" / "bindings.lua",
        home / ".config" / "hypr" / "bindings.conf",
    ]
    events = []
    for path in candidates:
        if path.exists():
            events.extend(event for event in _shortcut_events(path) if event["keys"] == wanted)
    if not events:
        return {"verdict": "missing", "message": _t(
            "No encontré un atajo para “" + wanted + "” en la configuración de Omarchy.",
            "I couldn't find a shortcut for “" + wanted + "” in the Omarchy configuration.",
        ), "events": []}
    latest = events[-1]
    if latest["action"] == "unbind":
        return {"verdict": "disabled", "message": _t(
            "“" + wanted + "” está desactivado en " + Path(latest["path"]).name + ", línea " + str(latest["line"]) + ".",
            "“" + wanted + "” is disabled in " + Path(latest["path"]).name + ", line " + str(latest["line"]) + ".",
        ), "events": events}
    return {"verdict": "bound", "message": _t(
        "“" + wanted + "” ejecuta “" + (latest["label"] or latest["command"]) + "”.",
        "“" + wanted + "” runs “" + (latest["label"] or latest["command"]) + "”.",
    ), "binding": latest, "events": events}


def desktop_status(home=None, omarchy_root=None, check_command=None):
    """Check the minimum pieces needed for Omarchy and OmaWhy to respond."""
    home = Path(home or Path.home())
    hypr_dir = home / ".config" / "hypr"
    config = "lua" if (hypr_dir / "hyprland.lua").exists() else "classic" if (hypr_dir / "hyprland.conf").exists() else "missing"
    if check_command is None:
        def runner(command):
            return subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False).returncode == 0
    else:
        runner = check_command
    shortcut = diagnose_shortcut("SUPER + SHIFT + I", home=home, omarchy_root=omarchy_root)
    checks = [
        {"label": _t("Configuración de Hyprland", "Hyprland configuration"), "state": "ok" if config != "missing" else "warning", "detail": _t("Formato Lua", "Lua format") if config == "lua" else _t("Formato clásico", "Classic format") if config == "classic" else _t("No encontré hyprland.lua ni hyprland.conf.", "I couldn't find hyprland.lua or hyprland.conf.")},
        {"label": _t("Hyprland y Quickshell", "Hyprland and Quickshell"), "state": "ok" if runner(["hyprctl", "-j", "version"]) and runner(["pgrep", "-x", "quickshell"]) else "warning", "detail": _t("Ambos procesos responden.", "Both processes respond.")},
        {"label": _t("Atajo de OmaWhy", "OmaWhy shortcut"), "state": "ok" if shortcut["verdict"] == "bound" else "warning", "detail": shortcut["message"]},
    ]
    ready = all(check["state"] == "ok" for check in checks)
    return {"config": config, "checks": checks, "message": _t("El escritorio base está listo.", "The base desktop is ready.") if ready else _t("Encontré algo que revisar antes de culpar a Omarchy.", "I found something to check before blaming Omarchy.")}


PLACEMENT_EFFECTS = {"workspace", "monitor", "float", "fullscreen", "pin", "move", "size"}


def _split_top_level(value):
    parts, start, depth, quote, escaped = [], 0, 0, None, False
    for index, char in enumerate(value):
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char in "({[":
            depth += 1
        elif char in ")}]":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(value[start:index].strip())
            start = index + 1
    parts.append(value[start:].strip())
    return [part for part in parts if part]


def _lua_value(value):
    value = value.strip()
    if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
        return value[1:-1].replace("\\\"", "\"").replace("\\\\", "\\")
    if value == "true":
        return True
    if value == "false":
        return False
    return value


def _lua_table(value):
    value = value.strip()
    if not (value.startswith("{") and value.endswith("}")):
        return {}
    fields = {}
    for item in _split_top_level(value[1:-1]):
        if "=" not in item:
            continue
        key, raw_value = item.split("=", 1)
        key = key.strip()
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            fields[key] = _lua_value(raw_value)
    return fields


def _lua_calls(text):
    """Yield complete o.window(...) calls, including multi-line tables."""
    needle, cursor = "o.window(", 0
    while True:
        start = text.find(needle, cursor)
        if start < 0:
            return
        position, depth, quote, escaped = start + len(needle), 1, None, False
        while position < len(text) and depth:
            char = text[position]
            if quote:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = None
            elif char in "\"'":
                quote = char
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            position += 1
        if depth == 0:
            yield text[start + len(needle):position - 1], text.count("\n", 0, start) + 1, start
        cursor = position


def _resolve_lua_module(module, home, omarchy_root):
    pieces = module.split(".")
    if pieces and pieces[0] == "hypr":
        return home / ".config" / "hypr" / ("/".join(pieces[1:]) + ".lua")
    if pieces[:2] == ["default", "hypr"]:
        return omarchy_root / "default" / "hypr" / ("/".join(pieces[2:]) + ".lua")
    return None


def _discover_conf_files(home):
    root = home / ".config" / "hypr" / "hyprland.conf"
    if not root.exists():
        return []
    discovered, pending = [], [root]
    while pending:
        path = pending.pop(0).resolve()
        if path in discovered or not path.exists():
            continue
        discovered.append(path)
        for source in re.findall(r"^\s*source\s*=\s*(.*?)\s*$", path.read_text(encoding="utf-8", errors="replace"), re.MULTILINE):
            expanded = Path(source.strip().replace("~", str(home), 1))
            candidates = sorted(expanded.parent.glob(expanded.name)) if any(mark in source for mark in "*?[") else [expanded]
            pending.extend(candidate for candidate in candidates if candidate.exists())
    return discovered


def _matches_window(match, window, tags):
    identifier, title = str(window.get("identifier") or ""), str(window.get("title") or "")
    for key, expected in match.items():
        if key == "class":
            try:
                if not re.search(str(expected), identifier):
                    return False
            except re.error:
                return False
        elif key == "title":
            try:
                if not re.search(str(expected), title):
                    return False
            except re.error:
                return False
        elif key == "tag" and str(expected).lstrip("+-") not in tags:
            return False
        elif key == "xwayland" and bool(expected) != (window.get("identifier_kind") == "class"):
            return False
    return bool(match)


def _normalize_effects(effects):
    normalized = {}
    for key, value in effects.items():
        if key in {"float", "fullscreen", "pin"}:
            normalized[key] = value is True or str(value).lower() in {"on", "true", "1"}
        elif key in {"workspace", "monitor"}:
            normalized[key] = str(value).replace(" silent", "").strip()
        else:
            normalized[key] = value
    return normalized


def _effect_state(effects, window):
    state = {}
    for key, value in effects.items():
        if key == "workspace":
            state[key] = "matches" if str(window.get(key)) == str(value) else "differs"
        elif key == "monitor":
            state[key] = "matches" if str(window.get(key)) == str(value) else "differs"
        elif key == "float":
            state[key] = "matches" if bool(window.get("floating")) == value else "differs"
        elif key == "fullscreen":
            state[key] = "matches" if bool(window.get("fullscreen")) == value else "differs"
        elif key == "pin":
            state[key] = "matches" if bool(window.get("pinned")) == value else "differs"
    return state


def _ordered_lua_rules(home, omarchy_root):
    """Expand require() in execution order so tag-based rules stay truthful."""
    root = home / ".config" / "hypr" / "hyprland.lua"
    visited = set()

    def record(path, call, line):
        arguments = _split_top_level(call)
        if len(arguments) != 2:
            return None
        first, second = arguments
        match = {"class": _lua_value(first)} if first.strip().startswith(("\"", "'")) else _lua_table(first)
        effects = _normalize_effects(_lua_table(second))
        if not match or not effects:
            return None
        return {"path": str(path), "line": line, "rule": "o.window(" + call + ")", "match": match, "effects": effects, "format": "lua"}

    def visit(path):
        path = path.resolve()
        if path in visited or not path.exists():
            return []
        visited.add(path)
        text = path.read_text(encoding="utf-8", errors="replace")
        events = []
        for call, line, position in _lua_calls(text):
            events.append((position, "rule", (call, line)))
        for match in re.finditer(r"(?:require|require_optional\.module)\(\s*[\"']([^\"']+)[\"']\s*\)", text):
            events.append((match.start(), "module", match.group(1)))
        for match in re.finditer(r"require_all\.files\(", text):
            if "default/hypr/apps" in text:
                events.append((match.start(), "all-default-apps", None))
        rules = []
        for _, kind, data in sorted(events, key=lambda event: event[0]):
            if kind == "rule":
                item = record(path, *data)
                if item:
                    rules.append(item)
            elif kind == "module":
                candidate = _resolve_lua_module(data, home, omarchy_root)
                if candidate:
                    rules.extend(visit(candidate))
            else:
                apps = omarchy_root / "default" / "hypr" / "apps"
                for candidate in sorted(apps.glob("*.lua")):
                    rules.extend(visit(candidate))
        return rules

    return visit(root)


def _conf_rules(path):
    for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        found = re.match(r"^\s*windowrule(?:v2)?\s*=\s*(.+)$", line)
        if not found:
            continue
        parts = _split_top_level(found.group(1))
        if not parts:
            continue
        effect = parts[0].split()
        if not effect:
            continue
        key, value = effect[0], " ".join(effect[1:])
        match = {}
        for item in parts[1:]:
            matched = re.match(r"match:(class|title)\s+(.+)$", item)
            if matched:
                match[matched.group(1)] = matched.group(2)
        if match:
            yield {"path": str(path), "line": number, "rule": line.strip(), "match": match, "effects": _normalize_effects({key: value}), "format": "conf"}


def explain_window_rules(window, home=None, omarchy_root=None):
    """Find loaded-looking static rules that match a selected live window."""
    home = Path(home or Path.home())
    omarchy_root = Path(omarchy_root or os.getenv("OMARCHY_PATH", "/usr/share/omarchy"))
    candidates = _ordered_lua_rules(home, omarchy_root)
    for path in _discover_conf_files(home):
        candidates.extend(_conf_rules(path))

    tags, matches = set(), []
    for candidate in candidates:
        if not _matches_window(candidate["match"], window, tags):
            continue
        effects = candidate["effects"]
        tag = effects.get("tag")
        if isinstance(tag, str):
            if tag.startswith("-"):
                tags.discard(tag[1:])
            else:
                tags.add(tag.lstrip("+"))
        candidate["state"] = _effect_state(effects, window)
        matches.append(candidate)

    placement = [match for match in matches if PLACEMENT_EFFECTS.intersection(match["effects"])]
    if placement:
        first = placement[0]
        facts = []
        if "workspace" in first["effects"]:
            facts.append("workspace " + first["effects"]["workspace"])
        if "monitor" in first["effects"]:
            facts.append("monitor " + first["effects"]["monitor"])
        if "float" in first["effects"]:
            facts.append(_t("flotante ", "floating ") + (_t("sí", "yes") if first["effects"]["float"] else _t("no", "no")))
        return {"verdict": "placement-rule", "message": _t(
            "Hay una regla coincidente que puede explicar " + ", ".join(facts) + ".",
            "There is a matching rule that can explain " + ", ".join(facts) + ".",
        ), "matches": matches}
    if matches:
        return {"verdict": "style-rule", "message": _t(
            "Hay reglas coincidentes, pero solo cambian estilo; no el workspace ni el monitor.",
            "There are matching rules, but they only change style, not the workspace or monitor.",
        ), "matches": matches}
    return {"verdict": "no-match", "message": _t(
        "No encontré una regla estática que coincida. La posición viene del layout, la aplicación o automatización externa.",
        "I couldn't find a matching static rule. The position comes from the layout, the app, or external automation.",
    ), "matches": []}


def action_command(action, window, current_workspace=None):
    """Return an argv-only command; never interpolate a selected window into a shell."""
    address = str(window.get("address") or "")
    if action == "copy-app-id":
        return ["wl-copy", str(window.get("app_id") or window.get("identifier") or "")]
    if action == "copy-class":
        return ["wl-copy", str(window.get("class") or window.get("identifier") or "")]
    if action == "copy-title":
        return ["wl-copy", str(window.get("title") or "")]
    if action == "copy-rule":
        return ["wl-copy", "\n".join(build_remembered_rules(window))]
    if not address:
        raise ValueError(_t("La ventana no tiene dirección Hyprland.", "The window has no Hyprland address."))
    if not re.fullmatch(r"0x[0-9a-fA-F]+", address):
        raise ValueError(_t("La dirección Hyprland no es válida.", "The Hyprland address is invalid."))
    selector = "address:" + address
    if action == "move-current":
        workspace = int(current_workspace or 0)
        if workspace <= 0:
            raise ValueError(_t("No se pudo determinar el workspace actual.", "Could not determine the current workspace."))
        return ["hyprctl", "dispatch", 'hl.dsp.window.move({ workspace = "' + str(workspace) + '", window = "' + selector + '" })']
    dispatches = {
        "center": 'hl.dsp.window.center({ window = "' + selector + '" })',
        "toggle-floating": 'hl.dsp.window.float({ action = "toggle", window = "' + selector + '" })',
        "toggle-fullscreen": 'hl.dsp.window.fullscreen({ mode = "fullscreen", action = "toggle", window = "' + selector + '" })',
        "toggle-pin": 'hl.dsp.window.pin({ action = "toggle", window = "' + selector + '" })',
    }
    if action not in dispatches:
        raise ValueError(_t("Acción no reconocida: ", "Unknown action: ") + action)
    return ["hyprctl", "dispatch", dispatches[action]]


def inspect_window_at_cursor(clients, cursor, monitors):
    """Pick and normalize the client under the pointer using Hyprland data."""
    raw = window_at_cursor(clients, cursor.get("x", -1), cursor.get("y", -1))
    if raw is None:
        return None
    window = normalize_window(raw)
    monitor_names = {monitor.get("id"): monitor.get("name") for monitor in monitors}
    window["monitor"] = monitor_names.get(raw.get("monitor"), str(raw.get("monitor") or ""))
    return window


def _command_binary(command):
    """Extract the first executable token from a Hyprland exec command."""
    tokens = str(command or "").strip().split()
    if not tokens:
        return None
    head = tokens[0].strip("\"'")
    if head in {"exec", "execr", "execrm"}:
        head = tokens[1].strip("\"'") if len(tokens) > 1 else None
    if not head or "=" in head:
        return None
    return head.split("/")[-1]


def _collect_binding_events(home, omarchy_root):
    """All bind/unbind events across default and user config, newest file order last."""
    candidates = [
        omarchy_root / "default" / "hypr" / "bindings.lua",
        omarchy_root / "default" / "hypr" / "bindings.conf",
        home / ".config" / "hypr" / "bindings.lua",
        home / ".config" / "hypr" / "bindings.conf",
    ]
    events = []
    for path in candidates:
        if path.exists():
            events.extend(_shortcut_events(path))
    return events


def _lua_requires(home, omarchy_root):
    """Find require() calls in the active Lua config that point to missing files."""
    root = home / ".config" / "hypr" / "hyprland.lua"
    if not root.exists():
        return []
    visited, problems = set(), []

    def visit(path):
        path = path.resolve()
        if path in visited or not path.exists():
            return
        visited.add(path)
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in re.finditer(r"(?:require|require_optional\.module)\(\s*[\"']([^\"']+)[\"']\s*\)", text):
            module = match.group(1)
            candidate = _resolve_lua_module(module, home, omarchy_root)
            if candidate is None or candidate.exists():
                continue
            problems.append({
                "severity": "warning",
                "title": _t("Require a un archivo que no existe", "Require of a file that does not exist"),
                "detail": "require(\"" + module + "\") " + _t("no resuelve a ", "does not resolve to ") + str(candidate),
                "path": str(path),
                "line": text.count("\n", 0, match.start()) + 1,
            })
        for sub in re.findall(r"(?:require|require_optional\.module)\(\s*[\"']([^\"']+)[\"']\s*\)", text):
            candidate = _resolve_lua_module(sub, home, omarchy_root)
            if candidate:
                visit(candidate)
        for match in re.finditer(r"require_all\.files\(", text):
            for candidate in sorted((omarchy_root / "default" / "hypr" / "apps").glob("*.lua")):
                visit(candidate)

    visit(root)
    return problems


def _conf_sources(home):
    """Find source= lines in classic config pointing to missing files."""
    root = home / ".config" / "hypr" / "hyprland.conf"
    if not root.exists():
        return []
    problems = []
    for path in _discover_conf_files(home):
        for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            found = re.match(r"^\s*source\s*=\s*(.*?)\s*$", line)
            if not found:
                continue
            expanded = Path(found.group(1).strip().replace("~", str(home), 1))
            exists = bool(list(expanded.parent.glob(expanded.name))) if any(mark in found.group(1) for mark in "*?[") else expanded.exists()
            if not exists:
                problems.append({
                    "severity": "warning",
                    "title": _t("Source a un archivo que no existe", "Source of a file that does not exist"),
                    "detail": "source = " + found.group(1).strip() + " " + _t("no se encuentra", "is not found"),
                    "path": str(path),
                    "line": number,
                })
    return problems


def _duplicate_shortcuts(events):
    """Report shortcut combos bound more than once without a later unbind."""
    by_keys = {}
    for event in events:
        by_keys.setdefault(event["keys"], []).append(event)
    problems = []
    for keys, group in by_keys.items():
        binds = [e for e in group if e["action"] == "bind"]
        unbinds = [e for e in group if e["action"] == "unbind"]
        if len(binds) > 1 and not unbinds:
            ordered = sorted(binds, key=lambda e: e["line"])
            last = ordered[-1]
            problems.append({
                "severity": "warning",
                "title": _t("Atajo definido más de una vez", "Shortcut defined more than once"),
                "detail": _t(
                    "\"" + keys + "\" se define " + str(len(ordered)) + " veces; gana el último en " + Path(last["path"]).name + ", línea " + str(last["line"]) + ". El resto se ignora en silencio.",
                    "\"" + keys + "\" is defined " + str(len(ordered)) + " times; the last one wins in " + Path(last["path"]).name + ", line " + str(last["line"]) + ". The rest are silently ignored.",
                ),
                "path": last["path"],
                "line": last["line"],
                "keys": keys,
            })
    return problems


def _broken_shortcut_commands(events, which_command=None):
    """Report bound commands whose first executable does not exist on PATH."""
    if which_command is None:
        def which(binary):
            return shutil.which(binary) is not None
    else:
        which = which_command
    problems = []
    seen = set()
    for event in events:
        if event["action"] != "bind":
            continue
        command = event.get("command") or event.get("label") or ""
        if event.get("command") == "comando compuesto" or not command:
            continue
        binary = _command_binary(command)
        if not binary or binary in seen:
            continue
        seen.add(binary)
        if not which(binary):
            problems.append({
                "severity": "error",
                "title": _t("Comando apunta a un ejecutable que no existe", "Command points to a missing executable"),
                "detail": _t(
                    "\"" + binary + "\" no está en el PATH. El atajo \"" + event["keys"] + "\" no va a funcionar hasta que instales el programa o corrijas el comando.",
                    "\"" + binary + "\" is not on the PATH. The shortcut \"" + event["keys"] + "\" will not work until you install the program or fix the command.",
                ),
                "path": event["path"],
                "line": event["line"],
            })
    return problems


def _broken_window_rule_matches(home):
    """Report window rules whose regex cannot compile (would fail to match anything)."""
    problems = []
    for path in _discover_conf_files(home):
        for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            found = re.match(r"^\s*windowrule(?:v2)?\s*=\s*(.+)$", line)
            if not found:
                continue
            parts = _split_top_level(found.group(1))
            for item in parts[1:]:
                matched = re.match(r"match:(class|title)\s+(.+)$", item)
                if not matched:
                    continue
                pattern = matched.group(2)
                try:
                    re.compile(pattern)
                except re.error as error:
                    problems.append({
                        "severity": "error",
                        "title": _t("Regla de ventana con expresión inválida", "Window rule with an invalid expression"),
                        "detail": _t(
                            "match:" + matched.group(1) + " " + pattern + " no compila (" + str(error) + "). La regla nunca va a coincidir.",
                            "match:" + matched.group(1) + " " + pattern + " does not compile (" + str(error) + "). The rule will never match.",
                        ),
                        "path": str(path),
                        "line": number,
                    })
    return problems


def scan_problems(home=None, omarchy_root=None, which_command=None, check_command=None):
    """Scan the active Omarchy/Hyprland config for real, verifiable problems.

    Only reports findings backed by files, PATH state, or process state.
    Never guesses a cause that cannot be evidenced.
    """
    home = Path(home or Path.home())
    omarchy_root = Path(omarchy_root or os.getenv("OMARCHY_PATH", "/usr/share/omarchy"))
    problems = []

    events = _collect_binding_events(home, omarchy_root)
    problems.extend(_duplicate_shortcuts(events))
    problems.extend(_broken_shortcut_commands(events, which_command=which_command))
    problems.extend(_lua_requires(home, omarchy_root))
    problems.extend(_conf_sources(home))
    problems.extend(_broken_window_rule_matches(home))

    # Reuse the desktop_status engine for runtime checks (active config,
    # Hyprland responsiveness, Quickshell running, and OmaWhy shortcut).
    # This keeps scan and the status diagnostic consistent and avoids
    # duplicating the config / Hyprland / Quickshell checks below.
    base_status = desktop_status(home=home, omarchy_root=omarchy_root, check_command=check_command)
    for item in base_status.get("checks", []):
        if item["state"] == "warning":
            # desktop_status also reports the OmaWhy shortcut, which is not a
            # "problem" in the system scan — that check belongs to the pointed
            # desktop-status diagnostic, not to the broad scan.
            if item["label"] == _t("Atajo de OmaWhy", "OmaWhy shortcut"):
                continue
            problems.append({
                "severity": "warning",
                "title": item["label"],
                "detail": item["detail"],
                "path": "",
                "line": 0,
            })

    counts = {"error": 0, "warning": 0, "info": 0}
    for problem in problems:
        counts[problem["severity"]] = counts.get(problem["severity"], 0) + 1
    total = len(problems)
    message = (
        _t("No encontré problemas evidentes.", "I found no obvious problems.")
        if total == 0
        else _t(
            "Encontré " + str(total) + " problema" + ("s" if total != 1 else "") + " que revisar.",
            "I found " + str(total) + " problem" + ("s" if total != 1 else "") + " to review.",
        )
    )
    return {"summary": counts, "total": total, "problems": problems, "message": message}


def _atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def _snapshot(path):
    return {"path": str(path), "exists": path.exists(), "text": path.read_text(encoding="utf-8") if path.exists() else ""}


def _reload_hyprland():
    completed = subprocess.run(["hyprctl", "reload"], text=True, capture_output=True, check=False)
    if completed.returncode:
        raise RuntimeError(_t("Hyprland rechazó la recarga", "Hyprland rejected the reload").strip())


def remember_window(window, home=None, reload_hyprland=True):
    """Persist a scoped rule file, keeping an exact one-step undo snapshot."""
    home = Path(home or Path.home())
    hypr_dir = home / ".config" / "hypr"
    lua_config = hypr_dir / "hyprland.lua"
    using_lua = lua_config.exists()
    config_file = lua_config if using_lua else hypr_dir / "apps.conf"
    rules_file = hypr_dir / "omawhy.lua" if using_lua else hypr_dir / "apps" / "omawhy.conf"
    state_dir = home / ".local" / "state" / "omawhy"
    state_file = state_dir / "last-change.json"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = state_dir / "backups" / stamp
    backup_dir.mkdir(parents=True, exist_ok=True)

    snapshots = [_snapshot(config_file), _snapshot(rules_file)]
    for snapshot in snapshots:
        if snapshot["exists"]:
            source = Path(snapshot["path"])
            shutil.copy2(source, backup_dir / source.name)
    _atomic_write(state_file, json.dumps({"snapshots": snapshots}, ensure_ascii=False))

    source_line = 'require("hypr.omawhy")' if using_lua else "source = " + str(rules_file)
    current_config = snapshots[0]["text"]
    if source_line not in current_config.splitlines():
        _atomic_write(config_file, current_config.rstrip("\n") + "\n" + source_line + "\n")

    token = hashlib.sha256(str(window.get("identifier") or "").encode("utf-8")).hexdigest()[:12]
    start = ("-- >>> OmaWhy " if using_lua else "# >>> OmaWhy ") + token
    end = ("-- <<< OmaWhy " if using_lua else "# <<< OmaWhy ") + token
    current_rules = snapshots[1]["text"]
    rule_lines = [build_remembered_lua_rule(window)] if using_lua else build_remembered_rules(window)
    section = start + "\n" + "\n".join(rule_lines) + "\n" + end + "\n"
    existing = re.compile(re.escape(start) + r"\n.*?" + re.escape(end) + r"\n?", re.DOTALL)
    _atomic_write(rules_file, existing.sub(section, current_rules) if existing.search(current_rules) else current_rules.rstrip("\n") + ("\n\n" if current_rules else "") + section)

    if reload_hyprland:
        _reload_hyprland()
    return {"rules_file": rules_file, "backup": backup_dir}


def undo_last_change(home=None, reload_hyprland=True):
    """Restore exactly the two files changed by the most recent Remember action."""
    home = Path(home or Path.home())
    state_file = home / ".local" / "state" / "omawhy" / "last-change.json"
    if not state_file.exists():
        return False
    state = json.loads(state_file.read_text(encoding="utf-8"))
    for snapshot in state.get("snapshots", []):
        path = Path(snapshot["path"])
        if snapshot.get("exists"):
            _atomic_write(path, snapshot.get("text", ""))
        elif path.exists():
            path.unlink()
    if reload_hyprland:
        _reload_hyprland()
    state_file.unlink()
    return True


def normalize_window(raw):
    """Normalize Hyprland's client JSON without inventing unavailable fields."""
    xwayland = bool(raw.get("xwayland", False))
    identifier = str(raw.get("class") or "")
    return {
        "address": str(raw.get("address") or ""),
        "app_id": "" if xwayland else identifier,
        "class": identifier if xwayland else "",
        "identifier": identifier,
        "identifier_kind": "class" if xwayland else "app_id",
        "title": str(raw.get("title") or ""),
        "workspace": int((raw.get("workspace") or {}).get("id") or 0),
        "monitor": raw.get("monitor", ""),
        "floating": bool(raw.get("floating", False)),
        "fullscreen": bool(raw.get("fullscreen", False)),
        "pinned": bool(raw.get("pinned", False)),
        "pid": int(raw.get("pid") or 0),
        "at": list(raw.get("at") or [0, 0]),
        "size": list(raw.get("size") or [0, 0]),
    }


def _hypr_json(subject):
    completed = subprocess.run(["hyprctl", "-j", subject], text=True, capture_output=True, check=False)
    if completed.returncode:
        raise RuntimeError(_t("hyprctl falló", "hyprctl failed"))
    return json.loads(completed.stdout)


def _emit(payload, exit_code=0):
    print(json.dumps(payload, ensure_ascii=False))
    return exit_code


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(description="OmaWhy helper")
    subcommands = parser.add_subparsers(dest="command", required=True)

    def _add_lang(p):
        p.add_argument("--lang", default="es", choices=["es", "en"])

    inspect_parser = subcommands.add_parser("inspect-at-cursor")
    _add_lang(inspect_parser)
    explain_parser = subcommands.add_parser("explain")
    _add_lang(explain_parser)
    explain_parser.add_argument("--window-json", required=True)
    shortcut_parser = subcommands.add_parser("shortcut")
    _add_lang(shortcut_parser)
    shortcut_parser.add_argument("--keys", required=True)
    desktop_parser = subcommands.add_parser("desktop-status")
    _add_lang(desktop_parser)
    scan_parser = subcommands.add_parser("scan")
    _add_lang(scan_parser)
    # "why" is an alias of "explain": it answers "why Omarchy did that?"
    # using the pointed window inspection (same as --window-json).
    why_parser = subcommands.add_parser("why")
    _add_lang(why_parser)
    why_parser.add_argument("--window-json", required=True)
    open_rule_parser = subcommands.add_parser("open-rule")
    _add_lang(open_rule_parser)
    open_rule_parser.add_argument("--path", required=True)
    action_parser = subcommands.add_parser("action")
    _add_lang(action_parser)
    action_parser.add_argument("action")
    action_parser.add_argument("--window-json", required=True)
    remember_parser = subcommands.add_parser("remember")
    _add_lang(remember_parser)
    remember_parser.add_argument("--window-json", required=True)
    undo_parser = subcommands.add_parser("undo")
    _add_lang(undo_parser)
    open_rules_parser = subcommands.add_parser("open-rules")
    _add_lang(open_rules_parser)
    copy_parser = subcommands.add_parser("copy-stdin")
    _add_lang(copy_parser)
    copy_parser.add_argument("--text", default="")

    args = parser.parse_args(argv)

    global LANG
    LANG = args.lang if args.lang in ("es", "en") else "es"

    try:
        if args.command == "copy-stdin":
            text = str(args.text or "")
            try:
                completed = subprocess.run(["wl-copy"], input=text, text=True, capture_output=True, check=False, timeout=10)
            except subprocess.TimeoutExpired:
                raise RuntimeError(_t("El portapapeles no respondió.", "The clipboard did not respond."))
            if completed.returncode:
                raise RuntimeError(_t("No pude usar el portapapeles.", "I could not use the clipboard."))
            return _emit({"ok": True, "message": _t("Copiado al portapapeles.", "Copied to the clipboard.")})
        if args.command == "inspect-at-cursor":
            window = inspect_window_at_cursor(_hypr_json("clients"), _hypr_json("cursorpos"), _hypr_json("monitors"))
            if window is None:
                return _emit({"ok": False, "error": _t("No hay una ventana bajo el cursor.", "There is no window under the cursor.")}, 1)
            return _emit({"ok": True, "window": window})
        if args.command == "explain" or args.command == "why":
            return _emit({"ok": True, "explanation": explain_window_rules(json.loads(args.window_json))})
        if args.command == "shortcut":
            return _emit({"ok": True, "diagnosis": diagnose_shortcut(args.keys)})
        if args.command == "desktop-status":
            return _emit({"ok": True, "status": desktop_status()})
        if args.command == "scan":
            return _emit({"ok": True, "scan": scan_problems()})
        if args.command == "open-rule":
            path = Path(args.path).expanduser().resolve()
            allowed = [Path.home() / ".config" / "hypr", Path(os.getenv("OMARCHY_PATH", "/usr/share/omarchy")) / "default" / "hypr"]
            if not any(path.is_relative_to(root.resolve()) for root in allowed) or not path.is_file():
                raise ValueError(_t("La regla no está en una ruta de configuración permitida.", "The rule is not in an allowed configuration path."))
            subprocess.Popen(["xdg-open", str(path)])
            return _emit({"ok": True, "message": _t("Archivo de regla abierto.", "Rule file opened.")})
        if args.command == "action":
            window = json.loads(args.window_json)
            current_workspace = _hypr_json("activeworkspace").get("id") if args.action == "move-current" else None
            completed = subprocess.run(action_command(args.action, window, current_workspace=current_workspace), text=True, capture_output=True, check=False)
            if completed.returncode:
                raise RuntimeError((completed.stderr or completed.stdout or _t("La acción falló", "The action failed")).strip())
            return _emit({"ok": True, "message": _t("Acción aplicada.", "Action applied.")})
        if args.command == "remember":
            result = remember_window(json.loads(args.window_json))
            return _emit({"ok": True, "message": _t("Regla guardada. Puedes deshacerla.", "Rule saved. You can undo it."), "rules_file": str(result["rules_file"])})
        if args.command == "undo":
            undone = undo_last_change()
            return _emit(
                {"ok": True, "message": _t("Cambio deshecho.", "Change undone.")}
                if undone
                else {"ok": False, "error": _t("No hay un cambio de OmaWhy para deshacer.", "There is no OmaWhy change to undo.")},
                0 if undone else 1,
            )
        hypr_dir = Path.home() / ".config" / "hypr"
        rules_file = hypr_dir / "omawhy.lua" if (hypr_dir / "hyprland.lua").exists() else hypr_dir / "apps" / "omawhy.conf"
        subprocess.Popen(["xdg-open", str(rules_file)])
        return _emit({"ok": True, "message": _t("Archivo de reglas abierto.", "Rules file opened.")})
    except (ValueError, RuntimeError, json.JSONDecodeError) as error:
        return _emit({"ok": False, "error": str(error)}, 1)


if __name__ == "__main__":
    raise SystemExit(main())
