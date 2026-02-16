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
    "jwt",
    "cryptography",
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

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", APP_NAME,
        "--noconfirm",
        # Folder mode (not single file) — faster startup, easier to debug
        "--onedir",
        # Don't open console window on Windows
        "--console",
    ]

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
        with open(dist_env, "w", encoding="utf-8") as f:
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
    if platform.system() == "Windows":
        print(f"Run:    dist/{APP_NAME}/create_shortcut.bat  (creates desktop icon)")
        print(f"        Then double-click 'Textile ERP' on desktop")
        print(f"Debug:  dist/{APP_NAME}/start.bat  (shows console)")
    else:
        print(f"Run:    dist/{APP_NAME}/start.sh")
    print("=" * 60)


def create_windows_launcher(dist_dir):
    # 1. Keep start.bat for manual/debug use (shows console)
    launcher = os.path.join(dist_dir, "start.bat")
    with open(launcher, "w") as f:
        f.write('@echo off\n')
        f.write('echo Starting Textile ERP System...\n')
        f.write('echo Application will be available at: http://localhost:8000\n')
        f.write('echo.\n')
        f.write(f'"{APP_NAME}.exe"\n')
        f.write('pause\n')
    print(f"  Created {launcher}")

    # 2. VBScript launcher — runs the exe with NO visible console window
    vbs = os.path.join(dist_dir, "TextileERP.vbs")
    with open(vbs, "w") as f:
        f.write('Set WshShell = CreateObject("WScript.Shell")\n')
        f.write('appDir = CreateObject("Scripting.FileSystemObject")'
                '.GetParentFolderName(WScript.ScriptFullName)\n')
        f.write('WshShell.CurrentDirectory = appDir\n')
        f.write(f'WshShell.Run chr(34) & appDir & "\\{APP_NAME}.exe" & chr(34), 0, False\n')
        # Wait a moment then open the browser
        f.write('WScript.Sleep 3000\n')
        f.write('WshShell.Run "http://localhost:8000", 1, False\n')
    print(f"  Created {vbs}")

    # 3. Stop script — kills the running server process
    stop_script = os.path.join(dist_dir, "stop.bat")
    with open(stop_script, "w") as f:
        f.write('@echo off\n')
        f.write('echo Stopping Textile ERP...\n')
        f.write(f'taskkill /IM "{APP_NAME}.exe" /F >nul 2>&1\n')
        f.write('if %errorlevel%==0 (\n')
        f.write('    echo Textile ERP has been stopped.\n')
        f.write(') else (\n')
        f.write('    echo Textile ERP is not running.\n')
        f.write(')\n')
        f.write('timeout /t 3 >nul\n')
    print(f"  Created {stop_script}")

    # 4. Script to create a desktop shortcut (run once after install)
    shortcut_script = os.path.join(dist_dir, "create_shortcut.bat")
    with open(shortcut_script, "w") as f:
        f.write('@echo off\n')
        f.write('echo Creating desktop shortcut for Textile ERP...\n')
        f.write('echo.\n')
        # Use PowerShell to create a .lnk shortcut — works on all modern Windows
        f.write('powershell -NoProfile -Command "')
        f.write("$ws = New-Object -ComObject WScript.Shell; ")
        f.write("$sc = $ws.CreateShortcut([IO.Path]::Combine("
                "$ws.SpecialFolders('Desktop'), 'Textile ERP.lnk')); ")
        f.write("$sc.TargetPath = '%~dp0TextileERP.vbs'; ")
        f.write("$sc.WorkingDirectory = '%~dp0'; ")
        f.write("$sc.IconLocation = '%~dp0textile-erp.exe,0'; ")
        f.write("$sc.Description = 'Textile ERP System'; ")
        f.write("$sc.Save()")
        f.write('"\n')
        f.write('echo.\n')
        f.write('echo Desktop shortcut created successfully!\n')
        f.write('echo You can now launch Textile ERP from your desktop.\n')
        f.write('pause\n')
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
