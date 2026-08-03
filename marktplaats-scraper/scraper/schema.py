"""Pydantic data model for a single Marktplaats listing."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class SellerType(str, Enum):
    PARTICULIER = "particulier"
    ZAKELIJK = "zakelijk"
    UNKNOWN = "unknown"


class Listing(BaseModel):
    listing_id: Optional[str] = None
    title: str
    price: Optional[float] = None
    price_type: Optional[str] = None  # e.g. FIXED, NEGOTIABLE, ON_REQUEST, EXCHANGE
    category: Optional[str] = None
    condition: Optional[str] = None
    location: Optional[str] = None
    seller_type: SellerType = SellerType.UNKNOWN
    posted_date: Optional[datetime] = None
    url: str
    images: list[str] = Field(default_factory=list)
    description_raw: Optional[str] = None

    @field_validator("url")
    @classmethod
    def _url_must_be_absolute(cls, v: str) -> str:
        if v.startswith("/"):
            v = f"https://www.marktplaats.nl{v}"
        return v

    def dedupe_key(self) -> str:
        return self.url
