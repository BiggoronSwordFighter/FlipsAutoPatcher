#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GUI-only helpers for Flips Auto Patcher.

This module contains only the visible Tkinter UI code:
- tooltip helper
- Info/Output box
- buttons / menus / checkboxes
- ScrolledText output widget
- .BPS/.IPS selector icon hookup

All application logic remains in main.py.
"""

import tkinter as tk
from tkinter import Menubutton, Menu
from tkinter.scrolledtext import ScrolledText

from utils import GUILogger, load_patch_type_button_icons


class ToolTip:
    """Very small helper that shows a tooltip when you hover a widget."""

    def __init__(self, widget, text, delay=500, wraplength=420):
        """__init__ helper.

        Guidance: keep inputs validated, prefer existing shared helpers, and log user-visible status through the current workflow logger when appropriate.
        """
        self.widget = widget
        self.text = text
        self.delay = delay
        self.wraplength = wraplength
        self._after_id = None
        self._tip = None
        widget.bind("<Enter>", self._schedule)
        widget.bind("<Leave>", self._hide)
        widget.bind("<ButtonPress>", self._hide)

    def _schedule(self, event=None):
        """_schedule helper.

        Guidance: keep inputs validated, prefer existing shared helpers, and log user-visible status through the current workflow logger when appropriate.
        """
        self._cancel()
        self._after_id = self.widget.after(self.delay, self._show)

    def _cancel(self):
        """_cancel helper.

        Guidance: keep inputs validated, prefer existing shared helpers, and log user-visible status through the current workflow logger when appropriate.
        """
        if self._after_id:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _show(self):
        """_show helper.

        Guidance: keep inputs validated, prefer existing shared helpers, and log user-visible status through the current workflow logger when appropriate.
        """
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
            tw,
            text=self.text,
            justify=tk.LEFT,
            relief=tk.SOLID,
            borderwidth=1,
            background="#ffffe0",
            wraplength=self.wraplength,
        )
        label.pack(ipadx=6, ipady=4)

    def _hide(self, event=None):
        """_hide helper.

        Guidance: keep inputs validated, prefer existing shared helpers, and log user-visible status through the current workflow logger when appropriate.
        """
        self._cancel()
        if self._tip:
            try:
                self._tip.destroy()
            except Exception:
                pass
            self._tip = None


def add_tooltip(widget, text, delay=500):
    """add_tooltip helper.

    Guidance: keep inputs validated, prefer existing shared helpers, and log user-visible status through the current workflow logger when appropriate.
    """
    try:
        ToolTip(widget, text, delay=delay)
    except Exception:
        pass




def build_main_gui(app, root, *, icon_path, script_dir):
    """Build all visible widgets on the provided app instance."""
    try:
        if icon_path:
            root.iconbitmap(icon_path)
    except tk.TclError:
        pass

    root.title("Flips Auto Patcher v2.3.1")
    root.geometry("1500x700")
    root.minsize(1360, 680)

    output_frame = tk.Frame(root)
    output_frame.pack(fill="both", expand=True, padx=20, pady=(10, 0))

    app.output_label = tk.Label(output_frame, text="Info/Output:", anchor="w")
    app.output_label.pack(anchor="nw", padx=5)

    app.console_output = ScrolledText(
        output_frame,
        height=15,
        width=100,
        state="disabled",
        wrap=tk.WORD,
        font=("Consolas", 10),
        spacing1=2,
        spacing2=1,
        spacing3=2,
    )
    app.console_output.pack(fill="both", expand=True, padx=5)

    try:
        app.logger = GUILogger(app.console_output)
    except Exception:
        app.logger = None

    control_area = tk.Frame(root)
    control_area.pack(fill="x", padx=20, pady=(6, 12))

    ctrl_row = tk.Frame(control_area)
    ctrl_row.pack(fill="x")

    # Keep the top-row buttons evenly sized so the row lines up neatly even when
    # button labels have different lengths.
    for c in range(8):
        ctrl_row.grid_columnconfigure(c, weight=1, uniform="main_buttons", minsize=130)

    top_button_grid = {"padx": 5, "pady": 4, "sticky": "ew"}
    top_button_width = 16

    opts_row = tk.Frame(control_area)
    opts_row.pack(fill="x", pady=(6, 0))

    app.patch_method_button = Menubutton(ctrl_row, text="Auto Patch Files", relief=tk.RAISED, width=top_button_width)
    app._uniform_button(app.patch_method_button)
    app.patch_method_menu = Menu(app.patch_method_button, tearoff=0)
    app.patch_method_menu.add_command(
        label="Auto Patch Files",
        command=lambda: app.update_patch_method("Auto Patch Files"),
    )
    app.patch_method_menu.add_command(
        label="Auto Create Patches",
        command=lambda: app.update_patch_method("Auto Create Patches"),
    )
    app.patch_method_button.configure(menu=app.patch_method_menu)
    app.patch_method_button.grid(row=0, column=0, **top_button_grid)
    add_tooltip(
        app.patch_method_button,
        "Choose the mode: “Auto Patch Files” applies .bps/.ips to a Base ROM. "
        "“Auto Create Patches” makes a .bps/.ips by comparing Base vs Modified ROM.",
    )

    app.select_file_button = Menubutton(ctrl_row, text=".BPS", relief=tk.RAISED, width=top_button_width)
    app._uniform_button(app.select_file_button)
    app.select_file_menu = Menu(app.select_file_button, tearoff=0)
    app.select_file_menu.add_command(label=".bps", command=lambda: app.select_files(".bps"))
    app.select_file_menu.add_command(label=".ips", command=lambda: app.select_files(".ips"))
    app.select_file_button.configure(menu=app.select_file_menu)
    app.select_file_button.grid(row=0, column=1, **top_button_grid)
    add_tooltip(app.select_file_button, "Choose which patch format you’re working with.")

    try:
        app._bps_icon_img, app._ips_icon_img = load_patch_type_button_icons(script_dir)
        if app.bps_ips_type.get() == ".ips" and app._ips_icon_img:
            app.select_file_button.config(image=app._ips_icon_img, compound="left")
        elif app._bps_icon_img:
            app.select_file_button.config(image=app._bps_icon_img, compound="left")
    except Exception:
        app._bps_icon_img, app._ips_icon_img = None, None

    app.start_button = tk.Button(ctrl_row, text="Start", command=app.start_patching, width=top_button_width)
    app._uniform_button(app.start_button)
    app.start_button.grid(row=0, column=2, **top_button_grid)
    add_tooltip(app.start_button, "Begin and select the needed files when prompted.")

    app.clear_console_button = tk.Button(ctrl_row, text="Clear", command=app.clear_console, width=top_button_width)
    app._uniform_button(app.clear_console_button)
    app.clear_console_button.grid(row=0, column=3, **top_button_grid)
    add_tooltip(app.clear_console_button, "Clear the Info/Output box. (Settings are kept.)")

    app.clear_button = tk.Button(ctrl_row, text="Reset", command=app.clear_output, width=top_button_width)
    app._uniform_button(app.clear_button)
    app.clear_button.grid(row=0, column=4, **top_button_grid)
    add_tooltip(app.clear_button, "Reset all settings to defaults and clear file selections.")

    app.load_cfg_button = tk.Button(ctrl_row, text="Load Config", command=app.load_config, width=top_button_width)
    app._uniform_button(app.load_cfg_button)
    app.load_cfg_button.grid(row=0, column=5, **top_button_grid)
    add_tooltip(app.load_cfg_button, "Load settings from a .json file.")

    app.save_cfg_button = tk.Button(ctrl_row, text="Save Config", command=app.save_config, width=top_button_width)
    app._uniform_button(app.save_cfg_button)
    app.save_cfg_button.grid(row=0, column=6, **top_button_grid)
    add_tooltip(app.save_cfg_button, "Save current settings to a .json file.")

    app.register_icons_button = tk.Button(ctrl_row, text="Settings", command=app.open_settings_window, width=top_button_width)
    app._uniform_button(app.register_icons_button)
    app.register_icons_button.grid(row=0, column=7, **top_button_grid)
    add_tooltip(
        app.register_icons_button,
        "Open the Settings window for file associations, emulator launch mode, automatic ROM selection, and Windows cleanup tools.",
    )

    app.force_patch_checkbox = tk.Checkbutton(
        opts_row,
        text="Force to Patch (Allows patching with mismatched CRC32).",
        variable=app.force_patch,
    )
    app.force_patch_checkbox.grid(row=0, column=0, padx=5, pady=2, sticky="w")
    add_tooltip(
        app.force_patch_checkbox,
        "If the patch’s expected CRC32 doesn't match your Base ROM, still apply it. "
        "May produce a broken ROM. Use with caution.",
    )

    app.append_suffix_checkbox = tk.Checkbutton(
        opts_row,
        text='Append "_patched" to output filename.',
        variable=app.append_suffix,
    )
    app.append_suffix_checkbox.grid(row=0, column=2, padx=5, pady=2, sticky="w")
    add_tooltip(app.append_suffix_checkbox, 'Adds "_patched" to output filenames.')

    app.trim_64mb_checkbox = tk.Checkbutton(
        opts_row,
        text="Trim data at 64MB",
        variable=app.trim_64mb,
    )
    app.trim_64mb_checkbox.grid(row=0, column=1, padx=5, pady=2, sticky="w")
    add_tooltip(
        app.trim_64mb_checkbox,
        'N64 hardware feature: Might fix the "File is too large" error for some ROMs on flash carts '
        '(mostly Ocarina of Time MQ Debug) by trimming "garbage data" past 64MB.\n\n'
        'Warning: Can produce a broken ROM. The data past 64MB gets omitted completely and this experimental '
        'feature may introduce bugs or crashes if you accidentally delete any sensitive code.',
    )

    app.bulk_packages_checkbox = tk.Checkbutton(
        opts_row,
        text="Bulk Patching",
        variable=app.bulk_packages,
    )
    app.bulk_packages_checkbox.grid(row=0, column=3, padx=5, pady=2, sticky="w")
    add_tooltip(
        app.bulk_packages_checkbox,
        "When enabled:\n"
        "• Bulk mode uses the folders next to the app:\n"
        "    ./bulk patching/patch files/  (put .bps/.ips here)\n"
        "    ./bulk patching/base roms/  (put clean base ROMs here)\n"
        "    ./bulk patching/output/        (patched ROMs are written here)\n"
        "• Ignores all file-select dialogs after you press Start\n"
        "• Automatically patches every .bps/.ips in the Patch Files folder\n"
        "• .bps: selects the correct base ROM by Source CRC32 (patch metadata)\n"
        "• .ips: does not store a source ROM hash. instead, it sorts for ROMs that match the expected truncate size, then tries applying the IPS until one succeeds.\n"
        "• Endian swapping and 64MB trimming only apply to Nintendo 64 ROMs\n",
    )

    app.byteswap_button = Menubutton(opts_row, text="Disable endian swapping", relief=tk.RAISED)
    app._uniform_button(app.byteswap_button)
    app.byteswap_menu = Menu(app.byteswap_button, tearoff=0)
    app.byteswap_menu.add_radiobutton(
        label="Z64 (big-endian)",
        value="z64",
        variable=app.byteswap_mode,
        command=lambda: app.byteswap_button.config(text="Z64 (big-endian)"),
    )
    app.byteswap_menu.add_radiobutton(
        label="N64 (little-endian)",
        value="n64",
        variable=app.byteswap_mode,
        command=lambda: app.byteswap_button.config(text="N64 (little-endian)"),
    )
    app.byteswap_menu.add_radiobutton(
        label="V64 (byte-swapped)",
        value="v64",
        variable=app.byteswap_mode,
        command=lambda: app.byteswap_button.config(text="V64 (byte-swapped)"),
    )
    app.byteswap_menu.add_radiobutton(
        label="Disable endian swapping",
        value="disable",
        variable=app.byteswap_mode,
        command=lambda: app.byteswap_button.config(text="Disable endian swapping"),
    )
    app.byteswap_button.configure(menu=app.byteswap_menu)
    app.byteswap_button.grid(row=0, column=6, padx=5, pady=2, ipady=2, sticky="w")
    add_tooltip(
        app.byteswap_button,
        "Nintendo 64 ROMs can exist in 3 byte orders (Z64/N64/V64).\n"
        "If enabled, the program will convert the *patched output ROM* to the chosen format.\n"
        "• Z64 = big-endian\n"
        "• N64 = little-endian\n"
        "• V64 = byte-swapped\n"
        "• Disable - Endian swapping is ignored.\n"
        "Endian swapping is ignored for non-N64 files.\n"
        "This feature only works in patch mode.\n",
    )

    app.search_scope_button = Menubutton(opts_row, text="Disable expanded file search", relief=tk.RAISED)
    app._uniform_button(app.search_scope_button)
    app.search_scope_menu = Menu(app.search_scope_button, tearoff=0)
    app.search_scope_menu.add_radiobutton(
        label="Search subfolders",
        value="enable",
        variable=app.search_scope,
        command=lambda: app.search_scope_button.config(text="Search subfolders"),
    )
    app.search_scope_menu.add_radiobutton(
        label="Search whole directory",
        value="directory",
        variable=app.search_scope,
        command=lambda: app.search_scope_button.config(text="Search whole directory"),
    )
    app.search_scope_menu.add_radiobutton(
        label="Disable expanded file search",
        value="disable",
        variable=app.search_scope,
        command=lambda: app.search_scope_button.config(text="Disable expanded file search"),
    )
    app.search_scope_button.configure(menu=app.search_scope_menu)
    app.search_scope_button.grid(row=0, column=5, padx=5, pady=2, ipady=2, sticky="w")

    app.rom_header_options_button = tk.Button(
        opts_row,
        text="ROM Header Options",
        command=app.open_rom_header_options,
    )
    app._uniform_button(app.rom_header_options_button)
    app.rom_header_options_button.grid(row=0, column=4, padx=5, pady=2, ipady=2, sticky="w")
    add_tooltip(
        app.search_scope_button,
        "After you pick one file, optionally add more from the same folder:\n"
        "• Search subfolders – include files in the folder AND its subfolders.\n"
        "• Search whole directory – include only files in the folder (no subfolders).\n"
        "• Disable – use only what you picked.",
    )

    add_tooltip(
        app.rom_header_options_button,
        "Open ROM header options.",
    )

    for c in range(7):
        opts_row.grid_columnconfigure(c, weight=1)
