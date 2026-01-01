from decouple import config

class Settings:
    MONGODB_URL: str = config("MONGODB_URL", default="mongodb://localhost:27017")
    DATABASE_NAME: str = config("DATABASE_NAME", default="textile_erp")
    SECRET_KEY: str = config("SECRET_KEY", default="your-secret-key")
    ALGORITHM: str = config("ALGORITHM", default="HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = config("ACCESS_TOKEN_EXPIRE_MINUTES", default=30, cast=int)
    UPLOAD_DIR: str = config("UPLOAD_DIR", default="app/static/uploads")

settings = Settings()