import os
import uuid
from pathlib import Path
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from . import models
from . import orders as orders_mod
from . import schemas
from .auth import (
    get_current_user,
    hash_password,
    set_login_cookie,
    verify_password,
    COOKIE_NAME,
)
from .db import Base, engine, get_db
from .seed import seed_demo_data

APP_DIR = Path(__file__).parent

app = FastAPI(title="BlogReach Marketplace")
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
templates = Jinja2Templates(directory=APP_DIR / "templates")


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    if os.getenv("SEED_ON_STARTUP", "true").lower() != "false":
        db = next(get_db())
        try:
            seed_demo_data(db)
        finally:
            db.close()


def render(request: Request, name: str, db: Session, context: dict | None = None,
           message: str | None = None, status_code: int = 200):
    ctx = {
        "request": request,
        "user": get_current_user(request, db),
        "message": message or request.query_params.get("msg"),
    }
    if context:
        ctx.update(context)
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)


def current_user_or_redirect(request: Request, db: Session):
    user = get_current_user(request, db)
    if user is None:
        return None, RedirectResponse("/login?msg=Please+login+first", status_code=303)
    return user, None


# ---------- Landing ----------

@app.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    listings = (
        db.query(models.Listing)
        .filter(models.Listing.is_active.is_(True))
        .order_by(models.Listing.created_at.desc())
        .limit(6)
        .all()
    )
    return render(request, "index.html", db, {"listings": listings})


# ---------- Auth ----------

@app.get("/register", response_class=HTMLResponse)
def register_form(request: Request, db: Session = Depends(get_db)):
    return render(request, "register.html", db)


@app.post("/register")
def register(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form("advertiser"),
    db: Session = Depends(get_db),
):
    email = email.strip().lower()
    if role not in ("publisher", "advertiser"):
        role = "advertiser"
    if len(password) < 8:
        return render(request, "register.html", db,
                      message="Password must be at least 8 characters.", status_code=400)
    if db.query(models.User).filter(models.User.email == email).first():
        return render(request, "register.html", db,
                      message="That email is already registered.", status_code=400)
    # First-ever registered user becomes admin automatically.
    if db.query(models.User).count() == 0:
        role = "admin"
    user = models.User(
        name=name.strip(), email=email,
        password_hash=hash_password(password), role=role,
    )
    db.add(user)
    db.commit()
    response = RedirectResponse("/dashboard?msg=Welcome+to+BlogReach", status_code=303)
    set_login_cookie(response, email)
    return response


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request, db: Session = Depends(get_db)):
    return render(request, "login.html", db)


@app.post("/login")
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.email == email.strip().lower()).first()
    if not user or not verify_password(password, user.password_hash):
        return render(request, "login.html", db,
                      message="Invalid email or password.", status_code=401)
    response = RedirectResponse("/dashboard", status_code=303)
    set_login_cookie(response, user.email)
    return response


@app.post("/logout")
def logout():
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response


# ---------- Dashboard (role aware) ----------

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    user, redirect = current_user_or_redirect(request, db)
    if redirect:
        return redirect
    ctx = {}
    if user.role == "publisher":
        ctx["my_listings"] = (
            db.query(models.Listing)
            .filter(models.Listing.publisher_id == user.id)
            .order_by(models.Listing.created_at.desc())
            .all()
        )
        ctx["incoming_orders"] = (
            db.query(models.Order)
            .filter(models.Order.publisher_id == user.id)
            .order_by(models.Order.created_at.desc())
            .all()
        )
    elif user.role == "advertiser":
        ctx["my_orders"] = (
            db.query(models.Order)
            .filter(models.Order.advertiser_id == user.id)
            .order_by(models.Order.created_at.desc())
            .all()
        )
    return render(request, "dashboard.html", db, ctx)


# ---------- Marketplace browse ----------

@app.get("/marketplace", response_class=HTMLResponse)
def marketplace(
    request: Request,
    niche: str = "",
    min_price: str = "",
    max_price: str = "",
    q: str = "",
    db: Session = Depends(get_db),
):
    query = db.query(models.Listing).filter(models.Listing.is_active.is_(True))
    if niche:
        query = query.filter(models.Listing.niche == niche)
    if min_price:
        try:
            query = query.filter(models.Listing.price_usd >= float(min_price))
        except ValueError:
            pass
    if max_price:
        try:
            query = query.filter(models.Listing.price_usd <= float(max_price))
        except ValueError:
            pass
    if q:
        like = f"%{q}%"
        query = query.filter(
            (models.Listing.site_name.ilike(like)) | (models.Listing.niche.ilike(like))
        )
    listings = query.order_by(models.Listing.created_at.desc()).all()
    niches = [
        row[0]
        for row in db.query(models.Listing.niche)
        .filter(models.Listing.is_active.is_(True))
        .distinct()
        .order_by(models.Listing.niche)
        .all()
    ]
    return render(
        request,
        "marketplace.html",
        db,
        {
            "listings": listings,
            "niches": niches,
            "filters": {"niche": niche, "min_price": min_price, "max_price": max_price, "q": q},
        },
    )


# ---------- Listings CRUD (publishers) ----------

def publisher_or_403(request: Request, db: Session):
    user, redirect = current_user_or_redirect(request, db)
    if redirect:
        return None, None, redirect
    if user.role not in ("publisher", "admin"):
        return None, None, render(request, "error.html", db,
                                  message="Only publishers can manage listings.",
                                  status_code=403)
    return user, db, None


@app.get("/listings/new", response_class=HTMLResponse)
def listing_new_form(request: Request, db: Session = Depends(get_db)):
    user, _, denied = publisher_or_403(request, db)
    if denied:
        return denied
    return render(request, "listing_form.html", db, {"listing": None})


@app.post("/listings")
def listing_create(
    request: Request,
    site_name: str = Form(...),
    site_url: str = Form(...),
    niche: str = Form(...),
    price_usd: float = Form(...),
    turnaround_days: int = Form(...),
    guidelines: str = Form(""),
    da_score: str = Form(""),
    db: Session = Depends(get_db),
):
    user, _, denied = publisher_or_403(request, db)
    if denied:
        return denied
    try:
        da = int(da_score) if da_score.strip() else None
    except ValueError:
        da = None
    listing = models.Listing(
        publisher_id=user.id,
        site_name=site_name.strip(),
        site_url=site_url.strip(),
        niche=niche.strip(),
        price_usd=price_usd,
        turnaround_days=turnaround_days,
        guidelines=guidelines.strip(),
        da_score=da,
    )
    db.add(listing)
    db.commit()
    return RedirectResponse(f"/listings/{listing.id}?msg=Listing+published", status_code=303)


@app.get("/listings/{listing_id}", response_class=HTMLResponse)
def listing_detail(request: Request, listing_id: int, db: Session = Depends(get_db)):
    listing = db.query(models.Listing).filter(models.Listing.id == listing_id).first()
    if not listing:
        return render(request, "error.html", db, message="Listing not found.", status_code=404)
    return render(request, "listing_detail.html", db, {"listing": listing})


def listing_owner_or_403(request: Request, db: Session, listing_id: int):
    user, redirect = current_user_or_redirect(request, db)
    if redirect:
        return None, None, redirect
    listing = db.query(models.Listing).filter(models.Listing.id == listing_id).first()
    if not listing:
        return None, None, render(request, "error.html", db,
                                  message="Listing not found.", status_code=404)
    if listing.publisher_id != user.id and user.role != "admin":
        return None, None, render(request, "error.html", db,
                                  message="You can only edit your own listings.",
                                  status_code=403)
    return user, listing, None


@app.get("/listings/{listing_id}/edit", response_class=HTMLResponse)
def listing_edit_form(request: Request, listing_id: int, db: Session = Depends(get_db)):
    _, listing, denied = listing_owner_or_403(request, db, listing_id)
    if denied:
        return denied
    return render(request, "listing_form.html", db, {"listing": listing})


@app.post("/listings/{listing_id}/edit")
def listing_edit(
    request: Request,
    listing_id: int,
    site_name: str = Form(...),
    site_url: str = Form(...),
    niche: str = Form(...),
    price_usd: float = Form(...),
    turnaround_days: int = Form(...),
    guidelines: str = Form(""),
    da_score: str = Form(""),
    db: Session = Depends(get_db),
):
    _, listing, denied = listing_owner_or_403(request, db, listing_id)
    if denied:
        return denied
    try:
        da = int(da_score) if da_score.strip() else None
    except ValueError:
        da = None
    listing.site_name = site_name.strip()
    listing.site_url = site_url.strip()
    listing.niche = niche.strip()
    listing.price_usd = price_usd
    listing.turnaround_days = turnaround_days
    listing.guidelines = guidelines.strip()
    listing.da_score = da
    db.commit()
    return RedirectResponse(f"/listings/{listing.id}?msg=Listing+updated", status_code=303)


@app.post("/listings/{listing_id}/deactivate")
def listing_deactivate(request: Request, listing_id: int, db: Session = Depends(get_db)):
    _, listing, denied = listing_owner_or_403(request, db, listing_id)
    if denied:
        return denied
    listing.is_active = False
    db.commit()
    return RedirectResponse(f"/listings/{listing.id}?msg=Listing+deactivated", status_code=303)


@app.post("/listings/{listing_id}/activate")
def listing_activate(request: Request, listing_id: int, db: Session = Depends(get_db)):
    _, listing, denied = listing_owner_or_403(request, db, listing_id)
    if denied:
        return denied
    listing.is_active = True
    db.commit()
    return RedirectResponse(f"/listings/{listing.id}?msg=Listing+activated", status_code=303)


# ---------- Orders ----------

@app.post("/listings/{listing_id}/orders")
def order_create(
    request: Request,
    listing_id: int,
    brief: str = Form(...),
    target_url: str = Form(...),
    anchor_text: str = Form(...),
    db: Session = Depends(get_db),
):
    user, redirect = current_user_or_redirect(request, db)
    if redirect:
        return redirect
    if user.role != "advertiser":
        return render(request, "error.html", db,
                      message="Only advertisers can place orders.", status_code=403)
    listing = db.query(models.Listing).filter(models.Listing.id == listing_id).first()
    if not listing:
        return render(request, "error.html", db, message="Listing not found.", status_code=404)
    if not listing.is_active:
        return render(request, "error.html", db,
                      message="This listing is not active.", status_code=400)
    order = models.Order(
        listing_id=listing.id,
        advertiser_id=user.id,
        publisher_id=listing.publisher_id,
        brief=brief.strip(),
        target_url=target_url.strip(),
        anchor_text=anchor_text.strip(),
        status="requested",
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    orders_mod._notify(db, order, "requested")
    return RedirectResponse(f"/orders/{order.id}/pay?msg=Order+created", status_code=303)


def order_visible_or_403(request: Request, db: Session, order_id: int):
    user, redirect = current_user_or_redirect(request, db)
    if redirect:
        return None, None, redirect
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order:
        return None, None, render(request, "error.html", db,
                                  message="Order not found.", status_code=404)
    if user.role != "admin" and user.id not in (order.advertiser_id, order.publisher_id):
        return None, None, render(request, "error.html", db,
                                  message="You cannot view this order.", status_code=403)
    return user, order, None


@app.get("/orders/{order_id}", response_class=HTMLResponse)
def order_detail(request: Request, order_id: int, db: Session = Depends(get_db)):
    user, order, denied = order_visible_or_403(request, db, order_id)
    if denied:
        return denied
    return render(request, "order_detail.html", db, {
        "order": order,
        "statuses": orders_mod.STATUSES,
        "next_actions": orders_mod.allowed_next(order, user),
    })


@app.post("/orders/{order_id}/status")
def order_change_status(
    request: Request,
    order_id: int,
    new_status: str = Form(...),
    db: Session = Depends(get_db),
):
    user, order, denied = order_visible_or_403(request, db, order_id)
    if denied:
        return denied
    try:
        orders_mod.change_status(db, order, user, new_status)
    except ValueError as exc:
        return render(request, "error.html", db, message=str(exc), status_code=400)
    return RedirectResponse(f"/orders/{order.id}?msg=Status+updated", status_code=303)


# ---------- JSON API ----------

def api_user(request: Request, db: Session = Depends(get_db)) -> models.User:
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def _apply_listing_filters(query, niche: str, min_price: str, max_price: str, q: str):
    if niche:
        query = query.filter(models.Listing.niche == niche)
    if min_price:
        try:
            query = query.filter(models.Listing.price_usd >= float(min_price))
        except ValueError:
            pass
    if max_price:
        try:
            query = query.filter(models.Listing.price_usd <= float(max_price))
        except ValueError:
            pass
    if q:
        like = f"%{q}%"
        query = query.filter(
            (models.Listing.site_name.ilike(like)) | (models.Listing.niche.ilike(like))
        )
    return query


@app.get("/api/listings", response_model=list[schemas.ListingOut])
def api_listings(
    niche: str = "",
    min_price: str = "",
    max_price: str = "",
    q: str = "",
    db: Session = Depends(get_db),
):
    query = _apply_listing_filters(
        db.query(models.Listing).filter(models.Listing.is_active.is_(True)),
        niche, min_price, max_price, q,
    )
    return query.order_by(models.Listing.created_at.desc()).all()


@app.post("/api/listings", response_model=schemas.ListingOut, status_code=201)
def api_listing_create(
    data: schemas.ListingCreate,
    user: models.User = Depends(api_user),
    db: Session = Depends(get_db),
):
    if user.role not in ("publisher", "admin"):
        raise HTTPException(status_code=403, detail="Only publishers can create listings")
    listing = models.Listing(publisher_id=user.id, **data.model_dump())
    db.add(listing)
    db.commit()
    db.refresh(listing)
    return listing


@app.post("/api/orders", response_model=schemas.OrderOut, status_code=201)
def api_order_create(
    data: schemas.OrderCreate,
    user: models.User = Depends(api_user),
    db: Session = Depends(get_db),
):
    if user.role != "advertiser":
        raise HTTPException(status_code=403, detail="Only advertisers can place orders")
    listing = db.query(models.Listing).filter(models.Listing.id == data.listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    if not listing.is_active:
        raise HTTPException(status_code=400, detail="Listing is not active")
    order = models.Order(
        listing_id=listing.id,
        advertiser_id=user.id,
        publisher_id=listing.publisher_id,
        brief=data.brief,
        target_url=data.target_url,
        anchor_text=data.anchor_text,
        status="requested",
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    orders_mod._notify(db, order, "requested")
    return order


@app.get("/api/orders/{order_id}", response_model=schemas.OrderOut)
def api_order_get(
    order_id: int,
    user: models.User = Depends(api_user),
    db: Session = Depends(get_db),
):
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if user.role != "admin" and user.id not in (order.advertiser_id, order.publisher_id):
        raise HTTPException(status_code=403, detail="You cannot view this order")
    return order


@app.post("/api/orders/{order_id}/status", response_model=schemas.OrderOut)
def api_order_status(
    order_id: int,
    data: schemas.StatusUpdate,
    user: models.User = Depends(api_user),
    db: Session = Depends(get_db),
):
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if user.id not in (order.advertiser_id, order.publisher_id):
        raise HTTPException(status_code=403, detail="Only the order's publisher or advertiser can change its status")
    try:
        orders_mod.change_status(db, order, user, data.status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return order


# ---------- Admin ----------

def admin_or_403(request: Request, db: Session):
    user, redirect = current_user_or_redirect(request, db)
    if redirect:
        return None, redirect
    if user.role != "admin":
        return None, render(request, "error.html", db,
                            message="Admin access only.", status_code=403)
    return user, None


@app.get("/admin/orders", response_class=HTMLResponse)
def admin_orders(request: Request, status: str = "", db: Session = Depends(get_db)):
    _, denied = admin_or_403(request, db)
    if denied:
        return denied
    query = db.query(models.Order).order_by(models.Order.created_at.desc())
    if status in orders_mod.STATUSES:
        query = query.filter(models.Order.status == status)
    return render(request, "admin_orders.html", db, {
        "orders": query.all(),
        "statuses": orders_mod.STATUSES,
        "status_filter": status,
    })


@app.get("/admin/email-log", response_class=HTMLResponse)
def admin_email_log(request: Request, db: Session = Depends(get_db)):
    _, denied = admin_or_403(request, db)
    if denied:
        return denied
    emails = db.query(models.EmailLog).order_by(models.EmailLog.created_at.desc()).all()
    return render(request, "admin_email_log.html", db, {"emails": emails})


# ---------- Mock payment ----------

@app.get("/orders/{order_id}/pay", response_class=HTMLResponse)
def pay_form(request: Request, order_id: int, db: Session = Depends(get_db)):
    user, order, denied = order_visible_or_403(request, db, order_id)
    if denied:
        return denied
    if user.id != order.advertiser_id and user.role != "admin":
        return render(request, "error.html", db,
                      message="Only the ordering advertiser can pay.", status_code=403)
    if order.mock_payment_ref:
        return RedirectResponse(f"/orders/{order.id}", status_code=303)
    return render(request, "pay.html", db, {"order": order})


@app.post("/orders/{order_id}/pay")
def pay_submit(request: Request, order_id: int, db: Session = Depends(get_db)):
    user, order, denied = order_visible_or_403(request, db, order_id)
    if denied:
        return denied
    if user.id != order.advertiser_id and user.role != "admin":
        return render(request, "error.html", db,
                      message="Only the ordering advertiser can pay.", status_code=403)
    if not order.mock_payment_ref:
        order.mock_payment_ref = "MOCK-" + uuid.uuid4().hex[:12].upper()
        db.commit()
    return RedirectResponse(f"/orders/{order.id}?msg=Mock+payment+recorded", status_code=303)
