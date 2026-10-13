from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    fal_key: str = ""
    generation_provider: str = "mock"
    s3_endpoint: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = "kitframe-assets"
    s3_region: str = "eu-west-1"
    s3_use_path_style: bool = True
    qc_pass_threshold: float = 0.90
    qc_fail_threshold: float = 0.60
    qc_check_floor: float = 0.75
    delta_e_curve_scale: float = 20.0
    delta_e_curve_exponent: float = 1.0
    extract_timeout_seconds: float = 30.0
    copy_timeout_seconds: float = 30.0
    image_ops_timeout_seconds: float = 60.0
    color_weight: float = 0.5
    logo_weight: float = 0.3
    resolution_weight: float = 0.2
    embedding_dim: int = 64
    fal_model_id: str = "fal-ai/flux/dev"


@lru_cache
def get_settings() -> Settings:
    return Settings()
