from pydantic import BaseModel


class ListingOut(BaseModel):
    id: int
    site_name: str
    site_url: str
    niche: str
    price_usd: float
    turnaround_days: int
    guidelines: str
    da_score: int | None
    is_active: bool
    publisher_id: int

    model_config = {"from_attributes": True}


class ListingCreate(BaseModel):
    site_name: str
    site_url: str
    niche: str
    price_usd: float
    turnaround_days: int
    guidelines: str = ""
    da_score: int | None = None


class OrderCreate(BaseModel):
    listing_id: int
    brief: str
    target_url: str
    anchor_text: str


class OrderOut(BaseModel):
    id: int
    listing_id: int
    advertiser_id: int
    publisher_id: int
    brief: str
    target_url: str
    anchor_text: str
    status: str
    mock_payment_ref: str | None

    model_config = {"from_attributes": True}


class StatusUpdate(BaseModel):
    status: str
