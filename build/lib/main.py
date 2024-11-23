import os
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, Menubutton, Menu, messagebox
from tkinter.scrolledtext import ScrolledText
from threading import Thread

# Import utility functions
from utils import calculate_crc32, calculate_md5, calculate_sha1, calculate_zle_hash, get_patch_metadata

# Handle file paths directly for compiled executables
# Fallback to current working directory if not in compiled executable
script_dir = os.getcwd()  # Use current working directory as fallback for executable

# Determine if we are running as an EXE or as a Python script
if getattr(sys, 'frozen', False):  # This check is true if the script is running as a bundled EXE
    flips_exe_path = os.path.join(script_dir, 'flips', 'flips.exe')  # Path for EXE version
else:
    flips_exe_path = os.path.join(script_dir, 'flips.exe')  # Path for regular Python script

# Check if flips.exe exists in the expected location
if not os.path.exists(flips_exe_path):
    flips_exe_path = os.path.join(script_dir, 'flips', 'flips.exe')  # Fall back to the /flips/ folder if not found in the main dir
    if not os.path.exists(flips_exe_path):
        raise FileNotFoundError("flips.exe is not found.")

# Check both the main directory and the 'ico' subdirectory for the icon
icon_path = None
# First, check if the icon is in the 'ico' subdirectory
main_icon_path = os.path.join(script_dir, 'ico', 'flips.ico')
if os.path.exists(main_icon_path):
    icon_path = main_icon_path
else:
    # If not found, check in the main script directory
    subdirectory_icon_path = os.path.join(script_dir, 'flips.ico')
    if os.path.exists(subdirectory_icon_path):
        icon_path = subdirectory_icon_path

# Print the icon path to verify the path calculation
if icon_path:
    print("Icon path:", icon_path)
else:
    print("Icon not found.")


class AutoPatcherApp:
    def __init__(self, root):
        self.root = root
        self.base_rom = None
        self.modified_rom = None
        self.patch_files = []
        self.patch_folder = None
        self.force_patch = tk.BooleanVar()
        self.patch_method = tk.StringVar(value="1 Choose Patching Method")
        self.bps_ips_type = tk.StringVar(value=".bps")
        self.selection_mode = tk.StringVar(value="files")  # Default to file selection

        # Set the window icon dynamically using the calculated icon path
        try:
            if icon_path:
                root.iconbitmap(icon_path)
        except tk.TclError:
            print(f"Failed to load the icon from: {icon_path}")

        # File types for filtering
        self.file_types_bps = [
            ("NES Files", "*.nes"),
            ("SNES Files", "*.sfc;*.smc"),
            ("Game Boy Advance Files", "*.gba;*.gbc"),
            ("Genesis Files", "*.gen;*.md;*.bin;*.rom"),
            ("N64 Files", "*.z64;*.n64;*.v64")
        ]
        self.file_types_ips = [
            ("NES Files", "*.nes"),
            ("SNES Files", "*.sfc;*.smc"),
            ("Game Boy Advance Files", "*.gba;*.gbc"),
            ("Genesis Files", "*.gen;*.md;*.bin;*.rom"),
            ("Sega Master System Files", "*.sms"),
            ("TurboGrafx-16 Files", "*.pce")
        ]

        # GUI setup
        root.title("Flips Auto Patcher V1.2.2")
        root.geometry("916x500")

        # Info/Output box with scrollbar
        output_frame = tk.Frame(root)
        output_frame.pack(fill='both', expand=True, padx=20, pady=(10, 0))

        self.output_label = tk.Label(output_frame, text="Info/Output:", anchor='w')
        self.output_label.pack(anchor='nw', padx=5)

        self.console_output = ScrolledText(output_frame, height=15, width=100, state='disabled', wrap=tk.WORD)
        self.console_output.pack(fill='both', expand=True, padx=5)

        # Frame for buttons
        button_frame = tk.Frame(root)
        button_frame.pack(fill='x', padx=20, pady=(5, 10))

        # Menubutton for selecting patch method
        self.patch_method_button = Menubutton(button_frame, text="1 Choose Patching Method", relief=tk.RAISED)
        self.patch_method_menu = Menu(self.patch_method_button, tearoff=0)
        self.patch_method_menu.add_command(label="Auto Patch Files", command=lambda: self.update_patch_method("Auto Patch Files"))
        self.patch_method_menu.add_command(label="Auto Create Patches", command=lambda: self.update_patch_method("Auto Create Patches"))
        self.patch_method_button.configure(menu=self.patch_method_menu)
        self.patch_method_button.grid(row=0, column=0, padx=5, pady=5, sticky="ew")

        # Patch type dropdown button, updated to reflect .bps or .ips selection
        self.select_file_button = Menubutton(button_frame, text="2 Choose Patch Type", relief=tk.RAISED)
        self.select_file_menu = Menu(self.select_file_button, tearoff=0)
        self.select_file_menu.add_command(label=".bps", command=lambda: self.select_files(".bps"))
        self.select_file_menu.add_command(label=".ips", command=lambda: self.select_files(".ips"))
        self.select_file_button.configure(menu=self.select_file_menu)
        self.select_file_button.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        # Force Patch checkbox
        self.force_patch_checkbox = tk.Checkbutton(button_frame, text="Force to Patch (Allows patching with mismatched CRC32).", variable=self.force_patch)
        self.force_patch_checkbox.grid(row=0, column=2, padx=5, pady=5, sticky="ew")

        # Start and Clear buttons
        self.start_button = tk.Button(button_frame, text="Start", command=self.start_patching)
        self.start_button.grid(row=0, column=3, padx=5, pady=5, sticky="ew")

        self.clear_button = tk.Button(button_frame, text="Clear", command=self.clear_output)
        self.clear_button.grid(row=0, column=4, padx=5, pady=5, sticky="ew")

    def create_patch(self):
        # Ensure base ROM and modified ROM are selected
        if not self.base_rom:
            self.log_message("Error: No Base ROM selected. Please select a Base ROM first.")
            return

        if not self.modified_rom:
            self.log_message("Error: No Modified ROM selected. Please select a Modified ROM first.")
            return

        # Iterate through each modified ROM
        for rom in self.modified_rom:
            # Get the file extension of the base ROM
            base_rom_extension = os.path.splitext(self.base_rom)[1]

            # Set the patch file path based on patch type
            if self.bps_ips_type.get() == ".ips":
                # If .ips mode is enabled, we append '_patched.ips'
                patch_file_path = os.path.splitext(rom)[0] + "_patched" + ".ips"
            else:
                # Otherwise, use .bps extension
                patch_file_path = os.path.splitext(rom)[0] + "_patched" + ".bps"

            try:
                # Run the patching tool, ensuring the correct file type is used
                command = [flips_exe_path, '--create', self.base_rom, rom, patch_file_path]
                result = subprocess.run(command, check=True, capture_output=True, text=True)
                self.log_message(f"Successfully created patch: {os.path.basename(patch_file_path)}")

            except subprocess.CalledProcessError as e:
                self.log_message(f"Error creating patch for {os.path.basename(rom)}:")
                self.log_message(f"  Command: {' '.join(command)}")
                self.log_message(f"  Stdout: {e.stdout.strip() if e.stdout else 'No output'}")
                self.log_message(f"  Stderr: {e.stderr.strip() if e.stderr else 'Unknown error occurred.'}")

        self.log_message("Patch creation process is complete.")

    def apply_patches(self):
        if not self.base_rom:
            self.log_message("Error: No Base ROM selected. Please select a Base ROM first.")
            return

        for patch_file_path in self.patch_files:
            # Get the file extension of the base ROM
            base_rom_extension = os.path.splitext(self.base_rom)[1]

            # Set the patched ROM path with the same extension as the base ROM
            patched_rom_path = os.path.splitext(patch_file_path)[0] + "_patched" + base_rom_extension

            metadata = get_patch_metadata(patch_file_path)
            base_crc32 = calculate_crc32(self.base_rom)

            if metadata and "Source CRC32" in metadata:
                source_crc32 = metadata["Source CRC32"]

                # Check if the CRC32 matches
                if f"{base_crc32:#010x}" != source_crc32:
                    # If there's a CRC32 mismatch, check Force to Patch
                    if self.force_patch.get():
                        self.log_message(f"Force to Patch enabled. Applying patch for {os.path.basename(patch_file_path)} despite CRC32 mismatch.")
                    else:
                        self.log_message(f"Skipping patching for {os.path.basename(patch_file_path)} due to CRC32 mismatch.")
                        continue
                else:
                    self.log_message(f"CRC32 match for {os.path.basename(patch_file_path)}. Proceeding with patch.")

            try:
                # Run the patch command
                if self.force_patch.get() and f"{base_crc32:#010x}" != source_crc32:
                    # If Force to Patch is enabled and CRC32 mismatch, apply patch and log the message
                    command = [flips_exe_path, '--apply', '--ignore-checksum', patch_file_path, self.base_rom, patched_rom_path]
                else:
                    # Normal patch application
                    command = [flips_exe_path, '--apply', patch_file_path, self.base_rom, patched_rom_path]

                result = subprocess.run(command, check=True, capture_output=True, text=True)

                # If Force Patch was enabled and CRC32 did not match, show "despite errors"
                if self.force_patch.get() and f"{base_crc32:#010x}" != source_crc32:
                    self.log_message(f"Successfully applied patch despite errors: {os.path.basename(patched_rom_path)}")
                else:
                    # Normal patch success
                    self.log_message(f"Successfully applied patch: {os.path.basename(patched_rom_path)}")

            except subprocess.CalledProcessError as e:
                if not os.path.exists(patched_rom_path):
                    self.log_message(f"Error applying patch [{os.path.basename(patch_file_path)}]:")
                    self.log_message(f"  Command: {' '.join(command)}")
                    self.log_message(f"  Stdout: {e.stdout.strip() if e.stdout else 'No output'}")
                    self.log_message(f"  Stderr: {e.stderr.strip() if e.stderr else 'Unknown error occurred.'}")
                else:
                    # If patch file exists despite errors, show "despite errors"
                    self.log_message(f"Successfully applied patch despite errors: [{os.path.basename(patch_file_path)}]")
                    self.log_message(f"Output file exists: {patched_rom_path}")

        self.log_message("Patching process is complete.")

    def clear_output(self):
        # Clear the output text area
        self.console_output.configure(state='normal')
        self.console_output.delete(1.0, tk.END)
        self.console_output.configure(state='disabled')

        # Reset the patching method to "1 Choose Patching Method"
        self.patch_method.set("1 Choose Patching Method")
        self.patch_method_button.config(text="1 Choose Patching Method")  # Update button text

        # Reset the Force Patch checkbox
        self.force_patch.set(False)

        # Clear file selections and patch files
        self.base_rom = None
        self.modified_rom = None
        self.patch_files = []

        # Reset "2 Choose Patch Type" button text to default
        self.select_file_button.config(text="2 Choose Patch Type")  # Reset the text back to default

    def log_message(self, message):
        self.console_output.configure(state='normal')
        self.console_output.insert(tk.END, f"{message}\n\n")
        self.console_output.configure(state='disabled')
        self.console_output.see(tk.END)
        self.root.update_idletasks()

    def update_patch_method(self, value):
        self.patch_method.set(f"1 {value}")
        self.patch_method_button.config(text=f"1 {value}")

    def select_files(self, file_type):
        self.bps_ips_type.set(file_type)
        # Update the button text to reflect the selected patch type
        self.select_file_button.config(text=f"2 {file_type.upper()}")

    def display_patch_metadata(self, file_path):
        metadata = get_patch_metadata(file_path)
        if metadata:
            self.log_message(f"Patch File Metadata ({os.path.basename(file_path)}):")
            for key, value in metadata.items():
                self.log_message(f"  {key}: {value}")
        else:
            self.log_message(f"No metadata available for {os.path.basename(file_path)}.")

    def display_modified_rom_hashes(self, file_path):
        crc32 = calculate_crc32(file_path)
        md5 = calculate_md5(file_path)
        sha1 = calculate_sha1(file_path)
        zle = calculate_zle_hash(file_path)
        self.log_message(f"Modified ROM Hashes ({os.path.basename(file_path)}):")
        self.log_message(f"  CRC32: {crc32:#010x}")
        self.log_message(f"  MD5:   {md5}")
        self.log_message(f"  SHA-1: {sha1}")
        self.log_message(f"  ZLE:   {zle}")

    def file_search_rom(self):
        file_types = self.file_types_ips if self.bps_ips_type.get() == ".ips" else self.file_types_bps
        base_rom_selection = filedialog.askopenfilename(title="Select The Base ROM File", filetypes=file_types)
        if base_rom_selection:
            self.base_rom = os.path.abspath(base_rom_selection)
            self.display_base_rom_hashes()
        else:
            self.log_message("No Base ROM file selected.")

    def display_base_rom_hashes(self):
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

    def start_patching(self):
        # Select the base ROM
        self.file_search_rom()
        if not self.base_rom:
            return  # No base ROM selected

        # Depending on the patch method, select the next file(s)
        if self.patch_method.get() == "1 Auto Create Patches":
            # Select the modified ROM(s)
            self.modified_rom = filedialog.askopenfilenames(title="Select The Modified ROM(s)", filetypes=self.file_types_bps if self.bps_ips_type.get() == ".bps" else self.file_types_ips)
            if not self.modified_rom:
                self.log_message("No Modified ROM file selected.")
                return

            # Check if base and modified ROMs are the same
            if any(os.path.basename(self.base_rom) == os.path.basename(rom) for rom in self.modified_rom):
                self.log_message("Error: Base ROM and Modified ROM cannot be the same file.")
                return

            # Log the selected modified ROM(s)
            for rom in self.modified_rom:
                self.log_message(f"Selected Modified ROM: {os.path.basename(rom)}")
                self.display_modified_rom_hashes(rom)

        elif self.patch_method.get() == "1 Auto Patch Files":
            # Select the patch file(s)
            self.patch_files = filedialog.askopenfilenames(title="Select Patch File(s)", filetypes=[(".BPS Patch Files", "*.bps")] if self.bps_ips_type.get() == ".bps" else [(".IPS Patch Files", "*.ips")])
            if not self.patch_files:
                self.log_message("No Patch Files selected.")
                return

            # Log the selected patch files
            for patch_file in self.patch_files:
                self.log_message(f"Selected Patch File: {os.path.basename(patch_file)}")
                self.display_patch_metadata(patch_file)

        # Starts the patching process
        if self.patch_method.get() == "1 Auto Create Patches":
            self.log_message("Patch creation process has started.")
            self.log_message("Note: for Nintendo 64 ROMs this will take time.")
            Thread(target=self.create_patch, daemon=True).start()
        elif self.patch_method.get() == "1 Auto Patch Files":
            self.log_message("Patching process has started.")
            Thread(target=self.apply_patches, daemon=True).start()


# Run the application
if __name__ == "__main__":
    root = tk.Tk()
    app = AutoPatcherApp(root)
    root.mainloop()