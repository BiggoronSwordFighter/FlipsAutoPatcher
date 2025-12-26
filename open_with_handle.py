"""
open_with_handle.py
-------------------
Small helper module that isolates “Open with” code logic.

- When you right‑click a file and choose “Open with Flips Auto Patcher”,
  this open_with_handle.py file receives that pre-selected file path on startup (in sys.argv).
- This module decides what that file is (patch vs ROM) to kick off with the right dialogue window:
  • If it’s a .bps/.ips → ask for the Base ROM and apply the patch.
  • If it’s a ROM       → ask if it’s the Base ROM or Modified ROM, then create a patch.

How it integrates with the app:
-  This file passes the top‑level GUI app instance into OpenWithHandler(app, icon_path).
-  The handler calls back into the app to reuse its existing methods: logging, file pickers,
-  hash display, patch creation/application, etc.
"""
from __future__ import annotations
import os
import tkinter as tk
from tkinter import filedialog

class OpenWithHandler:
    """ This class encapsulates "Open with …" behavior.

        The main GUI application (main.py) must provide these parameters:
        - update_patch_method(str)
        - display_patch_metadata(path), display_base_rom_hashes(), display_modified_rom_hashes(path)
        - file_search_rom(title_override: str|None = None, info_message: str|None = None)
        - log_message(str)
        - create_patches(), apply_patches()
        - root (tk.Tk), bps_ips_type (tk.StringVar), select_file_button (tk.Menubutton)
        - base_rom (str|None), modified_rom (list[str]|None), patch_files (list[str])
        - search_scope (tk.StringVar)
    """

    # Coordinates startup file routing.
    # The path to the window icon is "icon_path : str|None", which is used by the small dialogs that pop up.

    def __init__(self, app, icon_path: str | None):
        self.app = app
        self.icon_path = icon_path

    # -------------------- Public entry point --------------------
    def handle_startup_file(self, file_path: str):
        # Respond to OS 'Open with' action (when the user double-clicks or uses context menu).
        ext = os.path.splitext(file_path)[1].lower()
        patch_exts = {".bps", ".ips"}
        rom_exts = {".nes", ".sfc", ".smc", ".gba", ".gbc", ".gen", ".md", ".bin", ".rom",
                    ".z64", ".n64", ".v64", ".sms", ".pce"}

        if ext in patch_exts:
            self._start_patch_flow_with_preselected_patch(file_path, ext)
        elif ext in rom_exts:
            self._ask_base_or_modified(file_path)  # is it Base or Modified?
        else:
            self._ask_rom_or_patch(file_path)      # unknown → ask ROM vs Patch

    # ------------------------ Internals -------------------------
    def _start_patch_flow_with_preselected_patch(self, patch_path: str, ext: str):
        app = self.app
        app.update_patch_method("Auto Patch Files")
        app.bps_ips_type.set(ext)
        try:
            app.select_file_button.config(text=ext.upper())
        except Exception:
            pass

        app.patch_files = [os.path.abspath(patch_path)]
        app.log_message(f"Opened with Patch File: {os.path.basename(patch_path)}")
        try:
            app.display_patch_metadata(patch_path)
        except Exception:
            pass

        app.log_message("Select the base ROM file.")
        app.file_search_rom(info_message=None)
        if not app.base_rom:
            return

        app.log_message("Patching process has started.")
        from threading import Thread
        Thread(target=app.apply_patches, daemon=True).start()

    def _start_create_flow_with_preselected_base_rom(self, base_path: str):
        app = self.app
        app.update_patch_method("Auto Create Patches")
        app.base_rom = os.path.abspath(base_path)
        app.log_message(f"Opened with Base ROM file: {os.path.basename(base_path)}")
        try:
            app.display_base_rom_hashes()
        except Exception:
            pass

        app.log_message("Select the modified ROM(s).")
        modified = filedialog.askopenfilenames(
            title="Select The Modified ROM",
            filetypes=app.rom_file_types
        )
        if not modified:
            app.log_message("No Modified ROM file selected.")
            return

        # Expand per current search_scope.
        try:
            scope = app.search_scope.get()
            base_dir = os.path.dirname(os.path.abspath(modified[0]))
            rom_exts = (".nes", ".sfc", ".smc", ".gba", ".gbc", ".gen", ".md", ".bin",
                        ".rom", ".z64", ".n64", ".v64", ".sms", ".pce")
            collected = []
            abs_base = os.path.abspath(app.base_rom)
            if scope == "enable":
                for root, _, files in os.walk(base_dir):
                    for fname in files:
                        full = os.path.abspath(os.path.join(root, fname))
                        if full.lower().endswith(rom_exts) and full != abs_base:
                            collected.append(full)
            elif scope == "directory":
                try:
                    for fname in os.listdir(base_dir):
                        full = os.path.abspath(os.path.join(base_dir, fname))
                        if os.path.isfile(full) and full.lower().endswith(rom_exts) and full != abs_base:
                            collected.append(full)
                except Exception:
                    pass
            original = list(modified)
            seen = set(os.path.abspath(x) for x in original)
            for f in collected:
                if os.path.abspath(f) not in seen:
                    original.append(f)
                    seen.add(os.path.abspath(f))
            app.modified_rom = original
        except Exception as e:
            app.log_message(f"Search expansion error: {e}")
            app.modified_rom = list(modified)

        # Ignore if base modified ROM are the same.
        abs_base = os.path.abspath(app.base_rom)
        cleaned = []
        seen = set()
        for _p in app.modified_rom:
            ap = os.path.abspath(_p)
            if ap == abs_base:
                app.log_message("Error: Base ROM and Modified ROM cannot be the same file. Ignoring this one.")
                continue
            if ap in seen:
                continue
            cleaned.append(_p)
            seen.add(ap)
        app.modified_rom = cleaned
        if not app.modified_rom:
            app.log_message("No Modified ROM file selected.")
            return

        for rom in app.modified_rom:
            app.log_message(f"Select the Modified ROM file: {os.path.basename(rom)}")
            try:
                app.display_modified_rom_hashes(rom)
            except Exception:
                pass

        app.log_message("Patch creation process has started.")
        app.log_message("Note: for Nintendo 64 ROMs this will take time.")
        from threading import Thread
        Thread(target=app.create_patches, daemon=True).start()

    def _start_create_flow_with_preselected_modified_rom(self, mod_path: str):
        app = self.app
        app.update_patch_method("Auto Create Patches")

        app.modified_rom = [os.path.abspath(mod_path)]
        app.log_message(f"Opened with Modified ROM file: {os.path.basename(mod_path)}")
        try:
            app.display_modified_rom_hashes(mod_path)
        except Exception:
            pass

        app.file_search_rom(title_override="Select The Base ROM file", info_message="Select the Base ROM file.")
        if not app.base_rom:
            return

        app.log_message("Patch creation process has started.")
        app.log_message("Note: for Nintendo 64 ROMs this will take time.")
        from threading import Thread
        Thread(target=app.create_patches, daemon=True).start()

    # First Open-With dialog window.
    def _ask_rom_or_patch(self, file_path: str):
        app = self.app
        dlg = tk.Toplevel(app.root)
        dlg.title("Is this file a ROM or Patch?")
        try:
            if self.icon_path: dlg.iconbitmap(self.icon_path)
        except Exception: pass
        dlg.transient(app.root)
        dlg.grab_set()

        tk.Label(
            dlg,
            text=("Is the file a ROM or a Patch?\n\n"
                  "Choose “ROM” to create a patch (you'll select Modified ROMs next),\n"
                  "or “Patch” to apply a patch (you'll select the Base ROM next)."),
            justify="left", padx=14, pady=10
        ).pack(anchor="w")

        btns = tk.Frame(dlg); btns.pack(pady=(6, 10))

        def _choose_rom():
            try: dlg.destroy()
            finally: self._ask_base_or_modified(file_path)

        def _choose_patch():
            try: dlg.destroy()
            finally: self._start_patch_flow_with_preselected_patch(file_path, ".bps")

        def _on_close():
            try: dlg.destroy()
            finally: app.log_message("No valid ROM or Patch file selected.")

        tk.Button(btns, text="ROM", width=12, command=_choose_rom).pack(side="left", padx=6)
        tk.Button(btns, text="Patch", width=12, command=_choose_patch).pack(side="left", padx=6)
        dlg.protocol("WM_DELETE_WINDOW", _on_close)

        try:
            app.root.update_idletasks()
            x = app.root.winfo_rootx() + 60
            y = app.root.winfo_rooty() + 60
            dlg.geometry(f"+{x}+{y}")
        except Exception:
            pass

    # Second Open-With dialog window.
    def _ask_base_or_modified(self, file_path: str):
        app = self.app
        dlg = tk.Toplevel(app.root)
        dlg.title("Is this file a Base ROM or a Modified ROM?")
        try:
            if self.icon_path: dlg.iconbitmap(self.icon_path)
        except Exception: pass
        dlg.transient(app.root)
        dlg.grab_set()

        tk.Label(dlg, text="Is this file a Base ROM or a Modified ROM?", justify="left",
                 padx=14, pady=10).pack(anchor="w")

        btns = tk.Frame(dlg); btns.pack(pady=(6, 10))

        def _choose_base():
            try: dlg.destroy()
            finally: self._start_create_flow_with_preselected_base_rom(file_path)

        def _choose_modified():
            try: dlg.destroy()
            finally: self._start_create_flow_with_preselected_modified_rom(file_path)

        def _on_close():
            try: dlg.destroy()
            finally: app.log_message("No action or change occured.")

        tk.Button(btns, text="Base ROM", width=12, command=_choose_base).pack(side="left", padx=6)
        tk.Button(btns, text="Modified ROM", width=12, command=_choose_modified).pack(side="left", padx=6)
        dlg.protocol("WM_DELETE_WINDOW", _on_close)

        try:
            app.root.update_idletasks()
            x = app.root.winfo_rootx() + 60
            y = app.root.winfo_rooty() + 60
            dlg.geometry(f"+{x}+{y}")
        except Exception:
            pass
