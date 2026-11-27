from app.core.config import Settings
from fastapi import HTTPException

settings = Settings()

def require_cloud_edition():
    if settings.is_community:
        raise HTTPException(status_code = 403, detail = "This operation is unavailable in community edition")
