from typing import Optional

from pydantic import BaseModel


class ProviderResultItem(BaseModel):
    index: int
    file_type: str
    file_name: str
    file_path: str
    mime_type: str
    file_size: int
    width: Optional[int] = None
    height: Optional[int] = None
    duration_seconds: Optional[float] = None
    checksum: Optional[str] = None
