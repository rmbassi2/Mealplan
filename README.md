# 🍲 Dinner Decider — Mealie-Integrated Dinner Voting Web App

A lightweight, mobile-first web app designed for effortless dinner decision-making. "Dinner Decider" presents three randomly curated dinner options fetched directly from your self-hosted **[Mealie](https://hay-kot.github.io/mealie/)** instance, or lets your partner submit a custom craving. When locked in, it immediately schedules the selection on Mealie's meal plan for tonight and displays a playful confirmation screen.

---

## ✨ Features

- **📱 Mobile-First Bistro UX:** Designed specifically for smartphones (warm aesthetic, touch-friendly cards, clear typography, and subtle micro-interactions).
- **🎲 Curated Recipe Shuffle:** Pulls 3 random recipes from your Mealie recipe library with one tap.
- **🖼️ Built-in Image Proxy:** Safely proxies and caches Mealie recipe images (`/api/recipe-image/{id}`) so client browsers never need direct access or credentials to your Mealie instance.
- **🍜 Custom Craving ("Something Else"):** An intuitive input field for takeout, leftovers, or specific cravings. Typing in this field automatically deselects recipe cards.
- **📅 Instant Mealie Meal Plan Scheduling:** Submits either the recipe ID or custom text to Mealie's `/api/groups/mealplans` endpoint for today's date (`YYYY-MM-DD`).
- **🛡️ Built-in Mock & Resilient Fallback Mode:** Seamlessly falls back to curated mock recipes with beautiful vector dish illustrations if Mealie is temporarily offline, unreachable, or unconfigured during initial setup.
- **🐳 Multi-stage Docker Container:** Production-ready Python 3.11-slim container running as an unprivileged non-root user with healthchecks and Docker Compose support.

---

## 🛠️ Tech Stack

- **Backend:** Python (FastAPI, `httpx`, `pydantic`, `python-dotenv`, `uvicorn`)
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

## 🔑 How to Generate a Mealie API Token

1. Log into your self-hosted **Mealie** web interface.
2. Click your user profile avatar in the upper right corner and navigate to **Profile** (or **Settings**).
3. Select **API Tokens** (or **Manage Tokens**).
4. Click **Create Token**, give it a name like `Dinner-Decider`, and copy the generated token.
5. Paste it into `.env` as `MEALIE_API_TOKEN`.

---

## 📡 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Healthcheck returning service status and Mealie connection mode |
| `GET` | `/api/options` | Returns 3 randomly selected dinner recipes |
| `GET` | `/api/recipe-image/{recipe_id}` | Proxies recipe image from Mealie (with SVG fallback) |
| `POST` | `/api/choose` | Submits recipe or custom craving to Mealie Mealplanner API |

### Example Choice Submission:
```json
// Option A: Recipe Selection
POST /api/choose
{
  "recipe_id": "e4b1a8d0-2f9b-4b11-9e73-1a2b3c4d5e01"
}

// Option B: Custom Craving
POST /api/choose
{
  "custom_note": "Spicy Thai Green Curry Takeout"
}
```

---

## 🧪 Testing

Run the automated test suite with `pytest`:
```bash
pytest -v
```
All endpoints and mock fallback behaviors are covered.
