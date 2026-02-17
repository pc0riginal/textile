@echo off
setlocal enabledelayedexpansion

echo ================================================================
echo        TEXTILE ERP SYSTEM - WINDOWS AUTO SETUP
echo ================================================================
echo.
echo This script will check and install required tools:
echo   1. MongoDB 8.0 (database server)
echo   2. MongoDB Database Tools (mongodump/mongorestore for backups)
echo   3. Environment configuration
echo.
echo NOTE: Python is NOT required. The application is pre-built
echo       as a standalone executable.
echo ================================================================
echo.

set "ERRORS=0"
set "MONGO_FOUND=0"
set "TOOLS_FOUND=0"
set "TOOLS_BIN_PATH="

REM ---------------------------------------------------------------
REM  CHECK MONGODB SERVER
REM ---------------------------------------------------------------
echo [1/3] Checking MongoDB Server...

where mongod >nul 2>&1
if %errorlevel% equ 0 (
    set "MONGO_FOUND=1"
    echo   [OK] MongoDB (mongod) found in PATH.
)

if !MONGO_FOUND! equ 0 (
    for %%V in (8.0 7.0 6.0) do (
        if exist "C:\Program Files\MongoDB\Server\%%V\bin\mongod.exe" (
            set "MONGO_FOUND=1"
            echo   [OK] MongoDB %%V found at default location.
        )
    )
)

if !MONGO_FOUND! equ 0 (
    echo   [!!] MongoDB not found.
    echo.
    echo   Downloading MongoDB 8.0 Community Server...
    set "MONGO_URL=https://fastdl.mongodb.org/windows/mongodb-windows-x86_64-8.0.17-signed.msi"
    set "MONGO_INSTALLER=%TEMP%\mongodb-8.0.17.msi"

    where curl >nul 2>&1
    if %errorlevel% equ 0 (
        curl -L -o "!MONGO_INSTALLER!" "!MONGO_URL!"
    ) else (
        powershell -Command "Invoke-WebRequest -Uri '!MONGO_URL!' -OutFile '!MONGO_INSTALLER!'"
    )

    if exist "!MONGO_INSTALLER!" (
        echo   Installing MongoDB 8.0 (this may take a few minutes)...
        msiexec /i "!MONGO_INSTALLER!" /quiet /qn ADDLOCAL="ServerService,Client" ^
            SHOULD_INSTALL_COMPASS="0"
        if !errorlevel! equ 0 (
            echo   [OK] MongoDB 8.0 installed as a Windows service.
        ) else (
            echo   [WARN] Silent install may have failed. Launching interactive installer...
            msiexec /i "!MONGO_INSTALLER!"
        )
    ) else (
        echo   [FAIL] Could not download MongoDB installer.
        echo          Download manually: https://www.mongodb.com/try/download/community
        set "ERRORS=1"
    )
)

REM Check if MongoDB service is running
sc query MongoDB >nul 2>&1
if %errorlevel% equ 0 (
    sc query MongoDB | find "RUNNING" >nul 2>&1
    if %errorlevel% neq 0 (
        echo   Starting MongoDB service...
        net start MongoDB >nul 2>&1
        if !errorlevel! equ 0 (
            echo   [OK] MongoDB service started.
        ) else (
            echo   [WARN] Could not start MongoDB service. Start it manually via services.msc
        )
    ) else (
        echo   [OK] MongoDB service is running.
    )
) else (
    echo   [WARN] MongoDB service not registered. It may need to be started manually.
)

REM ---------------------------------------------------------------
REM  CHECK MONGODB DATABASE TOOLS (mongodump / mongorestore)
REM ---------------------------------------------------------------
echo.
echo [2/3] Checking MongoDB Database Tools (mongodump/mongorestore)...

REM Check PATH first
where mongodump >nul 2>&1
if %errorlevel% equ 0 (
    set "TOOLS_FOUND=1"
    echo   [OK] mongodump found in PATH.
)

REM Check common install locations
if !TOOLS_FOUND! equ 0 (
    for /d %%D in ("C:\Program Files\MongoDB\Tools\*") do (
        if exist "%%D\bin\mongodump.exe" (
            set "TOOLS_FOUND=1"
            set "TOOLS_BIN_PATH=%%D\bin"
            echo   [OK] MongoDB Database Tools found at %%D\bin
        )
    )
)

if !TOOLS_FOUND! equ 0 (
    echo   [!!] MongoDB Database Tools not found.
    echo       (Required for Backup and Restore features)
    echo.
    echo   Downloading MongoDB Database Tools...
    set "TOOLS_URL=https://fastdl.mongodb.org/tools/db/mongodb-database-tools-windows-x86_64-100.10.0.msi"
    set "TOOLS_INSTALLER=%TEMP%\mongodb-database-tools.msi"

    where curl >nul 2>&1
    if %errorlevel% equ 0 (
        curl -L -o "!TOOLS_INSTALLER!" "!TOOLS_URL!"
    ) else (
        powershell -Command "Invoke-WebRequest -Uri '!TOOLS_URL!' -OutFile '!TOOLS_INSTALLER!'"
    )

    if exist "!TOOLS_INSTALLER!" (
        echo   Installing MongoDB Database Tools...
        msiexec /i "!TOOLS_INSTALLER!" /quiet /qn
        if !errorlevel! equ 0 (
            echo   [OK] MongoDB Database Tools installed.
        ) else (
            echo   [WARN] Silent install may have failed. Launching interactive installer...
            msiexec /i "!TOOLS_INSTALLER!"
        )

        REM Find the installed path
        for /d %%D in ("C:\Program Files\MongoDB\Tools\*") do (
            if exist "%%D\bin\mongodump.exe" (
                set "TOOLS_BIN_PATH=%%D\bin"
            )
        )
    ) else (
        echo   [FAIL] Could not download MongoDB Database Tools.
        echo          Download manually: https://www.mongodb.com/try/download/database-tools
        set "ERRORS=1"
    )
)

REM ---------------------------------------------------------------
REM  ADD TOOLS TO SYSTEM PATH (if not already there)
REM ---------------------------------------------------------------
if defined TOOLS_BIN_PATH (
    REM Check if already in system PATH
    echo !PATH! | find /i "!TOOLS_BIN_PATH!" >nul 2>&1
    if !errorlevel! neq 0 (
        echo.
        echo   Adding MongoDB Database Tools to system PATH...
        echo   Path: !TOOLS_BIN_PATH!

        REM Add to system PATH permanently (requires admin)
        powershell -NoProfile -Command ^
            "$toolsPath = '!TOOLS_BIN_PATH!'; " ^
            "$currentPath = [Environment]::GetEnvironmentVariable('Path', 'Machine'); " ^
            "if ($currentPath -notlike \"*$toolsPath*\") { " ^
            "  [Environment]::SetEnvironmentVariable('Path', \"$currentPath;$toolsPath\", 'Machine'); " ^
            "  Write-Host '  [OK] Added to system PATH permanently.'; " ^
            "} else { " ^
            "  Write-Host '  [OK] Already in system PATH.'; " ^
            "}"

        REM Also add to current session so it works immediately
        set "PATH=!PATH!;!TOOLS_BIN_PATH!"

        REM Verify
        where mongodump >nul 2>&1
        if !errorlevel! equ 0 (
            echo   [OK] mongodump is now accessible.
        ) else (
            echo   [WARN] PATH updated but mongodump not found in current session.
            echo          Restart your terminal or PC for PATH changes to take effect.
        )
    )
)

REM ---------------------------------------------------------------
REM  ENVIRONMENT CONFIGURATION
REM ---------------------------------------------------------------
echo.
echo [3/3] Checking environment configuration...

REM Create required directories
if not exist "logs" mkdir logs
if not exist "backups" mkdir backups

if not exist ".env" (
    echo   Creating .env with default configuration...

    REM Generate secrets using PowerShell (no Python needed)
    for /f "delims=" %%k in ('powershell -NoProfile -Command "[Convert]::ToBase64String((1..48 | ForEach-Object { Get-Random -Max 256 }) -as [byte[]])"') do set "GEN_SECRET=%%k"
    for /f "delims=" %%k in ('powershell -NoProfile -Command "[Convert]::ToBase64String((1..32 | ForEach-Object { Get-Random -Max 256 }) -as [byte[]])"') do set "GEN_ADMIN=%%k"
    for /f "delims=" %%k in ('powershell -NoProfile -Command "[Convert]::ToBase64String((1..32 | ForEach-Object { Get-Random -Max 256 }) -as [byte[]])"') do set "GEN_LICENSE=%%k"

    (
        echo # Textile ERP — Configuration
        echo # Only edit MONGODB_URL if your MongoDB is not on localhost
        echo.
        echo MONGODB_URL=mongodb://localhost:27017/
        echo DATABASE_NAME=textile_erp
        echo SECRET_KEY=!GEN_SECRET!
        echo ALGORITHM=HS256
        echo ACCESS_TOKEN_EXPIRE_MINUTES=480
        echo ALLOWED_ORIGINS=http://localhost:8000
        echo ENV=production
        echo ADMIN_SECRET=!GEN_ADMIN!
        echo LICENSE_SIGN_SECRET=!GEN_LICENSE!
    ) > .env

    echo   [OK] .env created with auto-generated secrets.
) else (
    echo   [OK] .env already exists.
)

REM ---------------------------------------------------------------
REM  SUMMARY
REM ---------------------------------------------------------------
echo.
echo ================================================================
if !ERRORS! equ 0 (
    echo   SETUP COMPLETE - All checks passed!
) else (
    echo   SETUP COMPLETE - Some items need attention (see warnings above^)
)
echo ================================================================
echo.
echo   To start the application:
echo     Double-click "TextileERP.vbs" (silent, opens browser)
echo     OR double-click "start.bat" (shows console for debugging)
echo.
echo   First time? Run "create_shortcut.bat" to add a desktop icon.
echo.
echo   URL:   http://localhost:8000
echo   First launch will prompt you to create an admin account.
echo ================================================================
echo.
pause
