from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    polygon: list[tuple[float, float]] = Field(min_length=3)
    what: str | None = None
    include_blanket: bool = False
    limit: int = Field(default=500, ge=1, le=2000)


class JobLocation(BaseModel):
    raw_location: str | None
    precision: str
    latitude: float
    longitude: float


class Job(BaseModel):
    id: int
    source: str
    title: str
    employer: str | None
    url: str | None
    date_posted: str | None
    salary_min: float | None
    salary_max: float | None
    salary_interval: str | None
    is_blanket: bool
    locations: list[JobLocation]
