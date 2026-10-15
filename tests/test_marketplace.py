from app.db import SessionLocal
from app import models
from .conftest import login


def test_first_registered_user_becomes_admin(client):
    # Database starts empty in the test run: the first registration is admin.
    resp = client.post(
        "/register",
        data={"name": "First", "email": "first@test.com",
              "password": "First123!", "role": "advertiser"},
    )
    assert resp.status_code == 200
    db = SessionLocal()
    user = db.query(models.User).filter(models.User.email == "first@test.com").first()
    assert user is not None
    assert user.role == "admin"
    db.delete(user)
    db.commit()
    db.close()


def test_register_and_login(client, users):
    resp = client.post(
        "/register",
        data={"name": "New Adv", "email": "newadv@test.com",
              "password": "Newadv123!", "role": "advertiser"},
    )
    assert resp.status_code == 200
    assert "access_token" in client.cookies
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert "New Adv" in resp.text


def test_register_duplicate_email_rejected(client, users):
    resp = client.post(
        "/register",
        data={"name": "Dup", "email": "adv1@test.com",
              "password": "Dup12345!", "role": "advertiser"},
    )
    assert resp.status_code == 400


def test_login_wrong_password(client, users):
    resp = client.post("/login", data={"email": "adv1@test.com", "password": "wrong"})
    assert resp.status_code == 401


def test_unauthenticated_dashboard_redirects_to_login(client):
    resp = client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 303
    assert "/login" in resp.headers["location"]


def test_advertiser_cannot_open_listing_form(client, users):
    login(client, "adv1@test.com", "Advertiser123!")
    resp = client.get("/listings/new")
    assert resp.status_code == 403


def test_publisher_create_edit_deactivate_listing(client, users):
    login(client, "pub1@test.com", "Publisher123!")
    resp = client.post(
        "/listings",
        data={"site_name": "My Blog", "site_url": "https://myblog.example.com",
              "niche": "Tech", "price_usd": "75", "turnaround_days": "4",
              "guidelines": "g", "da_score": "40"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    listing_id = int(resp.headers["location"].split("/")[2].split("?")[0])

    resp = client.post(
        f"/listings/{listing_id}/edit",
        data={"site_name": "My Blog Updated", "site_url": "https://myblog.example.com",
              "niche": "Tech", "price_usd": "80", "turnaround_days": "4",
              "guidelines": "g", "da_score": "41"},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    db = SessionLocal()
    item = db.query(models.Listing).filter(models.Listing.id == listing_id).first()
    assert item.site_name == "My Blog Updated"
    assert item.price_usd == 80.0
    db.close()

    resp = client.post(f"/listings/{listing_id}/deactivate", follow_redirects=False)
    assert resp.status_code == 303
    db = SessionLocal()
    item = db.query(models.Listing).filter(models.Listing.id == listing_id).first()
    assert item.is_active is False
    db.close()

    # Deactivated listings disappear from the marketplace.
    resp = client.get("/marketplace")
    assert "My Blog Updated" not in resp.text


def test_publisher_cannot_edit_others_listing(client, users, listing):
    login(client, "pub2@test.com", "Publisher123!")
    resp = client.get(f"/listings/{listing.id}/edit")
    assert resp.status_code == 403
    resp = client.post(
        f"/listings/{listing.id}/edit",
        data={"site_name": "Hijacked", "site_url": "https://x.example.com",
              "niche": "SEO", "price_usd": "1", "turnaround_days": "1",
              "guidelines": "", "da_score": ""},
    )
    assert resp.status_code == 403


def _place_order(client, listing_id):
    resp = client.post(
        f"/listings/{listing_id}/orders",
        data={"brief": "Please write about SEO",
              "target_url": "https://advertiser.example.com/page",
              "anchor_text": "best seo guide"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    return int(resp.headers["location"].split("/")[2].split("?")[0])


def test_advertiser_place_order(client, users, listing):
    login(client, "adv1@test.com", "Advertiser123!")
    order_id = _place_order(client, listing.id)

    db = SessionLocal()
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    assert order.status == "requested"
    assert order.advertiser.email == "adv1@test.com"
    emails = db.query(models.EmailLog).filter(
        models.EmailLog.related_order_id == order_id).all()
    assert len(emails) == 1
    assert emails[0].to_email == "pub1@test.com"
    db.close()


def test_publisher_cannot_place_order(client, users, listing):
    login(client, "pub1@test.com", "Publisher123!")
    resp = client.post(
        f"/listings/{listing.id}/orders",
        data={"brief": "x", "target_url": "https://x.example.com",
              "anchor_text": "x"},
        follow_redirects=False,
    )
    assert resp.status_code == 403


def test_full_order_flow_with_emails(client, users, listing):
    login(client, "adv1@test.com", "Advertiser123!")
    order_id = _place_order(client, listing.id)

    # Mock payment keeps status at requested.
    resp = client.post(f"/orders/{order_id}/pay", data={}, follow_redirects=False)
    assert resp.status_code == 303
    db = SessionLocal()
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    assert order.status == "requested"
    assert order.mock_payment_ref.startswith("MOCK-")
    db.close()

    login(client, "pub1@test.com", "Publisher123!")
    for step in ["accepted", "in_progress", "delivered"]:
        resp = client.post(f"/orders/{order_id}/status",
                           data={"new_status": step}, follow_redirects=False)
        assert resp.status_code == 303, step

    login(client, "adv1@test.com", "Advertiser123!")
    resp = client.post(f"/orders/{order_id}/status",
                       data={"new_status": "completed"}, follow_redirects=False)
    assert resp.status_code == 303

    db = SessionLocal()
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    assert order.status == "completed"
    emails = db.query(models.EmailLog).filter(
        models.EmailLog.related_order_id == order_id
    ).order_by(models.EmailLog.id).all()
    assert len(emails) == 5
    recipients = [e.to_email for e in emails]
    assert recipients == ["pub1@test.com", "adv1@test.com", "adv1@test.com",
                          "adv1@test.com", "pub1@test.com"]
    db.close()


def test_rejection_flow(client, users, listing):
    login(client, "adv1@test.com", "Advertiser123!")
    order_id = _place_order(client, listing.id)

    login(client, "pub1@test.com", "Publisher123!")
    resp = client.post(f"/orders/{order_id}/status",
                       data={"new_status": "rejected"}, follow_redirects=False)
    assert resp.status_code == 303

    db = SessionLocal()
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    assert order.status == "rejected"
    emails = db.query(models.EmailLog).filter(
        models.EmailLog.related_order_id == order_id).all()
    assert len(emails) == 2  # requested + rejected
    assert emails[-1].to_email == "adv1@test.com"
    db.close()

    # Rejected is terminal.
    resp = client.post(f"/orders/{order_id}/status",
                       data={"new_status": "accepted"}, follow_redirects=False)
    assert resp.status_code == 400


def test_invalid_transition_returns_400(client, users, listing):
    login(client, "adv1@test.com", "Advertiser123!")
    order_id = _place_order(client, listing.id)

    # Advertiser cannot accept their own order, and requested cannot jump to completed.
    resp = client.post(f"/orders/{order_id}/status",
                       data={"new_status": "accepted"}, follow_redirects=False)
    assert resp.status_code == 400
    resp = client.post(f"/orders/{order_id}/status",
                       data={"new_status": "completed"}, follow_redirects=False)
    assert resp.status_code == 400

    db = SessionLocal()
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    assert order.status == "requested"
    db.close()


def test_admin_can_view_all_orders(client, users):
    login(client, "admin@test.com", "Admin123!")
    resp = client.get("/admin/orders")
    assert resp.status_code == 200
    resp = client.get("/admin/email-log")
    assert resp.status_code == 200


def test_non_admin_cannot_view_admin_pages(client, users):
    login(client, "adv1@test.com", "Advertiser123!")
    assert client.get("/admin/orders").status_code == 403
    assert client.get("/admin/email-log").status_code == 403


def test_api_listings_and_order_flow(client, users, listing):
    # Public listing list.
    resp = client.get("/api/listings")
    assert resp.status_code == 200
    assert any(item["site_name"] == "Test Site" for item in resp.json())

    # Advertiser creates an order via API.
    login(client, "adv1@test.com", "Advertiser123!")
    resp = client.post("/api/orders", json={
        "listing_id": listing.id, "brief": "API brief",
        "target_url": "https://advertiser.example.com/a", "anchor_text": "api anchor"})
    assert resp.status_code == 201
    order_id = resp.json()["id"]
    assert resp.json()["status"] == "requested"

    # Publisher moves it via API; invalid jump is 400.
    login(client, "pub1@test.com", "Publisher123!")
    resp = client.post(f"/api/orders/{order_id}/status", json={"status": "delivered"})
    assert resp.status_code == 400
    resp = client.post(f"/api/orders/{order_id}/status", json={"status": "accepted"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "accepted"

    # Unauthenticated API access is 401.
    fresh = client.__class__(client.app)
    assert fresh.post("/api/orders", json={}).status_code == 401
