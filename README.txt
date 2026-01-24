This is a third party tool extension for flips.exe that's used for auto patching ROMs. 
To build you'll need to make sure to add "flips.exe" inside the "/flips/" directory, 
then run "build.bat". After doing so, you'll find "FlipsAutoPatcher-v2.0.0.exe" in the 
"/dist/" directory, copy the contents of the dist folder wherever you want.

v2.0.0
FlipsAutoPatcher-main/
├── main.py                         # Main Python application
├── utils.py                        # Helper functions
├── open_with_handle.py             # "Open with" logic helper
├── flips/
│    └── flips.exe                   # Required executable (not included)
├── ico/
│   └── flips.ico                   # Required icon file (included)
├── build.bat                       # Build script 
├── dist/                           # Output folder for bundled executable
│   └── FlipsAutoPatcher-v2.0.0.exe # Compiled project
├── _tkinter.pyd                    # Python Tkinter extension (bundled)
├── tcl86t.dll / tk86t.dll          # Tcl/Tk DLLs (bundled)
├── lib/                            # Tcl/Tk support files (tk.tcl, etc)
├── other dependencies/             # Optional additional bundled files
├── README.txt                      # Project documentation
└── COPYING                         # Project license file

