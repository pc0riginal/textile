"""
Build script — compiles Textile ERP into a standalone distributable folder.

Usage:
    python build.py          # Build for current platform
    python build.py --clean  # Clean previous builds first

Requires: pip install pyinstaller
Output:   dist/textile-erp/   (folder with executable + all assets)
"""
import subprocess
import sys
import os
import shutil
import platform

APP_NAME = "textile-erp"
ENTRY_POINT = "main.py"

# Directories to bundle as data (source -> dest inside bundle)
DATA_DIRS = [
    ("app/templates", "app/templates"),
    ("app/static", "app/static"),
]

# Individual files to bundle
DATA_FILES = []

# Hidden imports that PyInstaller can't auto-detect
HIDDEN_IMPORTS = [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "motor",
    "motor.motor_asyncio",
    "pymongo",
    "dns.resolver",
    "dns.rdatatype",
    "dns.asyncresolver",
    "multipart",
    "jose",
    "bcrypt",
    "decouple",
    "openpyxl",
    "aiofiles",
    "PIL",
    "pydantic",
    "pydantic.deprecated.decorator",
    "email_validator",
]


def clean():
    """Remove previous build artifacts."""
    for d in ["build", "dist", f"{APP_NAME}.spec"]:
        if os.path.isdir(d):
            shutil.rmtree(d)
            print(f"  Removed {d}/")
        elif os.path.isfile(d):
            os.remove(d)
            print(f"  Removed {d}")


def build():
    # Check pyinstaller is installed
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("ERROR: PyInstaller not found.")
        print("Install it in your virtual environment first:")
        print("  pip install pyinstaller")
        print()
        print("Make sure you're running this from your venv:")
        print("  source venv/bin/activate")
        print("  pip install pyinstaller")
        print("  python build.py")
        sys.exit(1)

    dist_dir = os.path.join("dist", APP_NAME)

    # ── Preserve customer data before PyInstaller wipes dist/ ──
    # PyInstaller --noconfirm deletes the entire dist/<name> folder,
    # so we save .env, logs/, and backups/ to a temp location first.
    _preserve_items = [".env", "logs", "backups"]
    _backup_dir = os.path.join("dist", f".{APP_NAME}_preserve")
    _preserved = []
    if os.path.isdir(dist_dir):
        os.makedirs(_backup_dir, exist_ok=True)
        for item in _preserve_items:
            src = os.path.join(dist_dir, item)
            dst = os.path.join(_backup_dir, item)
            if os.path.exists(src):
                if os.path.isdir(src):
                    if os.path.exists(dst):
                        shutil.rmtree(dst)
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)
                _preserved.append(item)
                print(f"  Preserved {item}")
    # ── End preserve ──

    # App icon (Windows .ico)
    icon_path = os.path.join("app", "static", "images", "logo.ico")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", APP_NAME,
        "--noconfirm",
        # Folder mode (not single file) — faster startup, easier to debug
        "--onedir",
        # Don't open console window on Windows (windowed mode hides the terminal)
        "--windowed" if platform.system() == "Windows" else "--console",
    ]

    # Set executable icon on Windows
    if os.path.exists(icon_path):
        cmd.extend(["--icon", icon_path])

    # Add data directories
    sep = ";" if platform.system() == "Windows" else ":"
    for src, dest in DATA_DIRS:
        cmd.extend(["--add-data", f"{src}{sep}{dest}"])
    for src, dest in DATA_FILES:
        if os.path.exists(src):
            cmd.extend(["--add-data", f"{src}{sep}{dest}"])

    # Hidden imports
    for imp in HIDDEN_IMPORTS:
        cmd.extend(["--hidden-import", imp])

    # Exclude heavy unused packages to keep size down
    for exc in ["tkinter", "matplotlib", "numpy", "scipy", "pandas"]:
        cmd.extend(["--exclude-module", exc])

    # Entry point
    cmd.append(ENTRY_POINT)

    print(f"Building {APP_NAME} for {platform.system()}...")
    print(f"Command: {' '.join(cmd)}\n")
    subprocess.check_call(cmd)

    # Post-build: restore preserved customer data
    dist_dir = os.path.join("dist", APP_NAME)
    internal_dir = os.path.join(dist_dir, "_internal")

    if os.path.isdir(_backup_dir):
        for item in _preserved:
            src = os.path.join(_backup_dir, item)
            dst = os.path.join(dist_dir, item)
            if os.path.exists(src):
                if os.path.isdir(src):
                    if os.path.exists(dst):
                        shutil.rmtree(dst)
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)
                print(f"  Restored {item}")
        shutil.rmtree(_backup_dir)

    # Create .env only if it wasn't preserved (first-time build)
    dist_env = os.path.join(dist_dir, ".env")
    if not os.path.exists(dist_env):
        import secrets as _secrets
        with open(dist_env, "w") as f:
            f.write("# Textile ERP — Configuration\n")
            f.write("# Only edit MONGODB_URL if your MongoDB is not on localhost\n\n")
            f.write("MONGODB_URL=mongodb://localhost:27017\n")
            f.write("DATABASE_NAME=textile_erp\n")
            f.write(f"SECRET_KEY={_secrets.token_urlsafe(48)}\n")
            f.write("ALGORITHM=HS256\n")
            f.write("ACCESS_TOKEN_EXPIRE_MINUTES=480\n")
            f.write("ALLOWED_ORIGINS=http://localhost:8000\n")
            f.write("ENV=production\n")
        print(f"  Created customer .env at {dist_env}")

    # Create empty dirs the app expects (next to executable)
    os.makedirs(os.path.join(dist_dir, "logs"), exist_ok=True)
    os.makedirs(os.path.join(dist_dir, "backups"), exist_ok=True)

    # Copy launcher scripts
    if platform.system() == "Windows":
        create_windows_launcher(dist_dir)
    else:
        create_unix_launcher(dist_dir)

    print("\n" + "=" * 60)
    print(f"BUILD COMPLETE")
    print(f"Output: dist/{APP_NAME}/")
    print(f"Run:    dist/{APP_NAME}/{'start.bat' if platform.system() == 'Windows' else 'start.sh'}")
    print("=" * 60)


def create_windows_launcher(dist_dir):
    launcher = os.path.join(dist_dir, "start.bat")
    with open(launcher, "w") as f:
        f.write('@echo off\n')
        f.write('echo Starting Textile ERP System...\n')
        f.write('echo Application will be available at: http://localhost:8000\n')
        f.write('echo.\n')
        f.write('echo DO NOT CLOSE THIS WINDOW while using the application.\n')
        f.write('echo.\n')
        # Open browser after a short delay so the server has time to start
        f.write('start "" cmd /c "timeout /t 3 /noq >nul & start http://localhost:8000"\n')
        f.write(f'"{APP_NAME}.exe"\n')
        f.write('pause\n')
    print(f"  Created {launcher}")

    # Create desktop shortcut installer — customer runs this once
    shortcut_script = os.path.join(dist_dir, "Install Desktop Shortcut.vbs")
    with open(shortcut_script, "w") as f:
        f.write('Set WshShell = CreateObject("WScript.Shell")\n')
        f.write('Set fso = CreateObject("Scripting.FileSystemObject")\n')
        f.write('\n')
        f.write('strDesktop = WshShell.SpecialFolders("Desktop")\n')
        f.write('strAppDir = fso.GetParentFolderName(WScript.ScriptFullName)\n')
        f.write(f'strTarget = fso.BuildPath(strAppDir, "{APP_NAME}.exe")\n')
        f.write('strIcon = fso.BuildPath(strAppDir, "_internal\\app\\static\\images\\logo.ico")\n')
        f.write('\n')
        f.write('Set oShortcut = WshShell.CreateShortcut(strDesktop & "\\Textile ERP.lnk")\n')
        f.write('oShortcut.TargetPath = strTarget\n')
        f.write('oShortcut.WorkingDirectory = strAppDir\n')
        f.write('oShortcut.Description = "Textile ERP System"\n')
        f.write('If fso.FileExists(strIcon) Then\n')
        f.write('    oShortcut.IconLocation = strIcon\n')
        f.write('End If\n')
        f.write('oShortcut.Save\n')
        f.write('\n')
        f.write('MsgBox "Desktop shortcut created!" & vbCrLf & vbCrLf & _\n')
        f.write('    "You can now launch Textile ERP from your desktop.", _\n')
        f.write('    vbInformation, "Textile ERP"\n')
    print(f"  Created {shortcut_script}")


def create_unix_launcher(dist_dir):
    launcher = os.path.join(dist_dir, "start.sh")
    with open(launcher, "w") as f:
        f.write('#!/bin/bash\n')
        f.write('echo "Starting Textile ERP System..."\n')
        f.write('echo "Application will be available at: http://localhost:8000"\n')
        f.write('echo\n')
        f.write(f'DIR="$(cd "$(dirname "$0")" && pwd)"\n')
        f.write(f'"$DIR/{APP_NAME}"\n')
    os.chmod(launcher, 0o755)
    print(f"  Created {launcher}")


if __name__ == "__main__":
    if "--clean" in sys.argv:
        print("Cleaning previous builds...")
        clean()
        print()

    build()
