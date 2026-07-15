from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel


class Settings(BaseModel):
    app_name: str = "智慧排班 Agent"
    api_prefix: str = "/api"
    store_id: str = "fresh_store_001"
    store_name: str = "社区生鲜示范店"
    business_today: str = "2026-07-15"
    base_dir: Path = Path(__file__).resolve().parents[1]

    @property
    def seed_dir(self) -> Path:
        return self.base_dir / "seed"

    @property
    def data_dir(self) -> Path:
        return self.base_dir / "data"

    @property
    def database_path(self) -> Path:
        return self.data_dir / "demo.sqlite"

    @property
    def llm_config_path(self) -> Path:
        return self.base_dir.parent / "config" / "llm.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()
