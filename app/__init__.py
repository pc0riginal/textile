# Textile ERP Application
import os
import sys


def get_base_dir() -> str:
    """Return the base directory for the app.

    When running from source: returns the project root (parent of app/).
    When running from a PyInstaller bundle: returns the temp _MEIPASS dir
    where bundled data files are extracted.
    """
    if getattr(sys, "frozen", False):
        # PyInstaller sets sys._MEIPASS to the temp extraction folder
        return sys._MEIPASS
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


BASE_DIR = get_base_dir()
TEMPLATES_DIR = os.path.join(BASE_DIR, "app", "templates")
STATIC_DIR = os.path.join(BASE_DIR, "app", "static")