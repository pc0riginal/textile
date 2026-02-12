import os
import secrets
from decouple import config

class Settings:
    MONGODB_URL: str = config("MONGODB_URL", default="mongodb://localhost:27017")
    DATABASE_NAME: str = config("DATABASE_NAME", default="textile_erp")
    SECRET_KEY: str = config("SECRET_KEY", default="")
    ALGORITHM: str = config("ALGORITHM", default="HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = config("ACCESS_TOKEN_EXPIRE_MINUTES", default=480, cast=int)
    UPLOAD_DIR: str = config("UPLOAD_DIR", default="app/static/uploads")
    ALLOWED_ORIGINS: str = config("ALLOWED_ORIGINS", default="http://localhost:8000")
    ADMIN_SECRET: str = config("ADMIN_SECRET", default="")

    def __init__(self):
        if not self.SECRET_KEY:
            # Generate a random key for development; in production, always set SECRET_KEY env var
            self.SECRET_KEY = secrets.token_urlsafe(32)
            if os.getenv("ENV", "development") == "production":
                raise RuntimeError("SECRET_KEY must be set in production. Set the SECRET_KEY environment variable.")

settings = Settings()