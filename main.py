#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================= Flips Auto Patcher (GUI) =============================

• What this tool mainly does
  - “Auto Patch Files” → multiple applies existing patch files (.bps / .ips) to a Base ROM.
  - “Auto Create Patches” → creates multiple patch files by comparing a Base ROM with a Modified ROM.

• Required files for usage:
  - Base ROM: the original, unmodified game ROM (your “clean” file).
  - Modified ROM: the edited/changed ROM (the one that differs from the Base ROM).
  - Patch (.bps / .ips): a tiny file that stores the differences between a Base ROM and a Modified ROM.

• How the main UI buttons are arranged:
  Row 1 (left→right): Mode menu → .BPS/.IPS menu → Start → Clear → Reset → Load Config → Save Config
  Row 2 (left→right): Force to Patch → Append “_patched” → Expanded file search menu

• Code sections (glossary):
  1) SECTION A – Imports & paths
  2) SECTION B – Tooltip helper (small class for hover help)
  3) SECTION C – AutoPatcherApp (the main GUI app)
     C1) GUI build (buttons, menus, and help text)
     C2) Config save/load
     C3) Core operations (create_patches, apply_patches)
     C4) Utilities (logging, selection, metadata/hashes)
     C5) Start button logic (file pickers + background threads)
     C6) Utility helpers – moved to a separate module `utils.py`(what each helper does):
         - calculate_crc32(path) → returns a short checksum (hex) used by many patches to confirm the correct Base ROM.
         - calculate_md5(path) / calculate_sha1(path) → longer fingerprints used for verification.
         - calculate_zle_hash(path) → reads a small ROM header region (bytes 16..27) and formats it as hex; shown for reference.
         - get_patch_metadata(path) → for .bps files, reads the stored Source/Target CRC32 (and also reports hashes of the patch file itself).
     C7) “Open with …” helpers – moved to a separate module `open_with_handle.py`
         - update_patch_method(str)
         - display_patch_metadata(path), display_base_rom_hashes(), display_modified_rom_hashes(path)
         - file_search_rom(title_override: str|None = None, info_message: str|None = None)
         - log_message(str)
         - create_patches(), apply_patches()
         - root (tk.Tk), bps_ips_type (tk.StringVar), select_file_button (tk.Menubutton)
         - base_rom (str|None), modified_rom (list[str]|None), patch_files (list[str])
         - search_scope (tk.StringVar)
  4) SECTION D – Program start (the normal Python “if __name__ == '__main__':” block)

Everything is wrapped with big banners:  ===== START [name] ===== / ===== END [name] =====
So you can visually see where a section begins and where it ends.
====================================================================================
"""

# ===== START SECTION A: Imports & Paths ==========================================
import os
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, Menubutton, Menu, messagebox
from tkinter.scrolledtext import ScrolledText
from threading import Thread
import json

# Import "Open with …" logic (open_with_handle.py).
from open_with_handle import OpenWithHandler

# Import utility functions (utils.py).
# These helpers compute hashes (CRC32, MD5, SHA1, ZLE) and read .bps metadata.
from utils import calculate_crc32, calculate_md5, calculate_sha1, calculate_zle_hash, get_patch_metadata

# Determine where we are running (bundled EXE vs plain Python script).
script_dir = os.getcwd()  # default/fallback

if getattr(sys, 'frozen', False):  # True when running as a bundled EXE.
    flips_exe_path = os.path.join(script_dir, 'flips', 'flips.exe')
else:  # Running as a normal .py
    flips_exe_path = os.path.join(script_dir, 'flips.exe')

# If not found, try an alternative location (…/flips/flips.exe). Crash early if still missing.
if not os.path.exists(flips_exe_path):
    flips_exe_path = os.path.join(script_dir, 'flips', 'flips.exe')
    if not os.path.exists(flips_exe_path):
        raise FileNotFoundError("flips.exe is not found. Place it next to the app or in a 'flips' folder.")

# Icon: check both ./ico/flips.ico (compiled EXE) and ./flips.ico (Python script), either is acceptable.
icon_path = None
main_icon_path = os.path.join(script_dir, 'ico', 'flips.ico')
if os.path.exists(main_icon_path):
    icon_path = main_icon_path
else:
    alt_icon_path = os.path.join(script_dir, 'flips.ico')
    if os.path.exists(alt_icon_path):
        icon_path = alt_icon_path
# ===== END SECTION A: Imports & Paths ============================================


# ===== START SECTION B: Tooltip helper ===========================================
class ToolTip:
    """Very small helper that shows a tooltip when you hover a widget.

    You create this with: ToolTip(widget, "your text")
    The rest happens automatically.
    """
    def __init__(self, widget, text, delay=500, wraplength=420):
        self.widget = widget
        self.text = text
        self.delay = delay
        self.wraplength = wraplength
        self._after_id = None  # scheduled timer id
        self._tip = None       # the Toplevel window we show
        widget.bind("<Enter>", self._schedule)
        widget.bind("<Leave>", self._hide)
        widget.bind("<ButtonPress>", self._hide)

    def _schedule(self, event=None):
        # Wait a bit so we don't spam the user with instant popups.
        self._cancel()
        self._after_id = self.widget.after(self.delay, self._show)

    def _cancel(self):
        # cancel any pending tooltip show.
        if self._after_id:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _show(self):
        # Create a small always-on-top window near the widget.
        if self._tip or not self.text:
            return
        try:
            x = self.widget.winfo_rootx() + 20
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 10
        except Exception:
            return
        self._tip = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            tw, text=self.text, justify=tk.LEFT, relief=tk.SOLID, borderwidth=1,
            background="#ffffe0", wraplength=self.wraplength
        )
        label.pack(ipadx=6, ipady=4)

    def _hide(self, event=None):
        # Destroy the tooltip window if shown.
        self._cancel()
        if self._tip:
            try:
                self._tip.destroy()
            except Exception:
                pass
            self._tip = None


def add_tooltip(widget, text, delay=500):
    """Helper wrapper so text reads nicely where it’s used."""
    try:
        ToolTip(widget, text, delay=delay)
    except Exception:
        pass
# ===== END SECTION B: Tooltip helper =============================================


# ===== START SECTION C: Main Application Class ===================================
class AutoPatcherApp:

    """Main GUI application.

    This class builds the window, holds the current settings (mode, patch type,
    options), and implements the two workflows:
      • apply_patches()  – Auto Patch Files
      • create_patch()   – Auto Create Patches
    """

    # ----- START C1: GUI build ---------------------------------------------------
    def __init__(self, root):
        """ Small styling helper so buttons look consistent."""
        def _uniform_button(self, w):
            try:
                w.configure(relief=tk.RAISED, borderwidth=1, highlightthickness=0)
            except Exception:
                pass

        self.root = root
        """Helper that holds all "Open with …" behavior (open_with_handle.py)."""
        self.open_with = OpenWithHandler(self, icon_path)

        # Current selections / options (keep as attributes so all methods can read them).
        self.base_rom = None            # path to the chosen Base ROM.
        self.modified_rom = None        # tuple/list of Modified ROM paths.
        self.patch_files = []           # list of .bps/.ips paths.
        self.patch_folder = None        # (unused in current UI but kept for clarity).
        self.force_patch = tk.BooleanVar()
        self.patch_method = tk.StringVar(value="Auto Patch Files")  # mode
        self.bps_ips_type = tk.StringVar(value=".bps")              # .bps or .ips
        self.selection_mode = tk.StringVar(value="files")           # reserved for future UI

        # Set app icon if available.
        try:
            if icon_path:
                root.iconbitmap(icon_path)
        except tk.TclError:
            # non-Windows platforms or missing icon.
            pass

        # Expose the styling helper.
        self._uniform_button = _uniform_button.__get__(self, AutoPatcherApp)

        # File type filters for ROM pickers.
        self.rom_file_types = [
            ("Common ROM Extensions", "*.nes *.sfc *.smc *.gba *.gbc *.gen *.md *.bin *.rom *.z64 *.n64 *.v64 *.sms *.pce"),
            ("All Files", "*.*")
        ]

        # ------------------- Window skeleton -------------------
        root.title("Flips Auto Patcher V1.3.2")
        root.geometry("1200x560")

        # Info/Output area (top big text box).
        output_frame = tk.Frame(root)
        output_frame.pack(fill='both', expand=True, padx=20, pady=(10, 0))

        self.output_label = tk.Label(output_frame, text="Info/Output:", anchor='w')
        self.output_label.pack(anchor='nw', padx=5)

        self.console_output = ScrolledText(output_frame, height=15, width=100, state='disabled', wrap=tk.WORD)
        self.console_output.pack(fill='both', expand=True, padx=5)

        # Controls area.
        control_area = tk.Frame(root)
        control_area.pack(fill='x', padx=20, pady=(6, 12))

        # Row 1 – main actions.
        ctrl_row = tk.Frame(control_area)
        ctrl_row.pack(fill='x')

        # Row 2 – options.
        opts_row = tk.Frame(control_area)
        opts_row.pack(fill='x', pady=(6, 0))

        # --------------- Row 1 widgets ---------------
        # Mode menu (Auto Patch Files / Auto Create Patches).
        self.patch_method_button = Menubutton(ctrl_row, text="Auto Patch Files", relief=tk.RAISED)
        self._uniform_button(self.patch_method_button)
        self.patch_method_menu = Menu(self.patch_method_button, tearoff=0)
        self.patch_method_menu.add_command(label="Auto Patch Files", command=lambda: self.update_patch_method("Auto Patch Files"))
        self.patch_method_menu.add_command(label="Auto Create Patches", command=lambda: self.update_patch_method("Auto Create Patches"))
        self.patch_method_button.configure(menu=self.patch_method_menu)
        self.patch_method_button.grid(row=0, column=0, padx=5, pady=4, ipady=2, sticky="ew")
        add_tooltip(self.patch_method_button,
                    "Choose the mode: “Auto Patch Files” applies .bps/.ips to a Base ROM. "
                    "“Auto Create Patches” makes a .bps/.ips by comparing Base vs Modified ROM.")

        # Patch type menu (.BPS / .IPS) – this also controls the file filter dialogue used later.
        self.select_file_button = Menubutton(ctrl_row, text=".BPS", relief=tk.RAISED)
        self._uniform_button(self.select_file_button)
        self.select_file_menu = Menu(self.select_file_button, tearoff=0)
        self.select_file_menu.add_command(label=".bps", command=lambda: self.select_files(".bps"))
        self.select_file_menu.add_command(label=".ips", command=lambda: self.select_files(".ips"))
        self.select_file_button.configure(menu=self.select_file_menu)
        self.select_file_button.grid(row=0, column=1, padx=5, pady=4, ipady=2, sticky="ew")
        add_tooltip(self.select_file_button, "Choose which patch format you’re working with.")

        # Start – kicks off the chosen workflow.
        self.start_button = tk.Button(ctrl_row, text="Start", command=self.start_patching)
        self._uniform_button(self.start_button)
        self.start_button.grid(row=0, column=2, padx=5, pady=4, ipady=2, sticky="ew")
        add_tooltip(self.start_button, "Begin and select the needed files when prompted.")

        # Clear – clears only the Info/Output box.
        self.clear_console_button = tk.Button(ctrl_row, text="Clear", command=self.clear_console)
        self._uniform_button(self.clear_console_button)
        self.clear_console_button.grid(row=0, column=3, padx=5, pady=4, ipady=2, sticky="ew")
        add_tooltip(self.clear_console_button, "Clear the Info/Output box. (Settings are kept.)")

        # Reset – resets settings and selections.
        self.clear_button = tk.Button(ctrl_row, text="Reset", command=self.clear_output)
        self._uniform_button(self.clear_button)
        self.clear_button.grid(row=0, column=4, padx=5, pady=4, ipady=2, sticky="ew")
        add_tooltip(self.clear_button, "Reset all settings to defaults and clear file selections.")

        # Load Config / Save Config – JSON round-trip of the current options.
        self.load_cfg_button = tk.Button(ctrl_row, text="Load Config", command=self.load_config)
        self._uniform_button(self.load_cfg_button)
        self.load_cfg_button.grid(row=0, column=5, padx=5, pady=4, ipady=2, sticky="ew")
        add_tooltip(self.load_cfg_button, "Load settings from a .json file.")

        self.save_cfg_button = tk.Button(ctrl_row, text="Save Config", command=self.save_config)
        self._uniform_button(self.save_cfg_button)
        self.save_cfg_button.grid(row=0, column=6, padx=5, pady=4, ipady=2, sticky="ew")
        add_tooltip(self.save_cfg_button, "Save current settings to a .json file.")

        for c in range(7):
            ctrl_row.grid_columnconfigure(c, weight=1)

        # --------------- Row 2 widgets ---------------
        self.force_patch_checkbox = tk.Checkbutton(
            opts_row,
            text="Force to Patch (Allows patching with mismatched CRC32).",
            variable=self.force_patch
        )
        self.force_patch_checkbox.grid(row=0, column=0, padx=5, pady=2, sticky="w")
        add_tooltip(self.force_patch_checkbox,
                    "If the patch’s expected CRC32 doesn't match your Base ROM, still apply it. "
                    "May produce a broken ROM. Use with caution.")

        self.append_suffix = tk.BooleanVar(value=False)
        self.append_suffix_checkbox = tk.Checkbutton(
            opts_row,
            text='Append "_patched" to output filename.',
            variable=self.append_suffix
        )
        self.append_suffix_checkbox.grid(row=0, column=1, padx=5, pady=2, sticky="w")
        add_tooltip(self.append_suffix_checkbox, 'Adds "_patched" to output filenames.')

        # Expanded file search “scope” menu.
        self.search_scope = tk.StringVar(value="disable")  # default.
        self.search_scope_button = Menubutton(opts_row, text="Disable expanded file search", relief=tk.RAISED)
        self._uniform_button(self.search_scope_button)
        self.search_scope_menu = Menu(self.search_scope_button, tearoff=0)
        self.search_scope_menu.add_radiobutton(label="Search subfolders", value="enable", variable=self.search_scope,
                                               command=lambda: self.search_scope_button.config(text="Search subfolders"))
        self.search_scope_menu.add_radiobutton(label="Search whole directory", value="directory", variable=self.search_scope,
                                               command=lambda: self.search_scope_button.config(text="Search whole directory"))
        self.search_scope_menu.add_radiobutton(label="Disable expanded file search", value="disable", variable=self.search_scope,
                                               command=lambda: self.search_scope_button.config(text="Disable expanded file search"))
        self.search_scope_button.configure(menu=self.search_scope_menu)
        self.search_scope_button.grid(row=0, column=2, padx=5, pady=2, ipady=2, sticky="w")
        add_tooltip(self.search_scope_button,
                    "After you pick one file, optionally add more from the same folder:\n"
                    "• Search subfolders – include files in the folder AND its subfolders.\n"
                    "• Search whole directory – include only files in the folder (no subfolders).\n"
                    "• Disable – use only what you picked.")

        for c in range(3):
            opts_row.grid_columnconfigure(c, weight=1)

        # ---- START C1: Handle “Open with …” startup file (if any) ----
        # If the OS passes in a file (e.g., right-click → Open with), it gets handled once the
        # window has drawn so dialogs don’t appear behind the main window.
        try:
            if len(sys.argv) > 1:
                startup_path = sys.argv[1]
                if startup_path and os.path.exists(startup_path):
                    # Hand off to the dedicated handler module so this file stays simple.
                    self.root.after(50, lambda: self.open_with.handle_startup_file(startup_path))
        except Exception as _e:
            self.log_message(f"Startup file handling error: {_e}")
        # ---- END C1a ---------------------------------------------------
    # ----- END C1: GUI build ------------------------------------------------------

    # ----- START C2: Config Save/Load ---------------------------------------------
    def get_config(self):
        # Return a dict with the current options (used by Save Config).
        try:
            return {
                "patch_method": self.patch_method.get(),
                "bps_ips_type": self.bps_ips_type.get(),
                "force_patch": bool(self.force_patch.get()),
                "append_suffix": bool(self.append_suffix.get()),
                "search_scope": self.search_scope.get(),
            }
        except Exception:
            return {}

    def apply_config(self, cfg: dict):
        """Set current options based on a dict (used by Load Config)."""
        if not isinstance(cfg, dict):
            return
        # Patch method.
        pm = cfg.get("patch_method")
        if pm in {"Auto Patch Files", "Auto Create Patches"}:
            self.patch_method.set(pm)
            self.patch_method_button.config(text=pm)
        # Patch type.
        pt = cfg.get("bps_ips_type")
        if pt in {".bps", ".ips"}:
            self.bps_ips_type.set(pt)
            self.select_file_button.config(text=pt.upper())
        # Force to Patch / Append suffix.
        if "force_patch" in cfg:
            try: self.force_patch.set(bool(cfg.get("force_patch")))
            except Exception: pass
        if "append_suffix" in cfg:
            try: self.append_suffix.set(bool(cfg.get("append_suffix")))
            except Exception: pass
        # Search scope.
        sc = cfg.get("search_scope")
        label_map = {
            "enable": "Search subfolders",
            "directory": "Search whole directory",
            "disable": "Disable expanded file search",
        }
        if sc in label_map:
            try:
                self.search_scope.set(sc)
                self.search_scope_button.config(text=label_map[sc])
            except Exception:
                pass
        self.log_message("Config applied.")

    def save_config(self):
        """Open a file dialog and save the current options to JSON."""
        cfg = self.get_config()
        try:
            default_name = "flips_auto_patcher_config.json"
            path = filedialog.asksaveasfilename(
                title="Save Config",
                defaultextension=".json",
                filetypes=[("JSON files", "*.json"), ("All Files", "*.*")],
                initialfile=default_name,
            )
            if not path:
                self.log_message("Save canceled.")
                return
            with open(path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
            self.log_message(f"Config saved to: {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("Save Config Error", f"Could not save config: {e}")

    def load_config(self):
        """Open a file dialog, read JSON, and apply options."""
        try:
            path = filedialog.askopenfilename(
                title="Load Config",
                filetypes=[("JSON files", "*.json"), ("All Files", "*.*")],
            )
            if not path:
                self.log_message("Load canceled.")
                return
            with open(path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            self.apply_config(cfg)
            self.log_message(f"Config loaded from: {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("Load Config Error", f"Could not load config: {e}")
    # ----- END C2: Config Save/Load ----------------------------------------------

    # ----- START C3: Core operations (create/apply) -------------------------------
    def create_patches(self):
        """Create .bps/.ips patches by comparing Base ROM vs each Modified ROM."""
        # Safety checks.
        if not self.base_rom:
            self.log_message("Error: No Base ROM selected. Please select a Base ROM first.")
            return
        if not self.modified_rom:
            self.log_message("Error: No Modified ROM selected. Please select a Modified ROM first.")
            return

        # Finds path of the selected in-file name and appends "_patched" to the end of it's out-file name before it's extension.
        for rom in self.modified_rom:
            ext = ".ips" if self.bps_ips_type.get() == ".ips" else ".bps"
            rom_base = os.path.splitext(rom)[0]
            patch_file_path = rom_base + ("_patched" if self.append_suffix.get() else "") + ext

            # Skip the "Auto Patch Files" and "Auto Create Patches" process if the base and modified ROM are the same file.
            if os.path.abspath(rom) == os.path.abspath(self.base_rom):
                self.log_message("Error: Base ROM and Modified ROM must cannot be the same file. Ignoring this one.")
                continue

            # Skip identical files that don’t need a patch.
            try:
                if calculate_crc32(self.base_rom) == calculate_crc32(rom):
                    self.log_message(f"Skipping {os.path.basename(rom)}: Base and Modified are identical (no patch needed).")
                    continue
            except Exception:
                pass

            try:
                command = [flips_exe_path, '--create', self.base_rom, rom, patch_file_path]
                subprocess.run(command, check=True, capture_output=True, text=True)
                self.log_message(f"Successfully created patch: {os.path.basename(patch_file_path)}")
            except subprocess.CalledProcessError as e:
                msg_out = (e.stdout or '').strip()
                msg_err = (e.stderr or '').strip()
                if 'The files are identical' in msg_out:
                    self.log_message(f"Skipping {os.path.basename(rom)}: files are identical.")
                else:
                    self.log_message(f"Error creating patch for {os.path.basename(rom)}:")
                    self.log_message(f"  Command: {' '.join(command)}")
                    self.log_message(f"  Stdout: {msg_out if msg_out else 'No output'}")
                    self.log_message(f"  Stderr: {msg_err if msg_err else 'Unknown error occurred.'}")

        self.log_message("Patch creation process is complete.")

    def apply_patches(self):
        """Apply each selected .bps/.ips patch to the selected Base ROM."""
        if not self.base_rom:
            self.log_message("Error: No Base ROM selected. Please select a Base ROM first.")
            return

        for patch_file_path in self.patch_files:
            base_rom_extension = os.path.splitext(self.base_rom)[1]
            patched_rom_base = os.path.splitext(patch_file_path)[0]
            patched_rom_path = (patched_rom_base + "_patched" + base_rom_extension) if self.append_suffix.get() else (patched_rom_base + base_rom_extension)

            metadata = get_patch_metadata(patch_file_path)
            base_crc32 = calculate_crc32(self.base_rom)

            source_crc32 = None
            if metadata and "Source CRC32" in metadata:
                source_crc32 = metadata["Source CRC32"]
                # Check if the Base ROM matches what the patch expects.
                if f"{base_crc32:#010x}" != source_crc32:
                    if self.force_patch.get():
                        self.log_message(f"Force to Patch enabled. Applying patch for {os.path.basename(patch_file_path)} despite CRC32 mismatch.")
                    else:
                        self.log_message(f"Skipping patching for {os.path.basename(patch_file_path)} due to CRC32 mismatch.")
                        continue
                else:
                    self.log_message(f"CRC32 match for {os.path.basename(patch_file_path)}. Proceeding with patch.")

            try:
                # Build the command (with or without ignoring checksums).
                if self.force_patch.get() and source_crc32 and f"{base_crc32:#010x}" != source_crc32:
                    command = [flips_exe_path, '--apply', '--ignore-checksum', patch_file_path, self.base_rom, patched_rom_path]
                else:
                    command = [flips_exe_path, '--apply', patch_file_path, self.base_rom, patched_rom_path]

                subprocess.run(command, check=True, capture_output=True, text=True)

                if self.force_patch.get() and source_crc32 and f"{base_crc32:#010x}" != source_crc32:
                    self.log_message(f"Successfully applied patch despite errors: {os.path.basename(patched_rom_path)}")
                else:
                    self.log_message(f"Successfully applied patch: {os.path.basename(patched_rom_path)}")

            except subprocess.CalledProcessError as e:
                if not os.path.exists(patched_rom_path):
                    self.log_message(f"Error applying patch [{os.path.basename(patch_file_path)}]:")
                    self.log_message(f"  Command: {' '.join(command)}")
                    self.log_message(f"  Stdout: {e.stdout.strip() if e.stdout else 'No output'}")
                    self.log_message(f"  Stderr: {e.stderr.strip() if e.stderr else 'Unknown error occurred.'}")
                else:
                    self.log_message(f"Successfully applied patch despite errors: [{os.path.basename(patched_rom_path)}]")
                    self.log_message(f"Output file location: {patched_rom_path}")

        self.log_message("Patching process is complete.")
    # ----- END C3: Core operations (create/apply) ---------------------------------

    # ----- START C4: Small utilities (reset/logging/selection/metadata) ----------
    def clear_output(self):
        """Reset settings to defaults and clear the Info/Output box + selections."""
        # Clear text.
        self.console_output.configure(state='normal')
        self.console_output.delete(1.0, tk.END)
        self.console_output.configure(state='disabled')

        # Reset options.
        self.append_suffix.set(False)
        self.patch_method.set("Auto Patch Files")
        self.patch_method_button.config(text="Auto Patch Files")
        self.force_patch.set(False)
        try:
            self.search_scope.set("disable")
            self.search_scope_button.config(text="Disable expanded file search")
        except Exception:
            pass

        # Reset selections.
        self.base_rom = None
        self.modified_rom = None
        self.patch_files = []
        self.patch_folder = None

        # Reset visible .BPS/.IPS label.
        self.select_file_button.config(text=".BPS")

    def clear_console(self):
        # Clear only the Info/Output box (keep settings).
        self.console_output.configure(state='normal')
        self.console_output.delete(1.0, tk.END)
        self.console_output.configure(state='disabled')

    def log_message(self, message):
        # Append a line to the Info/Output box and keep it scrolled to bottom.
        self.console_output.configure(state='normal')
        self.console_output.insert(tk.END, f"{message}\n\n")
        self.console_output.configure(state='disabled')
        self.console_output.see(tk.END)
        self.root.update_idletasks()

    def update_patch_method(self, value):
        # Update the mode label and internal value.
        self.patch_method.set(value)
        self.patch_method_button.config(text=value)

    def select_files(self, file_type):
        # Record whether the user wants .bps or .ips.
        self.bps_ips_type.set(file_type)
        self.select_file_button.config(text=file_type.upper())

    def display_patch_metadata(self, file_path):
        """Read and log .bps metadata (source/target CRC32, etc)."""
        metadata = get_patch_metadata(file_path)
        if metadata:
            self.log_message(f"Patch File Metadata ({os.path.basename(file_path)}):")
            for key, value in metadata.items():
                self.log_message(f"  {key}: {value}")
        else:
            self.log_message(f"No metadata available for {os.path.basename(file_path)}.")

    def display_modified_rom_hashes(self, file_path):
        """Compute and log a few hashes for a ROM so users can verify files."""
        crc32 = calculate_crc32(file_path)
        md5 = calculate_md5(file_path)
        sha1 = calculate_sha1(file_path)
        zle = calculate_zle_hash(file_path)
        self.log_message(f"Modified ROM Hashes ({os.path.basename(file_path)}):")
        self.log_message(f"  CRC32: {crc32:#010x}")
        self.log_message(f"  MD5:   {md5}")
        self.log_message(f"  SHA-1: {sha1}")
        self.log_message(f"  ZLE:   {zle}")

    def file_search_rom(self, *, title_override=None, info_message=None):
        """Open a file dialog to pick a Base ROM and then log its hashes."""
        if info_message:
            self.log_message(info_message)
        file_types = self.rom_file_types
        title = title_override or "Select The Base ROM File."
        base_rom_selection = filedialog.askopenfilename(title=title, filetypes=file_types)
        if base_rom_selection:
            self.base_rom = os.path.abspath(base_rom_selection)
            self.display_base_rom_hashes()
        else:
            self.base_rom = None
            self.log_message("No Base ROM file selected.")

    def display_base_rom_hashes(self):
        """Log hashes for the selected Base ROM (helps users verify they picked the right file)."""
        if self.base_rom:
            crc32 = calculate_crc32(self.base_rom)
            md5 = calculate_md5(self.base_rom)
            sha1 = calculate_sha1(self.base_rom)
            zle = calculate_zle_hash(self.base_rom)
            self.log_message(f"Base ROM Hashes ({os.path.basename(self.base_rom)}):")
            self.log_message(f"  CRC32: {crc32:#010x}")
            self.log_message(f"  MD5:   {md5}")
            self.log_message(f"  SHA-1: {sha1}")
            self.log_message(f"  ZLE:   {zle}")
    # ----- END C4: Small utilities -----------------------------------------------s

    # ----- START C5: Start button logic (file pickers + threads) -----------------
    def start_patching(self):
        """Entry point for the Start button; steers to the right workflow."""
        mode = self.patch_method.get()

        if mode == "Auto Patch Files":
            # (1) Pick patch file(s) first.
            self.patch_files = filedialog.askopenfilenames(
                title="Select Patch File(s)",
                filetypes=[(".BPS Patch Files", "*.bps"), ("All Files", "*.*")]
                if self.bps_ips_type.get() == ".bps"
                else [(".IPS Patch Files", "*.ips"), ("All File     if not app.base_rom", "*.*")]
            )
            if not self.patch_files:
                self.log_message("No Patch Files selected.")
                return

            # (2) Optionally expand selection per the 'scope' menu (see header for definitions).
            if self.patch_files:
                try:
                    scope = self.search_scope.get()
                    base_dir = os.path.dirname(self.patch_files[0])
                    target_ext = ".bps" if self.bps_ips_type.get() == ".bps" else ".ips"
                    collected = []
                    if scope == "enable":
                        for root, _, files in os.walk(base_dir):
                            for fname in files:
                                if fname.lower().endswith(target_ext):
                                    collected.append(os.path.join(root, fname))
                    elif scope == "directory":
                        try:
                            for fname in os.listdir(base_dir):
                                full = os.path.join(base_dir, fname)
                                if os.path.isfile(full) and fname.lower().endswith(target_ext):
                                    collected.append(full)
                        except Exception:
                            pass
                    original = list(self.patch_files)
                    seen = set(original)
                    for f in collected:
                        if f not in seen:
                            original.append(f)
                            seen.add(f)
                    self.patch_files = original # Select the base ROM file
                except Exception as e:
                    self.log_message(f"Search expansion error: {e}")

            # (3) Log choices & metadata so the user understands what was found.
            for patch_file in self.patch_files:
                self.log_message(f"Selected Patch File: {os.path.basename(patch_file)}")
                self.display_patch_metadata(patch_file)

            # (4) Pick the Base ROM second.
            self.file_search_rom(info_message="Select the base ROM file.")
            if not self.base_rom:
                return

            # (5) Run patching in a background thread so the UI stays responsive.
            self.log_message("Patching process has started.")
            Thread(target=self.apply_patches, daemon=True).start()

        elif mode == "Auto Create Patches":
            # (1) Pick Modified ROM first.
            self.modified_rom = filedialog.askopenfilenames(
                title="Select The Modified ROM",
                filetypes=self.rom_file_types
            )
            if not self.modified_rom:
                self.log_message("No valid Modified ROM files selected.")
                return

            # (2) Optional expanded selection based on the folder of the first pick.
            if self.modified_rom:
                try:
                    scope = self.search_scope.get()
                    base_dir = os.path.dirname(self.modified_rom[0])
                    rom_exts = (".nes", ".sfc", ".smc", ".gba", ".gbc", ".gen", ".md", ".bin", ".rom", ".z64", ".n64", ".v64", ".sms", ".pce")
                    collected = []
                    abs_base = os.path.abspath(self.base_rom) if self.base_rom else None
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
                    original = list(self.modified_rom)
                    seen = set(os.path.abspath(x) for x in original)
                    for f in collected:
                        if os.path.abspath(f) not in seen:
                            original.append(f)
                            seen.add(os.path.abspath(f))
                    self.modified_rom = original
                except Exception as e:
                    self.log_message(f"Search expansion error: {e}")


            # (2a) Immediately show hashes for the selected Modified ROM(s) (before Base ROM prompt)
            #     This ensures the Info/Output box populates right after the first dialog,
            #     matching the behavior of “Auto Patch Files” when expanded search is enabled.
            for rom in self.modified_rom:
                self.log_message(f"Selected Modified ROM file: {os.path.basename(rom)}")
                self.display_modified_rom_hashes(rom)
                self.log_message(f"Select the base ROM file.")
                ################################################################# USE AI LATER TO GET THIS PART TO ONLY DISPLAY ONCE OR REMOVE IT
            # (3) Pick the Base ROM second
            self.file_search_rom()
            if not self.base_rom:
                return

            # (4) Final clean-up: never allow Base==Modified; remove duplicates
            abs_base = os.path.abspath(self.base_rom)
            cleaned = []
            seen = set()
            for _p in self.modified_rom:
                ap = os.path.abspath(_p)
                if ap == abs_base:
                    self.log_message("Error: Base ROM and Modified ROM cannot be the same file. Ignoring this one.")
                    continue
                if ap in seen:
                    continue
                cleaned.append(_p)
                seen.add(ap)
            self.modified_rom = cleaned
            if not self.modified_rom:
                self.log_message("No valid Modified ROM files selected.")
                return

            # (5) Log hashes so users can verify each Modified ROM
            # (5) Hashes already displayed earlier after first selection.
            # (6) Create patches in background
            self.log_message("Patch creation process has started.")
            self.log_message("Note: for Nintendo 64 ROMs this will take time.")
            Thread(target=self.create_patches, daemon=True).start()
    # ----- END C5: Start button logic --------------------------------------------

    # ----- START C6: “Utility …” helpers (moved) --------------------------------
# NOTE: All code that used to be here now resides in utils.py
#       as utility functions: calculate_crc32, calculate_md5, calculate_sha1, calculate_zle_hash, get_patch_metadata.
#       We keep this stub so section numbering and
#       guidance comments remain consistent with earlier versions.
#       Check: utils.calculate_crc32, utils.calculate_md5, utils.calculate_sha1, utils.calculate_zle_hash, utils.get_patch_metadata
#       for the implementation.
# ----- END C6: “Open with …” helpers ------------------------------------------

    # ----- START C7: “Open with …” helpers (moved) --------------------------------
# NOTE: All code that used to be here now resides in open_with_handle.py
#       as class: OpenWithHandler. We keep this stub so section numbering and
#       guidance comments remain consistent with earlier versions.
#       Check: open_with_handle.OpenWithHandler for the implementation.
# ----- END C7: “Open with …” helpers ------------------------------------------
# ===== END SECTION C: Main Application Class =====================================


# ===== START SECTION D: Program start ============================================
if __name__ == "__main__":
    root = tk.Tk()
    app = AutoPatcherApp(root)
    root.mainloop()
# ===== END SECTION D: Program start ==============================================