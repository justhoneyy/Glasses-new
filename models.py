from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import JSONB

db = SQLAlchemy()


def now():
    return datetime.utcnow()


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    google_id = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    name = db.Column(db.String(255))
    profile_image = db.Column(db.String(500))
    role = db.Column(db.String(20), default="customer", nullable=False)  # customer | admin
    created_at = db.Column(db.DateTime, default=now)

    orders = db.relationship("Order", backref="customer", lazy="dynamic")
    cart_items = db.relationship("CartItem", backref="user", lazy="dynamic", cascade="all, delete-orphan")
    wishlist_items = db.relationship("WishlistItem", backref="user", lazy="dynamic", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "profile_image": self.profile_image,
            "role": self.role,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Category(db.Model):
    """Admin-managed custom categories / tags shown as filter suggestions."""
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    kind = db.Column(db.String(30), default="custom")  # gender|shape|style|type|collection|custom
    created_at = db.Column(db.DateTime, default=now)

    def to_dict(self):
        return {"id": self.id, "name": self.name, "kind": self.kind}


class Product(db.Model):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, default="")
    price = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    sale_price = db.Column(db.Numeric(10, 2), nullable=True)
    image = db.Column(db.String(500), default="")
    additional_images = db.Column(db.JSON, default=list)  # list[str]
    brand = db.Column(db.String(120), default="")
    stock = db.Column(db.Integer, default=0)
    sku = db.Column(db.String(80), unique=True, nullable=False)
    active = db.Column(db.Boolean, default=True)

    # multi-select category-like attributes, stored as JSONB arrays of strings
    # (JSONB — not plain JSON — so PostgreSQL's containment operator `@>` works
    # for the multi-select filters below via SQLAlchemy's .contains())
    gender = db.Column(JSONB, default=list)       # ["Men","Women","Kids","Teenagers"]
    shape = db.Column(JSONB, default=list)         # ["Round","Square",...]
    style = db.Column(JSONB, default=list)         # ["Casual","Professional",...]
    type = db.Column(JSONB, default=list)          # ["Eyeglasses","Sunglasses",...]
    color = db.Column(db.String(120), default="")
    material = db.Column(db.String(120), default="")
    collection = db.Column(db.String(120), default="")
    tags = db.Column(JSONB, default=list)          # free-form custom tags

    created_at = db.Column(db.DateTime, default=now)
    updated_at = db.Column(db.DateTime, default=now, onupdate=now)

    def effective_price(self):
        return float(self.sale_price) if self.sale_price else float(self.price)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "price": float(self.price),
            "sale_price": float(self.sale_price) if self.sale_price is not None else None,
            "effective_price": self.effective_price(),
            "discount_pct": (
                round((1 - self.effective_price() / float(self.price)) * 100)
                if self.sale_price and float(self.price) > 0 else 0
            ),
            "image": self.image,
            "additional_images": self.additional_images or [],
            "brand": self.brand,
            "stock": self.stock,
            "in_stock": self.stock > 0,
            "sku": self.sku,
            "active": self.active,
            "gender": self.gender or [],
            "shape": self.shape or [],
            "style": self.style or [],
            "type": self.type or [],
            "color": self.color,
            "material": self.material,
            "collection": self.collection,
            "tags": self.tags or [],
        }


class CartItem(db.Model):
    __tablename__ = "cart_items"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    session_id = db.Column(db.String(64), nullable=True, index=True)  # for guest carts
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=now)

    product = db.relationship("Product")

    def to_dict(self):
        return {
            "id": self.id,
            "product": self.product.to_dict() if self.product else None,
            "quantity": self.quantity,
            "subtotal": round(self.product.effective_price() * self.quantity, 2) if self.product else 0,
        }


class WishlistItem(db.Model):
    __tablename__ = "wishlist_items"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=now)

    product = db.relationship("Product")

    __table_args__ = (db.UniqueConstraint("user_id", "product_id", name="uq_user_product_wishlist"),)

    def to_dict(self):
        return {"id": self.id, "product": self.product.to_dict() if self.product else None}


class Order(db.Model):
    __tablename__ = "orders"

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    total = db.Column(db.Numeric(10, 2), nullable=False)

    prescription = db.Column(db.JSON, default=dict)   # right/left SPH,CYL,AXIS + ADD/PD/notes, or {"has_checkup": false}
    customer_snapshot = db.Column(db.JSON, default=dict)  # name/email captured at order time

    status = db.Column(db.String(20), default="New")  # New|Contacted|Confirmed|Processing|Completed|Cancelled
    whatsapp_sent = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=now)

    product = db.relationship("Product")

    def to_dict(self):
        return {
            "id": self.id,
            "customer": self.customer.to_dict() if self.customer else None,
            "customer_snapshot": self.customer_snapshot or {},
            "product": self.product.to_dict() if self.product else None,
            "quantity": self.quantity,
            "price": float(self.price),
            "total": float(self.total),
            "prescription": self.prescription or {},
            "status": self.status,
            "whatsapp_sent": self.whatsapp_sent,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class HeroSlide(db.Model):
    __tablename__ = "hero_slides"

    id = db.Column(db.Integer, primary_key=True)
    image = db.Column(db.String(500), default="")
    video = db.Column(db.String(500), default="")
    heading = db.Column(db.String(255), default="")
    subtitle = db.Column(db.String(500), default="")
    button_text = db.Column(db.String(80), default="")
    button_link = db.Column(db.String(300), default="")
    tone = db.Column(db.String(10), default="dark")  # dark|light text tone
    sort_order = db.Column(db.Integer, default=0)
    active = db.Column(db.Boolean, default=True)

    def to_dict(self):
        return {
            "id": self.id, "image": self.image, "video": self.video,
            "heading": self.heading, "subtitle": self.subtitle,
            "button_text": self.button_text, "button_link": self.button_link,
            "tone": self.tone, "sort_order": self.sort_order, "active": self.active,
        }


class Section(db.Model):
    """A CMS-controlled homepage section that shows a curated set of products."""
    __tablename__ = "sections"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(80), unique=True, nullable=False)  # slug, e.g. "new-arrivals"
    title = db.Column(db.String(255), default="")
    subtitle = db.Column(db.String(500), default="")
    button_text = db.Column(db.String(80), default="")
    # filter used to pick products for this section, e.g. {"tags": ["new"], "gender": ["Men"]}
    filter_config = db.Column(db.JSON, default=dict)
    limit = db.Column(db.Integer, default=8)
    sort_order = db.Column(db.Integer, default=0)
    visible = db.Column(db.Boolean, default=True)

    def to_dict(self):
        return {
            "id": self.id, "key": self.key, "title": self.title, "subtitle": self.subtitle,
            "button_text": self.button_text, "filter_config": self.filter_config or {},
            "limit": self.limit, "sort_order": self.sort_order, "visible": self.visible,
        }


class SiteConfig(db.Model):
    """Single-row-per-key store for footer content / misc landing page config."""
    __tablename__ = "site_config"

    key = db.Column(db.String(80), primary_key=True)
    value = db.Column(db.JSON, default=dict)
