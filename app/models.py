import re

from pydantic import BaseModel, Field, field_validator, model_validator

SAFE_LINK_SCHEMES = ("http://", "https://", "mailto:")


EMAIL = re.compile(r"^[^@\s:/]+@[^@\s]+\.[^@\s]+$")


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
    contact_email: str = Field(pattern=EMAIL.pattern, max_length=200)
    street_address: str = Field(min_length=3, max_length=300)
    apply_url: str = Field(min_length=3, max_length=500)
    employment_type: list[str] | None = Field(default=None, max_length=5)
    # Hidden on the form. People never see it; bots fill in every field.
    website: str | None = Field(default=None, max_length=500)

    # Employers type a link or an email address. The scheme is added here, then
    # checked, because this lands in an href on a public page and "javascript:..."
    # would run when a job seeker taps Apply.
    @field_validator("apply_url")
    @classmethod
    def apply_url_scheme(cls, value):
        value = value.strip()
        if EMAIL.match(value):
            value = f"mailto:{value}"
        elif "://" not in value and not value.lower().startswith("mailto:") and "." in value.split("/")[0]:
            value = f"https://{value}"
        if not is_safe_link(value) or " " in value:
            raise ValueError("Enter a link to your application or an email address.")
        return value


class PlaceRequest(BaseModel):
    address: str | None = Field(default=None, min_length=3, max_length=400)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

    @model_validator(mode="after")
    def address_or_point(self):
        if not self.address and (self.latitude is None or self.longitude is None):
            raise ValueError("send an address, or both latitude and longitude")
        return self


class RemoveRequest(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class OptOutRequest(BaseModel):
    name: str = Field(min_length=2, max_length=200)


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
