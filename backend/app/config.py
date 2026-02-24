from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import List


class Settings(BaseSettings):
    # AWS
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "us-east-1"

    # Database
    database_url: str = "sqlite:///./safety_inspector.db"

    # File storage
    upload_dir: str = "uploads"
    use_s3: bool = False
    s3_bucket: str = ""

    # Nova model IDs
    nova_pro_model_id: str   = "amazon.nova-pro-v1:0"     # multimodal image analysis
    nova_lite_model_id: str  = "amazon.nova-lite-v1:0"    # OSHA mapping + reports
    nova_sonic_model_id: str = "amazon.nova-sonic-v1:0"   # real-time voice

    # CORS
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",")]

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
