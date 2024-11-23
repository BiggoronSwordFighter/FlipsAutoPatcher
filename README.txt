This is a third party tool extension for auto patching ROMs with flips.exe. 
You can find the FlipsAutoPatcher-v1.2.2.EXE in "/dist/", copy the contents of the dist folder where ever you want.

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
FlipsAutoPatcher-main/              <-- Root directory of the project
├── dist/                          <-- Directory for bundled executable and dependencies
│   ├── FlipsAutoPatcher-v1.2.2.exe  <-- Executable file created by PyInstaller
│   ├── tcl/                        <-- Directory containing Tcl-related files (e.g., `tk.tcl`)
│   │   ├── tk8.6/                  <-- Directory for Tk-related files
│   │   │   ├── tk.tcl              <-- Required Tk TCL file
│   │   │   └── other_tcl_files     <-- Other Tcl-related files
│   ├── tk86t.dll                   <-- Tk DLL file
│   ├── tcl86t.dll                  <-- Tcl DLL file
│   ├── flips.ico                   <-- Icon file (if used in GUI)
│   ├── _tkinter.pyd                <-- Python extension for tkinter
│   └── other_dependencies/         <-- Any other required bundled libraries
├── main.py                         <-- Main script that starts the application
├── utils.py                        <-- Utility file with helper functions 
├── README.txt                      <-- Project documentation or instructions
├── run.bat                         <-- Batch file to run the project (Windows CMD)
├── setup.py                        <-- Setup script for packaging
├── setup1.bat                      <-- Setup batch file
├── setup2.bat                      <-- Setup batch file
├── ico/                            <-- Directory for additional icons
│   └── flips.ico                   <-- Icon for the project
└── LICENSE                         <-- Project license file 
