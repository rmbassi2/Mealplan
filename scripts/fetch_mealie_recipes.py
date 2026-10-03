import asyncio
import json
import os
import sys
from dotenv import load_dotenv
import httpx

load_dotenv()

BASE_URL = os.getenv("MEALIE_BASE_URL", "https://mealie.rmbtech.ca").rstrip("/")
API_TOKEN = os.getenv("MEALIE_API_TOKEN", "")

if not API_TOKEN:
    # Try reading from Mealie Tagging if not in current .env
    tagging_env = r"C:\Users\Rob\Documents\Projects\Mealie Tagging\.env"
    if os.path.exists(tagging_env):
        with open(tagging_env, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MEALIE_API_TOKEN="):
                    API_TOKEN = line.split("=", 1)[1].strip()
                elif line.startswith("MEALIE_URL="):
                    BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

print(f"Connecting to Mealie at {BASE_URL}...")
headers = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Accept": "application/json",
}

async def fetch_all_recipes():
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(f"{BASE_URL}/api/recipes?perPage=250", headers=headers)
        if resp.status_code != 200:
            print(f"Failed to fetch recipe list: {resp.status_code} - {resp.text}")
            return []
        
        data = resp.json()
        items = data.get("items", []) if isinstance(data, dict) else data
        print(f"Discovered {len(items)} recipes in Mealie. Fetching full details for each...")

        sem = asyncio.Semaphore(10)
        full_recipes = []

        async def fetch_one(slug):
            async with sem:
                try:
                    r = await client.get(f"{BASE_URL}/api/recipes/{slug}", headers=headers)
                    if r.status_code == 200:
                        return r.json()
                    else:
                        print(f"Warning: HTTP {r.status_code} for recipe {slug}")
                except Exception as e:
                    print(f"Error fetching recipe {slug}: {e}")
                return None

        tasks = [fetch_one(it["slug"]) for it in items if "slug" in it]
        results = await asyncio.gather(*tasks)
        full_recipes = [r for r in results if r is not None]
        print(f"Successfully fetched {len(full_recipes)} full recipes.")

        # Save to data/recipes_cache.json
        os.makedirs("data", exist_ok=True)
        with open("data/mock_recipes_real.json", "w", encoding="utf-8") as f:
            json.dump(full_recipes, f, indent=2, ensure_ascii=False)
        print("Saved to data/mock_recipes_real.json")
        return full_recipes

if __name__ == "__main__":
    asyncio.run(fetch_all_recipes())
