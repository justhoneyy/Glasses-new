import os
import uuid
from functools import wraps
from urllib.parse import quote

from flask import session, jsonify, current_app, request


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def current_user():
    """Return the logged-in User row, or None. Imported lazily to avoid circulars."""
    from models import User

    uid = session.get("user_id")
    if not uid:
        return None
    return User.query.get(uid)


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return jsonify({"error": "Login required"}), 401
        return fn(*args, **kwargs)
    return wrapper


def admin_required(fn):
    """Server-side admin check only — never trust anything the client sends."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user_id") or session.get("role") != "admin":
            return jsonify({"error": "Admin authorization required"}), 403
        return fn(*args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# Google Identity token verification
# ---------------------------------------------------------------------------

def verify_google_id_token(token):
    """Verify a Google Identity Services credential (ID token). Returns claims dict or None."""
    try:
        from google.oauth2 import id_token as google_id_token
        from google.auth.transport import requests as google_requests

        claims = google_id_token.verify_oauth2_token(
            token, google_requests.Request(), current_app.config["GOOGLE_CLIENT_ID"]
        )
        if claims.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
            current_app.logger.warning("Google token rejected: unexpected issuer %r", claims.get("iss"))
            return None
        return claims
    except Exception:
        # Log the real reason (missing dependency, expired token, audience mismatch,
        # network error reaching Google's cert endpoint, etc.) — without this, every
        # failure looks identical to the client ("Invalid Google token").
        current_app.logger.exception("Google ID token verification failed")
        return None


# ---------------------------------------------------------------------------
# Uploads
# ---------------------------------------------------------------------------

def allowed_file(filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in current_app.config["ALLOWED_EXTENSIONS"]


def save_upload(file_storage):
    """Save an uploaded image to the uploads folder, return its public URL path."""
    if not file_storage or file_storage.filename == "":
        return None
    if not allowed_file(file_storage.filename):
        raise ValueError("Unsupported file type")

    ext = file_storage.filename.rsplit(".", 1)[-1].lower()
    fname = f"{uuid.uuid4().hex}.{ext}"
    folder = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, fname)
    file_storage.save(path)
    return f"/static/uploads/{fname}"


# ---------------------------------------------------------------------------
# Pricing / filters
# ---------------------------------------------------------------------------

PRICE_BANDS = {
    "under-750": (0, 750),
    "750-1500": (750, 1500),
    "1500-3000": (1500, 3000),
    "3000-plus": (3000, None),
}


# ---------------------------------------------------------------------------
# WhatsApp message builder
# ---------------------------------------------------------------------------

def build_whatsapp_link(number, message):
    return f"https://wa.me/{number}?text={quote(message)}"


def build_order_message(product, quantity, prescription, customer, total):
    lines = ["Hello, I want to order this glasses:", ""]
    lines.append(f"Product: {product.name}")
    lines.append(f"SKU: {product.sku}")
    lines.append(f"Price: ₹{product.effective_price():.0f}")
    lines.append("")
    lines.append(f"Quantity: {quantity}")

    if prescription and prescription.get("has_checkup"):
        right = prescription.get("right", {})
        left = prescription.get("left", {})
        lines.append("")
        lines.append("Right Eye:")
        lines.append(f"SPH: {right.get('sph', '-')}")
        lines.append(f"CYL: {right.get('cyl', '-')}")
        lines.append(f"AXIS: {right.get('axis', '-')}")
        lines.append("")
        lines.append("Left Eye:")
        lines.append(f"SPH: {left.get('sph', '-')}")
        lines.append(f"CYL: {left.get('cyl', '-')}")
        lines.append(f"AXIS: {left.get('axis', '-')}")
        if prescription.get("pd"):
            lines.append("")
            lines.append(f"PD: {prescription.get('pd')}")
        if prescription.get("add"):
            lines.append(f"ADD: {prescription.get('add')}")
        if prescription.get("notes"):
            lines.append(f"Notes: {prescription.get('notes')}")

    lines.append("")
    lines.append("Customer:")
    lines.append(f"Name: {customer.get('name', '-')}")
    lines.append(f"Email: {customer.get('email', '-')}")

    if product.image:
        lines.append("")
        lines.append("Product Image:")
        lines.append(product.image)

    lines.append("")
    lines.append(f"Total: ₹{total:.0f}")
    lines.append("")
    lines.append("Please confirm my order.")
    return "\n".join(lines)


def build_checkup_message():
    return "Hello, I want to get a free eye checkup for purchasing glasses."


def get_or_create_session_id():
    if "cart_session_id" not in session:
        session["cart_session_id"] = uuid.uuid4().hex
    return session["cart_session_id"]
