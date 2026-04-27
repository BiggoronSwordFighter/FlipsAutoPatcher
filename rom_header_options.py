#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ROM Header Options UI helpers for Flips Auto Patcher.

This module owns the popup UI for the "ROM Header Options" button and keeps the
selection rules centralized so they do not regress.

IMPORTANT MAINTAINER NOTES
--------------------------
These controls intentionally behave as TWO independent checkbox groups with
radio-style exclusivity.

Group 1 (NES):
  1) Remove iNES header from output.
  2) Add iNES copier header to output.
  3) Remove iNES header temporarily before restoring it to output. (automate)

Group 2 (SNES):
  4) Remove SNES copier header from output.
  5) Add SNES copier header to output.
  6) Remove SNES copier header temporarily before adding copier header to output. (automate)

Behavior that MUST stay true:
- Each group allows ONE selected option at a time.
- Each group also allows NONE selected. Default startup state is NONE selected.
- Clicking an already-selected option turns it back OFF.
- The actual patching/output log messages still go to the MAIN Info/Output box
  through app.log_message(...). This popup is only the selector UI.
- Options 1/2/4/5 are direct single-ROM actions.
- Options 3/6 are the automatic temporary-header workflows used by Auto Patch
  Files and Bulk Patching.
"""

from __future__ import annotations

import tkinter as tk


NES_REMOVE = 1
NES_ADD = 2
NES_TEMP = 3
SNES_REMOVE = 4
SNES_ADD = 5
SNES_TEMP = 6


def reset_header_option_defaults(app) -> None:
    """Force all six header options OFF."""
    for name in (
        "remove_ines_header",
        "add_ines_header",
        "temp_remove_ines_header",
        "remove_snes_header",
        "add_snes_header",
        "temp_remove_snes_header",
    ):
        try:
            getattr(app, name).set(False)
        except Exception:
            pass


def _get_group_value_from_flags(app, group: str) -> int:
    """Translate the app BooleanVars into the popup selection."""
    try:
        if group == "nes":
            if bool(app.remove_ines_header.get()):
                return NES_REMOVE
            if bool(app.add_ines_header.get()):
                return NES_ADD
            if bool(app.temp_remove_ines_header.get()):
                return NES_TEMP
            return 0
        if bool(app.remove_snes_header.get()):
            return SNES_REMOVE
        if bool(app.add_snes_header.get()):
            return SNES_ADD
        if bool(app.temp_remove_snes_header.get()):
            return SNES_TEMP
    except Exception:
        pass
    return 0


def _apply_group_value_to_flags(app, group: str, selected_value: int) -> None:
    """Write one group's selection back into the app BooleanVars.

    This is the core rule that must never break:
    - one active flag at a time per group
    - or all off for that group
    """
    if group == "nes":
        app.remove_ines_header.set(selected_value == NES_REMOVE)
        app.add_ines_header.set(selected_value == NES_ADD)
        app.temp_remove_ines_header.set(selected_value == NES_TEMP)
        return

    app.remove_snes_header.set(selected_value == SNES_REMOVE)
    app.add_snes_header.set(selected_value == SNES_ADD)
    app.temp_remove_snes_header.set(selected_value == SNES_TEMP)


def _log_header_option_selection(app) -> None:
    """Show the current ROM Header Options state in the main Info/Output box."""
    try:
        messages = []
        if bool(app.remove_ines_header.get()):
            messages.append("ROM Header Options → NES: Remove iNES header from output.")
        elif bool(app.add_ines_header.get()):
            messages.append("ROM Header Options → NES: Add iNES copier header to output.")
        elif bool(app.temp_remove_ines_header.get()):
            messages.append("ROM Header Options → NES: Remove iNES header temporarily before restoring it to output. (automate)")
        else:
            messages.append("ROM Header Options → NES: none selected.")

        if bool(app.remove_snes_header.get()):
            messages.append("ROM Header Options → SNES: Remove SNES copier header from output.")
        elif bool(app.add_snes_header.get()):
            messages.append("ROM Header Options → SNES: Add SNES copier header to output.")
        elif bool(app.temp_remove_snes_header.get()):
            messages.append("ROM Header Options → SNES: Remove SNES copier header temporarily before adding copier header to output. (automate)")
        else:
            messages.append("ROM Header Options → SNES: none selected.")

        for msg in messages:
            app.log_message(msg)
    except Exception:
        pass


def open_rom_header_options(app):
    """Open the ROM Header Options popup.

    The popup uses square checkboxes, but each group still behaves like a radio
    group with an allowed NONE state:
    - checking one option clears the others in the same group
    - clicking the active option again turns it off
    """
    existing = getattr(app, "rom_header_options_window", None)
    if existing is not None:
        try:
            if existing.winfo_exists():
                existing.deiconify()
                existing.lift()
                existing.focus_force()
                _log_header_option_selection(app)
                return
        except Exception:
            pass

    win = tk.Toplevel(app.root)
    app.rom_header_options_window = win
    win.title("ROM Header Options")
    win.resizable(False, False)
    try:
        if getattr(app, "icon_path", None):
            win.iconbitmap(app.icon_path)
    except Exception:
        pass
    win.transient(app.root)

    def _on_close():
        try:
            win.destroy()
        finally:
            app.rom_header_options_window = None

    win.protocol("WM_DELETE_WINDOW", _on_close)

    frame = tk.Frame(win, padx=12, pady=12)
    frame.pack(fill="both", expand=True)

    tk.Label(
        frame,
        text="Choose output header actions and optional temporary patch-input header handling.",
        anchor="w",
        justify=tk.LEFT,
    ).pack(anchor="w", pady=(0, 4))

    tk.Label(
        frame,
        text="Auto options work for \"Bulk Patching\" and \"Auto Patch files\".",
        anchor="w",
        justify=tk.LEFT,
    ).pack(anchor="w", pady=(0, 8))

    nes_choice = tk.IntVar(value=_get_group_value_from_flags(app, "nes"))
    snes_choice = tk.IntVar(value=_get_group_value_from_flags(app, "snes"))

    nes_remove_var = tk.BooleanVar(value=nes_choice.get() == NES_REMOVE)
    nes_add_var = tk.BooleanVar(value=nes_choice.get() == NES_ADD)
    nes_temp_var = tk.BooleanVar(value=nes_choice.get() == NES_TEMP)

    snes_remove_var = tk.BooleanVar(value=snes_choice.get() == SNES_REMOVE)
    snes_add_var = tk.BooleanVar(value=snes_choice.get() == SNES_ADD)
    snes_temp_var = tk.BooleanVar(value=snes_choice.get() == SNES_TEMP)

    group_vars = {
        "nes": {
            NES_REMOVE: nes_remove_var,
            NES_ADD: nes_add_var,
            NES_TEMP: nes_temp_var,
        },
        "snes": {
            SNES_REMOVE: snes_remove_var,
            SNES_ADD: snes_add_var,
            SNES_TEMP: snes_temp_var,
        },
    }

    group_choice_vars = {
        "nes": nes_choice,
        "snes": snes_choice,
    }

    def _set_group_selection(group: str, selected_value: int) -> None:
        choice_var = group_choice_vars[group]
        if int(choice_var.get() or 0) == selected_value:
            choice_var.set(0)
        else:
            choice_var.set(selected_value)

        current = int(choice_var.get() or 0)
        for option_value, bool_var in group_vars[group].items():
            bool_var.set(option_value == current)

        _apply_group_value_to_flags(app, group, current)
        _log_header_option_selection(app)

    nes_box = tk.LabelFrame(frame, text="NES Header Options (.nes)", padx=10, pady=8)
    nes_box.pack(fill="x", expand=True, pady=(0, 10))

    tk.Checkbutton(
        nes_box,
        text="Remove iNES header from output.",
        variable=nes_remove_var,
        command=lambda: _set_group_selection("nes", NES_REMOVE),
    ).pack(anchor="w", pady=2)
    tk.Checkbutton(
        nes_box,
        text="Restore iNES header to output.",
        variable=nes_add_var,
        command=lambda: _set_group_selection("nes", NES_ADD),
    ).pack(anchor="w", pady=2)
    tk.Checkbutton(
        nes_box,
        text="Remove iNES header temporarily before restoring it to output. (automate)",
        variable=nes_temp_var,
        command=lambda: _set_group_selection("nes", NES_TEMP),
    ).pack(anchor="w", pady=2)

    sep = tk.Frame(frame, height=2, bd=1, relief="sunken")
    sep.pack(fill="x", pady=(0, 10))

    snes_box = tk.LabelFrame(frame, text="SNES Header Options (.sfc/.smc/.swc/.fig)", padx=10, pady=8)
    snes_box.pack(fill="x", expand=True, pady=(0, 10))

    tk.Checkbutton(
        snes_box,
        text="Remove SNES header from output.",
        variable=snes_remove_var,
        command=lambda: _set_group_selection("snes", SNES_REMOVE),
    ).pack(anchor="w", pady=2)
    tk.Checkbutton(
        snes_box,
        text="Add SNES copier header to output.",
        variable=snes_add_var,
        command=lambda: _set_group_selection("snes", SNES_ADD),
    ).pack(anchor="w", pady=2)
    tk.Checkbutton(
        snes_box,
        text="Remove SNES header temporarily before adding copier header to output. (automate)",
        variable=snes_temp_var,
        command=lambda: _set_group_selection("snes", SNES_TEMP),
    ).pack(anchor="w", pady=2)

    close_btn = tk.Button(frame, text="Close", command=_on_close, width=12)
    close_btn.pack(anchor="e", pady=(0, 0))

    _log_header_option_selection(app)
