# the tests import the map code in src/ and the helper function in this folder.

import sys
from pathlib import Path

THIS_FOLDER = Path(__file__).resolve().parent
SOURCE_FOLDER = THIS_FOLDER.parents[1] / "src"

for folder in (THIS_FOLDER, SOURCE_FOLDER):
    folder_text = str(folder)
    if folder_text not in sys.path:
        sys.path.insert(0, folder_text)
