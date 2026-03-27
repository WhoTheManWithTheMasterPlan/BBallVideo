from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://bballvideo:localdev@localhost:5432/bballvideo"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Storage (local filesystem on TrueNAS)
    storage_base_path: str = "/mnt/apps/bballvideo/storage"
    storage_max_gb: int = 1024  # 1 TB limit

    # Supabase Auth
    supabase_url: str = ""
    supabase_key: str = ""

    # CORS
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://192.168.68.10:3001",
        "http://bball.adamsspecialtyservices.com",
        "https://bball.adamsspecialtyservices.com",
    ]

    # Remote storage (GPU worker → TrueNAS file transfer via SCP)
    remote_storage_enabled: bool = False
    remote_storage_host: str = "192.168.68.10"
    remote_storage_user: str = "root"
    remote_storage_path: str = "/mnt/apps/bballvideo/storage"

    # Processing
    max_video_size_mb: int = 2048
    supported_formats: list[str] = [".mp4", ".mov", ".avi", ".mkv"]

    # Basketball detection model (ball + hoop)
    basketball_model_path: str = "ml/models/shot-tracker/best.pt"

    model_config = {"env_file": [".env", ".env.worker"], "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
