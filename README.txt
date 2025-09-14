This is a third party tool extension for flips.exe that's used for auto patching ROMs. 
To build you'll need to add flips.exe to the root folder (where you find main.py), then you'll run the files "setup1.bat" and "setup2.bat" in order. 
After doing so, you'll find FlipsAutoPatcher-v1.2.2.EXE in the "/dist/" directory, copy the contents of the dist folder wherever you want.

v2.0.0
FlipsAutoPatcher-main/              <-- Root directory of the project.
├── dist/                           <-- Directory for bundled executable and dependencies.
│   ├── FlipsAutoPatcher-v1.2.2.exe <-- Executable file created by PyInstaller.
│   ├── lib/                        <-- Directory containing Tcl-related files (e.g., `tk.tcl`).
│   │   ├── tk/                     <-- Directory for Tk-related files.
│   │   │   ├── tk.tcl              <-- Required Tk TCL file (output file for the EXE).
│   │   │   └── other_tcl_files     <-- Other Tcl-related files.
│   │   └── tcl                     <-- More Tcl/Tk library files.
│   ├── tk86t.dll                   <-- Tk DLL file.
│   ├── tcl86t.dll                  <-- Tcl DLL file.
│   ├── flips/                      <-- Flips folder.
│   │   └── flips.exe               <-- Flips.exe (setup.py outputs file for the EXE).
│   ├── ico/                        <-- Icon folder.
│   │   └── flips.ico               <-- Icon file (setup.py outputs file for the EXE).
│   ├── _tkinter.pyd                <-- Python extension for tkinter.
│   └── other_dependencies/         <-- Any other required bundled libraries.
├── main.py                         <-- Main script for the application.
├── utils.py                        <-- Utility file with functions for getting hash info.
├── open_with_handle.py             <-- Small helper module that isolates “Open with” code logic.
├── README.txt                      <-- Project documentation or instructions.
├── run.bat                         <-- Batch file to run main.py in Windows CMD.
├── setup.py                        <-- Setup script for packaging.
├── setup1.bat                      <-- First setup file (builds the EXE).
├── setup2.bat                      <-- Second setup file (builds the EXE).                        
├── flips.ico                       <-- Required Icon for the project (included).
├── flips.exe                       <-- Required EXE for the project (not included).
└── COPYING                         <-- Project license file. 
