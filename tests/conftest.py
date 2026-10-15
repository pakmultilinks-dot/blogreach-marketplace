import os

# Must be set before app modules are imported: isolated test database, no seed.
os.environ["DATABASE_URL"] = "sqlite:////tmp/blogreach_test.db"
os.environ["SEED_ON_STARTUP"] = "false"
os.environ["SECRET_KEY"] = "test-secret-key"

if os.path.exists("/tmp/blogreach_test.db"):
    os.remove("/tmp/blogreach_test.db")

import pytest
from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app
from app import models
from app.auth import hash_password

Base.metadata.create_all(bind=engine)


def make_user(name, email, password, role):
    db = SessionLocal()
    user = models.User(
        name=name, email=email, password_hash=hash_password(password), role=role
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.close()
    return user


@pytest.fixture(scope="session")
def users():
    admin = make_user("Admin", "admin@test.com", "Admin123!", "admin")
    pub1 = make_user("Pub One", "pub1@test.com", "Publisher123!", "publisher")
    pub2 = make_user("Pub Two", "pub2@test.com", "Publisher123!", "publisher")
    adv = make_user("Adv One", "adv1@test.com", "Advertiser123!", "advertiser")
    return {"admin": admin, "pub1": pub1, "pub2": pub2, "adv": adv}


@pytest.fixture(scope="session")
def listing(users):
    db = SessionLocal()
    item = models.Listing(
        publisher_id=users["pub1"].id,
        site_name="Test Site",
        site_url="https://testsite.example.com",
        niche="SEO",
        price_usd=100.0,
        turnaround_days=5,
        guidelines="Test guidelines",
        da_score=50,
        is_active=True,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    db.close()
    return item


@pytest.fixture()
def client():
    return TestClient(app)


def login(client, email, password):
    resp = client.post("/login", data={"email": email, "password": password})
    assert resp.status_code == 200
    return client
