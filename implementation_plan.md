# Medicine Refill Tracker — Full Implementation Plan

**The problem:** People managing multiple medications for chronic conditions — especially elderly relatives — run out of prescriptions without warning, or get a new medication prescribed that dangerously interacts with something they are already taking, with no one flagging it until it's a major health issue.

**The solution:** A self-hosted caregiver dashboard paired with a Telegram notification bot. The system tracks patients' medication lists, calculates exact days remaining, alerts caregivers and patients via Telegram before running low, checks newly added medications against existing prescriptions for interactions using the NIH RxNav database, and resolves Indian brand names to active ingredients via LLM and web search.

**Core features:**
*   **Multi-Caregiver Management:** Caregivers can link with multiple patients (e.g., spouse and adult child co-managing an elderly parent).
*   **Daily Refill Projections:** Real-time calculation of days remaining based on quantities, dosage values, and frequencies.
*   **Telegram Notification Bot:** Free, instant alerts without Meta/Twilio verification hurdles or rate-limiting costs.
*   **Smart Drug Resolution Pipeline:** Translates Indian brand names (like "Dolo 650" or "Ecosprin") to their active ingredients via Gemini AI and web scraping before running drug interaction checks.
*   **Prescription OCR:** Caregiver uploads a photo of a structured prescription note, and Gemini Vision extracts medication name, dosage, and frequency into an editable draft form.

**How it works end to end:** A caregiver registers and adds a patient profile → The patient or caregiver starts a chat with the Telegram bot to link their account → The caregiver uploads a prescription scan or enters drugs manually → The backend attempts to resolve the drug names to canonical active ingredient RxCUIs using a 4-layer resolution hierarchy → Once resolved, the backend checks for interactions against the patient's existing list, issuing warnings for major/contraindicated pairs → Every morning at 8:00 AM IST, a scheduled job calculates remaining medication stocks and sends Telegram alerts if thresholds are breached.

**Target users:** Caregivers managing chronic medication regimens for elderly relatives or children. First tested within a single family environment before wider use.

---

## Final Architecture Decision Summary

| Concern | Decision |
|---|---|
| **Hosting** | Backend: Railway (Hobby tier, always-on container)<br>Frontend: Vercel (Hobby tier, serverless Next.js static hosting) |
| **Domain & SSL** | Railway auto-generated domain + Let's Encrypt managed SSL |
| **Database** | PostgreSQL 16 on Railway (managed service with automatic daily backups) |
| **Backend** | FastAPI (Python, async, with lifespan management for background jobs) |
| **ORM** | SQLAlchemy (async) + Alembic for schema migrations |
| **Telegram Bot** | python-telegram-bot v20+, Webhook mode linked to FastAPI |
| **OCR & NLP** | Google Gemini 1.5 Flash API (Free tier for OCR parsing and composition identification) |
| **Web Search** | Google Custom Search JSON API (100 free queries/day for ingredient lookup fallbacks) |
| **Drug Database** | NIH RxNav REST API (free, public) + DB caching layer |
| **Frontend UI** | Next.js (App Router, React 18, TailwindCSS, Axios for backend connection) |
| **Orchestration** | Docker Compose for local development (FastAPI API + Postgres) |

---

## System Architecture Diagram

```
User (Caregiver / Patient)
│
▼ (Telegram / HTTPS Webhook)
┌───────────────────────────────────────────────────────────┐
│ RAILWAY                                                   │
│                                                           │
│ ┌────────────────┐      ┌──────────────┐   ┌────────────┐ │
│ │ Next.js UI     │      │ FastAPI      │──▶│ Postgres   │ │
│ │ (Vercel)       │◀────▶│ (port 8000)  │   │ (port 5432)│ │
│ └────────────────┘      │              │   └────────────┘ │
│                         │ /webhook     │                  │
│                         │ /api/...     │                  │
│                         └──────┬───────┘                  │
│                                │                          │
│ ┌──────────────────────────────▼────────────────────────┐ │
│ │ APScheduler (inside FastAPI)                          │ │
│ │ - Daily Refill Calculation & Telegram Alerts (02:30UTC)│ │
│ └───────────────────────────────────────────────────────┘ │
└────────────────────────────────┬──────────────────────────┘
                                 │ HTTP requests
                                 ▼
 ┌──────────────────────────────────────────────────────────┐
 │ External API Services                                    │
 │ - Telegram Bot API (Free notification channel)           │
 │ - NIH RxNav API (Free drug interaction queries)          │
 │ - Google Gemini API (OCR + Brand Ingredient extraction)  │
 │ - Google Custom Search (1mg.com web scraping fallback)   │
 └──────────────────────────────────────────────────────────┘
```

---

## Database Schema (PostgreSQL 16)

### Table: `users`
Stores caregivers managing patients.
```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    telegram_chat_id BIGINT UNIQUE, -- Caregiver's telegram chat ID
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_users_email ON users(email);
```

### Table: `patients`
Stores patients whose prescriptions are being tracked.
```sql
CREATE TABLE patients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name VARCHAR(255) NOT NULL,
    age INT,
    telegram_chat_id BIGINT UNIQUE, -- Patient's personal telegram chat ID (optional)
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Table: `caregiver_patients`
Associates caregivers and patients (Many-to-Many).
```sql
CREATE TABLE caregiver_patients (
    id SERIAL PRIMARY KEY,
    caregiver_id UUID REFERENCES users(id) ON DELETE CASCADE,
    patient_id UUID REFERENCES patients(id) ON DELETE CASCADE,
    role VARCHAR(32) DEFAULT 'primary', -- 'primary', 'secondary'
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(caregiver_id, patient_id)
);
CREATE INDEX idx_caregiver_patients_patient ON caregiver_patients(patient_id);
```

### Table: `medications`
Tracks specific drugs, inventory, dosage, and refill parameters.
```sql
CREATE TABLE medications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID REFERENCES patients(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL, -- Brand/Common Name
    rxcui VARCHAR(32), -- RxNorm Concept ID (resolved generic representation)
    resolved_generic_names JSONB DEFAULT '[]', -- Array of active ingredients
    resolution_source VARCHAR(64) DEFAULT 'unresolved', -- 'rxnorm', 'gemini', 'web_search', 'manual'
    dose_value NUMERIC(10, 2) NOT NULL, -- e.g., 500.00
    dose_unit VARCHAR(32) NOT NULL, -- e.g., 'mg', 'ml', 'capsule'
    frequency_per_day NUMERIC(4, 2) NOT NULL, -- e.g., 2.0 (twice a day) or 0.5 (half tablet)
    quantity_on_hand NUMERIC(10, 2) NOT NULL, -- Current stock
    start_date DATE NOT NULL,
    refill_threshold_days INT DEFAULT 7, -- Warn at X days remaining
    reminder_escalation_days INT DEFAULT 3, -- Escalate warn at Y days remaining
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_medications_patient ON medications(patient_id);
CREATE INDEX idx_medications_rxcui ON medications(rxcui) WHERE rxcui IS NOT NULL;
```

### Table: `drug_interactions_cache`
Caches pairwise interaction status from RxNav to minimize API roundtrips.
```sql
CREATE TABLE drug_interactions_cache (
    id SERIAL PRIMARY KEY,
    rxcui_1 VARCHAR(32) NOT NULL,
    rxcui_2 VARCHAR(32) NOT NULL,
    severity VARCHAR(32) NOT NULL, -- 'contraindicated', 'major', 'moderate', 'minor'
    description TEXT NOT NULL,
    fetched_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(rxcui_1, rxcui_2)
);
CREATE INDEX idx_interactions_pair ON drug_interactions_cache(rxcui_1, rxcui_2);
```

### Table: `refill_reminders_log`
Tracks notifications sent to prevent spamming and log delivery metrics.
```sql
CREATE TABLE refill_reminders_log (
    id SERIAL PRIMARY KEY,
    medication_id UUID REFERENCES medications(id) ON DELETE CASCADE,
    sent_at TIMESTAMPTZ DEFAULT NOW(),
    chat_id BIGINT NOT NULL,
    days_remaining_at_send INT NOT NULL,
    status VARCHAR(16) NOT NULL -- 'sent', 'failed'
);
CREATE INDEX idx_reminders_log_med_date ON refill_reminders_log(medication_id, sent_at);
```

### Table: `prescription_scans`
Holds raw image OCR data and processing state.
```sql
CREATE TABLE prescription_scans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID REFERENCES patients(id) ON DELETE CASCADE,
    uploaded_by UUID REFERENCES users(id) ON DELETE SET NULL,
    image_url TEXT NOT NULL,
    extracted_data JSONB DEFAULT '{}', -- Extracted medications JSON structure
    reviewed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## Telegram Bot — User Flows

Caregivers and patients link their profiles to the bot using a token generated on the web interface.

### Bot Commands

| Command | Description |
|---|---|
| `/start` | Bot welcome message, usage directions. |
| `/link <token>` | Links current Telegram chat ID to a patient/caregiver profile using dashboard token. |
| `/status` | Returns a list of active medications, current quantities, and projected refill dates. |
| `/refill <med_name> <qty>` | Updates a medication inventory count directly from Telegram. |
| `/help` | Explains linking process and command list. |

### Link & Notification Flow (Conversation)

```
User: /start
Bot: 💊 Welcome to the Medicine Refill Tracker Bot!
     To begin receiving alerts, please link this chat to your Caregiver Profile.
     Type: /link <your-token-from-dashboard>

User: /link LINK-7734-X99
Bot: ✅ Success! Chat linked to Caregiver Profile: "Virendra Singh".
     You will receive daily warnings at 8:00 AM IST for medications approaching refill limits.

User: /status
Bot: 📊 Ramesh Singh's Medication Status:
     🔴 Ecosprin 75mg: 1.5 days remaining (Refill by 18-Jul-2026) - Qty: 3 tab left
     🟡 Dolo 650: 5.0 days remaining (Refill by 21-Jul-2026) - Qty: 10 tab left
     🟢 Metformin 500mg: 25.0 days remaining (Refill by 10-Aug-2026) - Qty: 50 tab left

User: /refill Ecosprin 30
Bot: ✅ Inventory updated! Ecosprin 75mg: Stock is now 33 tablets (Projected: 16.5 days remaining).
```

---

## Core Backend Logic

### 1. Indian Drug Name Resolution Pipeline
If an Indian brand name is added (e.g. "Ecosprin 75mg"), it must be resolved into generic ingredients (e.g., "Aspirin") to perform RxNav interaction checks.

```python
import httpx
from google import genai
from google.genai import types

async def resolve_brand_name(drug_name: str, gemini_client: genai.Client, google_search_key: str, google_cx: str) -> dict:
    """
    4-Layer Drug Name Resolution:
    Layer 1: Direct RxNorm query.
    Layer 2: Gemini AI Brand-to-Generic Composition extraction.
    Layer 3: Google Search (1mg.com/medindia.net) + Gemini parse composition text.
    Layer 4: Fallback to manual entry flag.
    """
    # LAYER 1: Check direct RxNorm API
    async with httpx.AsyncClient() as client:
        rxcui_resp = await client.get("https://rxnav.nlm.nih.gov/REST/rxcui.json", params={"name": drug_name})
        if rxcui_resp.status_code == 200:
            data = rxcui_resp.json()
            if "rxnormId" in data.get("idGroup", {}):
                return {
                    "resolved": True,
                    "rxcui": data["idGroup"]["rxnormId"][0],
                    "generic_names": [drug_name],
                    "source": "rxnorm",
                    "confidence": "high"
                }

    # LAYER 2: Query Gemini AI for composition
    prompt = (
        f"Identify the active pharmaceutical ingredients of the Indian brand medicine '{drug_name}'. "
        "Provide your output strictly in JSON format with keys: "
        "'generic_names' (list of strings) and 'confidence' ('high', 'medium', or 'low')."
    )
    
    try:
        response = await gemini_client.aio.models.generate_content(
            model='gemini-1.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        import json
        gemini_data = json.loads(response.text)
        if gemini_data.get("confidence") == "high":
            # Attempt to resolve the generic names via RxNorm
            rxcui_list = []
            for g in gemini_data["generic_names"]:
                async with httpx.AsyncClient() as client:
                    r = await client.get("https://rxnav.nlm.nih.gov/REST/rxcui.json", params={"name": g})
                    if r.status_code == 200 and "rxnormId" in r.json().get("idGroup", {}):
                        rxcui_list.append(r.json()["idGroup"]["rxnormId"][0])
            
            if rxcui_list:
                return {
                    "resolved": True,
                    "rxcui": rxcui_list[0],  # Main active component
                    "generic_names": gemini_data["generic_names"],
                    "source": "gemini",
                    "confidence": "high"
                }
    except Exception:
        pass

    # LAYER 3: Web search fallbacks (1mg / Medindia)
    try:
        search_query = f"{drug_name} composition active ingredients site:1mg.com OR site:medindia.net"
        async with httpx.AsyncClient() as client:
            search_resp = await client.get(
                "https://www.googleapis.com/customsearch/v1",
                params={"key": google_search_key, "cx": google_cx, "q": search_query}
            )
            if search_resp.status_code == 200:
                results = search_resp.json()
                snippets = " ".join([item.get("snippet", "") for item in results.get("items", [])])
                
                # Ask Gemini to parse search snippets
                parse_prompt = (
                    f"Given these snippets about '{drug_name}': '{snippets}', extract "
                    "the generic active ingredients. Return strictly JSON with keys "
                    "'generic_names' (list) and 'confidence'."
                )
                response = await gemini_client.aio.models.generate_content(
                    model='gemini-1.5-flash',
                    contents=parse_prompt,
                    config=types.GenerateContentConfig(response_mime_type="application/json")
                )
                web_data = json.loads(response.text)
                if web_data.get("generic_names"):
                    # Resolve generics
                    for g in web_data["generic_names"]:
                        async with httpx.AsyncClient() as client:
                            r = await client.get("https://rxnav.nlm.nih.gov/REST/rxcui.json", params={"name": g})
                            if r.status_code == 200 and "rxnormId" in r.json().get("idGroup", {}):
                                return {
                                    "resolved": True,
                                    "rxcui": r.json()["idGroup"]["rxnormId"][0],
                                    "generic_names": web_data["generic_names"],
                                    "source": "web_search",
                                    "confidence": "medium"
                                }
    except Exception:
        pass

    # LAYER 4: Manual Fallback
    return {
        "resolved": False,
        "rxcui": None,
        "generic_names": [],
        "source": "unresolved",
        "confidence": "low"
    }
```

### 2. Refill Alert Logic (APScheduler Job)
Runs every morning at 02:30 UTC (8:00 AM IST).

```python
from datetime import date
from sqlalchemy import select
from app.models import Medication, Patient, User

async def run_daily_refill_calculations(session_factory):
    async with session_factory() as session:
        # Fetch active medications
        stmt = (
            select(Medication, Patient)
            .join(Patient, Medication.patient_id == Patient.id)
            .where(Medication.is_active == True)
        )
        results = await session.execute(stmt)
        
        for med, patient in results:
            daily_dose = med.dose_value * med.frequency_per_day
            if daily_dose <= 0:
                continue
                
            days_remaining = med.quantity_on_hand / daily_dose
            
            # Decide trigger levels
            threshold = med.refill_threshold_days
            escalation = med.reminder_escalation_days
            
            message = None
            if days_remaining <= escalation:
                message = f"🚨 *CRITICAL REFILL URGENT:* {med.name} has only {days_remaining:.1f} days remaining! ({med.quantity_on_hand:.0f} {med.dose_unit}s left)."
            elif days_remaining <= threshold:
                message = f"⚠️ *Refill Reminder:* {med.name} has {days_remaining:.1f} days remaining. ({med.quantity_on_hand:.0f} {med.dose_unit}s left)."
                
            if message:
                # Send to Patient Telegram
                if patient.telegram_chat_id:
                    await send_telegram_alert(patient.telegram_chat_id, message)
                
                # Send to linked Caregivers
                caregiver_stmt = select(User).join(CaregiverPatient).where(CaregiverPatient.patient_id == patient.id)
                cg_results = await session.execute(caregiver_stmt)
                for cg in cg_results.scalars():
                    if cg.telegram_chat_id:
                        await send_telegram_alert(cg.telegram_chat_id, message)
```

### 3. Drug Interaction Check (RxNav Lookup)
```python
async def check_drug_interaction(rxcui_1: str, rxcui_2: str, session: AsyncSession) -> dict:
    """
    Checks interaction between two drugs via local cache, falling back to RxNav API.
    """
    # Normalize order
    cui_min, cui_max = sorted([rxcui_1, rxcui_2])
    
    # Check cache
    cache_stmt = select(DrugInteractionCache).where(
        (DrugInteractionCache.rxcui_1 == cui_min) & (DrugInteractionCache.rxcui_2 == cui_max)
    )
    cache_res = await session.execute(cache_stmt)
    cached = cache_res.scalar_one_or_none()
    if cached:
        return {"interaction": True, "severity": cached.severity, "description": cached.description}

    # Fetch API
    url = f"https://rxnav.nlm.nih.gov/REST/interaction/list.json?rxcuis={cui_min}+{cui_max}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
        if resp.status_code == 200:
            data = resp.json()
            interaction_group = data.get("fullInteractionTypeGroup", [])
            for group in interaction_group:
                for fit in group.get("fullInteractionType", []):
                    for item in fit.get("interactionPair", []):
                        severity = item.get("severity", "moderate")
                        description = item.get("description", "Potential interaction detected.")
                        
                        # Cache it
                        new_cache = DrugInteractionCache(
                            rxcui_1=cui_min, rxcui_2=cui_max,
                            severity=severity, description=description
                        )
                        session.add(new_cache)
                        await session.commit()
                        return {"interaction": True, "severity": severity, "description": description}
                        
    return {"interaction": False, "severity": None, "description": None}
```

---

## Project Folder Structure

```
medicine-tracker/
├── docker-compose.yml
├── .env.example
├── .env
│
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py              # FastAPI application setup & lifecycle hooks
│   │   ├── bot.py               # Telegram bot dispatcher & state conversation
│   │   ├── database.py          # SQLAlchemy engine & session generation
│   │   ├── routers/
│   │   │   ├── auth.py          # Register, Login, Refresh tokens
│   │   │   ├── patients.py      # Patient profiles CRUD
│   │   │   ├── medications.py   # Medications list CRUD + Interaction triggers
│   │   │   ├── ocr.py           # Gemini Vision image upload OCR processor
│   │   │   └── webhook.py       # Telegram webhook handler
│   │   ├── services/
│   │   │   ├── drug_resolver.py # 4-layer resolution algorithm
│   │   │   ├── interaction.py   # RxNav queries & DB Cache logic
│   │   │   └── scheduler.py     # Daily APScheduler job definitions
│   │   ├── models/
│   │   │   └── models.py        # SQLAlchemy schema representations
│   │   └── schemas/
│   │       └── schemas.py       # Pydantic request/response validation schemas
│   └── alembic/
│       ├── env.py
│       └── versions/            # Migration scripts directory
│
├── frontend/                    # Next.js SPA
│   ├── package.json
│   ├── tsconfig.json
│   ├── tailwind.config.js
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx
│   │   │   ├── page.tsx         # Dashboard landing page
│   │   │   ├── login/
│   │   │   │   └── page.tsx     # Login view
│   │   │   ├── patients/
│   │   │   │   ├── page.tsx     # Patients List panel
│   │   │   │   └── [id]/
│   │   │   │       └── page.tsx # Patient Detail (Meds list, refilling scheduler)
│   │   │   └── prescriptions/
│   │   │       └── scan/
│   │   │           └── page.tsx # File upload dropzone + draft confirmation review
│   │   ├── components/
│   │   │   ├── MedCard.tsx      # Renders stock levels & color warnings
│   │   │   ├── OCRDrafts.tsx    # List of medications parsed from scan for approval
│   │   │   └── InteractionAlert.tsx # Modal warning during manual medicine entry
│   │   └── api/
│   │       └── client.ts        # Axios API wrapper with request interceptors for JWT
```

---

## Docker Compose Setup (Local Dev)

This configuration coordinates local API development with a Postgres server container.

```yaml
version: "3.9"

services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: medicine_tracker
      POSTGRES_USER: tracker_admin
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    mem_limit: 256m
    restart: always

  api:
    build: ./backend
    depends_on:
      - db
    environment:
      DATABASE_URL: postgresql+asyncpg://tracker_admin:${DB_PASSWORD}@db:5432/medicine_tracker
      TELEGRAM_BOT_TOKEN: ${TELEGRAM_BOT_TOKEN}
      GEMINI_API_KEY: ${GEMINI_API_KEY}
      GOOGLE_CSE_API_KEY: ${GOOGLE_CSE_API_KEY}
      GOOGLE_CSE_ID: ${GOOGLE_CSE_ID}
      JWT_SECRET: ${JWT_SECRET}
    ports:
      - "8000:8000"
    volumes:
      - ./backend:/app
    mem_limit: 256m
    restart: always

volumes:
  pgdata:
```

---

## API Endpoints (FastAPI)

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/auth/register` | Register a new caregiver. |
| `POST` | `/api/auth/login` | Log in and return JWT token pair. |
| `POST` | `/api/auth/refresh` | Rotate access and refresh tokens. |
| `GET` | `/api/patients` | Retrieve list of associated patients. |
| `POST` | `/api/patients` | Create a patient profile. |
| `GET` | `/api/patients/{id}/medications` | Get active medications with calculated days left. |
| `POST` | `/api/patients/{id}/medications` | Add medicine to patient list (triggers interaction run). |
| `PATCH` | `/api/medications/{med_id}` | Edit dose parameters or adjust stock quantity. |
| `POST` | `/api/ocr/scan` | Upload prescription scan to parse via Gemini Vision. |
| `POST` | `/api/webhook` | Handles updates sent from Telegram bot. |

---

## React/Next.js Dashboard — Pages & Components

### Pages
*   `Dashboard Root (/)` — Global overview of active patients, alert items (low stock meds), and links to quick scan.
*   `Patient Dashboard (/patients/[id])` — Full list of active prescriptions with status badges, days remaining metrics, timeline, and audit logs.
*   `Prescription Uploader (/prescriptions/scan)` — Interactive file upload dropzone. Previews uploaded scanned images and displays generated draft entries in an editable grid before final db check-in.

### Key UI Components
*   `<MedCard>` — Displays medication metadata, a color-coded slider (Red: <3d, Yellow: <7d, Green: Ok), and actions to adjust quantity.
*   `<InteractionAlert>` — Inline warning widget showing red notices for contraindicated medications or yellow notices for moderate warning interactions.
*   `<PrescriptionPreviewTable>` — Spreadsheet-style form for adjusting parsed names, doses, and schedules before adding them.

---

## Deployment Runbook (Step by Step)

### Phase 1 — Database & Hosting Setup (Railway)
1. Log in to [Railway](https://railway.app) and launch a new project.
2. Select **Provision PostgreSQL** from the catalog to instantiate a database container.
3. Choose **Deploy from GitHub repository** and hook up the FastAPI repository.
4. Set the builder settings to build using the Dockerfile inside `backend/`.
5. Populate the Railway env list with production values:
   *   `DATABASE_URL` (automatically referenced by the database provisioning)
   *   `TELEGRAM_BOT_TOKEN`
   *   `GEMINI_API_KEY`
   *   `GOOGLE_CSE_API_KEY`
   *   `GOOGLE_CSE_ID`
   *   `JWT_SECRET`

### Phase 2 — Database Migrations
1. Run target migrations from a deployment container tool window or local instance targeting the prod database:
   ```bash
   docker compose exec api alembic upgrade head
   ```

### Phase 3 — Telegram Webhook Configuration
1. Open a browser or run a terminal curl call to bind the bot to your live API instance:
   ```bash
   curl "https://api.telegram.org/bot<YOUR_TELEGRAM_TOKEN>/setWebhook?url=https://<your-railway-app-subdomain>/api/webhook"
   ```

### Phase 4 — Frontend Deployment (Vercel)
1. Go to [Vercel](https://vercel.com) and create a project pointing to your Next.js folder.
2. Add the deployment environment variables:
   *   `NEXT_PUBLIC_API_URL`: `https://<your-railway-app-subdomain>`
3. Click **Deploy**. Vercel will build the Next.js static layers and serve them via CDN.

---

## What to Study Before Scaffolding

### Week 1 — Async Backend Basics (FastAPI & SQLAlchemy)
*   **Day 1-2:** Learn async/await patterns. Focus on concurrent client requests using `httpx.AsyncClient` and handling lists using `asyncio.gather`.
*   **Day 3-4:** Study FastAPI path and query variables, middleware configurations, CORS structures, and automatic documentation endpoints (`/docs`).
*   **Day 5-7:** Review SQLAlchemy 2.0 Async declarative mappings and async sessions. Implement Alembic migrations.

### Week 2 — Integrations & Local Docker Deployments
*   **Day 8-9:** Study `python-telegram-bot` webhook bindings. Create handlers with simple routing commands.
*   **Day 10-11:** Integrate Gemini API wrapper functions to pass text requests and image payloads.
*   **Day 12-14:** Practice building target applications using multi-container environments. Configure connections between APIs and database networks.

### Week 3 — Frontend Development (Next.js & Styling)
*   **Day 15-17:** Learn Next.js App Router routing models, data fetching setups, and form control strategies.
*   **Day 18-19:** Design reactive dashboard cards, inputs, and modals using TailwindCSS guidelines.
*   **Day 20-21:** Implement authorization rules. Learn how to store JWTs securely and map routes with Middleware interceptors.

---

## Phased Rollout

| Phase | Goal | Duration |
|---|---|---|
| **Phase 1** | Implement PostgreSQL models and migrations. Setup FastAPI scaffolding and auth endpoints. Deploy to Railway. | Week 1–2 |
| **Phase 2** | Integrate Telegram webhook receiver and user linking flow. Build daily calculation job and alert notifications. | Week 3 |
| **Phase 3** | Implement the 4-layer drug name resolution pipeline. Integrate RxNav API logic and caching. | Week 4 |
| **Phase 4** | Setup Next.js caregiver panel dashboard. Integrate OCR scanner capabilities via Gemini Vision. | Week 5 |
| **Phase 5** | Run staging trials on your family's medication list. Refine notifications and OCR extraction based on user feedback. | Week 6+ |

---

## Open Questions / Future Scope

*   **Abuse Mitigation:** Add rate limit counters for Telegram commands (e.g. max 5 status checks/minute) and OCR uploads (max 10 images/day) to manage database load and API limits.
*   **Offline Access:** Implement service worker caching and offline forms on Next.js so caregivers can check medication schedules or input inventory modifications while offline, syncing changes once back online.
*   **Prescription Image Lifecycle:** Uploaded prescription images will be sent directly to Cloudinary (free tier, 25GB storage) to optimize CDN delivery, auto-purging image records older than 90 days to respect privacy.
*   **Dosage Compliance Verification:** Add a caregiver-configurable setting requiring patients to reply to their morning Telegram notifications confirming they have taken their scheduled medications (e.g., via interactive inline "Taken" buttons). If no response is received by a certain time, alert the primary caregiver.
