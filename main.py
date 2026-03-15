#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================= Flips Auto Patcher (GUI) =============================

• What this tool mainly does
  - “Auto Patch Files” → applies multiple existing patch files (.bps / .ips) to a Base ROM.
  - “Auto Create Patches” → creates multiple patch files by comparing a Base ROM with a Modified ROM.

• Required files for usage:
  - Base ROM: the original, unmodified game ROM (your “clean” file).
  - Modified ROM: the edited/changed ROM.
  - Patch (.bps / .ips): a tiny file that stores the differences between a Base ROM and a Modified ROM.

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
from tkinter import filedialog, messagebox, ttk
from threading import Thread
import json
import platform
import glob
import time

try:
    import winreg
except Exception:
    winreg = None

# Import "Open with …" logic (open_with_handle.py).
from open_with_handle import OpenWithHandler
from gui import build_main_gui

# Import utility functions (utils.py).
# These helpers compute hashes (CRC32, MD5, SHA1, ZLE) and read .bps metadata.
from utils import calculate_crc32, calculate_md5, calculate_sha1, calculate_zle_hash, get_patch_metadata, get_ips_metadata

# Import Nintendo 64 ROM endian swap helpers (rom_byteswap.py).
# Used by the optional Byte-Swap feature in the GUI.
import endian_swap as rom_byteswap
# Import Nintendo 64 ROM data trimming helper (data_trim.py).
# Used by the optional "Trim data at 64MiB" feature in the GUI.
import trim as data_trim
import bulk

# Determine where we are running (bundled EXE vs plain Python script).
# FIXED: use sys.executable when frozen so py2exe/compiled exe finds flips.exe beside the exe.
if getattr(sys, 'frozen', False):  # Running as a bundled EXE.
    script_dir = os.path.dirname(sys.executable)
else:  # Running as a normal .py
    script_dir = os.path.dirname(os.path.abspath(__file__))

# Primary expected locations for flips.exe.
# Try each candidate in order and keep the first one that actually exists.
_flips_candidates = [
    os.path.join(script_dir, 'flips.exe'),
    os.path.join(script_dir, 'flips', 'flips.exe'),
    os.path.join(script_dir, '_internal', 'flips', 'flips.exe'),
]
flips_exe_path = next((p for p in _flips_candidates if os.path.exists(p)), None)

# If still not found, raise an error.
if not flips_exe_path:
    raise FileNotFoundError("flips.exe is not found. Place it next to the app or in a 'flips' folder.")


# Icon: search multiple possible locations
icon_candidates = [
    os.path.join(script_dir, "ico", "flips.ico"),
    os.path.join(script_dir, "flips.ico"),
    os.path.join(script_dir, "_internal", "ico", "flips.ico"),
]

icon_path = next((p for p in icon_candidates if os.path.exists(p)), None)

# Explorer file-type icons can be different from the app window icon.
# Prefer file-specific icons when they exist, and only fall back to flips.ico.
bps_icon_candidates = [
    os.path.join(script_dir, "ico", "bps.ico"),
    os.path.join(script_dir, "bps.ico"),
    os.path.join(script_dir, "_internal", "ico", "bps.ico"),
]
bps_icon_path = next((p for p in bps_icon_candidates if os.path.exists(p)), icon_path)

ips_icon_candidates = [
    os.path.join(script_dir, "ico", "ips.ico"),
    os.path.join(script_dir, "ips.ico"),
    os.path.join(script_dir, "_internal", "ico", "ips.ico"),
]
ips_icon_path = next((p for p in ips_icon_candidates if os.path.exists(p)), icon_path)


# ===== END SECTION A: Imports & Paths ============================================


# ===== START SECTION B: Tooltip helper ===========================================
# Tooltip / visible widget-build code now lives in gui.py.
# main.py keeps the application logic and asks gui.build_main_gui(...) to create
# the Info/Output box, buttons, menus, checkboxes, scrollbar, and .BPS/.IPS icon UI.
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
        self.root = root
        """Helper that holds all "Open with …" behavior (open_with_handle.py)."""
        self.open_with = OpenWithHandler(self, icon_path)
        self.icon_path = icon_path
        self.bps_icon_path = bps_icon_path
        self.ips_icon_path = ips_icon_path
        self.app_executable_path = self._detect_app_command_path()

        # Current selections / options (keep as attributes so all methods can read them).
        self.base_rom = None            # path to the chosen Base ROM.
        self.modified_rom = None        # tuple/list of Modified ROM paths.
        self.patch_files = []           # list of .bps/.ips paths.
        self.patch_folder = None        # (unused in current UI but kept for clarity).
        self.force_patch = tk.BooleanVar()
        self.patch_method = tk.StringVar(value="Auto Patch Files")  # mode
        self.bps_ips_type = tk.StringVar(value=".bps")              # .bps or .ips
        self.selection_mode = tk.StringVar(value="files")           # reserved for future UI
        self.append_suffix = tk.BooleanVar(value=False)
        self.trim_64mb = tk.BooleanVar(value=False)
        self.bulk_packages = tk.BooleanVar(value=False)
        self.byteswap_mode = tk.StringVar(value="disable")
        self.search_scope = tk.StringVar(value="disable")
        self.emulator_path = tk.StringVar(value="")
        self.emulator_assignments = []
        self.association_action = tk.StringVar(value="create_rom")
        self.auto_rom_selector = tk.BooleanVar(value=False)
        self.rom_autoselect_cache = {}
        self.settings_window = None
        self._settings_busy = False
        self._settings_cleanup_buttons = []
        if getattr(sys, "frozen", False):
            settings_dir = os.path.join(script_dir, "_internal", "tmp")
        else:
            settings_dir = script_dir
        os.makedirs(settings_dir, exist_ok=True)
        self.settings_json_path = os.path.join(settings_dir, "flips_auto_patcher_settings.json")
        self.rom_type_options = [
            "nes", "sfc", "smc", "gba", "gbc",
            "gen", "md", "bin", "rom",
            "z64", "n64", "v64",
            "sms", "pce",
        ]

        # File type filters for ROM pickers.
        self.rom_file_types = [
            ("Common ROM Extensions", "*.nes *.sfc *.smc *.gba *.gbc *.gen *.md *.bin *.rom *.z64 *.n64 *.v64 *.sms *.pce"),
            ("All Files", "*.*")
        ]

        # Delegate all visible Tkinter widget creation to gui.py.
        build_main_gui(self, root, icon_path=icon_path, script_dir=script_dir)
        self.load_app_settings(log_result=False)
        self._sync_option_states()

        # ---- START C1a: Handle “Open with …” startup file (if any) ----
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

        # Best-effort Windows file-type/icon registration so .bps/.ips files
        # show their own icon in Explorer without requiring a separate script.
        try:
            self.root.after(100, self._auto_register_windows_file_types)
        except Exception:
            pass
        # ---- END C1a ---------------------------------------------------

    def _detect_app_command_path(self) -> str:
        """Return the best command target for Windows file association."""
        try:
            if getattr(sys, "frozen", False):
                return os.path.abspath(sys.executable)
        except Exception:
            pass
        try:
            return os.path.abspath(__file__)
        except Exception:
            return os.path.abspath(sys.argv[0])

    def _auto_register_windows_file_types(self):
        """Silently register file types on startup when running on Windows.

        This keeps Explorer icons working even when the user never clicks the
        manual Register Icons button. Failures stay quiet unless verbose logging
        is needed later from the manual action.
        """
        try:
            if platform.system() != "Windows":
                return False
            if winreg is None:
                return False
            if not ((self.bps_icon_path and os.path.exists(self.bps_icon_path)) or (self.ips_icon_path and os.path.exists(self.ips_icon_path))):
                return False
            if not self.app_executable_path or not os.path.exists(self.app_executable_path):
                return False
            return self.register_windows_file_types(log_result=False)
        except Exception:
            return False

    def _refresh_windows_shell(self):
        """Best-effort refresh so Explorer picks up new icons/associations."""
        try:
            import ctypes
            SHCNE_ASSOCCHANGED = 0x08000000
            SHCNF_IDLIST = 0x0000
            ctypes.windll.shell32.SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_IDLIST, None, None)
        except Exception:
            pass

        # Extra refresh helpers used by Explorer on many Windows installs.
        for cmd in (
            ["ie4uinit.exe", "-show"],
            ["ie4uinit.exe", "-ClearIconCache"],
        ):
            try:
                subprocess.run(cmd, capture_output=True, check=False)
            except Exception:
                pass

    def register_windows_file_types(self, log_result=True):
        """Register .bps/.ips file associations and icon paths using the app's own detected paths."""
        if platform.system() != "Windows":
            if log_result:
                self.log_message("File-type registration is only available on Windows.")
            return False

        if winreg is None:
            if log_result:
                self.log_message("Windows registry support is unavailable in this Python build.")
            return False

        if not ((self.bps_icon_path and os.path.exists(self.bps_icon_path)) or (self.ips_icon_path and os.path.exists(self.ips_icon_path))):
            if log_result:
                self.log_message("Registration failed: no usable bps.ico / ips.ico / flips.ico file was found beside the app.")
            return False

        command_target = self.app_executable_path
        if not command_target or not os.path.exists(command_target):
            if log_result:
                self.log_message("Registration failed: app executable/script path could not be resolved.")
            return False

        bps_icon_value = f'"{os.path.abspath(self.bps_icon_path)}",0' if self.bps_icon_path and os.path.exists(self.bps_icon_path) else None
        ips_icon_value = f'"{os.path.abspath(self.ips_icon_path)}",0' if self.ips_icon_path and os.path.exists(self.ips_icon_path) else bps_icon_value
        if getattr(sys, "frozen", False):
            command_value = f'"{os.path.abspath(command_target)}" "%1"'
        else:
            pythonw_path = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
            python_cmd = pythonw_path if os.path.exists(pythonw_path) else sys.executable
            command_value = f'"{os.path.abspath(python_cmd)}" "{os.path.abspath(command_target)}" "%1"'

        classes_root = r"Software\Classes"
        registrations = {
            ".bps": ("BPSPatchFile", "BPS Patch File", bps_icon_value),
            ".ips": ("IPSPatchFile", "IPS Patch File", ips_icon_value),
        }

        try:
            base = winreg.CreateKey(winreg.HKEY_CURRENT_USER, classes_root)
            winreg.CloseKey(base)

            for ext, (prog_id, friendly_name, file_icon_value) in registrations.items():
                ext_key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, fr"{classes_root}\{ext}")
                winreg.SetValueEx(ext_key, "", 0, winreg.REG_SZ, prog_id)
                winreg.CloseKey(ext_key)

                prog_key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, fr"{classes_root}\{prog_id}")
                winreg.SetValueEx(prog_key, "", 0, winreg.REG_SZ, friendly_name)
                winreg.CloseKey(prog_key)

                if file_icon_value:
                    icon_key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, fr"{classes_root}\{prog_id}\DefaultIcon")
                    winreg.SetValueEx(icon_key, "", 0, winreg.REG_SZ, file_icon_value)
                    winreg.CloseKey(icon_key)

                command_key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, fr"{classes_root}\{prog_id}\shell\open\command")
                winreg.SetValueEx(command_key, "", 0, winreg.REG_SZ, command_value)
                winreg.CloseKey(command_key)

            self._refresh_windows_shell()
            if log_result:
                self.log_message("Registered Windows file types for .bps and .ips.")
                self.log_message(f"Icon path: {os.path.abspath(self.icon_path)}")
                self.log_message(f"Open command: {command_value}")
            return True
        except Exception as e:
            if log_result:
                self.log_message(f"File-type registration error: {e}")
            return False

    def _uniform_button(self, w):
        """Small styling helper so buttons look consistent."""
        try:
            w.configure(relief=tk.RAISED, borderwidth=1, highlightthickness=0)
        except Exception:
            pass
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
                "byteswap_mode": self.byteswap_mode.get(),
                "trim_64mb": bool(self.trim_64mb.get()),
                "bulk_packages": bool(self.bulk_packages.get()),
                "emulator_path": self.emulator_path.get(),
                "emulator_assignments": list(self.emulator_assignments),
                "association_action": self.association_action.get(),
                "auto_rom_selector": bool(self.auto_rom_selector.get()),
                "rom_autoselect_cache": dict(self.rom_autoselect_cache),
            }
        except Exception:
            return {}

    def apply_config(self, cfg: dict, *, log_result: bool = True):
        """Set current options based on a dict (used by Load Config)."""
        if not isinstance(cfg, dict):
            return
        # Patch method.
        pm = cfg.get("patch_method")
        if pm in {"Auto Patch Files", "Auto Create Patches"}:
            self.update_patch_method(pm)
        # Patch type.
        pt = cfg.get("bps_ips_type")
        if pt in {".bps", ".ips"}:
            self.select_files(pt)
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

        # Byte-swap mode.
        bm = cfg.get("byteswap_mode")
        label_map2 = {
            "z64": "Z64 (big-endian)",
            "n64": "N64 (little-endian)",
            "v64": "V64 (byte-swapped)",
            "disable": "Disable endian swapping",
        }
        if bm in label_map2:
            try:
                self.byteswap_mode.set(bm)
                self.byteswap_button.config(text=label_map2[bm])
            except Exception:
                pass

        # Trim 64MiB.
        if "trim_64mb" in cfg:
            try:
                self.trim_64mb.set(bool(cfg.get("trim_64mb")))
            except Exception:
                pass


        # Bulk Patching.
        if "bulk_packages" in cfg:
            try:
                self.bulk_packages.set(bool(cfg.get("bulk_packages")))
            except Exception:
                pass

        if "emulator_path" in cfg:
            try:
                self.emulator_path.set(str(cfg.get("emulator_path") or ""))
            except Exception:
                pass

        assignments = cfg.get("emulator_assignments")
        normalized_assignments = []
        if isinstance(assignments, list):
            for item in assignments:
                if not isinstance(item, dict):
                    continue
                emu_path = os.path.abspath(str(item.get("path") or "").strip())
                rom_type = str(item.get("rom_type") or "").strip().lower()
                if not emu_path:
                    continue
                normalized_assignments.append({"path": emu_path, "rom_type": rom_type})
        elif self.emulator_path.get().strip():
            normalized_assignments.append({"path": os.path.abspath(self.emulator_path.get().strip()), "rom_type": ""})
        self.emulator_assignments = normalized_assignments

        aa = str(cfg.get("association_action") or "").strip().lower()
        if aa in {"create_rom", "run_emulator"}:
            try:
                self.association_action.set(aa)
            except Exception:
                pass

        if "auto_rom_selector" in cfg:
            try:
                self.auto_rom_selector.set(bool(cfg.get("auto_rom_selector")))
            except Exception:
                pass

        cache = cfg.get("rom_autoselect_cache")
        if isinstance(cache, dict):
            try:
                self.rom_autoselect_cache = {str(k).lower(): str(v) for k, v in cache.items() if v}
            except Exception:
                pass

        self._sync_option_states()
        if log_result:
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

    # ----- START C2b: App settings / Windows integration --------------------------
    def _normalize_crc32_text(self, value):
        try:
            if value is None:
                return None
            text = str(value).strip().lower()
            if not text:
                return None
            return text if text.startswith("0x") else f"0x{int(text, 16):08x}"
        except Exception:
            return None

    def _get_app_settings_payload(self):
        return {
            "emulator_path": self.emulator_path.get(),
            "emulator_assignments": list(self.emulator_assignments),
            "association_action": self.association_action.get(),
            "auto_rom_selector": bool(self.auto_rom_selector.get()),
            "rom_autoselect_cache": dict(self.rom_autoselect_cache),
        }

    def save_app_settings(self, log_result=False):
        try:
            with open(self.settings_json_path, "w", encoding="utf-8") as f:
                json.dump(self._get_app_settings_payload(), f, indent=2)
            if log_result:
                self.log_message(f"Saved app settings: {os.path.basename(self.settings_json_path)}")
            return True
        except Exception as e:
            if log_result:
                self.log_message(f"Settings save error: {e}")
            return False

    def load_app_settings(self, log_result=False):
        try:
            if not os.path.exists(self.settings_json_path):
                return False
            with open(self.settings_json_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            self.apply_config(cfg, log_result=False)
            if log_result:
                self.log_message(f"Loaded app settings: {os.path.basename(self.settings_json_path)}")
            return True
        except Exception as e:
            if log_result:
                self.log_message(f"Settings load error: {e}")
            return False

    def _delete_registry_tree(self, root, subkey):
        try:
            with winreg.OpenKey(root, subkey, 0, winreg.KEY_READ | winreg.KEY_WRITE) as key:
                while True:
                    try:
                        child = winreg.EnumKey(key, 0)
                    except OSError:
                        break
                    self._delete_registry_tree(root, subkey + "\\" + child)
            winreg.DeleteKey(root, subkey)
            return True
        except FileNotFoundError:
            return False
        except OSError:
            try:
                winreg.DeleteKey(root, subkey)
                return True
            except Exception:
                return False

    def _set_settings_busy(self, busy: bool, message: str | None = None):
        self._settings_busy = bool(busy)
        state = tk.DISABLED if busy else tk.NORMAL
        try:
            for widget in list(getattr(self, "_settings_cleanup_buttons", [])):
                if widget and widget.winfo_exists():
                    widget.configure(state=state)
        except Exception:
            pass
        try:
            if self.settings_window and self.settings_window.winfo_exists():
                self.settings_window.configure(cursor=("watch" if busy else ""))
        except Exception:
            pass
        try:
            self.root.configure(cursor=("watch" if busy else ""))
        except Exception:
            pass
        if message:
            self.log_message(message)

    def _run_settings_task(self, task_fn, *, start_message=None, finish_message=None):
        if self._settings_busy:
            self.log_message("Another settings task is already running.")
            return False

        self._set_settings_busy(True, start_message)

        def worker():
            error_text = None
            try:
                task_fn()
            except Exception as e:
                error_text = str(e)

            def finalize():
                self._set_settings_busy(False)
                if error_text:
                    self.log_message(f"Settings task error: {error_text}")
                elif finish_message:
                    self.log_message(finish_message)

            try:
                self.root.after(0, finalize)
            except Exception:
                pass

        Thread(target=worker, daemon=True).start()
        return True

    def _delete_registry_values(self, root, subkey, value_names):
        try:
            key = winreg.OpenKey(root, subkey, 0, winreg.KEY_READ | winreg.KEY_WRITE)
        except FileNotFoundError:
            return False
        except Exception:
            return False

        removed = False
        try:
            for value_name in value_names:
                try:
                    winreg.DeleteValue(key, value_name)
                    removed = True
                except FileNotFoundError:
                    continue
                except OSError:
                    continue
        finally:
            try:
                winreg.CloseKey(key)
            except Exception:
                pass
        return removed

    def _clear_openwith_history_for_extensions(self, extensions):
        removed = False
        for ext in extensions:
            ext = str(ext or "").strip().lower()
            if not ext.startswith("."):
                continue

            fileext_root = fr"Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\{ext}"
            for subkey in ("OpenWithList", "OpenWithProgids"):
                try:
                    if self._delete_registry_tree(winreg.HKEY_CURRENT_USER, fr"{fileext_root}\{subkey}"):
                        removed = True
                except Exception:
                    pass

            try:
                if self._delete_registry_values(
                    winreg.HKEY_CURRENT_USER,
                    fileext_root,
                    ["Application", "ProgId", "UserChoiceProgid", "MRUListEx"],
                ):
                    removed = True
            except Exception:
                pass

            try:
                if self._delete_registry_tree(winreg.HKEY_CURRENT_USER, fr"Software\Classes\{ext}\OpenWithProgids"):
                    removed = True
            except Exception:
                pass
        return removed

    def _restart_explorer_and_clear_caches(self, *, clear_icon_cache=False, clear_thumb_cache=False):
        if platform.system() != "Windows":
            return False

        local_app_data = os.environ.get("LOCALAPPDATA", "")
        explorer_dir = os.path.join(local_app_data, "Microsoft", "Windows", "Explorer") if local_app_data else ""

        try:
            subprocess.run(["taskkill", "/f", "/im", "explorer.exe"], capture_output=True, check=False)
            time.sleep(0.8)

            if explorer_dir and os.path.isdir(explorer_dir):
                patterns = []
                if clear_icon_cache:
                    patterns.append("iconcache*")
                if clear_thumb_cache:
                    patterns.append("thumbcache*")
                for pattern in patterns:
                    for file_path in glob.glob(os.path.join(explorer_dir, pattern)):
                        try:
                            os.remove(file_path)
                        except Exception:
                            pass
        finally:
            try:
                subprocess.Popen(["explorer.exe"])
            except Exception:
                pass
            self._refresh_windows_shell()
        return True

    def clear_windows_file_icons(self, log_result=True):
        if platform.system() != "Windows":
            if log_result:
                self.log_message("Clear Icons is only available on Windows.")
            return False
        if winreg is None:
            if log_result:
                self.log_message("Windows registry support is unavailable in this Python build.")
            return False

        removed = False
        for subkey in (
            r"Software\Classes\.bps",
            r"Software\Classes\.ips",
            r"Software\Classes\BPSPatchFile",
            r"Software\Classes\IPSPatchFile",
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.bps",
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.ips",
        ):
            try:
                if self._delete_registry_tree(winreg.HKEY_CURRENT_USER, subkey):
                    removed = True
                elif log_result:
                    self.log_message(f"Registry key not found: HKCU\\{subkey}")
            except Exception as e:
                if log_result:
                    self.log_message(f"Clear icons registry cleanup error for HKCU\\{subkey}: {e}")

        self._restart_explorer_and_clear_caches(clear_icon_cache=True, clear_thumb_cache=False)
        if log_result:
            if removed:
                self.log_message("Cleared .bps/.ips file associations and icon cache.")
            else:
                self.log_message("No .bps/.ips icon associations were found to clear. Icon cache was still refreshed.")
        return True

    def clear_apps_from_context_menu(self, log_result=True):
        if platform.system() != "Windows":
            if log_result:
                self.log_message("Clear apps from context menu is not support on this Windows.")
            return False
        if winreg is None:
            if log_result:
                self.log_message("Windows registry support is unavailable in this Python build.")
            return False

        # Only clear the file types this app actually works with, plus a few related launchers.
        # The old version deleted entire high-level registry trees like FileExts and Applications,
        # which can take a very long time and makes the Settings window appear frozen.
        target_extensions = (
            ".bps", ".ips", ".ups",
            ".exe", ".bat", ".cmd", ".py", ".pyw",
        )
        removed = self._clear_openwith_history_for_extensions(target_extensions)

        self._restart_explorer_and_clear_caches(clear_icon_cache=False, clear_thumb_cache=False)
        if log_result:
            if removed:
                self.log_message("Cleared current-user Open With history for supported patch/app launcher file types.")
            else:
                self.log_message("No matching current-user Open With history was found to clear. Explorer was still refreshed.")
        return True

    def _normalize_rom_type_text(self, value):
        text = str(value or "").strip().lower()
        if text.startswith("."):
            text = text[1:]
        return text

    def _parse_rom_type_tokens(self, value):
        if isinstance(value, (list, tuple, set)):
            raw_tokens = value
        else:
            raw_tokens = str(value or "").replace(';', ',').split(',')
        seen = set()
        ordered = []
        for token in raw_tokens:
            norm = self._normalize_rom_type_text(token)
            if not norm or norm in seen:
                continue
            seen.add(norm)
            ordered.append(norm)
        return ordered

    def _format_rom_type_tokens(self, value):
        tokens = self._parse_rom_type_tokens(value)
        return ", ".join(tokens)

    def _open_rom_type_picker(self, initial_value=""):
        parent = self.settings_window if self.settings_window and self.settings_window.winfo_exists() else self.root
        result = {"value": None}

        dialog = tk.Toplevel(parent)
        dialog.title("ROM type")
        dialog.transient(parent)
        dialog.resizable(False, False)
        dialog.grab_set()
        try:
            if self.icon_path:
                dialog.iconbitmap(self.icon_path)
        except Exception:
            pass

        rom_type_options = list(getattr(self, "rom_type_options", []))
        if not rom_type_options:
            rom_type_options = [
                "nes", "sfc", "smc", "gba", "gbc",
                "gen", "md", "bin", "rom",
                "z64", "n64", "v64",
                "sms", "pce",
            ]
            self.rom_type_options = rom_type_options

        outer = tk.Frame(dialog, padx=12, pady=12)
        outer.pack(fill="both", expand=True)

        tk.Label(
            outer,
            text=(
                "Choose a ROM type from the drop-down list.\n"
                "You can also assign multiple ROM types to one emulator.\n"
                "These get associated with your emulator so it knows which kind of roms to open."
            ),
            justify="left",
            anchor="w",
        ).pack(anchor="w")

        picker_row = tk.Frame(outer)
        picker_row.pack(fill="x", pady=(10, 8))

        selected_type = tk.StringVar(value=rom_type_options[0])
        combo = ttk.Combobox(
            picker_row,
            textvariable=selected_type,
            values=rom_type_options,
            state="readonly",
            width=28,
            height=min(len(rom_type_options), 12),
        )
        combo.pack(side="left", fill="x", expand=True)
        combo.current(0)

        assigned_tokens = self._parse_rom_type_tokens(initial_value)
        listbox = tk.Listbox(outer, height=6, exportselection=False)

        def refresh_assigned_list():
            listbox.delete(0, tk.END)
            for token in assigned_tokens:
                listbox.insert(tk.END, token)
            try:
                current_text = self._format_rom_type_tokens(assigned_tokens) or "(none)"
                self._settings_rom_type_var.set(current_text)
            except Exception:
                pass

        def add_selected_type():
            token = self._normalize_rom_type_text(selected_type.get())
            if token and token not in assigned_tokens:
                assigned_tokens.append(token)
                refresh_assigned_list()

        def remove_selected_type():
            selection = listbox.curselection()
            if not selection:
                return
            for idx in reversed(selection):
                if 0 <= idx < len(assigned_tokens):
                    assigned_tokens.pop(idx)
            refresh_assigned_list()

        tk.Button(picker_row, text="Add type", width=12, command=add_selected_type).pack(side="left", padx=(8, 0))

        tk.Label(outer, text="Assigned ROM types:", anchor="w", justify="left").pack(anchor="w")
        listbox.pack(fill="x")
        tk.Button(outer, text="Remove selected", width=16, command=remove_selected_type).pack(anchor="w", pady=(6, 10))

        tk.Label(
            outer,
            text="Available ROM types: " + ", ".join(rom_type_options),
            justify="left",
            anchor="w",
            wraplength=420,
        ).pack(anchor="w")

        button_row = tk.Frame(outer)
        button_row.pack(fill="x", pady=(12, 0))

        def confirm():
            result["value"] = self._format_rom_type_tokens(assigned_tokens)
            dialog.destroy()

        def cancel():
            dialog.destroy()

        tk.Button(button_row, text="OK", width=10, command=confirm).pack(side="left")
        tk.Button(button_row, text="Cancel", width=10, command=cancel).pack(side="left", padx=(8, 0))

        combo.bind("<Return>", lambda _e: add_selected_type())
        dialog.bind("<Escape>", lambda _e: cancel())
        dialog.bind("<Return>", lambda _e: confirm())

        refresh_assigned_list()
        if assigned_tokens:
            listbox.selection_set(0)

        dialog.update_idletasks()
        req_w = max(dialog.winfo_reqwidth(), 520)
        req_h = max(dialog.winfo_reqheight(), 360)
        if parent.winfo_ismapped():
            parent_x = parent.winfo_rootx()
            parent_y = parent.winfo_rooty()
            parent_w = parent.winfo_width()
            parent_h = parent.winfo_height()
        else:
            parent_x = 100
            parent_y = 100
            parent_w = req_w
            parent_h = req_h
        pos_x = parent_x + max((parent_w - req_w) // 2, 0)
        pos_y = parent_y + max((parent_h - req_h) // 2, 0)
        dialog.minsize(520, 360)
        dialog.geometry(f"{req_w}x{req_h}+{pos_x}+{pos_y}")

        combo.focus_set()
        parent.wait_window(dialog)
        return result["value"]

    def _refresh_emulator_assignments_view(self):
        try:
            tree = getattr(self, "_settings_emulator_tree", None)
            if not tree or not tree.winfo_exists():
                return
            for item in tree.get_children():
                tree.delete(item)
            for idx, item in enumerate(self.emulator_assignments):
                path_text = str(item.get("path") or "")
                rom_type_text = self._format_rom_type_tokens(item.get("rom_type") or "") or "(any)"
                tree.insert("", "end", iid=str(idx), values=(rom_type_text, path_text))
        except Exception:
            pass

    def _on_emulator_assignment_selected(self, _event=None):
        try:
            tree = getattr(self, "_settings_emulator_tree", None)
            if not tree or not tree.winfo_exists():
                return
            selected = tree.selection()
            if not selected:
                self._settings_rom_type_var.set("")
                return
            idx = int(selected[0])
            item = self.emulator_assignments[idx]
            self._settings_rom_type_var.set(self._format_rom_type_tokens(item.get("rom_type") or ""))
        except Exception:
            pass

    def _save_selected_emulator_rom_type(self):
        try:
            tree = getattr(self, "_settings_emulator_tree", None)
            if not tree or not tree.winfo_exists():
                return
            selected = tree.selection()
            if not selected:
                return
            idx = int(selected[0])
            current_value = self.emulator_assignments[idx].get("rom_type") or ""
            rom_type = self._open_rom_type_picker(current_value)
            if rom_type is None:
                self._on_emulator_assignment_selected()
                return
            self.emulator_assignments[idx]["rom_type"] = self._format_rom_type_tokens(rom_type)
            if len(self.emulator_assignments) == 1:
                self.emulator_path.set(str(self.emulator_assignments[0].get("path") or ""))
            self._refresh_emulator_assignments_view()
            tree.selection_set(str(idx))
            tree.focus(str(idx))
            self._on_emulator_assignment_selected()
            self.save_app_settings(log_result=False)
            self.log_message("Updated emulator ROM type assignment.")
        except Exception as e:
            self.log_message(f"Could not update emulator ROM type: {e}")

    def add_emulator_assignment(self):
        path = filedialog.askopenfilename(
            title="Select emulator executable",
            filetypes=[("Programs", "*.exe"), ("All Files", "*.*")],
        )
        if not path:
            return
        rom_type = self._open_rom_type_picker("")
        if rom_type is None:
            return
        item = {
            "path": os.path.abspath(path),
            "rom_type": self._format_rom_type_tokens(rom_type),
        }
        self.emulator_assignments.append(item)
        self.emulator_path.set(item["path"])
        self._refresh_emulator_assignments_view()
        try:
            tree = getattr(self, "_settings_emulator_tree", None)
            if tree and tree.winfo_exists():
                new_id = str(len(self.emulator_assignments) - 1)
                tree.selection_set(new_id)
                tree.focus(new_id)
                self._on_emulator_assignment_selected()
        except Exception:
            pass
        self.save_app_settings(log_result=False)
        self.log_message(f"Added emulator: {os.path.basename(path)}")

    def remove_selected_emulator_assignment(self):
        try:
            tree = getattr(self, "_settings_emulator_tree", None)
            if not tree or not tree.winfo_exists():
                return
            selected = tree.selection()
            if not selected:
                return
            idx = int(selected[0])
            removed = self.emulator_assignments.pop(idx)
            self.emulator_path.set(str(self.emulator_assignments[0].get("path") or "") if self.emulator_assignments else "")
            self._settings_rom_type_var.set("")
            self._refresh_emulator_assignments_view()
            self.save_app_settings(log_result=False)
            self.log_message(f"Removed emulator: {os.path.basename(str(removed.get('path') or ''))}")
        except Exception as e:
            self.log_message(f"Could not remove emulator: {e}")

    def clear_all_emulator_assignments(self):
        self.emulator_assignments = []
        self.emulator_path.set("")
        try:
            self._settings_rom_type_var.set("")
        except Exception:
            pass
        self._refresh_emulator_assignments_view()
        self.save_app_settings(log_result=False)
        self.log_message("Cleared all emulator assignments.")

    def choose_emulator(self):
        self.add_emulator_assignment()

    def clear_selected_emulator(self):
        self.remove_selected_emulator_assignment()

    def _on_settings_var_changed(self):
        self.save_app_settings(log_result=False)

    def open_settings_window(self):
        if self.settings_window and self.settings_window.winfo_exists():
            try:
                self.settings_window.deiconify()
                self.settings_window.lift()
                self.settings_window.focus_force()
            except Exception:
                pass
            return

        win = tk.Toplevel(self.root)
        self.settings_window = win
        win.title("Settings")
        try:
            if self.icon_path:
                win.iconbitmap(self.icon_path)
        except Exception:
            pass
        win.transient(self.root)
        win.resizable(True, True)
        win.minsize(540, 430)
        win.configure(bg="#f0f0f0")

        def _on_close():
            self.save_app_settings(log_result=False)
            try:
                win.destroy()
            finally:
                self.settings_window = None
                self._settings_cleanup_buttons = []
                self._settings_busy = False

        outer = tk.Frame(win, padx=10, pady=10, bg="#f0f0f0")
        outer.pack(fill="both", expand=True)

        file_assoc = tk.LabelFrame(outer, text="File associations", padx=8, pady=8, bg="#f0f0f0")
        file_assoc.pack(fill="x", pady=(0, 10))
        assoc_btns = tk.Frame(file_assoc, bg="#f0f0f0")
        assoc_btns.pack(fill="x")
        fix_icons_btn = tk.Button(assoc_btns, text="Fix app icons", command=self.register_windows_file_types, width=14)
        fix_icons_btn.pack(side="left", padx=(0, 8))

        def _clear_icon_cache_confirm():
            if not messagebox.askyesno(
                "Clear icon cache",
                "This will clear Explorer icon cache and restart Explorer. Continue?",
                parent=win,
            ):
                return
            self._run_settings_task(
                lambda: self.clear_windows_file_icons(log_result=True),
                start_message="Clearing icon cache in the background...",
                finish_message="Icon cache task finished.",
            )

        clear_icon_btn = tk.Button(assoc_btns, text="Clear icon cache", command=_clear_icon_cache_confirm, width=16)
        clear_icon_btn.pack(side="left", padx=(0, 8))

        def _clear_context_menu_confirm():
            if not messagebox.askyesno(
                "Clear apps from context menu",
                "This will remove current-user Open With history for supported patch/app launcher file types and refresh Explorer. Continue?",
                parent=win,
            ):
                return
            self._run_settings_task(
                lambda: self.clear_apps_from_context_menu(log_result=True),
                start_message="Clearing Open With history in the background...",
                finish_message="Context menu cleanup task finished.",
            )

        clear_context_btn = tk.Button(assoc_btns, text="Clear apps from Windows context menu", command=_clear_context_menu_confirm, width=34)
        clear_context_btn.pack(side="left")
        self._settings_cleanup_buttons = [fix_icons_btn, clear_icon_btn, clear_context_btn]

        emu = tk.LabelFrame(outer, text="Emulators", padx=8, pady=8, bg="#f0f0f0")
        emu.pack(fill="both", expand=True, pady=(0, 10))

        emu_btns = tk.Frame(emu, bg="#f0f0f0")
        emu_btns.pack(fill="x", pady=(0, 8))
        tk.Button(emu_btns, text="Add emulator", command=self.add_emulator_assignment, width=16).pack(side="left")
        tk.Button(emu_btns, text="Remove selected", command=self.remove_selected_emulator_assignment, width=16).pack(side="left", padx=(8, 8))
        tk.Button(emu_btns, text="Clear all", command=self.clear_all_emulator_assignments, width=12).pack(side="left")

        tree_frame = tk.Frame(emu, bg="#f0f0f0")
        tree_frame.pack(fill="both", expand=True)
        self._settings_emulator_tree = ttk.Treeview(tree_frame, columns=("romtype", "path"), show="headings", height=7)
        self._settings_emulator_tree.heading("romtype", text="ROM type")
        self._settings_emulator_tree.heading("path", text="Emulator path")
        self._settings_emulator_tree.column("romtype", width=110, anchor="w")
        self._settings_emulator_tree.column("path", width=360, anchor="w")
        self._settings_emulator_tree.pack(side="left", fill="both", expand=True)
        self._settings_emulator_tree.bind("<<TreeviewSelect>>", self._on_emulator_assignment_selected)
        emu_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self._settings_emulator_tree.yview)
        emu_scroll.pack(side="right", fill="y")
        self._settings_emulator_tree.configure(yscrollcommand=emu_scroll.set)

        edit_row = tk.Frame(emu, bg="#f0f0f0")
        edit_row.pack(fill="x", pady=(8, 0))
        tk.Label(edit_row, text="Assigned ROM types:", bg="#f0f0f0").pack(side="left")
        self._settings_rom_type_var = tk.StringVar(value="")
        tk.Label(edit_row, textvariable=self._settings_rom_type_var, bg="#f0f0f0", anchor="w").pack(side="left", fill="x", expand=True, padx=(8, 8))
        tk.Button(edit_row, text="Edit types", command=self._save_selected_emulator_rom_type, width=12).pack(side="left")

        assoc = tk.LabelFrame(outer, text="When opening through associations", padx=8, pady=8, bg="#f0f0f0")
        assoc.pack(fill="x", pady=(0, 10))
        tk.Radiobutton(assoc, text="Create ROM", variable=self.association_action, value="create_rom", command=self._on_settings_var_changed, bg="#f0f0f0").pack(anchor="w")
        tk.Radiobutton(assoc, text="Run in emulator", variable=self.association_action, value="run_emulator", command=self._on_settings_var_changed, bg="#f0f0f0").pack(anchor="w", pady=(6, 0))
        tk.Checkbutton(assoc, text="Enable automatic ROM selector", variable=self.auto_rom_selector, command=self._on_settings_var_changed, bg="#f0f0f0").pack(anchor="w", pady=(10, 0))

        desc = tk.Label(
            outer,
            justify="left",
            anchor="w",
            wraplength=500,
            bg="#f0f0f0",
            text=(
                "Create ROM creates a patched ROM file but does not launch the emulator.\n"
                "Run in emulator behaves like Flips' association mode: after patching, the new ROM is launched\n"
                "with the emulator assigned to that ROM type.\n"
                "Automatic ROM selector only applies to BPS patches and reuses a previously matched base ROM when the source CRC32 still matches."
            ),
        )
        desc.pack(fill="x", pady=(2, 10))

        footer = tk.Frame(outer, bg="#f0f0f0")
        footer.pack(fill="x", pady=(2, 0))
        tk.Button(footer, text="Close", command=_on_close, width=10).pack(side="right", padx=(0, 8), pady=(0, 2))

        self._refresh_emulator_assignments_view()
        win.protocol("WM_DELETE_WINDOW", _on_close)
    def _remember_base_rom_for_patch(self, patch_file_path: str, base_rom_path: str):
        try:
            if os.path.splitext(patch_file_path)[1].lower() != ".bps":
                return False
            metadata = get_patch_metadata(patch_file_path)
            source_crc = self._normalize_crc32_text((metadata or {}).get("Source CRC32"))
            if not source_crc:
                return False
            self.rom_autoselect_cache[source_crc] = os.path.abspath(base_rom_path)
            self.save_app_settings(log_result=False)
            return True
        except Exception:
            return False

    def _try_auto_select_base_rom_for_patch_files(self, patch_files):
        try:
            enabled = bool(self.auto_rom_selector.get())
        except Exception:
            enabled = False
        if not enabled:
            return False

        patch_files = list(patch_files or [])
        if not patch_files:
            return False

        source_crcs = set()
        for patch_file_path in patch_files:
            if os.path.splitext(patch_file_path)[1].lower() != ".bps":
                return False
            metadata = get_patch_metadata(patch_file_path)
            source_crc = self._normalize_crc32_text((metadata or {}).get("Source CRC32"))
            if not source_crc:
                return False
            source_crcs.add(source_crc)

        if len(source_crcs) != 1:
            return False

        source_crc = next(iter(source_crcs))
        candidate = os.path.abspath(self.rom_autoselect_cache.get(source_crc, "")) if self.rom_autoselect_cache.get(source_crc) else ""
        if not candidate or not os.path.exists(candidate):
            if source_crc in self.rom_autoselect_cache:
                self.rom_autoselect_cache.pop(source_crc, None)
                self.save_app_settings(log_result=False)
            return False

        try:
            actual_crc = f"{calculate_crc32(candidate):#010x}".lower()
        except Exception:
            return False

        if actual_crc != source_crc:
            self.rom_autoselect_cache.pop(source_crc, None)
            self.save_app_settings(log_result=False)
            return False

        self.base_rom = candidate
        self.log_message(f"Automatic ROM selector matched Base ROM: {os.path.basename(candidate)}")
        try:
            self.display_base_rom_hashes()
        except Exception:
            pass
        return True

    def launch_emulator_if_configured(self, rom_path: str):
        try:
            if self.association_action.get() != "run_emulator":
                return False
        except Exception:
            return False

        if not rom_path or not os.path.exists(rom_path):
            self.log_message("Patched ROM was not found, so the emulator was not launched.")
            return False

        rom_ext = self._normalize_rom_type_text(os.path.splitext(rom_path)[1])
        emulator = ""
        matched_rule = ""
        for item in self.emulator_assignments:
            emu_path = os.path.abspath(str(item.get("path") or "").strip())
            rule_text = str(item.get("rom_type") or "").strip().lower()
            tokens = [self._normalize_rom_type_text(x) for x in rule_text.replace(';', ',').split(',') if self._normalize_rom_type_text(x)]
            if rom_ext and rom_ext in tokens:
                emulator = emu_path
                matched_rule = rule_text
                break

        if not emulator and len(self.emulator_assignments) == 1:
            emulator = os.path.abspath(str(self.emulator_assignments[0].get("path") or "").strip())
            matched_rule = str(self.emulator_assignments[0].get("rom_type") or "").strip().lower()

        if not emulator:
            emulator = os.path.abspath(str(self.emulator_path.get() or "").strip())

        if not emulator:
            self.log_message(f"Run in emulator is enabled, but no emulator is assigned for .{rom_ext or 'rom'} files.")
            return False
        if not os.path.exists(emulator):
            self.log_message(f"Selected emulator was not found: {emulator}")
            return False

        try:
            subprocess.Popen([emulator, rom_path])
            extra = f" (matched {matched_rule})" if matched_rule else ""
            self.log_message(f"Launched emulator with: {os.path.basename(rom_path)}{extra}")
            return True
        except Exception as e:
            self.log_message(f"Emulator launch error: {e}")
            return False
    # ----- END C2b: App settings / Windows integration ---------------------------

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

                # Optional post-patch N64 endian conversion.
                patched_rom_path = self._apply_byteswap_to_output(patched_rom_path)

                # Optional post-patch N64 size trim to 64MiB.
                patched_rom_path = self._apply_trim_to_64mb_output(patched_rom_path)
                self._remember_base_rom_for_patch(patch_file_path, self.base_rom)
                self.launch_emulator_if_configured(patched_rom_path)

            except subprocess.CalledProcessError as e:
                if not os.path.exists(patched_rom_path):
                    self.log_message(f"Error applying patch [{os.path.basename(patch_file_path)}]:")
                    self.log_message(f"  Command: {' '.join(command)}")
                    self.log_message(f"  Stdout: {e.stdout.strip() if e.stdout else 'No output'}")
                    self.log_message(f"  Stderr: {e.stderr.strip() if e.stderr else 'Unknown error occurred.'}")
                else:
                    self.log_message(f"Successfully applied patch despite errors: [{os.path.basename(patched_rom_path)}]")
                    self.log_message(f"Output file location: {patched_rom_path}")

                    # Optional post-patch N64 endian conversion.
                    patched_rom_path = self._apply_byteswap_to_output(patched_rom_path)

                    # Optional post-patch N64 size trim to 64MiB.
                    patched_rom_path = self._apply_trim_to_64mb_output(patched_rom_path)
                    self._remember_base_rom_for_patch(patch_file_path, self.base_rom)
                    self.launch_emulator_if_configured(patched_rom_path)

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

        # Reset byte-swap option.
        try:
            self.byteswap_mode.set("disable")
            self.byteswap_button.config(text="Disable endian swapping")
        except Exception:
            pass

        # Reset trim option.
        try:
            self.trim_64mb.set(False)
        except Exception:
            pass


        # Reset bulk patching option.
        try:
            self.bulk_packages.set(False)
        except Exception:
            pass

        self._sync_option_states()

        # Reset selections.
        self.base_rom = None
        self.modified_rom = None
        self.patch_files = []
        self.patch_folder = None

        # Reset visible .BPS/.IPS label + selector icon.
        self.select_files(".bps")

    def clear_console(self):
        # Clear only the Info/Output box (keep settings).
        self.console_output.configure(state='normal')
        self.console_output.delete(1.0, tk.END)
        self.console_output.configure(state='disabled')

    def log_message(self, message):
        # Append a line to the Info/Output box (buffered + cleaned).
        try:
            if hasattr(self, "logger") and self.logger is not None:
                self.logger.write(message)
                return
        except Exception:
            pass
        # Fallback (should rarely happen)
        self.console_output.configure(state='normal')
        self.console_output.insert(tk.END, f"{message}\n")
        self.console_output.configure(state='disabled')
        self.console_output.see(tk.END)
        self.root.update_idletasks()

    def _sync_option_states(self):
        """Enable/disable mode-specific options so they behave predictably."""
        mode = self.patch_method.get()
        patch_mode = (mode == "Auto Patch Files")

        try:
            self.force_patch_checkbox.config(state=(tk.NORMAL if patch_mode else tk.DISABLED))
        except Exception:
            pass

        try:
            self.trim_64mb_checkbox.config(state=(tk.NORMAL if patch_mode else tk.DISABLED))
        except Exception:
            pass

        try:
            self.bulk_packages_checkbox.config(state=(tk.NORMAL if patch_mode else tk.DISABLED))
        except Exception:
            pass

        try:
            self.byteswap_button.config(state=(tk.NORMAL if patch_mode else tk.DISABLED))
        except Exception:
            pass

        if not patch_mode:
            try:
                self.force_patch.set(False)
            except Exception:
                pass
            try:
                self.trim_64mb.set(False)
            except Exception:
                pass
            try:
                self.bulk_packages.set(False)
            except Exception:
                pass
            try:
                self.byteswap_mode.set("disable")
                self.byteswap_button.config(text="Disable endian swapping")
            except Exception:
                pass

    def update_patch_method(self, value):
        # Update the mode label and internal value.
        self.patch_method.set(value)
        self.patch_method_button.config(text=value)
        self._sync_option_states()

    def select_files(self, file_type):
        # Record whether the user wants .bps or .ips.
        self.bps_ips_type.set(file_type)
        self.select_file_button.config(text=file_type.upper())

        # Swap the selector icon to match the chosen patch type.
        try:
            if file_type == ".ips" and getattr(self, "_ips_icon_img", None):
                self.select_file_button.config(image=self._ips_icon_img, compound="left")
            elif file_type == ".bps" and getattr(self, "_bps_icon_img", None):
                self.select_file_button.config(image=self._bps_icon_img, compound="left")
            else:
                # If we don't have icons, ensure we don't show stale ones.
                self.select_file_button.config(image="", compound="none")
        except Exception:
            pass

    def reset_file_selections(self):
        """Clear only the currently selected files/folders for the active workflow."""
        self.base_rom = None
        self.modified_rom = None
        self.patch_files = []
        self.patch_folder = None


    def _describe_n64_endian(self, file_path: str) -> str | None:
        """Return a human-readable endian description for N64 ROMs, or None if not an N64 file."""
        try:
            ext = os.path.splitext(file_path)[1].lower()
        except Exception:
            return None

        if ext not in {".z64", ".n64", ".v64"}:
            return None

        try:
            with open(file_path, "rb") as f:
                head = f.read(4)
            fmt = rom_byteswap.MAGIC_TO_FORMAT.get(head)
            if fmt == "z64":
                return "Big-endian (Z64)"
            if fmt == "n64":
                return "Little-endian (N64)"
            if fmt == "v64":
                return "Byte-swapped (V64)"
            return "Unknown (invalid N64 magic)"
        except Exception:
            return "Unknown (read error)"

    def _log_byteswap_non_n64_warning_if_needed(self, file_path: str):
        """If byte-swap is enabled and file is not an N64 type, print the requested message."""
        try:
            if self.byteswap_mode.get() == "disable":
                return
            ext = os.path.splitext(file_path)[1].lower()
            if ext not in {".z64", ".n64", ".v64"}:
                self.log_message("File does not use endian swapping.")
        except Exception:
            pass

    def _apply_byteswap_to_output(self, patched_rom_path: str) -> str:
        """Optionally convert a patched N64 ROM to the selected byte order.

        Returns the final output path (may be unchanged).
        """
        mode = "disable"
        try:
            mode = self.byteswap_mode.get()
        except Exception:
            mode = "disable"

        if mode == "disable":
            return patched_rom_path

        ext = os.path.splitext(patched_rom_path)[1].lower()
        if ext not in {".z64", ".n64", ".v64"}:
            # Only N64 ROMs have these formats.
            self.log_message("File does not use endian swapping.")
            return patched_rom_path

        try:
            with open(patched_rom_path, "rb") as f:
                data = f.read()
        except Exception as e:
            self.log_message(f"Byte-swap read error: {e}")
            return patched_rom_path

        try:
            src = rom_byteswap.detect_format(data)
        except Exception:
            self.log_message("File does not use endian swapping.")
            return patched_rom_path

        dst = mode  # 'z64' / 'n64' / 'v64'
        try:
            out_data = rom_byteswap.convert(data, src, dst)
        except Exception as e:
            self.log_message(f"Byte-swap convert error: {e}")
            return patched_rom_path

        base_no_ext = os.path.splitext(patched_rom_path)[0]
        out_path = f"{base_no_ext}.{dst}"

        try:
            with open(out_path, "wb") as f:
                f.write(out_data)

            if os.path.abspath(out_path) != os.path.abspath(patched_rom_path):
                try:
                    os.remove(patched_rom_path)
                except Exception:
                    pass

            self.log_message(f"Byte-swap complete → {os.path.basename(out_path)}")
            return out_path
        except Exception as e:
            self.log_message(f"Byte-swap write error: {e}")
            return patched_rom_path

    def _apply_trim_to_64mb_output(self, patched_rom_path: str) -> str:
        """Optionally trim the patched output ROM to 64MiB.

        This is an experimental N64-only feature that truncates data past 64MiB.
        Returns the final output path (unchanged filename; may be unmodified).
        """
        try:
            enabled = bool(self.trim_64mb.get())
        except Exception:
            enabled = False

        if not enabled:
            return patched_rom_path

        try:
            # data_trim handles the size check and N64 extension filtering.
            data_trim.trim_to_64mb(
                rom_path=patched_rom_path,
                enabled=True,
                log_fn=self.log_message,
            )
        except Exception as e:
            self.log_message(f"Trim error: {e}")
        return patched_rom_path


    def display_patch_metadata(self, file_path):
        """Log patch-file metadata. For .bps we show embedded Source/Target CRC32. For .ips we show IPS requirements."""
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".ips":
            metadata = get_ips_metadata(file_path)
        else:
            metadata = get_patch_metadata(file_path)

        if metadata:
            self.log_message(f"Patch File Metadata ({os.path.basename(file_path)}):")
            for key, value in metadata.items():
                # IPS does not contain Source/Target CRC32; utils.get_ips_metadata won't include them.
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

        endian = self._describe_n64_endian(file_path)
        if endian:
            self.log_message(f"  Endian: {endian}")
        else:
            self._log_byteswap_non_n64_warning_if_needed(file_path)

    def file_search_rom(self, *, title_override=None, info_message=None):
        """Open a file dialog to pick a Base ROM and then log its hashes."""
        if info_message:
            self.log_message(info_message)
        file_types = self.rom_file_types
        title = title_override or "Select the Base ROM File."
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

            endian = self._describe_n64_endian(self.base_rom)
            if endian:
                self.log_message(f"  Endian: {endian}")
            else:
                self._log_byteswap_non_n64_warning_if_needed(self.base_rom)
    # ----- END C4: Small utilities -----------------------------------------------

    # ----- START C4b: Bulk Patching helpers --------------------------------------
    # NOTE: Bulk Patching implementation is in bulk.py (kept separate from main.py).
    def _bulk_apply_all(self):
        """Bulk patcher workflow (implemented in bulk.py)."""
        return bulk.bulk_apply_all(self, script_dir=script_dir, flips_exe_path=flips_exe_path)
    # ----- END C4b: Bulk Patching helpers ----------------------------------------
# ----- START C5: Start button logic (file pickers + threads) -----------------
    def start_patching(self):
        """Entry point for the Start button; steers to the right workflow."""
        mode = self.patch_method.get()

        if mode == "Auto Patch Files":
            # Bulk Patching mode: no dialogs, patch everything in ./patches/ automatically.
            try:
                if bool(self.bulk_packages.get()):
                    self.log_message("Bulk Patching enabled → running automatic patching from ./bulk patching/")
                    Thread(target=self._bulk_apply_all, daemon=True).start()
                    return
            except Exception:
                pass

            # (1) Pick patch file(s) first.
            self.patch_files = filedialog.askopenfilenames(
                title="Select the Patch file (drag for multi-select).",
                filetypes=[(".BPS Patch Files", "*.bps"), ("All Files", "*.*")]
                if self.bps_ips_type.get() == ".bps"
                else [(".IPS Patch Files", "*.ips"), ("All Files", "*.*")]
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
                    self.patch_files = original # Select the Base ROM file
                except Exception as e:
                    self.log_message(f"Search expansion error: {e}")

            # (3) Log choices & metadata so the user understands what was found.
            for patch_file in self.patch_files:
                self.log_message(f"Selected Patch File: {os.path.basename(patch_file)}")
                self.display_patch_metadata(patch_file)

            # (4) Pick the Base ROM second, unless automatic ROM selection finds a saved match.
            auto_selected = self._try_auto_select_base_rom_for_patch_files(self.patch_files)
            if not auto_selected:
                self.file_search_rom(info_message="Select the base ROM file.")
            if not self.base_rom:
                return

            # (5) Run patching in a background thread so the UI stays responsive.
            self.log_message("Patching process has started.")
            Thread(target=self.apply_patches, daemon=True).start()

        elif mode == "Auto Create Patches":
            # (1) Pick Modified ROM first.
            self.modified_rom = filedialog.askopenfilenames(
                title="Select the Modified ROM file (drag for multi-select).",
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


            # (2a) Immediately show hashes for the selected Modified ROMs (before Base ROM prompt).
            #     This ensures the Info/Output box populates right after the first dialog,
            #     matching the behavior of “Auto Patch Files” when expanded search is enabled.
            for rom in self.modified_rom:
                self.log_message(f"Selected Modified ROM file: {os.path.basename(rom)}")
                self.display_modified_rom_hashes(rom)
                self.log_message(f"Select the base ROM file.")

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
    # Window fix for compiled exe - make window movable/resizable
    root.resizable(True, True)
    root.minsize(800, 500)
    app = AutoPatcherApp(root)
    root.mainloop()
# ===== END SECTION D: Program start ==============================================

