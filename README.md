# 🍲 Dinner Decider — Mealie-Integrated Dinner Voting Web App

A lightweight, mobile-first web app designed for effortless dinner decision-making. "Dinner Decider" presents three randomly curated dinner options fetched directly from your self-hosted **[Mealie](https://hay-kot.github.io/mealie/)** instance, or lets your partner submit a custom craving. When locked in, it immediately schedules the selection on Mealie's meal plan for tonight and displays a playful confirmation screen.

---

## ✨ Features

- **📱 Mobile-First Bistro UX:** Designed specifically for smartphones (warm aesthetic, touch-friendly cards, clear typography, and subtle micro-interactions).
- **🎲 Curated Recipe Shuffle:** Pulls 3 random recipes from your Mealie recipe library with one tap, powered by an anti-monotony weighted shuffle algorithm.
- **🧺 Embedded Pantry Inventory & "Pantry Ready" Filtering:** Built-in SQLite pantry engine (`data/pantry.db`) with automatic recipe ingredient discovery, culinary normalization, and kitchen staples bypass. The `🧺 Pantry Ready` carousel filter surfaces recipes you can cook right now (0 missing ingredients) or are at most 1 item off from making.
- **🛒 One-Tap Mealie Shopping List Integration:** When locking in a dinner that is 1 ingredient off, an inline prompt lets you add the missing item straight to Mealie's household shopping list.
- **🥗 2-Step Side Dish Pairing:** Optional second step allowing you to pair tonight's main with a recommended side dish or household staple (e.g. Jasmine Rice, Caesar Salad, Garlic Bread) before final confirmation.
- **🖼️ Built-in Image Proxy:** Safely proxies and caches Mealie recipe images (`/api/recipe-image/{id}`) so client browsers never need direct access or credentials to your Mealie instance.
- **🍜 Custom Craving ("Something Else"):** An intuitive input field for takeout, leftovers, or specific cravings. Typing in this field automatically deselects recipe cards.
- **📅 Instant Mealie Meal Plan Scheduling:** Submits either the recipe ID or custom text to Mealie's `/api/groups/mealplans` endpoint for today's date (`YYYY-MM-DD`).
- **🛡️ Built-in Mock & Resilient Fallback Mode:** Seamlessly falls back to curated mock recipes with beautiful vector dish illustrations if Mealie is temporarily offline, unreachable, or unconfigured during initial setup.
- **🐳 Multi-stage Docker Container:** Production-ready Python 3.12-slim container running as an unprivileged non-root user with healthchecks, persistent data volumes, and Docker Compose support.

---

## 🛠️ Tech Stack

- **Backend:** Python (FastAPI, `httpx`, `pydantic`, `python-dotenv`, `uvicorn`, `sqlite3`)
- **Database:** SQLite (`data/pantry.db` for zero-friction persistent pantry tracking)
- **Frontend:** Single-page app served directly by FastAPI with Tailwind CSS (CDN) and zero heavy Node.js/npm dependencies.
- **Containerization:** Multi-stage `Dockerfile` & `docker-compose.yml`.

---

## 🚀 Quickstart

### Option 1: Docker Compose (Recommended)

1. Clone or copy this repository:
   ```bash
   git clone <repo-url>
   cd Mealplan
   ```

2. Create your `.env` file from the provided template:
   ```bash
   cp .env.example .env
   ```

3. Configure your Mealie instance details in `.env`:
   ```dotenv
   MEALIE_BASE_URL=http://192.168.1.50:9000
   MEALIE_API_TOKEN=your_mealie_api_token_here
   PORT=8000
   MOCK_MODE=false
   ```

4. Launch the container:
   ```bash
   docker compose up -d --build
   ```

5. Open your mobile browser or desktop at `http://localhost:8000`.

---

### Option 2: Local Python Execution

1. Create and activate a Python virtual environment:
   ```bash
   python -m venv .venv
   # Windows:
   .\.venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the development server:
   ```bash
   python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```

---

### Option 3: LXC Container (Proxmox VE / LXD / Incus)

Dinner Decider includes turnkey provisioning scripts to deploy as a lightweight LXC container without Docker overhead:

#### A. Automated Proxmox VE Provisioning (from Proxmox Host Shell)
Run directly from your Proxmox node shell or SSH session:
```bash
bash lxc/create-proxmox-lxc.sh
```
This script will:
- Download the official Debian 12 LXC template (if not already cached).
- Create a lightweight unprivileged container (1 vCPU, 512MB RAM, 4GB disk, auto-DHCP).
- Push project files and run `lxc/install.sh` inside the container.
- Output your web interface URL (`http://<lxc-ip>:8000`).

#### B. Inside an Existing Debian / Ubuntu LXC Container
1. Copy or clone the project inside your container:
   ```bash
   cd /opt
   git clone <repo-url> dinner-decider
   cd dinner-decider
   ```
2. Run the automated installer:
   ```bash
   bash lxc/install.sh
   ```
3. Update your Mealie credentials:
   ```bash
   nano /opt/dinner-decider/.env
   systemctl restart dinner-decider
   ```

#### C. Incus or Canonical LXD
Run from your host machine:
```bash
bash lxc/create-incus-lxd.sh
```

#### LXC Service Management:
```bash
# Check status
systemctl status dinner-decider

# View live stream of logs
journalctl -u dinner-decider -f

# Restart after configuration changes
systemctl restart dinner-decider
```

---

## 🔑 How to Generate a Mealie API Token

1. Log into your self-hosted **Mealie** web interface.
2. Click your user profile avatar in the upper right corner and navigate to **Profile** (or **Settings**).
3. Select **API Tokens** (or **Manage Tokens**).
4. Click **Create Token**, give it a name like `Dinner-Decider`, and copy the generated token.
5. Paste it into `.env` as `MEALIE_API_TOKEN`.

---

## 🔔 Mobile Push Notifications (ntfy.sh)

Dinner Decider uses **[ntfy.sh](https://ntfy.sh/)** to immediately alert the chef on their phone when dinner is locked in, complete with recipe cook times and a tap-to-open button for Mealie:

1. **Install the free app:** Download **ntfy** on [iOS App Store](https://apps.apple.com/app/ntfy/id1625396347) or [Google Play](https://play.google.com/store/apps/details?id=io.heckel.ntfy) (also on F-Droid).
2. **Subscribe to a topic:** Choose a unique, unguessable topic name (e.g. `dinner-rob-family-9872`), open the ntfy app, tap `+`, and subscribe to it.
3. **Configure `.env`:**
   ```dotenv
   NTFY_TOPIC=dinner-rob-family-9872
   NTFY_BASE_URL=https://ntfy.sh
   ```
4. **Done!** Whenever your partner selects a meal or enters a craving, your phone will chime with a high-priority push notification and a direct link to the recipe.

---

## 🧺 Pantry Inventory & "Pantry Ready" Decider

Dinner Decider includes a zero-friction, embedded pantry inventory tracker designed to eliminate dinner-time ingredient friction:

1. **Auto-Seeding & Normalization:** On startup or when clicking **⚡ Sync**, the backend automatically scans your recipes and seeds the pantry database. Measurements and culinary prep verbs are cleaned, and common staples (*salt, black pepper, cooking oils, water*) are bypassed so basic ingredients never disqualify dishes.
2. **Interactive Drawer Modal:** Tap the **🧺 Pantry** header button to view current stock. Filter by status (*All*, *In Stock*, *Missing*) or search instantly. Tap any item to toggle between **✓ In Stock** and **✕ Out**.
3. **"Pantry Ready" Carousel Filter:** Tap the **🧺 Pantry Ready** filter pill in the style bar to filter the carousel to meals you have 100% of the ingredients for, or are at most 1 item off from making.
4. **Missing Ingredient Badges & Alerts:** Recipe cards display clear stock badges (`🟢 Pantry Ready` or `⚠️ Need: [Item]`) and inline missing item alerts.
5. **One-Tap Mealie Shopping List:** When locking in a dinner missing 1 item, tap **Add to Mealie Shopping List** to instantly push the deficit item to your Mealie household list.
6. **Data Persistence:** Stored in a lightweight SQLite database (`data/pantry.db`). When running in Docker, `./data:/app/data` is mounted to ensure persistence across restarts.

---

## 📡 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Healthcheck returning service status and Mealie connection mode |
| `GET` | `/api/options` | Returns 3 curated dinner recipes (supports `?mood=pantry`, `?protein=...`, etc.) |
| `GET` | `/api/side-options` | Returns 3 curated side dish pairings |
| `GET` | `/api/recipe-image/{recipe_id}` | Proxies recipe image from Mealie (with SVG fallback) |
| `POST` | `/api/choose` | Submits recipe or custom craving to Mealie Mealplanner API |
| `GET` | `/api/pantry` | Retrieves inventory items and in-stock/out-of-stock statistics |
| `POST` | `/api/pantry/toggle` | Toggles an ingredient's in-stock status |
| `POST` | `/api/pantry/item` | Adds a custom ingredient to the pantry inventory |
| `DELETE` | `/api/pantry/item/{id}` | Deletes an ingredient from the pantry |
| `POST` | `/api/pantry/sync` | Scans recipes and auto-discovers newly added ingredients |
| `POST` | `/api/pantry/bulk-stock` | Sets all pantry items to in-stock |
| `POST` | `/api/shopping-list/add` | Appends a missing ingredient directly to Mealie's shopping list |

### Example Choice Submission:
```json
// Option A: Recipe Selection
POST /api/choose
{
  "recipe_id": "e4b1a8d0-2f9b-4b11-9e73-1a2b3c4d5e01",
  "side_recipe_id": "optional-side-recipe-uuid"
}

// Option B: Custom Craving
POST /api/choose
{
  "custom_note": "Spicy Thai Green Curry Takeout",
  "side_note": "Jasmine Rice"
}
```

---

## 🧪 Testing

Run the automated test suite with `pytest`:
```bash
pytest -v
```
All endpoints and mock fallback behaviors are covered.
