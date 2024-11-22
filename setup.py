import sys
import os

# Get the directory where the setup.py script is located
main_folder = os.path.dirname(os.path.abspath(__file__))
sys.path.append(main_folder)

from distutils.core import setup
import py2exe

setup(
    console=['main.py'],  # This is the main script to be compiled
    data_files=[('flips', ['flips.exe']), ('ico', ['flips.ico'])],  # Ensure files are bundled
    py_modules=['main', 'utils'],  # Explicitly add both main.py and utils.py
    windows=[{'script': 'main.py', 'icon_resources': [(1, 'flips.ico')]}]  # Add icon for Windows executables
)