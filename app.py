import os
from decimal import Decimal

from flask import (
    Flask, render_template, request, jsonify, session, redirect, url_for, send_from_directory
)
from sqlalchemy import or_

from config import Config
from models import (
    db, User, Product, Category, CartItem, WishlistItem, Order, HeroSlide, Section, SiteConfig,
)
from utils import (
    current_user, login_required, admin_required, verify_google_id_token,
    save_upload, PRICE_BANDS, build_whatsapp_link, build_order_message,
    build_checkup_message, get_or_create_session_id,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "frontend", "templates"),
    static_folder=os.path.join(BASE_DIR, "frontend", "static"),
)
app.config.from_object(Config)
db.init_app(app)


# ---------------------------------------------------------------------------
# DB init + first-run seed (never wipes existing data)
# ---------------------------------------------------------------------------

def init_db():
    db.create_all()

    if not SiteConfig.query.get("footer"):
        db.session.add(SiteConfig(key="footer", value={
            "support_text": "Need help? Chat with us anytime.",
            "about_links": [
                {"label": "About Us", "url": "#"},
                {"label": "Careers", "url": "#"},
                {"label": "Store Locator", "url": "#"},
                {"label": "Terms & Privacy Policy", "url": "#"},
            ],
            "social_links": [
                {"label": "Instagram", "url": "#", "icon": "fa-instagram"},
                {"label": "Facebook", "url": "#", "icon": "fa-facebook"},
                {"label": "YouTube", "url": "#", "icon": "fa-youtube"},
            ],
            "copyright": "© 2026 Shop Eyeglasses. All rights reserved.",
        }))

    if Section.query.count() == 0:
        db.session.add_all([
            Section(key="new-arrivals", title="New Arrivals", subtitle="Fresh frames just dropped",
                    button_text="View All", filter_config={"tags": ["new"]}, limit=8, sort_order=1),
            Section(key="best-sellers", title="Best Sellers", subtitle="Loved by thousands of customers",
                    button_text="View All", filter_config={"tags": ["bestseller"]}, limit=8, sort_order=2),
        ])

    if Product.query.count() == 0:
        demo = [
            dict(name="Aria Round Frame", description="Lightweight round acetate frame.",
                 price=1499, sale_price=999, brand="Lenskart Air", sku="DEMO-001", stock=25,
                 image="https://images.unsplash.com/photo-1577803645773-f96470509666?w=600",
                 gender=["Men", "Women"], shape=["Round"], style=["Casual"], type=["Eyeglasses"],
                 color="Black", material="Acetate", collection="Air", tags=["new", "bestseller"]),
            dict(name="Nova Rectangle Frame", description="Sleek rectangle frame for daily wear.",
                 price=2199, sale_price=1699, brand="Lenskart Studio", sku="DEMO-002", stock=15,
                 image="https://images.unsplash.com/photo-1614715838608-2793c26d371c?w=600",
                 gender=["Men"], shape=["Rectangle"], style=["Professional"], type=["Eyeglasses"],
                 color="Gunmetal", material="Metal", collection="Studio", tags=["new"]),
            dict(name="Bloom Cat Eye", description="Bold cat-eye frame with a modern twist.",
                 price=1799, sale_price=None, brand="Lenskart Blu", sku="DEMO-003", stock=10,
                 image="https://images.unsplash.com/photo-1591076482161-42ce6da69f67?w=600",
                 gender=["Women"], shape=["Cat Eye"], style=["Festive"], type=["Eyeglasses"],
                 color="Tortoise", material="Acetate", collection="Blu", tags=["bestseller"]),
            dict(name="Drift Aviator Sunglasses", description="Classic aviator sunglasses, UV400.",
                 price=2999, sale_price=2399, brand="Lenskart Sun", sku="DEMO-004", stock=30,
                 image="https://images.unsplash.com/photo-1572635196237-14b3f281503f?w=600",
                 gender=["Men", "Women"], shape=["Aviator"], style=["Casual"], type=["Sunglasses"],
                 color="Gold", material="Metal", collection="Sun", tags=["new", "bestseller"]),
        ]
        for d in demo:
            db.session.add(Product(**d))

    db.session.commit()


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template(
        "index.html",
        google_client_id=app.config["GOOGLE_CLIENT_ID"],
        whatsapp_number=app.config["WHATSAPP_NUMBER"],
    )


@app.route("/product/<int:product_id>")
def product_page(product_id):
    product = Product.query.get_or_404(product_id)
    return render_template(
        "product.html", product=product,
        google_client_id=app.config["GOOGLE_CLIENT_ID"],
        whatsapp_number=app.config["WHATSAPP_NUMBER"],
    )


@app.route("/login")
def login_page():
    return render_template(
        "login.html",
        google_client_id=app.config["GOOGLE_CLIENT_ID"],
        whatsapp_number=app.config["WHATSAPP_NUMBER"],
    )


@app.route("/shop")
def shop_page():
    """Dedicated category / filtered-listing page — e.g. /shop?gender=Men,
    /shop?shape=Round, /shop?price_band=under-750. Products are fetched
    client-side from /api/products so every combination of filters works
    without adding a new route per category."""
    return render_template(
        "shop.html",
        google_client_id=app.config["GOOGLE_CLIENT_ID"],
        whatsapp_number=app.config["WHATSAPP_NUMBER"],
    )


@app.route("/admin")
def admin_page():
    # Client cannot self-grant admin; page loads, but every API call is re-checked server-side.
    return render_template(
        "admin.html",
        google_client_id=app.config["GOOGLE_CLIENT_ID"],
        whatsapp_number=app.config["WHATSAPP_NUMBER"],
    )


# ---------------------------------------------------------------------------
# Auth API
# ---------------------------------------------------------------------------

@app.route("/api/auth/google", methods=["POST"])
def auth_google():
    data = request.get_json(silent=True) or {}
    token = data.get("credential")
    if not token:
        return jsonify({"error": "Missing credential"}), 400

    claims = verify_google_id_token(token)
    if not claims:
        return jsonify({"error": "Invalid Google token"}), 401

    email = claims.get("email")
    google_id = claims.get("sub")
    if not email or not google_id:
        return jsonify({"error": "Google account missing required fields"}), 400

    user = User.query.filter_by(google_id=google_id).first()
    role = "admin" if email.lower() == app.config["ADMIN_EMAIL"].lower() else "customer"

    if user:
        user.email = email
        user.name = claims.get("name", user.name)
        user.profile_image = claims.get("picture", user.profile_image)
        user.role = role  # re-derive server-side every login; never trust client
    else:
        user = User(
            google_id=google_id, email=email, name=claims.get("name", ""),
            profile_image=claims.get("picture", ""), role=role,
        )
        db.session.add(user)
    db.session.commit()

    session.clear()
    session["user_id"] = user.id
    session["role"] = user.role

    # merge guest cart (by session cart_session_id) into the account
    guest_sid = session.get("cart_session_id")
    if guest_sid:
        for item in CartItem.query.filter_by(session_id=guest_sid).all():
            existing = CartItem.query.filter_by(user_id=user.id, product_id=item.product_id).first()
            if existing:
                existing.quantity += item.quantity
                db.session.delete(item)
            else:
                item.user_id = user.id
                item.session_id = None
        db.session.commit()

    return jsonify({"user": user.to_dict()})


@app.route("/api/auth/logout", methods=["POST"])
def auth_logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/auth/me")
def auth_me():
    user = current_user()
    return jsonify({"user": user.to_dict() if user else None})


# ---------------------------------------------------------------------------
# Product API (public)
# ---------------------------------------------------------------------------

def _apply_product_filters(query, args):
    search = args.get("search", "").strip()
    if search:
        like = f"%{search}%"
        query = query.filter(or_(
            Product.name.ilike(like), Product.brand.ilike(like),
            Product.sku.ilike(like), Product.color.ilike(like),
            Product.collection.ilike(like),
        ))

    def multi_get(key):
        vals = args.getlist(key)
        if len(vals) == 1 and "," in vals[0]:
            vals = vals[0].split(",")
        return [v for v in vals if v]

    for field_name, column in (("gender", Product.gender), ("shape", Product.shape),
                                ("style", Product.style), ("type", Product.type)):
        values = multi_get(field_name)
        if values:
            conds = [column.contains([v]) for v in values]
            query = query.filter(or_(*conds))

    brand = args.get("brand")
    if brand:
        query = query.filter(Product.brand == brand)

    tag = args.get("tag")
    if tag:
        query = query.filter(Product.tags.contains([tag]))

    # multiple tags (comma-separated or repeated) = OR match, used by
    # "View All" links from CMS sections that filter on more than one tag
    tags = multi_get("tags")
    if tags:
        query = query.filter(or_(*[Product.tags.contains([t]) for t in tags]))

    price_band = args.get("price_band")
    if price_band in PRICE_BANDS:
        lo, hi = PRICE_BANDS[price_band]
        # filter on effective price (sale price if present, else price) in Python since it's derived
        pass  # handled after fetch below for correctness with sale price

    return query


@app.route("/api/products")
def api_products():
    query = Product.query.filter_by(active=True)
    query = _apply_product_filters(query, request.args)
    products = query.order_by(Product.created_at.desc()).all()

    price_band = request.args.get("price_band")
    if price_band in PRICE_BANDS:
        lo, hi = PRICE_BANDS[price_band]
        products = [p for p in products if p.effective_price() >= lo and (hi is None or p.effective_price() < hi)]

    return jsonify({
        "products": [p.to_dict() for p in products],
        "count": len(products),
    })


@app.route("/api/products/<int:product_id>")
def api_product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    return jsonify({"product": product.to_dict()})


@app.route("/api/brands")
def api_brands():
    brands = [b[0] for b in db.session.query(Product.brand).filter(Product.brand != "").distinct().all()]
    return jsonify({"brands": sorted(brands)})


@app.route("/api/categories")
def api_categories():
    cats = Category.query.order_by(Category.kind, Category.name).all()
    return jsonify({"categories": [c.to_dict() for c in cats]})


# ---------------------------------------------------------------------------
# Cart API
# ---------------------------------------------------------------------------

def _cart_query():
    user = current_user()
    if user:
        return CartItem.query.filter_by(user_id=user.id)
    sid = get_or_create_session_id()
    return CartItem.query.filter_by(session_id=sid)


@app.route("/api/cart")
def api_cart_get():
    items = _cart_query().all()
    total = sum(i.product.effective_price() * i.quantity for i in items if i.product)
    return jsonify({"items": [i.to_dict() for i in items], "total": round(total, 2)})


@app.route("/api/cart/add", methods=["POST"])
def api_cart_add():
    data = request.get_json(silent=True) or {}
    product_id = data.get("product_id")
    quantity = max(1, int(data.get("quantity", 1)))

    product = Product.query.get(product_id)
    if not product or not product.active:
        return jsonify({"error": "Product not found"}), 404
    if product.stock < quantity:
        return jsonify({"error": "Not enough stock"}), 400

    user = current_user()
    existing_q = CartItem.query.filter_by(product_id=product.id)
    existing_q = existing_q.filter_by(user_id=user.id) if user else existing_q.filter_by(session_id=get_or_create_session_id())
    existing = existing_q.first()

    if existing:
        existing.quantity += quantity
    else:
        item = CartItem(product_id=product.id, quantity=quantity)
        if user:
            item.user_id = user.id
        else:
            item.session_id = get_or_create_session_id()
        db.session.add(item)

    db.session.commit()
    return jsonify({"ok": True})


@app.route("/api/cart/update", methods=["POST"])
def api_cart_update():
    data = request.get_json(silent=True) or {}
    item = _cart_query().filter_by(id=data.get("item_id")).first()
    if not item:
        return jsonify({"error": "Item not found"}), 404
    quantity = int(data.get("quantity", 1))
    if quantity <= 0:
        db.session.delete(item)
    else:
        item.quantity = min(quantity, max(item.product.stock, 1))
    db.session.commit()
    return jsonify({"ok": True})


@app.route("/api/cart/remove", methods=["POST"])
def api_cart_remove():
    data = request.get_json(silent=True) or {}
    item = _cart_query().filter_by(id=data.get("item_id")).first()
    if item:
        db.session.delete(item)
        db.session.commit()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Wishlist API (requires login — it's tied to the account)
# ---------------------------------------------------------------------------

@app.route("/api/wishlist")
def api_wishlist_get():
    user = current_user()
    if not user:
        return jsonify({"items": []})
    items = WishlistItem.query.filter_by(user_id=user.id).all()
    return jsonify({"items": [i.to_dict() for i in items]})


@app.route("/api/wishlist/toggle", methods=["POST"])
@login_required
def api_wishlist_toggle():
    data = request.get_json(silent=True) or {}
    product_id = data.get("product_id")
    user = current_user()
    existing = WishlistItem.query.filter_by(user_id=user.id, product_id=product_id).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        return jsonify({"ok": True, "wishlisted": False})

    product = Product.query.get(product_id)
    if not product:
        return jsonify({"error": "Product not found"}), 404
    db.session.add(WishlistItem(user_id=user.id, product_id=product_id))
    db.session.commit()
    return jsonify({"ok": True, "wishlisted": True})


# ---------------------------------------------------------------------------
# Orders API
# ---------------------------------------------------------------------------

def _validate_prescription(p):
    if not p or not p.get("has_checkup"):
        return {"has_checkup": False}

    def clean_eye(eye):
        out = {}
        for field in ("sph", "cyl", "axis"):
            val = eye.get(field, "")
            if val in ("", None):
                out[field] = ""
                continue
            try:
                fval = float(val)
            except (TypeError, ValueError):
                raise ValueError(f"Invalid {field.upper()} value")
            if field == "axis" and not (0 <= fval <= 180):
                raise ValueError("AXIS must be between 0 and 180")
            if field in ("sph", "cyl") and not (-20 <= fval <= 20):
                raise ValueError(f"{field.upper()} out of range")
            out[field] = fval
        return out

    right = clean_eye(p.get("right", {}))
    left = clean_eye(p.get("left", {}))
    result = {"has_checkup": True, "right": right, "left": left}
    if p.get("pd"):
        try:
            result["pd"] = float(p["pd"])
        except (TypeError, ValueError):
            raise ValueError("Invalid PD value")
    if p.get("add"):
        result["add"] = p["add"]
    if p.get("notes"):
        result["notes"] = str(p["notes"])[:500]
    return result


@app.route("/api/orders/create", methods=["POST"])
@login_required
def api_create_order():
    data = request.get_json(silent=True) or {}
    product = Product.query.get(data.get("product_id"))
    if not product or not product.active:
        return jsonify({"error": "Product not found"}), 404

    quantity = max(1, int(data.get("quantity", 1)))
    if product.stock < quantity:
        return jsonify({"error": "Not enough stock"}), 400

    try:
        prescription = _validate_prescription(data.get("prescription"))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    user = current_user()
    price = product.effective_price()
    total = round(price * quantity, 2)

    order = Order(
        customer_id=user.id, product_id=product.id, quantity=quantity,
        price=price, total=total, prescription=prescription,
        customer_snapshot={"name": user.name, "email": user.email},
        status="New",
    )
    db.session.add(order)
    db.session.commit()

    message = build_order_message(
        product, quantity, prescription, {"name": user.name, "email": user.email}, total
    )
    whatsapp_url = build_whatsapp_link(app.config["WHATSAPP_NUMBER"], message)

    return jsonify({"order": order.to_dict(), "whatsapp_url": whatsapp_url})


@app.route("/api/whatsapp/checkup-link")
def api_checkup_link():
    from utils import build_checkup_message
    return jsonify({"whatsapp_url": build_whatsapp_link(app.config["WHATSAPP_NUMBER"], build_checkup_message())})


@app.route("/api/orders/mine")
@login_required
def api_orders_mine():
    user = current_user()
    orders = Order.query.filter_by(customer_id=user.id).order_by(Order.created_at.desc()).all()
    return jsonify({"orders": [o.to_dict() for o in orders]})


# ---------------------------------------------------------------------------
# Landing page content API (public read)
# ---------------------------------------------------------------------------

@app.route("/api/hero-slides")
def api_hero_slides():
    slides = HeroSlide.query.filter_by(active=True).order_by(HeroSlide.sort_order).all()
    return jsonify({"slides": [s.to_dict() for s in slides]})


@app.route("/api/sections")
def api_sections():
    sections = Section.query.filter_by(visible=True).order_by(Section.sort_order).all()
    result = []
    for s in sections:
        q = Product.query.filter_by(active=True)
        fc = s.filter_config or {}
        for field_name, column in (("gender", Product.gender), ("shape", Product.shape),
                                    ("style", Product.style), ("type", Product.type)):
            vals = fc.get(field_name)
            if vals:
                q = q.filter(or_(*[column.contains([v]) for v in vals]))
        if fc.get("tags"):
            q = q.filter(or_(*[Product.tags.contains([t]) for t in fc["tags"]]))
        if fc.get("brand"):
            q = q.filter(Product.brand == fc["brand"])
        products = q.order_by(Product.created_at.desc()).limit(s.limit or 8).all()
        d = s.to_dict()
        d["products"] = [p.to_dict() for p in products]
        result.append(d)
    return jsonify({"sections": result})


@app.route("/api/site-config/<key>")
def api_site_config(key):
    cfg = SiteConfig.query.get(key)
    return jsonify({"key": key, "value": cfg.value if cfg else {}})


# ---------------------------------------------------------------------------
# Admin API — every route is server-side gated by @admin_required
# ---------------------------------------------------------------------------

@app.route("/api/admin/overview")
@admin_required
def admin_overview():
    return jsonify({
        "total_products": Product.query.count(),
        "active_products": Product.query.filter_by(active=True).count(),
        "customers": User.query.filter_by(role="customer").count(),
        "orders": Order.query.count(),
        "pending_orders": Order.query.filter(Order.status.in_(["New", "Contacted"])).count(),
        "revenue": float(db.session.query(db.func.coalesce(db.func.sum(Order.total), 0))
                          .filter(Order.status != "Cancelled").scalar() or 0),
    })


@app.route("/api/admin/products", methods=["GET", "POST"])
@admin_required
def admin_products():
    if request.method == "GET":
        products = Product.query.order_by(Product.created_at.desc()).all()
        return jsonify({"products": [p.to_dict() for p in products]})

    data = request.get_json(silent=True) or {}
    if not data.get("name") or not data.get("sku"):
        return jsonify({"error": "name and sku are required"}), 400
    if Product.query.filter_by(sku=data["sku"]).first():
        return jsonify({"error": "SKU already exists"}), 400

    product = Product(
        name=data["name"], description=data.get("description", ""),
        price=Decimal(str(data.get("price", 0))),
        sale_price=Decimal(str(data["sale_price"])) if data.get("sale_price") not in (None, "") else None,
        image=data.get("image", ""), additional_images=data.get("additional_images", []),
        brand=data.get("brand", ""), stock=int(data.get("stock", 0)), sku=data["sku"],
        active=bool(data.get("active", True)),
        gender=data.get("gender", []), shape=data.get("shape", []),
        style=data.get("style", []), type=data.get("type", []),
        color=data.get("color", ""), material=data.get("material", ""),
        collection=data.get("collection", ""), tags=data.get("tags", []),
    )
    db.session.add(product)
    db.session.commit()
    return jsonify({"product": product.to_dict()}), 201


@app.route("/api/admin/products/<int:product_id>", methods=["PUT", "DELETE"])
@admin_required
def admin_product_detail(product_id):
    product = Product.query.get_or_404(product_id)

    if request.method == "DELETE":
        db.session.delete(product)
        db.session.commit()
        return jsonify({"ok": True})

    data = request.get_json(silent=True) or {}
    for field in ("name", "description", "image", "additional_images", "brand", "sku",
                  "gender", "shape", "style", "type", "color", "material", "collection", "tags"):
        if field in data:
            setattr(product, field, data[field])
    if "price" in data:
        product.price = Decimal(str(data["price"]))
    if "sale_price" in data:
        product.sale_price = Decimal(str(data["sale_price"])) if data["sale_price"] not in (None, "") else None
    if "stock" in data:
        product.stock = int(data["stock"])
    if "active" in data:
        product.active = bool(data["active"])

    db.session.commit()
    return jsonify({"product": product.to_dict()})


@app.route("/api/admin/upload", methods=["POST"])
@admin_required
def admin_upload():
    file = request.files.get("file")
    try:
        url = save_upload(file)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    if not url:
        return jsonify({"error": "No file provided"}), 400
    return jsonify({"url": url})


@app.route("/api/admin/orders")
@admin_required
def admin_orders():
    orders = Order.query.order_by(Order.created_at.desc()).all()
    return jsonify({"orders": [o.to_dict() for o in orders]})


@app.route("/api/admin/orders/<int:order_id>", methods=["PUT"])
@admin_required
def admin_order_update(order_id):
    order = Order.query.get_or_404(order_id)
    data = request.get_json(silent=True) or {}
    status = data.get("status")
    if status not in ("New", "Contacted", "Confirmed", "Processing", "Completed", "Cancelled"):
        return jsonify({"error": "Invalid status"}), 400
    order.status = status
    if "whatsapp_sent" in data:
        order.whatsapp_sent = bool(data["whatsapp_sent"])
    db.session.commit()
    return jsonify({"order": order.to_dict()})


@app.route("/api/admin/customers")
@admin_required
def admin_customers():
    users = User.query.filter_by(role="customer").order_by(User.created_at.desc()).all()
    return jsonify({"customers": [u.to_dict() for u in users]})


@app.route("/api/admin/categories", methods=["GET", "POST"])
@admin_required
def admin_categories():
    if request.method == "GET":
        return jsonify({"categories": [c.to_dict() for c in Category.query.all()]})
    data = request.get_json(silent=True) or {}
    if not data.get("name"):
        return jsonify({"error": "name required"}), 400
    cat = Category(name=data["name"], kind=data.get("kind", "custom"))
    db.session.add(cat)
    db.session.commit()
    return jsonify({"category": cat.to_dict()}), 201


@app.route("/api/admin/categories/<int:category_id>", methods=["DELETE"])
@admin_required
def admin_category_delete(category_id):
    cat = Category.query.get_or_404(category_id)
    db.session.delete(cat)
    db.session.commit()
    return jsonify({"ok": True})


@app.route("/api/admin/hero-slides", methods=["GET", "POST"])
@admin_required
def admin_hero_slides():
    if request.method == "GET":
        slides = HeroSlide.query.order_by(HeroSlide.sort_order).all()
        return jsonify({"slides": [s.to_dict() for s in slides]})
    data = request.get_json(silent=True) or {}
    slide = HeroSlide(
        image=data.get("image", ""), video=data.get("video", ""),
        heading=data.get("heading", ""), subtitle=data.get("subtitle", ""),
        button_text=data.get("button_text", ""), button_link=data.get("button_link", ""),
        tone=data.get("tone", "dark"), sort_order=int(data.get("sort_order", 0)),
        active=bool(data.get("active", True)),
    )
    db.session.add(slide)
    db.session.commit()
    return jsonify({"slide": slide.to_dict()}), 201


@app.route("/api/admin/hero-slides/<int:slide_id>", methods=["PUT", "DELETE"])
@admin_required
def admin_hero_slide_detail(slide_id):
    slide = HeroSlide.query.get_or_404(slide_id)
    if request.method == "DELETE":
        db.session.delete(slide)
        db.session.commit()
        return jsonify({"ok": True})
    data = request.get_json(silent=True) or {}
    for field in ("image", "video", "heading", "subtitle", "button_text", "button_link", "tone"):
        if field in data:
            setattr(slide, field, data[field])
    if "sort_order" in data:
        slide.sort_order = int(data["sort_order"])
    if "active" in data:
        slide.active = bool(data["active"])
    db.session.commit()
    return jsonify({"slide": slide.to_dict()})


@app.route("/api/admin/sections", methods=["GET", "POST"])
@admin_required
def admin_sections():
    if request.method == "GET":
        sections = Section.query.order_by(Section.sort_order).all()
        return jsonify({"sections": [s.to_dict() for s in sections]})
    data = request.get_json(silent=True) or {}
    if not data.get("key") or not data.get("title"):
        return jsonify({"error": "key and title required"}), 400
    if Section.query.filter_by(key=data["key"]).first():
        return jsonify({"error": "section key already exists"}), 400
    section = Section(
        key=data["key"], title=data["title"], subtitle=data.get("subtitle", ""),
        button_text=data.get("button_text", ""), filter_config=data.get("filter_config", {}),
        limit=int(data.get("limit", 8)), sort_order=int(data.get("sort_order", 0)),
        visible=bool(data.get("visible", True)),
    )
    db.session.add(section)
    db.session.commit()
    return jsonify({"section": section.to_dict()}), 201


@app.route("/api/admin/sections/<int:section_id>", methods=["PUT", "DELETE"])
@admin_required
def admin_section_detail(section_id):
    section = Section.query.get_or_404(section_id)
    if request.method == "DELETE":
        db.session.delete(section)
        db.session.commit()
        return jsonify({"ok": True})
    data = request.get_json(silent=True) or {}
    for field in ("title", "subtitle", "button_text", "filter_config"):
        if field in data:
            setattr(section, field, data[field])
    if "limit" in data:
        section.limit = int(data["limit"])
    if "sort_order" in data:
        section.sort_order = int(data["sort_order"])
    if "visible" in data:
        section.visible = bool(data["visible"])
    db.session.commit()
    return jsonify({"section": section.to_dict()})


@app.route("/api/admin/site-config/<key>", methods=["PUT"])
@admin_required
def admin_site_config_update(key):
    data = request.get_json(silent=True) or {}
    cfg = SiteConfig.query.get(key)
    if not cfg:
        cfg = SiteConfig(key=key, value={})
        db.session.add(cfg)
    cfg.value = data.get("value", {})
    db.session.commit()
    return jsonify({"key": key, "value": cfg.value})


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------

@app.errorhandler(404)
def not_found(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Not found"}), 404
    return render_template(
        "index.html",
        google_client_id=app.config["GOOGLE_CLIENT_ID"],
        whatsapp_number=app.config["WHATSAPP_NUMBER"],
    ), 404


@app.errorhandler(500)
def server_error(e):
    db.session.rollback()
    if request.path.startswith("/api/"):
        return jsonify({"error": "Server error"}), 500
    return "Something went wrong. Please try again.", 500


@app.errorhandler(403)
def forbidden(e):
    return jsonify({"error": "Forbidden"}), 403


with app.app_context():
    init_db()


if __name__ == "__main__":
    app.run(debug=True)
