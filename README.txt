This is a third party tool extension for auto patching ROMs with flips.exe. 
To build you'll need to add flips.exe to the root folder (where you find main.py), then you'll run the files "setup1.bat" and "setup2.bat" in order. 
After doing so, you'll find FlipsAutoPatcher-v1.2.2.EXE in the "/dist/" directory, copy the contents of the dist folder wherever you want.

Notes:
1. Added slightly better error handling.
2. User now has the option to choose ".IPS" files.
3. Scrollbar added to the "Info/Output:" box (GUI).
4. Neater line spacing.
5. Fixed small bugs.
6. New App Icon.

There are a few .BPS files inside the "/PATCHES/" folder if you want to take a look. 
To decode the patch files you'll need to find a ROM that matches this: 

ROM NAME: OOTUSA1.0.z64                                                               
CRC32: cd16c529                                                              
MD5: 5bd1fe107bf8106b2ab6650abecd54d6                                                            
SHA-1: ad69c91157f6705e8ab06c79fe08aad47bb57ba7                                                                 
ROM ZLE: (ec7011b77616d72b)

v1.2.2 
FlipsAutoPatcher-main/               <-- Root directory of the project
├── dist/                            <-- Directory for bundled executable and dependencies
│   ├── FlipsAutoPatcher-v1.2.2.exe  <-- Executable file created by PyInstaller
│   ├── lib/                         <-- Directory containing Tcl-related files (e.g., `tk.tcl`)
│   │   ├── tk/                      <-- Directory for Tk-related files
│   │   │   ├── tk.tcl               <-- Required Tk TCL file (output file for the EXE)
│   │   │   └── other_tcl_files      <-- Other Tcl-related files
│   ├── tk86t.dll                    <-- Tk DLL file
│   ├── tcl86t.dll                   <-- Tcl DLL file
│   ├── flips/                       <-- Flips folder
│   │   └── flips.exe                <-- Flips.exe (setup.py outputs file for the EXE)
│   ├── ico/                         <-- Icon folder 
│   │   └── flips.ico                <-- Icon file (setup.py outputs file for the EXE)
│   ├── _tkinter.pyd                 <-- Python extension for tkinter
│   └── other_dependencies/          <-- Any other required bundled libraries
├── main.py                          <-- Main script for the application
├── utils.py                         <-- Utility file with helper functions 
├── README.txt                       <-- Project documentation or instructions
├── run.bat                          <-- Batch file to run the main.py in Windows CMD
├── setup.py                         <-- Setup script for packaging 
├── setup1.bat                       <-- First setup file
├── setup2.bat                       <-- Second setup file                             
├── flips.ico                        <-- Required Icon for the project (included)
├── flips.exe                        <-- Required EXE for the project (not included)
└── COPYING                          <-- Project license file 
