#!/bin/bash
set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

ERRORS=0

ok()   { echo -e "  ${GREEN}[OK]${NC} $1"; }
warn() { echo -e "  ${YELLOW}[!!]${NC} $1"; ERRORS=1; }
fail() { echo -e "  ${RED}[FAIL]${NC} $1"; ERRORS=1; }
info() { echo -e "  ${CYAN}[..]${NC} $1"; }

echo ""
echo -e "${CYAN}================================================================${NC}"
echo -e "${CYAN}        TEXTILE ERP SYSTEM - LINUX AUTO SETUP${NC}"
echo -e "${CYAN}================================================================${NC}"
echo ""
echo "  This script will check and install required tools:"
echo "    1. MongoDB 8.0 (database server)"
echo "    2. MongoDB Database Tools (mongodump/mongorestore for backups)"
echo "    3. Environment configuration"
echo ""
echo "  NOTE: Python is NOT required. The application is pre-built"
echo "        as a standalone executable."
echo ""
echo -e "${CYAN}================================================================${NC}"
echo ""

# Detect package manager
detect_pkg_manager() {
    if command -v apt-get &>/dev/null; then
        PKG_MGR="apt"
    elif command -v dnf &>/dev/null; then
        PKG_MGR="dnf"
    elif command -v yum &>/dev/null; then
        PKG_MGR="yum"
    elif command -v pacman &>/dev/null; then
        PKG_MGR="pacman"
    else
        PKG_MGR="unknown"
    fi
}

detect_pkg_manager
echo "  Detected package manager: $PKG_MGR"
echo ""

# ---------------------------------------------------------------
#  CHECK MONGODB
# ---------------------------------------------------------------
echo "[1/2] Checking MongoDB..."

if command -v mongod &>/dev/null; then
    MONGO_VER=$(mongod --version 2>&1 | head -1 | grep -oP 'v\K[0-9.]+' || echo "unknown")
    ok "MongoDB $MONGO_VER found."
else
    warn "MongoDB not found. Attempting to install..."

    case $PKG_MGR in
        apt)
            info "Adding MongoDB 8.0 repository..."
            DISTRO=$(lsb_release -is 2>/dev/null | tr '[:upper:]' '[:lower:]' || echo "ubuntu")
            CODENAME=$(lsb_release -cs 2>/dev/null || echo "jammy")

            sudo apt-get install -y gnupg curl

            curl -fsSL https://www.mongodb.org/static/pgp/server-8.0.asc | \
                sudo gpg --dearmor -o /usr/share/keyrings/mongodb-server-8.0.gpg 2>/dev/null

            echo "deb [ signed-by=/usr/share/keyrings/mongodb-server-8.0.gpg ] https://repo.mongodb.org/apt/${DISTRO} ${CODENAME}/mongodb-org/8.0 multiverse" | \
                sudo tee /etc/apt/sources.list.d/mongodb-org-8.0.list

            sudo apt-get update -y
            sudo apt-get install -y mongodb-org
            ;;
        dnf|yum)
            info "Adding MongoDB 8.0 repository..."
            sudo tee /etc/yum.repos.d/mongodb-org-8.0.repo <<'REPO'
[mongodb-org-8.0]
name=MongoDB Repository
baseurl=https://repo.mongodb.org/yum/redhat/$releasever/mongodb-org/8.0/x86_64/
gpgcheck=1
enabled=1
gpgkey=https://www.mongodb.org/static/pgp/server-8.0.asc
REPO
            sudo $PKG_MGR install -y mongodb-org
            ;;
        pacman)
            warn "On Arch Linux, install MongoDB from AUR: yay -S mongodb-bin"
            ;;
        *)
            fail "Cannot auto-install MongoDB. Please install manually."
            fail "Visit: https://www.mongodb.com/try/download/community"
            ;;
    esac

    if command -v mongod &>/dev/null; then
        ok "MongoDB installed."
    fi
fi

# Start MongoDB service
if command -v systemctl &>/dev/null; then
    if systemctl is-active --quiet mongod 2>/dev/null; then
        ok "MongoDB service is running."
    else
        info "Starting MongoDB service..."
        sudo systemctl start mongod 2>/dev/null && sudo systemctl enable mongod 2>/dev/null
        if systemctl is-active --quiet mongod 2>/dev/null; then
            ok "MongoDB service started and enabled."
        else
            warn "Could not start MongoDB. Start it manually: sudo systemctl start mongod"
        fi
    fi
fi

# ---------------------------------------------------------------
#  CHECK MONGODB DATABASE TOOLS (mongodump / mongorestore)
# ---------------------------------------------------------------
echo ""
echo "[2/3] Checking MongoDB Database Tools (mongodump/mongorestore)..."

if command -v mongodump &>/dev/null; then
    ok "mongodump found."
else
    warn "MongoDB Database Tools not found. (Required for Backup/Restore)"
    info "Attempting to install..."

    case $PKG_MGR in
        apt)
            # mongodb-database-tools is included in the mongodb-org meta-package,
            # but if only the server was installed, install tools separately
            sudo apt-get install -y mongodb-database-tools 2>/dev/null || true
            ;;
        dnf|yum)
            sudo $PKG_MGR install -y mongodb-database-tools 2>/dev/null || true
            ;;
        pacman)
            warn "On Arch, install from AUR: yay -S mongodb-tools-bin"
            ;;
        *)
            fail "Cannot auto-install MongoDB Database Tools."
            fail "Download from: https://www.mongodb.com/try/download/database-tools"
            ;;
    esac

    if command -v mongodump &>/dev/null; then
        ok "MongoDB Database Tools installed."
    else
        warn "mongodump still not found. Backup/Restore will not work."
        warn "Download manually: https://www.mongodb.com/try/download/database-tools"
    fi
fi

# ---------------------------------------------------------------
#  ENVIRONMENT CONFIGURATION
# ---------------------------------------------------------------
echo ""
echo "[3/3] Checking environment configuration..."

# Create required directories
mkdir -p logs backups

if [ ! -f ".env" ]; then
    info "Creating .env with default configuration..."

    # Generate secrets using openssl (no Python needed)
    GEN_SECRET=$(openssl rand -base64 48 2>/dev/null || head -c 48 /dev/urandom | base64)
    GEN_ADMIN=$(openssl rand -base64 32 2>/dev/null || head -c 32 /dev/urandom | base64)
    GEN_LICENSE=$(openssl rand -base64 32 2>/dev/null || head -c 32 /dev/urandom | base64)

    cat > .env <<EOF
# Textile ERP — Configuration
# Only edit MONGODB_URL if your MongoDB is not on localhost

MONGODB_URL=mongodb://localhost:27017/
DATABASE_NAME=textile_erp
SECRET_KEY=${GEN_SECRET}
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=480
ALLOWED_ORIGINS=http://localhost:8000
ENV=production
ADMIN_SECRET=${GEN_ADMIN}
LICENSE_SIGN_SECRET=${GEN_LICENSE}
EOF

    ok ".env created with auto-generated secrets."
else
    ok ".env already exists."
fi

# Make the executable runnable
if [ -f "textile-erp" ]; then
    chmod +x textile-erp
    ok "Made textile-erp executable."
fi
if [ -f "start.sh" ]; then
    chmod +x start.sh
fi

# ---------------------------------------------------------------
#  SUMMARY
# ---------------------------------------------------------------
echo ""
echo -e "${CYAN}================================================================${NC}"
if [ "$ERRORS" -eq 0 ]; then
    echo -e "  ${GREEN}SETUP COMPLETE - All checks passed!${NC}"
else
    echo -e "  ${YELLOW}SETUP COMPLETE - Some items need attention (see warnings above)${NC}"
fi
echo -e "${CYAN}================================================================${NC}"
echo ""
echo "  To start the application:"
echo "    ./start.sh"
echo "    OR"
echo "    ./textile-erp"
echo ""
echo "  URL:   http://localhost:8000"
echo "  First launch will prompt you to create an admin account."
echo -e "${CYAN}================================================================${NC}"
echo ""
