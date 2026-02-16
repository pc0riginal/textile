import os
import sys
import secrets
from decouple import config, RepositoryEnv, Config

# When running as a PyInstaller bundle, .env lives next to the executable
if getattr(sys, "frozen", False):
    os.chdir(os.path.dirname(sys.executable))

# Force UTF-8 reading of .env on Windows (default cp1252 breaks on special chars)
_env_path = os.path.join(os.getcwd(), ".env")
if os.path.exists(_env_path):
    try:
        _repo = RepositoryEnv(_env_path, encoding="utf-8")
        _config = Config(_repo)
    except TypeError:
        # Older python-decouple versions don't support encoding param
        _config = Config(RepositoryEnv(_env_path))
else:
    _config = config  # fallback to default AutoConfig

def cfg(key, **kwargs):
    """Read config value, preferring env vars over .env file."""
    # Environment variables always take priority
    env_val = os.environ.get(key)
    if env_val is not None:
        cast = kwargs.get("cast")
        return cast(env_val) if cast else env_val
    return _config(key, **kwargs)

class Settings:
    MONGODB_URL: str = cfg("MONGODB_URL", default="mongodb://localhost:27017")
    DATABASE_NAME: str = cfg("DATABASE_NAME", default="textile_erp")
    SECRET_KEY: str = cfg("SECRET_KEY", default="")
    ALGORITHM: str = cfg("ALGORITHM", default="HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = cfg("ACCESS_TOKEN_EXPIRE_MINUTES", default=480, cast=int)
    UPLOAD_DIR: str = cfg("UPLOAD_DIR", default="app/static/uploads")
    ALLOWED_ORIGINS: str = cfg("ALLOWED_ORIGINS", default="http://localhost:8000")
    ADMIN_SECRET: str = cfg("ADMIN_SECRET", default="")
    LICENSE_PRIVATE_KEY: str = cfg("LICENSE_PRIVATE_KEY", default="")
    GOOGLE_CLIENT_ID: str = cfg("GOOGLE_CLIENT_ID", default="")
    GOOGLE_CLIENT_SECRET: str = cfg("GOOGLE_CLIENT_SECRET", default="")

    def __init__(self):
        if not self.SECRET_KEY:
            # Generate a random key for development; in production, always set SECRET_KEY env var
            self.SECRET_KEY = secrets.token_urlsafe(32)
            if os.getenv("ENV", "development") == "production":
                raise RuntimeError("SECRET_KEY must be set in production. Set the SECRET_KEY environment variable.")

settings = Settings()