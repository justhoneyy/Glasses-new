# Shop Eyeglasses — Deployment Guide

## 1. File tree
```
project/
├── app.py                  # Flask app: pages + all API routes
├── config.py                # Env-driven config
├── models.py                 # SQLAlchemy models (Postgres/JSONB)
├── utils.py                  # Auth, uploads, WhatsApp message builder
├── requirements.txt
├── runtime.txt
└── frontend/
    ├── templates/
    │   ├── index.html         # Your original design + inlined CSS/JS, fully data-driven
    │   ├── shop.html            # Category / filtered listing page (Men, Women, by shape, by price, search…)
    │   ├── admin.html            # Admin dashboard (self-contained)
    │   ├── login.html            # Google-only login (self-contained)
    │   └── product.html        # Buy flow, with the same shared CSS/JS inlined
    └── static/
        └── uploads/              # Admin-uploaded images land here (served at /static/uploads/…)
```
Each page template is a single self-contained file — the shared CSS and the cart/wishlist/
search/filter JS (`app.js`) that used to live under `static/css` and `static/js` are now
inlined directly into `index.html` and `product.html`. The only thing left in `static/` is
the `uploads/` folder, which has to stay on disk (or point at object storage — see §8) so
Flask has somewhere to save and serve admin-uploaded product/hero images.


## 2. Environment variables
| Variable | Required | Default |
|---|---|---|
| `DATABASE_URL` | Yes | — (Render provides this automatically) |
| `SECRET_KEY` | Yes | — set a long random value |
| `PYTHON_VERSION` | Recommended | see §9 — set to `3.12.7` in Render's dashboard |
| `GOOGLE_CLIENT_ID` | No | provided default client ID |
| `GOOGLE_CLIENT_SECRET` | No | not used by the ID-token flow, reserved for future use |
| `ADMIN_EMAIL` | No | `smartmind2910@gmail.com` |
| `WHATSAPP_NUMBER` | No | `919718709078` |

## 3. PostgreSQL setup
Create a Render PostgreSQL instance and copy its **Internal Database URL** into `DATABASE_URL`
on the web service. Tables are created automatically on first boot (`db.create_all()`); a
few demo products and default landing sections are seeded **only if the database is empty**.
Existing data is never wiped on redeploy.

The multi-select product fields (gender, shape, style, type, tags) are stored as PostgreSQL
`JSONB` columns so admin-selected values can be queried efficiently — this app targets
Postgres only, per the "no SQLite in production" requirement.

## 4. Render Build Command
```
pip install -r requirements.txt
```

## 5. Render Start Command
```
gunicorn app:app
```
Render sets `$PORT` automatically; Gunicorn binds to it by default when run this way.

## 6. Google OAuth / Identity configuration
This app uses **Google Identity Services** (the modern "Sign in with Google" button + ID
token verification), not the redirect-based OAuth flow — so there's no OAuth redirect URI
to register. Instead, in the Google Cloud Console, under the OAuth Client's
**Authorized JavaScript origins**, add:
```
https://your-app-name.onrender.com
```
(and `http://localhost:5000` for local testing). The client ID itself is already set as the
default in `config.py` / `GOOGLE_CLIENT_ID`.

## 7. Deployment steps
1. Push this project to a GitHub repo.
2. On Render: New → Web Service → connect the repo.
3. Add a PostgreSQL instance, copy its URL into `DATABASE_URL`.
4. Set `SECRET_KEY` (and optionally `ADMIN_EMAIL`, `WHATSAPP_NUMBER`, `GOOGLE_CLIENT_ID`).
5. Build command: `pip install -r requirements.txt`. Start command: `gunicorn app:app`.
6. Deploy. Visit `/admin` and sign in with the `ADMIN_EMAIL` Google account to manage the store.

## 8. Known limitations
- Uploaded images are saved to the app's local disk (`frontend/static/uploads/`). Render's
  filesystem is **ephemeral on redeploy** — for production durability, point `save_upload()`
  in `utils.py` at an external object-storage bucket (S3, Cloudinary, etc.) and store the
  returned URL instead. The upload function is isolated specifically to make this swap easy.
- The homepage hero keeps its original built-in slides until an admin adds at least one
  slide via **Admin → Hero Slider** — after that, the CMS-managed slides take over.
- Video hero slides are supported in the data model and admin form is image-first; add a
  `video` URL directly via the API if you need a video slide immediately (a dedicated video
  upload field can be added the same way as the image field).
- First-boot table creation can race across multiple Gunicorn workers on a brand-new database;
  this is harmless (checks are idempotent) but you may see a duplicate-key log line once — it
  will not recur after the first successful boot.

## 9. Pinning the Python version (important)
Render has, at times, ignored `runtime.txt` and defaulted new services to its latest
available Python (currently 3.14) — which breaks `psycopg2`-style binary wheels that haven't
been rebuilt for a brand-new interpreter yet. This project defends against that two ways:
1. A `.python-version` file at the repo root (Render's current, documented way to pin a
   version) set to `3.12.7`.
2. The Postgres driver itself: `requirements.txt` uses `psycopg[binary]` (psycopg **3**)
   instead of `psycopg2-binary`, since psycopg 3 ships wheels for new Python releases much
   faster and is less likely to break the next time Render bumps its default.

If a deploy ever fails again with an `ImportError: ... undefined symbol` from a C extension,
it almost always means the build ran on a newer Python than expected. Belt-and-suspenders
fix: also set the `PYTHON_VERSION` environment variable to `3.12.7` directly on the Render
service (Dashboard → Environment) — this is Render's officially recommended override and
takes priority over file-based pinning.

## 10. Category pages (`/shop`)
Clicking "Men", "Women", "Kids", a frame shape, a style card, or a price band anywhere on
the homepage now navigates to a dedicated listing page instead of filtering products inline
on the homepage:
```
/shop?gender=Men
/shop?shape=Round
/shop?price_band=under-750
/shop?style=Professional
/shop?search=aviator
```
Filters combine (e.g. `/shop?gender=Men&shape=Round`) and the in-page filter chips let
shoppers refine further without leaving the page. The homepage itself only shows curated
CMS sections (New Arrivals, Best Sellers, etc.) as previews — full browsing by category
happens on `/shop`. "View All" on a homepage section links to `/shop` pre-filtered to that
section's own tags/gender/shape.
