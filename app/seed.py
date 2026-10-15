from sqlalchemy.orm import Session
from . import models
from .auth import hash_password

DEMO_USERS = [
    ("Admin User", "admin@blogreach.com", "Admin123!", "admin"),
    ("Demo Publisher", "publisher@blogreach.com", "Publisher123!", "publisher"),
    ("Demo Advertiser", "advertiser@blogreach.com", "Advertiser123!", "advertiser"),
]

DEMO_LISTINGS = [
    {
        "site_name": "SEO Growth Hub",
        "site_url": "https://seogrowthhub.example.com",
        "niche": "SEO",
        "price_usd": 120.0,
        "turnaround_days": 5,
        "guidelines": "Original content only, 1000+ words, up to 2 dofollow links. No casino or adult topics.",
        "da_score": 58,
    },
    {
        "site_name": "Tech Daily Digest",
        "site_url": "https://techdailydigest.example.com",
        "niche": "Tech",
        "price_usd": 95.0,
        "turnaround_days": 3,
        "guidelines": "Tech news and tutorials. We write or accept drafts. One link in body, one in author bio.",
        "da_score": 51,
    },
    {
        "site_name": "Wellness Wire",
        "site_url": "https://wellnesswire.example.com",
        "niche": "Health",
        "price_usd": 80.0,
        "turnaround_days": 7,
        "guidelines": "Evidence-based health content reviewed by our editor. No medical claims without sources.",
        "da_score": 44,
    },
    {
        "site_name": "Money Matters Blog",
        "site_url": "https://moneymattersblog.example.com",
        "niche": "Finance",
        "price_usd": 150.0,
        "turnaround_days": 5,
        "guidelines": "Personal finance and investing. No financial advice guarantees. Disclosure of sponsored content.",
        "da_score": 62,
    },
    {
        "site_name": "Wander Path",
        "site_url": "https://wanderpath.example.com",
        "niche": "Travel",
        "price_usd": 70.0,
        "turnaround_days": 4,
        "guidelines": "Destination guides with original photos preferred. Family friendly content only.",
        "da_score": 39,
    },
    {
        "site_name": "Tasty Bytes",
        "site_url": "https://tastybytes.example.com",
        "niche": "Food",
        "price_usd": 60.0,
        "turnaround_days": 3,
        "guidelines": "Recipes and restaurant features. Original photography required for recipe posts.",
        "da_score": 47,
    },
]


def seed_demo_data(db: Session):
    """Create demo users and listings on a fresh database. Idempotent."""
    if db.query(models.User).count() > 0:
        return
    users = {}
    for name, email, password, role in DEMO_USERS:
        user = models.User(
            name=name,
            email=email,
            password_hash=hash_password(password),
            role=role,
        )
        db.add(user)
        users[role] = user
    db.commit()
    publisher = users["publisher"]
    for item in DEMO_LISTINGS:
        db.add(models.Listing(publisher_id=publisher.id, **item))
    db.commit()
    print("[seed] demo users and listings created", flush=True)
