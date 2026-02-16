import logging
from logging.handlers import RotatingFileHandler
import os
import sys

# Logs go next to the executable (not inside _MEIPASS)
if getattr(sys, "frozen", False):
    _log_dir = os.path.join(os.path.dirname(sys.executable), "logs")
else:
    # Use /tmp for serverless environments (Vercel, AWS Lambda, etc.)
    _log_dir = "/tmp/logs" if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME") else "logs"

try:
    os.makedirs(_log_dir, exist_ok=True)
except OSError:
    # Fallback to /tmp if logs directory creation fails
    _log_dir = "/tmp/logs"
    os.makedirs(_log_dir, exist_ok=True)

logger = logging.getLogger("textile_app")
logger.setLevel(logging.INFO)

if not logger.handlers:
    handler = RotatingFileHandler(os.path.join(_log_dir, "app.log"), maxBytes=10*1024*1024, backupCount=5)
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)
