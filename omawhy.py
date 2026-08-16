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


def _matcher(window):
    identifier = str(window.get("identifier") or "")
    if not identifier:
        raise ValueError("La ventana no expone app_id/class; no es seguro crear una regla.")
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


def action_command(action, window):
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
        raise ValueError("La ventana no tiene dirección Hyprland.")
    selector = "address:" + address
    dispatches = {
        "move-current": ["movetoworkspace", "current," + selector],
        "center": ["centerwindow", selector],
        "toggle-floating": ["togglefloating", selector],
        "toggle-fullscreen": ["fullscreen", "0," + selector],
        "toggle-pin": ["pin", selector],
    }
    if action not in dispatches:
        raise ValueError("Acción no reconocida: " + action)
    return ["hyprctl", "dispatch", *dispatches[action]]


def inspect_window_at_cursor(clients, cursor, monitors):
    """Pick and normalize the client under the pointer using Hyprland data."""
    raw = window_at_cursor(clients, cursor.get("x", -1), cursor.get("y", -1))
    if raw is None:
        return None
    window = normalize_window(raw)
    monitor_names = {monitor.get("id"): monitor.get("name") for monitor in monitors}
    window["monitor"] = monitor_names.get(raw.get("monitor"), str(raw.get("monitor") or ""))
    return window


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
        raise RuntimeError((completed.stderr or completed.stdout or "Hyprland rechazó la recarga").strip())


def remember_window(window, home=None, reload_hyprland=True):
    """Persist a scoped rule file, keeping an exact one-step undo snapshot."""
    home = Path(home or Path.home())
    hypr_dir = home / ".config" / "hypr"
    apps_file = hypr_dir / "apps.conf"
    rules_file = hypr_dir / "apps" / "omawhy.conf"
    state_dir = home / ".local" / "state" / "omawhy"
    state_file = state_dir / "last-change.json"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = state_dir / "backups" / stamp
    backup_dir.mkdir(parents=True, exist_ok=True)

    snapshots = [_snapshot(apps_file), _snapshot(rules_file)]
    for snapshot in snapshots:
        if snapshot["exists"]:
            source = Path(snapshot["path"])
            shutil.copy2(source, backup_dir / source.name)
    _atomic_write(state_file, json.dumps({"snapshots": snapshots}, ensure_ascii=False))

    source_line = "source = " + str(rules_file)
    current_apps = snapshots[0]["text"]
    if source_line not in current_apps.splitlines():
        _atomic_write(apps_file, current_apps.rstrip("\n") + "\n" + source_line + "\n")

    token = hashlib.sha256(str(window.get("identifier") or "").encode("utf-8")).hexdigest()[:12]
    start = "# >>> OmaWhy " + token
    end = "# <<< OmaWhy " + token
    current_rules = snapshots[1]["text"]
    section = start + "\n" + "\n".join(build_remembered_rules(window)) + "\n" + end + "\n"
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
        raise RuntimeError((completed.stderr or completed.stdout or "hyprctl falló").strip())
    return json.loads(completed.stdout)


def _emit(payload, exit_code=0):
    print(json.dumps(payload, ensure_ascii=False))
    return exit_code


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(description="OmaWhy helper")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("inspect-at-cursor")
    window_parser = subcommands.add_parser("action")
    window_parser.add_argument("action")
    window_parser.add_argument("--window-json", required=True)
    remember_parser = subcommands.add_parser("remember")
    remember_parser.add_argument("--window-json", required=True)
    subcommands.add_parser("undo")
    subcommands.add_parser("open-rules")
    args = parser.parse_args(argv)

    try:
        if args.command == "inspect-at-cursor":
            window = inspect_window_at_cursor(_hypr_json("clients"), _hypr_json("cursorpos"), _hypr_json("monitors"))
            if window is None:
                return _emit({"ok": False, "error": "No hay una ventana bajo el cursor."}, 1)
            return _emit({"ok": True, "window": window})
        if args.command == "action":
            window = json.loads(args.window_json)
            completed = subprocess.run(action_command(args.action, window), text=True, capture_output=True, check=False)
            if completed.returncode:
                raise RuntimeError((completed.stderr or completed.stdout or "La acción falló").strip())
            return _emit({"ok": True, "message": "Acción aplicada."})
        if args.command == "remember":
            result = remember_window(json.loads(args.window_json))
            return _emit({"ok": True, "message": "Regla guardada. Puedes deshacerla.", "rules_file": str(result["rules_file"])})
        if args.command == "undo":
            undone = undo_last_change()
            return _emit(
                {"ok": True, "message": "Cambio deshecho."}
                if undone
                else {"ok": False, "error": "No hay un cambio de OmaWhy para deshacer."},
                0 if undone else 1,
            )
        rules_file = Path.home() / ".config" / "hypr" / "apps" / "omawhy.conf"
        subprocess.Popen(["xdg-open", str(rules_file)])
        return _emit({"ok": True, "message": "Archivo de reglas abierto."})
    except (ValueError, RuntimeError, json.JSONDecodeError) as error:
        return _emit({"ok": False, "error": str(error)}, 1)


if __name__ == "__main__":
    raise SystemExit(main())
