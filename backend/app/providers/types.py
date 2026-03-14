from pydantic import BaseModel


class ProviderResultItem(BaseModel):
    index: int
    file_type: str
    file_name: str
    file_path: str
    mime_type: str
    file_size: int
