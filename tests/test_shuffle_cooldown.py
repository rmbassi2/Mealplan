import pytest
from httpx import AsyncClient, ASGITransport

from main import app
from app.mealie_client import mealie_client
from app.mock_data import MOCK_RECIPES
from app.shuffle_cooldown import ShuffleCooldownTracker
from app.taxonomy import select_balanced_recipes, select_side_recipes


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def reset_shuffle_cooldown():
    """Ensure shuffle cooldown state is clean before and after every test."""
    orig_tracker = mealie_client.shuffle_cooldown
    mealie_client.clear_shuffle_cooldown()
    yield
    mealie_client.shuffle_cooldown = orig_tracker
    mealie_client.clear_shuffle_cooldown()


def test_cooldown_tracker_decay_and_expiry():
    now = [1000.0]
    tracker = ShuffleCooldownTracker(cooldown_seconds=1800.0, time_fn=lambda: now[0])

    tracker.record_shuffled(["rec-1", "rec-2"])
    p0 = tracker.get_penalties()
    assert set(p0.keys()) == {"rec-1", "rec-2"}
    assert p0["rec-1"] == pytest.approx(1.0)

    # 15 minutes later -> half cooldown remaining
    now[0] += 900.0
    p15 = tracker.get_penalties()
    assert p15["rec-1"] == pytest.approx(0.5)

    # Refresh rec-2 at 15 minutes -> rec-2 resets to 1.0 while rec-1 stays at 0.5
    tracker.record_shuffled(["rec-2"])
    p15_after = tracker.get_penalties()
    assert p15_after["rec-1"] == pytest.approx(0.5)
    assert p15_after["rec-2"] == pytest.approx(1.0)

    # 30 minutes after initial shuffle -> rec-1 expires, rec-2 still has 15 minutes left
    now[0] += 900.0
    p30 = tracker.get_penalties()
    assert "rec-1" not in p30
    assert p30["rec-2"] == pytest.approx(0.5)

    # Another 15 minutes -> rec-2 also expires
    now[0] += 900.0
    assert tracker.get_penalties() == {}


def test_cooldown_tracker_disabled_when_zero():
    tracker = ShuffleCooldownTracker(cooldown_seconds=0)
    tracker.record_shuffled(["rec-1"])
    assert tracker.get_penalties() == {}


def test_select_balanced_recipes_excludes_penalized_when_fresh_available():
    penalized_ids = {r["id"] for r in MOCK_RECIPES[:4]}
    penalties = {rid: 0.95 for rid in penalized_ids}

    # Across many trials, none of the penalized recipes should appear since 6 fresh remain
    for _ in range(40):
        selected = select_balanced_recipes(MOCK_RECIPES, count=3, penalized_recipes=penalties)
        assert len(selected) == 3
        chosen_ids = {r["id"] for r in selected}
        assert chosen_ids.isdisjoint(penalized_ids)


def test_select_balanced_recipes_partial_fallback_prioritizes_fresh():
    # Leave only 2 fresh recipes out of 10; both fresh recipes must be chosen first
    fresh_ids = {r["id"] for r in MOCK_RECIPES[:2]}
    penalties = {r["id"]: 0.9 for r in MOCK_RECIPES[2:]}

    for _ in range(25):
        selected = select_balanced_recipes(MOCK_RECIPES, count=3, penalized_recipes=penalties)
        assert len(selected) == 3
        chosen_ids = {r["id"] for r in selected}
        assert fresh_ids.issubset(chosen_ids)


def test_select_balanced_recipes_full_cooldown_prefers_oldest_shuffled():
    # All 6 recipes are on cooldown: first 3 shuffled 20 mins ago, last 3 shuffled 2 secs ago
    pool = MOCK_RECIPES[:6]
    old_ids = {r["id"] for r in pool[:3]}
    new_ids = {r["id"] for r in pool[3:]}
    penalties = {
        **{rid: 10 / 30 for rid in old_ids},
        **{rid: 29.97 / 30 for rid in new_ids},
    }

    old_hits = 0
    new_hits = 0
    for _ in range(50):
        selected = select_balanced_recipes(pool, count=3, penalized_recipes=penalties)
        for r in selected:
            if r["id"] in old_ids:
                old_hits += 1
            else:
                new_hits += 1

    # Oldest-shuffled recipes should overwhelmingly win over just-shuffled recipes
    assert old_hits > new_hits * 10


def test_select_side_recipes_avoids_penalized_sides():
    side_candidates = [
        {"id": "s-sal-1", "name": "Garden Salad", "recipeCategory": [{"name": "Side Dish"}], "tags": [{"slug": "salad"}]},
        {"id": "s-sal-2", "name": "Asian Slaw", "recipeCategory": [{"name": "Side Dish"}], "tags": [{"slug": "salad"}]},
        {"id": "s-sta-1", "name": "Garlic Potatoes", "recipeCategory": [{"name": "Side Dish"}], "tags": [{"slug": "vegan"}]},
        {"id": "s-sta-2", "name": "Mexican Red Rice", "recipeCategory": [{"name": "Side Dish"}], "tags": [{"slug": "one-pot"}]},
        {"id": "s-veg-1", "name": "Roasted Broccoli", "recipeCategory": [{"name": "Side Dish"}], "tags": [{"slug": "sheet-pan"}]},
        {"id": "s-veg-2", "name": "Grilled Zucchini", "recipeCategory": [{"name": "Side Dish"}], "tags": [{"slug": "grill-bbq"}]},
    ]
    penalized = {"s-sal-1": 1.0, "s-sta-1": 1.0, "s-veg-1": 1.0}

    for _ in range(20):
        picked = select_side_recipes(side_candidates, count=3, penalized_recipes=penalized)
        picked_ids = {s["id"] for s in picked}
        assert picked_ids == {"s-sal-2", "s-sta-2", "s-veg-2"}


@pytest.mark.anyio
async def test_api_options_shuffle_penalty_and_expiry():
    now = [5000.0]
    mealie_client.shuffle_cooldown = ShuffleCooldownTracker(
        cooldown_seconds=1800.0,
        time_fn=lambda: now[0],
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Initial load: 3 dinner options
        r1 = await client.get("/api/options")
        assert r1.status_code == 200
        batch1_ids = [o["id"] for o in r1.json()["options"]]
        assert len(batch1_ids) == 3

        # Shuffle #1: penalize batch 1 -> none of batch 1 should appear in batch 2
        r2 = await client.get(f"/api/options?penalize={','.join(batch1_ids)}")
        assert r2.status_code == 200
        batch2_ids = [o["id"] for o in r2.json()["options"]]
        assert len(batch2_ids) == 3
        assert set(batch2_ids).isdisjoint(set(batch1_ids))

        # Shuffle #2: penalize batch 2 -> neither batch 1 nor batch 2 should appear in batch 3
        # (MOCK_RECIPES has 10 items, so 4 fresh recipes still remain)
        r3 = await client.get(f"/api/options?penalize={','.join(batch2_ids)}")
        assert r3.status_code == 200
        batch3_ids = [o["id"] for o in r3.json()["options"]]
        assert len(batch3_ids) == 3
        assert set(batch3_ids).isdisjoint(set(batch1_ids) | set(batch2_ids))

        # Subsequent non-shuffle fetch within 30 mins still respects the 6 penalized recipes
        r4 = await client.get("/api/options")
        assert r4.status_code == 200
        batch4_ids = [o["id"] for o in r4.json()["options"]]
        assert set(batch4_ids).isdisjoint(set(batch1_ids) | set(batch2_ids))

        # Fast-forward 31 minutes -> cooldown expires, all recipes eligible again
        now[0] += 31 * 60
        assert mealie_client.shuffle_cooldown.get_penalties() == {}


@pytest.mark.anyio
async def test_api_side_options_shuffle_penalty():
    now = [8000.0]
    mealie_client.shuffle_cooldown = ShuffleCooldownTracker(
        cooldown_seconds=1800.0,
        time_fn=lambda: now[0],
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r1 = await client.get("/api/side-options")
        assert r1.status_code == 200
        side_batch1 = [o["id"] for o in r1.json()["options"]]
        assert len(side_batch1) == 3

        # Shuffle sides away -> none of batch 1 should reappear immediately
        r2 = await client.get(f"/api/side-options?penalize={','.join(side_batch1)}")
        assert r2.status_code == 200
        side_batch2 = [o["id"] for o in r2.json()["options"]]
        assert len(side_batch2) == 3
        assert set(side_batch2).isdisjoint(set(side_batch1))
