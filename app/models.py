from pydantic import BaseModel

class SearchRequest(BaseModel):
    what: str
    where: str
    polygon: list[tuple[float, float]]