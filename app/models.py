from pydantic import BaseModel

class SearchRequest(BaseModel):
    what: str
    polygon: list[tuple[float, float]]