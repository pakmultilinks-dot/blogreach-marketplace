import os
from pathlib import Path
from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from . import models
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


# ---------- Dashboard (role aware, extended in later steps) ----------

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    user, redirect = current_user_or_redirect(request, db)
    if redirect:
        return redirect
    return render(request, "dashboard.html", db)
