# Supply Chain & Warehouse Management System (SC&WMS) — v2
**Student:** Mubashira Zainab | BS Mathematics 5th Semester | CASPAM, BZU Multan
**Course:** DBMS (COMP351) | **Supervisor:** Dr. Imran Javaid | 2026

A database-driven web application (Flask + PostgreSQL) for suppliers, products, warehouses, stock,
customers, orders and shipments — now with an **AI data assistant** and **live map tracking**.

## What's new in v2
| Feature | What it does |
|---|---|
| 🤖 **AI Assistant** (`/assistant`) | Ask in English / Urdu / Roman Urdu → AI writes SQL → server validates it → runs it read-only → explains the result. Gemini first, Groq as automatic backup. |
| 🗺️ **Shipment map tracking** (`/shipments`, `/shipments/<id>/track`) | Route origin warehouse → customer, checkpoint timeline, live truck position, distance, progress and ETA. Free OpenStreetMap + Leaflet (no key). |
| 🛡️ **Security** | Hashed passwords, CSRF protection, POST-only deletes, role-based access (Admin / Manager / Viewer), secrets only in `.env`, safe-SQL filter + read-only DB session for the AI. |
| 🗄️ **New DB objects** | `Shipment_Tracking` table, `Shipment_Tracking_Detail` view, triggers `trg_prepare_shipment`, `trg_first_tracking_event`, `trg_shipment_status_event`; lat/long on `Warehouse` and `Customer`. |

## Project structure
```
app.py                  Flask routes (all pages + tracking + AI endpoints)
ai_assistant.py         AI module: prompts, Gemini/Groq clients, SQL safety filter, read-only runner
geo.py                  Pakistani city coordinates + distance helpers (for the map)
config.py               Reads every secret from environment variables
.env.example            Template for your secrets  ->  copy to .env
database/               schema.sql · sample_data.sql · demo_transactions.sql · ai_readonly_role.sql
templates/              HTML pages (assistant.html, track.html, shipments.html are new/updated)
public/static/          css + js (tracking.js, assistant.js)   <- static files live in public/ for Vercel
```

## Run locally
1. **Install:** `pip install -r requirements.txt`
2. **Database:** create `supply_chain_db` in pgAdmin, then run `database/schema.sql` and `database/sample_data.sql`
   (re-running them resets the data — needed once for v2 because the schema changed).
3. **Secrets:** copy `.env.example` to **`.env`** (same folder as `app.py`) and fill in `DB_PASSWORD` and `SECRET_KEY`.
4. **Start:** `python app.py` → open http://localhost:5000

**Demo logins:** `admin / admin123` · `manager / manager123` · `viewer / viewer123`
(passwords are stored hashed; change them before any real use).

## Add the AI keys (when you are ready)
Open **`.env`** (next to `app.py`) and paste the keys — nothing else to change, users never type keys:
```
GEMINI_API_KEY=your-gemini-key      # https://aistudio.google.com  -> Get API key
GROQ_API_KEY=your-groq-key          # https://console.groq.com     -> API Keys
```
Restart the app. If Gemini is out of quota or fails, Groq answers automatically.
If a model name is retired, edit `GEMINI_MODELS` / `GROQ_MODELS` in `.env` (no code change).

## Deploy on Vercel
Vercel cannot reach your local PostgreSQL, so:
1. Create a free cloud Postgres (**Neon** or **Supabase**), run `schema.sql` then `sample_data.sql` on it.
2. Push this repo to GitHub (`.env` is git-ignored — never commit it).
3. On vercel.com → **Add New Project** → import the repo (Vercel detects Flask from `app.py`).
4. **Settings → Environment Variables**, add: `DATABASE_URL`, `SECRET_KEY`, `GEMINI_API_KEY`, `GROQ_API_KEY`
   (and optionally `AI_DATABASE_URL`, see `database/ai_readonly_role.sql`).
5. Deploy → test login, the map and the assistant on the live link.

## Roles
| Role | Can do |
|---|---|
| Admin | everything, including delete |
| Manager | add / update records, move shipments |
| Viewer | read-only (can still use the AI assistant and map) |

## Notes on the AI feature
* The AI only ever sees the **table structure** and (for the explanation) up to 20 result rows with
  phone / e-mail / address columns removed.
* Generated SQL must be a single `SELECT`; anything else, the `Users` table and system catalogs are rejected,
  and the query runs in a **read-only transaction** with a 5-second timeout.
* Free API tiers have rate limits; the app also limits each login session to 40 questions per hour.

## Tests
```
python tests/test_ai_safety.py      # SQL safety filter (no database)
python tests/test_ai_providers.py   # Gemini / Groq fallback with simulated replies (no keys needed)
python tests/test_app.py            # 38 end-to-end checks; needs a FRESH schema.sql + sample_data.sql in PostgreSQL
```
