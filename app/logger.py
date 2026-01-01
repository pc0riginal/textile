import logging
from logging.handlers import RotatingFileHandler
import os

os.makedirs("logs", exist_ok=True)

logger = logging.getLogger("textile_app")
logger.setLevel(logging.INFO)

if not logger.handlers:
    handler = RotatingFileHandler("logs/app.log", maxBytes=10*1024*1024, backupCount=5)
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)
