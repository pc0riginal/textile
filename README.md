# 🧵 Textile ERP System

A web-based business management application for textile trading companies in India. Supports multi-company, multi-financial-year operations with GST compliance, inventory tracking, and full audit logging.

---

## Features

- Multi-company and multi-financial-year support
- Party management (customers, suppliers, brokers, transporters)
- Purchase challans with inventory tracking (boxes, meters)
- Inventory transfers with full material lineage/traceability
- Sales invoicing with GST (CGST, SGST, IGST, TCS, TDS)
- Payment and receipt management with party ledgers
- Banking/passbook management
- Quality (fabric quality) master data
- Reporting with PDF/Excel export
- Audit logging for all key operations
- Real-time dashboard

---

## Customer Installation (Pre-built Executable)

The application is distributed as a standalone executable built with PyInstaller. **Python is NOT required** on the customer's machine. The only external dependency is MongoDB.

### Quick Setup (Automatic)

Copy the `dist/textile-erp/` folder to the customer's machine, then run the setup script from inside that folder:

**Windows:**
```bat
setup.bat
```

**Linux (Ubuntu/Debian/Fedora/Arch):**
```bash
chmod +x setup.sh
sudo ./setup.sh
```

The script will:
1. Check if MongoDB is installed — download and install it if missing
2. Check if MongoDB Database Tools (`mongodump`/`mongorestore`) are installed — needed for backup/restore
3. Start the MongoDB service
4. Generate `.env` with random secrets if it doesn't exist
5. Create required directories (logs, backups)

After setup, launch the app:
- Windows: double-click `TextileERP.vbs` (or `start.bat` for console mode)
- Linux: `./start.sh`

---

### Manual / Offline Installation

For machines with no internet, download the MongoDB installer separately and bring it on a USB drive.

#### Windows Offline

| What to download | Where |
|-----------------|-------|
| MongoDB 8.0 MSI | https://www.mongodb.com/try/download/community → Windows x64, MSI |
| MongoDB Database Tools MSI | https://www.mongodb.com/try/download/database-tools → Windows x64, MSI |

Steps on the offline machine:

1. Run the MongoDB `.msi` installer → choose Complete → check "Install as Service"
2. Run the MongoDB Database Tools `.msi` installer (needed for backup/restore)
3. Copy the `dist/textile-erp/` folder to e.g. `C:\TextileERP\`
4. Double-click `start.bat`
3. Open the folder and double-click `start.bat`
4. Open http://localhost:8000 — first launch will prompt you to create an admin account

The `.env` file is auto-created on first run by the build script. Edit it only if MongoDB is on a different host.

#### Linux Offline

| What to download | Where |
|-----------------|-------|
| MongoDB 8.0 deb/rpm | https://www.mongodb.com/try/download/community → select your distro |
| MongoDB Database Tools deb/rpm | https://www.mongodb.com/try/download/database-tools → select your distro |

Steps on the offline machine:

1. Install MongoDB:
   ```bash
   # Debian/Ubuntu
   sudo dpkg -i mongodb-org-server_7.0*.deb
   sudo systemctl start mongod
   sudo systemctl enable mongod

   # RHEL/Fedora
   sudo rpm -i mongodb-org-server-7.0*.rpm
   sudo systemctl start mongod
   sudo systemctl enable mongod
   ```
2. Copy the `dist/textile-erp/` folder to e.g. `/opt/textile-erp/`
3. Run:
   ```bash
   chmod +x textile-erp start.sh
   ./start.sh
   ```
4. Open http://localhost:8000 — first launch will prompt you to create an admin account

---

### Running as a Background Service (Linux)

Create `/etc/systemd/system/textile-erp.service`:

```ini
[Unit]
Description=Textile ERP System
After=network.target mongod.service

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/textile-erp
ExecStart=/opt/textile-erp/textile-erp
Restart=always
EnvironmentFile=/opt/textile-erp/.env

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable textile-erp
sudo systemctl start textile-erp
```

---

## Developer Setup (Source Code)

For developers working on the source code, Python 3.11+ is required.

```bash
# Create venv and install deps
python3 -m venv venv
source venv/bin/activate   # Linux/macOS
# venv\Scripts\activate    # Windows
pip install -r requirements.txt

# Run dev server
python start.py
```

### Building the Distributable

```bash
pip install pyinstaller
python build.py
```

Output: `dist/textile-erp/` — a self-contained folder ready to ship to customers.

---

## Quick Reference

| Item | Value |
|------|-------|
| Default URL | http://localhost:8000 |
| First launch | Create your admin account at the registration page |
| Config file | `.env` |
| Logs | `logs/app.log` |
| Backups | `backups/` |
