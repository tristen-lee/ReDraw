from pydantic import BaseModel, Field, field_validator

SAFE_LINK_SCHEMES = ("http://", "https://", "mailto:")


def is_safe_link(url):
    return bool(url) and url.strip().lower().startswith(SAFE_LINK_SCHEMES)


class SearchRequest(BaseModel):
    polygon: list[tuple[float, float]] = Field(min_length=3)
    what: str | None = None
    include_blanket: bool = False
    limit: int = Field(default=500, ge=1, le=2000)


class JobSubmission(BaseModel):
    employer: str = Field(min_length=2, max_length=200)
    title: str = Field(min_length=2, max_length=200)
    description: str = Field(min_length=20, max_length=20000)
    town: str = Field(min_length=2, max_length=120)
    contact_email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=200)
    street_address: str | None = Field(default=None, max_length=300)
    apply_url: str | None = Field(default=None, max_length=500)
    employment_type: list[str] | None = Field(default=None, max_length=5)

    # Rendered into an href on a public page. HTML escaping does nothing about
    # the scheme, so "javascript:..." would run when a job seeker taps Apply.
    @field_validator("apply_url")
    @classmethod
    def apply_url_scheme(cls, value):
        if value is None or not value.strip():
            return None
        if not is_safe_link(value):
            raise ValueError("must start with http://, https:// or mailto:")
        return value.strip()


class ReviewRequest(BaseModel):
    approve: bool
    note: str | None = Field(default=None, max_length=500)


class JobLocation(BaseModel):
    raw_location: str | None
    precision: str
    latitude: float
    longitude: float


class Job(BaseModel):
    id: int
    path: str
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
