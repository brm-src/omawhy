# OmaWhy

**Make Hyprland window rules visible, then fix them without guessing.**

OmaWhy is an Omarchy Quattro service for anyone who has asked: *why did this window open here?*

Press `Super + Shift + I`, click a window, and get its real Hyprland identity and state. From the same overlay, copy a rule, correct the window, or save its current placement as a reversible rule.

## Install

```bash
omarchy plugin add https://github.com/brm-src/omawhy.git --enable --yes
~/.config/omarchy/plugins/io.github.brm-src.omawhy/setup.sh
```

The second command adds exactly one marked binding to `~/.config/hypr/bindings.conf` and reloads Hyprland:

```text
Super + Shift + I
```

It does not install packages, elevate permissions, access the network, or run automatically during `omarchy plugin add`.

## Use

1. Press `Super + Shift + I`.
2. Click the window you want to understand.
3. OmaWhy shows the actual identifier, title, workspace, monitor, floating/fullscreen/pinned state, PID, and Hyprland address.
4. Use a small action or choose **Recordar**.

### Actions

- Copy app ID, XWayland class, title, or the generated rule.
- Move the selected window to the current workspace.
- Center it.
- Toggle floating, fullscreen, or pinning.
- Open the OmaWhy rule file.
- Undo the most recent saved rule.

### Remember this position

Before writing anything, OmaWhy shows the selected window's workspace, monitor, floating state, and other live facts.

On confirmation it writes a dedicated file:

```text
~/.config/hypr/apps/omawhy.conf
```

and adds one `source = …` line to `~/.config/hypr/apps.conf` if it is missing. It creates a timestamped backup in:

```text
~/.local/state/omawhy/backups/
```

**Undo** restores both files exactly to their state before the last Remember action.

Rules use an anchored `match:class` identifier. In Hyprland this field is a Wayland `app_id` for native Wayland clients and an X11 class for XWayland clients. A remembered rule therefore applies to future windows with that same application identifier—not to an unverified title match. Edit `omawhy.conf` if you want a narrower rule.

## Remove

```bash
~/.config/omarchy/plugins/io.github.brm-src.omawhy/setup.sh --remove
omarchy plugin remove io.github.brm-src.omawhy --yes
```

The first command removes only OmaWhy's marked hotkey block; it leaves the rest of your bindings alone.

## Requirements

- Omarchy Quattro
- Hyprland
- `python3`, `hyprctl`, and `wl-copy` (present on standard Omarchy installs)

No API keys, account, background service, external server, or telemetry.

## Development checks

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile omawhy.py
qmllint -I /usr/share/omarchy/shell OmaWhy.qml
omarchy plugin validate .
```

## License

MIT
