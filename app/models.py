"""Everything the site stores lives in PostgreSQL: users, sign-ins, cards, drafts, photos, images, settings."""
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, LargeBinary, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    login: Mapped[Optional[str]] = mapped_column(String(160), unique=True, index=True)  # lower-case name or e-mail
    name: Mapped[str] = mapped_column(String(160))
    password_hash: Mapped[Optional[str]] = mapped_column(String(255))  # argon2id, never the password itself
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OAuthAccount(Base):
    """Sign-in through Google / Yandex / Mail.ru / VK. Only a SHA-256 hash of the provider's user id is kept."""
    __tablename__ = "oauth_accounts"
    __table_args__ = (UniqueConstraint("provider", "subject_hash"),)
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(20))
    subject_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LoginSession(Base):
    """Browser sessions. The cookie holds a random token, the table only its SHA-256 hash."""
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class Item(Base):
    """A card in the library (kind='card') or an autosaved draft (kind='draft')."""
    __tablename__ = "items"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(10))
    title: Mapped[str] = mapped_column(String(300), default="")
    thumb: Mapped[Optional[str]] = mapped_column(Text)  # small JPEG as data: URL
    state: Mapped[Optional[dict]] = mapped_column(JSONB)  # all editor settings
    t: Mapped[int] = mapped_column(BigInteger)  # client time, ms
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ItemFile(Base):
    """Print files the card author keeps with a card (3MF projects, STL, G-code). Never shown to customers."""
    __tablename__ = "item_files"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    item_id: Mapped[str] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(300))
    size: Mapped[int] = mapped_column(BigInteger)
    note: Mapped[str] = mapped_column(String(300), default="")
    data: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Photo(Base):
    """Every photo the user uploaded (the file itself is in blobs with the same id)."""
    __tablename__ = "photos"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(300), default="фото")
    size: Mapped[int] = mapped_column(BigInteger, default=0)
    thumb: Mapped[Optional[str]] = mapped_column(Text)
    t: Mapped[int] = mapped_column(BigInteger)


class BlobSet(Base):
    """Binary data of a card/draft/photo: finished PNG, original photo, cut-out item, manual mask."""
    __tablename__ = "blobs"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    png: Mapped[Optional[bytes]] = mapped_column(LargeBinary)
    photo: Mapped[Optional[bytes]] = mapped_column(LargeBinary)
    photo_type: Mapped[Optional[str]] = mapped_column(String(80))
    product: Mapped[Optional[bytes]] = mapped_column(LargeBinary)
    product_cut: Mapped[bool] = mapped_column(Boolean, default=True)
    manual: Mapped[Optional[bytes]] = mapped_column(LargeBinary)


class Pref(Base):
    """Per-user settings, e.g. saved card colours."""
    __tablename__ = "prefs"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    data: Mapped[dict] = mapped_column(JSONB, default=dict)


# ---------------------------------------------------------------- shop ----

class ShopSetting(Base):
    """Shop-wide settings edited by the admin: workshop costs for the calculator, printers, contacts."""
    __tablename__ = "shop_settings"
    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    data: Mapped[dict] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Product(Base):
    """A card published in the shop. Text, price and pictures are copied from the card at publish time,
    so later edits of the card change the shop only when it is published again."""
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    item_id: Mapped[Optional[str]] = mapped_column(ForeignKey("items.id", ondelete="SET NULL"), unique=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    features: Mapped[str] = mapped_column(Text, default="")  # "Key: value" lines
    category: Mapped[str] = mapped_column(String(80), default="")
    price: Mapped[float] = mapped_column(Numeric(12, 2))
    old_price: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    cost: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))  # cost price from the calculator
    calc: Mapped[Optional[dict]] = mapped_column(JSONB)  # calculator inputs and breakdown
    print_minutes: Mapped[int] = mapped_column(Integer, default=0)  # printer time for one piece
    grams: Mapped[float] = mapped_column(Numeric(10, 1), default=0)  # plastic for one piece
    material: Mapped[str] = mapped_column(String(60), default="")
    stock: Mapped[int] = mapped_column(Integer, default=0)  # ready pieces on the shelf; 0 = printed to order
    published: Mapped[bool] = mapped_column(Boolean, default=True)
    sort: Mapped[int] = mapped_column(Integer, default=0)
    colors: Mapped[Optional[list]] = mapped_column(JSONB)  # ids of filament colours the buyer may choose
    image: Mapped[Optional[bytes]] = mapped_column(LargeBinary)  # the card, JPEG
    thumb: Mapped[Optional[bytes]] = mapped_column(LargeBinary)  # small JPEG
    tile: Mapped[Optional[bytes]] = mapped_column(LargeBinary)  # catalogue preview without the price plate, JPEG
    default_color: Mapped[Optional[int]] = mapped_column(Integer)  # palette colour chosen in the builder
    views: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


ORDER_STATUSES = ("new", "confirmed", "printing", "ready", "shipped", "done", "cancelled")
REQUEST_STATUSES = ("new", "reviewing", "quoted", "accepted", "rejected", "ordered")


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    token: Mapped[str] = mapped_column(String(40), index=True)  # secret for the tracking link of guests
    user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="new", index=True)
    name: Mapped[str] = mapped_column(String(160))
    phone: Mapped[str] = mapped_column(String(60), default="")
    email: Mapped[str] = mapped_column(String(160), default="")
    delivery: Mapped[str] = mapped_column(String(40), default="pickup")
    address: Mapped[str] = mapped_column(Text, default="")
    comment: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(60), default="")  # where an order made by the admin came from: MAX, Avito…
    admin_note: Mapped[str] = mapped_column(Text, default="")
    total: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    cost: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    print_minutes: Mapped[int] = mapped_column(Integer, default=0)  # printer time still needed for the whole order
    grams: Mapped[float] = mapped_column(Numeric(10, 1), default=0)
    paid: Mapped[bool] = mapped_column(Boolean, default=False)
    request_id: Mapped[Optional[int]] = mapped_column(ForeignKey("custom_requests.id", ondelete="SET NULL"))
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class OrderItem(Base):
    """A line of an order. Title, price and print time are copied, so old orders keep their numbers."""
    __tablename__ = "order_items"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[Optional[int]] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    price: Mapped[float] = mapped_column(Numeric(12, 2))
    cost: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    qty: Mapped[int] = mapped_column(Integer, default=1)
    print_minutes: Mapped[int] = mapped_column(Integer, default=0)  # for one piece
    grams: Mapped[float] = mapped_column(Numeric(10, 1), default=0)
    note: Mapped[str] = mapped_column(String(300), default="")  # wishes
    color: Mapped[str] = mapped_column(String(120), default="")  # chosen filament colour
    from_stock: Mapped[int] = mapped_column(Integer, default=0)  # pieces taken from the shelf, not printed
    price_pending: Mapped[bool] = mapped_column(Boolean, default=False)  # several colours: price set by the admin after the slicer


class OrderEvent(Base):
    """History of an order: who changed what and when."""
    __tablename__ = "order_events"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[Optional[int]] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    request_id: Mapped[Optional[int]] = mapped_column(ForeignKey("custom_requests.id", ondelete="CASCADE"), index=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    who: Mapped[str] = mapped_column(String(160), default="")
    status: Mapped[Optional[str]] = mapped_column(String(20))
    text: Mapped[str] = mapped_column(Text, default="")


class CustomRequest(Base):
    """A customer's idea: description plus pictures or 3D files; the admin reviews it and names a price."""
    __tablename__ = "custom_requests"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    token: Mapped[str] = mapped_column(String(40), index=True)
    user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="new", index=True)
    name: Mapped[str] = mapped_column(String(160))
    phone: Mapped[str] = mapped_column(String(60), default="")
    email: Mapped[str] = mapped_column(String(160), default="")
    title: Mapped[str] = mapped_column(String(300), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    size: Mapped[str] = mapped_column(String(160), default="")
    color: Mapped[str] = mapped_column(String(160), default="")
    qty: Mapped[int] = mapped_column(Integer, default=1)
    budget: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    quote_price: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))  # admin's price for the whole request
    quote_cost: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    quote_minutes: Mapped[Optional[int]] = mapped_column(Integer)
    quote_grams: Mapped[Optional[float]] = mapped_column(Numeric(10, 1))
    quote_text: Mapped[str] = mapped_column(Text, default="")
    admin_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class RequestFile(Base):
    __tablename__ = "request_files"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("custom_requests.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(300))
    mime: Mapped[str] = mapped_column(String(120))
    size: Mapped[int] = mapped_column(BigInteger)
    data: Mapped[bytes] = mapped_column(LargeBinary)
    thumb: Mapped[Optional[bytes]] = mapped_column(LargeBinary)  # JPEG preview for pictures


class ProductMedia(Base):
    """Extra photos and videos of a product (the card picture itself stays in Product.image)."""
    __tablename__ = "product_media"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(10))  # image | video
    mime: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(300), default="")
    size: Mapped[int] = mapped_column(BigInteger, default=0)
    data: Mapped[bytes] = mapped_column(LargeBinary)
    thumb: Mapped[Optional[bytes]] = mapped_column(LargeBinary)
    sort: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FilamentColor(Base):
    """A colour of plastic the shop has, with a photo of the filament."""
    __tablename__ = "filament_colors"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120))
    hex: Mapped[str] = mapped_column(String(9), default="#cccccc")
    hex2: Mapped[str] = mapped_column(String(9), default="")  # second colour for gradient/silk/dual filaments
    material: Mapped[str] = mapped_column(String(60), default="")
    note: Mapped[str] = mapped_column(String(300), default="")
    kg_price: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))  # price of this plastic, ₽ per kg
    photo: Mapped[Optional[bytes]] = mapped_column(LargeBinary)
    thumb: Mapped[Optional[bytes]] = mapped_column(LargeBinary)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Feedback(Base):
    """A message from the feedback form."""
    __tablename__ = "feedback"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(160))
    contact: Mapped[str] = mapped_column(String(200))
    text: Mapped[str] = mapped_column(Text)
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    emailed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Category(Base):
    """A group of products on the shop front: name, icon (emoji) and order. Products refer to it by name."""
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    icon: Mapped[str] = mapped_column(String(16), default="📦")
    sort: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Cart(Base):
    """What a visitor put in the cart and has not ordered yet (no personal data, an account only if signed in)."""
    __tablename__ = "carts"
    token: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    items: Mapped[list] = mapped_column(JSONB, default=list)
    favs: Mapped[list] = mapped_column(JSONB, default=list)  # product ids put aside with ♡
    total: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Favorite(Base):
    __tablename__ = "favorites"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Review(Base):
    """A buyer's review: stars, text and photos. Shown only after the admin approves it."""
    __tablename__ = "reviews"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(80))
    rating: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(12), default="pending", index=True)  # pending, approved, rejected
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReviewPhoto(Base):
    __tablename__ = "review_photos"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    review_id: Mapped[int] = mapped_column(ForeignKey("reviews.id", ondelete="CASCADE"), index=True)
    data: Mapped[bytes] = mapped_column(LargeBinary)
    thumb: Mapped[bytes] = mapped_column(LargeBinary)

