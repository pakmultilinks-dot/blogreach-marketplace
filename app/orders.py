from sqlalchemy.orm import Session
from . import models
from .email_service import EmailService

# Allowed transitions: current status -> list of (next status, who may do it).
# "publisher" = the listing owner, "advertiser" = the ordering advertiser.
TRANSITIONS: dict[str, list[tuple[str, str]]] = {
    "requested": [("accepted", "publisher"), ("rejected", "publisher")],
    "accepted": [("in_progress", "publisher"), ("rejected", "publisher")],
    "in_progress": [("delivered", "publisher"), ("rejected", "publisher")],
    "delivered": [("completed", "advertiser")],
    "completed": [],
    "rejected": [],
}

STATUSES = list(TRANSITIONS.keys())


def actor_role(order: models.Order, user: models.User) -> str | None:
    if user.id == order.publisher_id:
        return "publisher"
    if user.id == order.advertiser_id:
        return "advertiser"
    return None


def allowed_next(order: models.Order, user: models.User) -> list[str]:
    role = actor_role(order, user)
    return [next_status for next_status, who in TRANSITIONS[order.status] if who == role]


def change_status(db: Session, order: models.Order, user: models.User, new_status: str) -> models.Order:
    """Validate and apply a status change, notifying the other party by email.

    Raises ValueError with a human message when the transition is invalid.
    """
    role = actor_role(order, user)
    valid = [(s, w) for s, w in TRANSITIONS.get(order.status, []) if w == role]
    if new_status not in [s for s, _ in valid]:
        raise ValueError(
            f"Cannot move order from '{order.status}' to '{new_status}' as {role or 'viewer'}."
        )
    order.status = new_status
    db.commit()
    db.refresh(order)
    _notify(db, order, new_status)
    return order


def _notify(db: Session, order: models.Order, new_status: str):
    listing = order.listing
    advertiser = order.advertiser
    publisher = order.publisher
    order_url = f"/orders/{order.id}"
    if new_status == "requested":
        EmailService.send(
            db, publisher.email,
            f"New order request for {listing.site_name}",
            f"Hi {publisher.name},\n\n{advertiser.name} requested a guest post placement "
            f"on {listing.site_name} (${listing.price_usd:.2f}).\n\n"
            f"Brief: {order.brief}\nTarget URL: {order.target_url}\n"
            f"Anchor text: {order.anchor_text}\n\nReview it here: {order_url}",
            related_order_id=order.id,
        )
    elif new_status == "accepted":
        EmailService.send(
            db, advertiser.email,
            f"Your order for {listing.site_name} was accepted",
            f"Hi {advertiser.name},\n\nGood news: {publisher.name} accepted your order "
            f"for a guest post on {listing.site_name}. They will start working on it shortly.\n\n"
            f"Track it here: {order_url}",
            related_order_id=order.id,
        )
    elif new_status == "in_progress":
        EmailService.send(
            db, advertiser.email,
            f"Your order for {listing.site_name} is in progress",
            f"Hi {advertiser.name},\n\n{publisher.name} has started working on your "
            f"guest post for {listing.site_name}.\n\nTrack it here: {order_url}",
            related_order_id=order.id,
        )
    elif new_status == "delivered":
        EmailService.send(
            db, advertiser.email,
            f"Your guest post on {listing.site_name} was delivered",
            f"Hi {advertiser.name},\n\n{publisher.name} marked your order for "
            f"{listing.site_name} as delivered. Please review and mark it completed "
            f"once the published link looks good.\n\nReview it here: {order_url}",
            related_order_id=order.id,
        )
    elif new_status == "completed":
        EmailService.send(
            db, publisher.email,
            f"Order for {listing.site_name} completed",
            f"Hi {publisher.name},\n\n{advertiser.name} marked the order for "
            f"{listing.site_name} as completed. Nice work.\n\nView it here: {order_url}",
            related_order_id=order.id,
        )
    elif new_status == "rejected":
        EmailService.send(
            db, advertiser.email,
            f"Your order for {listing.site_name} was rejected",
            f"Hi {advertiser.name},\n\n{publisher.name} rejected your order request "
            f"for {listing.site_name}. You can browse other listings in the marketplace.\n\n"
            f"View it here: {order_url}",
            related_order_id=order.id,
        )
