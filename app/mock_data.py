"""Mock data and fallback recipes for Dinner Decider.

Used when Mealie is unreachable, not yet configured, or when MOCK_MODE is enabled.
"""

from typing import List, Dict, Any

MOCK_RECIPES: List[Dict[str, Any]] = [
    {
        "id": "e4b1a8d0-2f9b-4b11-9e73-1a2b3c4d5e01",
        "name": "Crispy Honey Garlic Salmon",
        "slug": "crispy-honey-garlic-salmon",
        "description": "Pan-seared salmon fillets glazed in a sticky, sweet honey garlic sauce with a squeeze of fresh lemon and toasted sesame seeds.",
        "totalTime": "25 mins",
        "category": "Seafood",
        "emoji": "🐟",
        "gradient": ("#f97316", "#e11d48"),
        "recipeCategory": [{"name": "Dinner", "slug": "dinner"}],
        "tools": [{"name": "Cast Iron Skillet", "slug": "cast-iron-skillet"}],
        "tags": [
            {"name": "seafood", "slug": "seafood"},
            {"name": "skillet", "slug": "skillet"},
            {"name": "quick-weeknight", "slug": "quick-weeknight"},
            {"name": "light-fresh", "slug": "light-fresh"},
            {"name": "gluten-free", "slug": "gluten-free"},
        ],
    },
    {
        "id": "e4b1a8d0-2f9b-4b11-9e73-1a2b3c4d5e02",
        "name": "Creamy Tuscan Garlic Chicken",
        "slug": "creamy-tuscan-garlic-chicken",
        "description": "Tender chicken breasts in a rich garlic cream sauce simmered with sun-dried tomatoes, wilted baby spinach, and parmesan.",
        "totalTime": "35 mins",
        "category": "Poultry",
        "emoji": "🍗",
        "gradient": ("#eab308", "#d97706"),
        "recipeCategory": [{"name": "Dinner", "slug": "dinner"}],
        "tools": [{"name": "Cast Iron Skillet", "slug": "cast-iron-skillet"}],
        "tags": [
            {"name": "chicken", "slug": "chicken"},
            {"name": "skillet", "slug": "skillet"},
            {"name": "comfort-food", "slug": "comfort-food"},
            {"name": "italian", "slug": "italian"},
            {"name": "low-carb", "slug": "low-carb"},
        ],
    },
    {
        "id": "e4b1a8d0-2f9b-4b11-9e73-1a2b3c4d5e03",
        "name": "Artisan Margherita Pizza",
        "slug": "artisan-margherita-pizza",
        "description": "Crispy charred crust topped with San Marzano tomato sauce, bubbly fresh mozzarella, aromatic basil leaves, and extra virgin olive oil.",
        "totalTime": "30 mins",
        "category": "Italian",
        "emoji": "🍕",
        "gradient": ("#ef4444", "#b91c1c"),
        "recipeCategory": [{"name": "Dinner", "slug": "dinner"}],
        "tools": [{"name": "Baking Dish", "slug": "baking-dish"}],
        "tags": [
            {"name": "vegetarian", "slug": "vegetarian"},
            {"name": "baked-casserole", "slug": "baked-casserole"},
            {"name": "italian", "slug": "italian"},
            {"name": "kid-friendly", "slug": "kid-friendly"},
            {"name": "comfort-food", "slug": "comfort-food"},
        ],
    },
    {
        "id": "e4b1a8d0-2f9b-4b11-9e73-1a2b3c4d5e04",
        "name": "Slow-Cooker Beef Birria Tacos",
        "slug": "slow-cooker-beef-birria-tacos",
        "description": "Fork-tender chuck roast braised in rich guajillo consomme, folded into crispy corn tortillas with melted oaxaca cheese and cilantro.",
        "totalTime": "45 mins",
        "category": "Mexican",
        "emoji": "🌮",
        "gradient": ("#f59e0b", "#b45309"),
        "recipeCategory": [{"name": "Dinner", "slug": "dinner"}],
        "tools": [{"name": "Slow Cooker", "slug": "slow-cooker"}],
        "tags": [
            {"name": "beef", "slug": "beef"},
            {"name": "mexican-texmex", "slug": "mexican-texmex"},
            {"name": "crowd-pleaser", "slug": "crowd-pleaser"},
            {"name": "comfort-food", "slug": "comfort-food"},
        ],
    },
    {
        "id": "e4b1a8d0-2f9b-4b11-9e73-1a2b3c4d5e05",
        "name": "Spicy Sesame Peanut Noodles",
        "slug": "spicy-sesame-peanut-noodles",
        "description": "Chewy noodles tossed in a luscious peanut chili sauce, garnished with crisp cucumber matchsticks, scallions, and crushed peanuts.",
        "totalTime": "20 mins",
        "category": "Asian",
        "emoji": "🍜",
        "gradient": ("#d97706", "#92400e"),
        "recipeCategory": [{"name": "Dinner", "slug": "dinner"}],
        "tools": [{"name": "Wok", "slug": "wok"}],
        "tags": [
            {"name": "pasta-noodles", "slug": "pasta-noodles"},
            {"name": "vegetarian", "slug": "vegetarian"},
            {"name": "stir-fry", "slug": "stir-fry"},
            {"name": "quick-weeknight", "slug": "quick-weeknight"},
            {"name": "east-asian", "slug": "east-asian"},
        ],
    },
    {
        "id": "e4b1a8d0-2f9b-4b11-9e73-1a2b3c4d5e06",
        "name": "Lemon Herb Roasted Chicken & Veggies",
        "slug": "lemon-herb-roasted-chicken-veggies",
        "description": "Juicy bone-in chicken thighs roasted on a sheet pan with baby potatoes, rosemary, asparagus, and caramelized garlic cloves.",
        "totalTime": "40 mins",
        "category": "Sheet Pan",
        "emoji": "🥘",
        "gradient": ("#84cc16", "#4d7c0f"),
        "recipeCategory": [{"name": "Dinner", "slug": "dinner"}],
        "tools": [{"name": "Sheet Pan", "slug": "sheet-pan"}],
        "tags": [
            {"name": "chicken", "slug": "chicken"},
            {"name": "sheet-pan", "slug": "sheet-pan"},
            {"name": "low-effort", "slug": "low-effort"},
            {"name": "light-fresh", "slug": "light-fresh"},
            {"name": "gluten-free", "slug": "gluten-free"},
        ],
    },
    {
        "id": "e4b1a8d0-2f9b-4b11-9e73-1a2b3c4d5e07",
        "name": "Classic Double Smash Burgers",
        "slug": "classic-double-smash-burgers",
        "description": "Two lacy-edged smashed beef patties with melted American cheese, griddled onions, pickles, and secret burger sauce on toasted brioche.",
        "totalTime": "25 mins",
        "category": "Comfort Food",
        "emoji": "🍔",
        "gradient": ("#f97316", "#c2410c"),
        "recipeCategory": [{"name": "Dinner", "slug": "dinner"}],
        "tools": [{"name": "Cast Iron Skillet", "slug": "cast-iron-skillet"}],
        "tags": [
            {"name": "beef", "slug": "beef"},
            {"name": "skillet", "slug": "skillet"},
            {"name": "american-classic", "slug": "american-classic"},
            {"name": "quick-weeknight", "slug": "quick-weeknight"},
            {"name": "comfort-food", "slug": "comfort-food"},
            {"name": "kid-friendly", "slug": "kid-friendly"},
        ],
    },
    {
        "id": "e4b1a8d0-2f9b-4b11-9e73-1a2b3c4d5e08",
        "name": "Creamy Butternut Squash Risotto",
        "slug": "creamy-butternut-squash-risotto",
        "description": "Slow-stirred arborio rice with roasted butternut squash puree, crispy fried sage leaves, browned butter, and aged parmesan.",
        "totalTime": "40 mins",
        "category": "Vegetarian",
        "emoji": "🍲",
        "gradient": ("#fbbf24", "#d97706"),
        "recipeCategory": [{"name": "Dinner", "slug": "dinner"}],
        "tools": [{"name": "Dutch Oven", "slug": "dutch-oven"}],
        "tags": [
            {"name": "vegetarian", "slug": "vegetarian"},
            {"name": "one-pot", "slug": "one-pot"},
            {"name": "italian", "slug": "italian"},
            {"name": "comfort-food", "slug": "comfort-food"},
            {"name": "gluten-free", "slug": "gluten-free"},
        ],
    },
    {
        "id": "e4b1a8d0-2f9b-4b11-9e73-1a2b3c4d5e09",
        "name": "Asian Style Pork Burgers",
        "slug": "asian-style-pork-burgers",
        "description": "Juicy seasoned ground pork patties seared with ginger, garlic, scallions, and savory hoisin glaze.",
        "totalTime": "25 mins",
        "category": "Pork",
        "emoji": "🍔",
        "gradient": ("#f97316", "#c2410c"),
        "recipeCategory": [{"name": "Dinner", "slug": "dinner"}],
        "tools": [{"name": "Cast Iron Skillet", "slug": "cast-iron-skillet"}],
        "tags": [
            {"name": "pork", "slug": "pork"},
            {"name": "skillet", "slug": "skillet"},
            {"name": "sandwich-wrap", "slug": "sandwich-wrap"},
            {"name": "east-asian", "slug": "east-asian"},
            {"name": "quick-weeknight", "slug": "quick-weeknight"},
        ],
    },
    {
        "id": "e4b1a8d0-2f9b-4b11-9e73-1a2b3c4d5e10",
        "name": "Chicken Spiedini",
        "slug": "chicken-spiedini",
        "description": "Skewered tender chicken cutlets rolled in seasoned breadcrumbs and herb-infused lemon garlic butter, grilled over high heat.",
        "totalTime": "30 mins",
        "category": "Poultry",
        "emoji": "🔥",
        "gradient": ("#eab308", "#ca8a04"),
        "recipeCategory": [{"name": "Dinner", "slug": "dinner"}],
        "tools": [{"name": "Grill", "slug": "grill"}],
        "tags": [
            {"name": "chicken", "slug": "chicken"},
            {"name": "grill-bbq", "slug": "grill-bbq"},
            {"name": "quick-weeknight", "slug": "quick-weeknight"},
            {"name": "italian", "slug": "italian"},
        ],
    },
]


MOCK_SIDES: List[Dict[str, Any]] = [
    {
        "id": "side-e4b1-001",
        "name": "Garlic Butter Baby Potatoes",
        "slug": "garlic-butter-baby-potatoes",
        "description": "Crispy roasted mini gold potatoes tossed in melted butter, minced garlic, cracked pepper, and fresh parsley.",
        "totalTime": "25 mins",
        "category": "Side Dish",
        "emoji": "🥔",
        "gradient": ("#eab308", "#ca8a04"),
        "recipeCategory": [{"name": "Side Dish", "slug": "side-dish"}],
        "tools": [{"name": "Sheet Pan", "slug": "sheet-pan"}],
        "tags": [
            {"name": "vegetarian", "slug": "vegetarian"},
            {"name": "comfort-food", "slug": "comfort-food"},
            {"name": "gluten-free", "slug": "gluten-free"},
        ],
    },
    {
        "id": "side-e4b1-002",
        "name": "Chimichurri Green Bean Salad",
        "slug": "chimichurri-green-bean-salad",
        "description": "Blanched crisp green beans tossed with aromatic chimichurri herb dressing and toasted pine nuts.",
        "totalTime": "20 mins",
        "category": "Side Dish",
        "emoji": "🥗",
        "gradient": ("#10b981", "#059669"),
        "recipeCategory": [{"name": "Side Dish", "slug": "side-dish"}],
        "tools": [],
        "tags": [
            {"name": "vegetarian", "slug": "vegetarian"},
            {"name": "salad", "slug": "salad"},
            {"name": "quick-weeknight", "slug": "quick-weeknight"},
            {"name": "light-fresh", "slug": "light-fresh"},
            {"name": "gluten-free", "slug": "gluten-free"},
        ],
    },
    {
        "id": "side-e4b1-003",
        "name": "Greek Lemon Potatoes",
        "slug": "greek-lemon-potatoes",
        "description": "Tender wedges baked with oregano, garlic, rich olive oil, and fresh squeezed lemon until golden.",
        "totalTime": "45 mins",
        "category": "Side Dish",
        "emoji": "🥔",
        "gradient": ("#f59e0b", "#d97706"),
        "recipeCategory": [{"name": "Side Dish", "slug": "side-dish"}],
        "tools": [{"name": "Baking Dish", "slug": "baking-dish"}],
        "tags": [
            {"name": "vegan", "slug": "vegan"},
            {"name": "mediterranean-greek", "slug": "mediterranean-greek"},
            {"name": "comfort-food", "slug": "comfort-food"},
            {"name": "gluten-free", "slug": "gluten-free"},
        ],
    },
    {
        "id": "side-e4b1-004",
        "name": "Miso-Glazed Roasted Brussels Sprouts",
        "slug": "miso-glazed-roasted-brussels-sprouts",
        "description": "Caramelized halved brussels sprouts glazed in savory sweet white miso with toasted sesame.",
        "totalTime": "25 mins",
        "category": "Side Dish",
        "emoji": "🥬",
        "gradient": ("#84cc16", "#4d7c0f"),
        "recipeCategory": [{"name": "Side Dish", "slug": "side-dish"}],
        "tools": [{"name": "Cast Iron Skillet", "slug": "cast-iron-skillet"}],
        "tags": [
            {"name": "vegan", "slug": "vegan"},
            {"name": "skillet", "slug": "skillet"},
            {"name": "quick-weeknight", "slug": "quick-weeknight"},
            {"name": "east-asian", "slug": "east-asian"},
        ],
    },
    {
        "id": "side-e4b1-005",
        "name": "Asian Slaw with Ginger Peanut Dressing",
        "slug": "asian-slaw-with-ginger-peanut-dressing",
        "description": "Shredded purple cabbage, carrots, scallions, and cilantro tossed in a creamy ginger peanut vinaigrette.",
        "totalTime": "15 mins",
        "category": "Side Dish",
        "emoji": "🥗",
        "gradient": ("#ec4899", "#be185d"),
        "recipeCategory": [{"name": "Side Dish", "slug": "side-dish"}],
        "tools": [],
        "tags": [
            {"name": "vegetarian", "slug": "vegetarian"},
            {"name": "salad", "slug": "salad"},
            {"name": "no-cook", "slug": "no-cook"},
            {"name": "east-asian", "slug": "east-asian"},
            {"name": "light-fresh", "slug": "light-fresh"},
        ],
    },
    {
        "id": "side-e4b1-006",
        "name": "Grilled Zucchini Ribbons",
        "slug": "grilled-zucchini-ribbons",
        "description": "Thin summer squash ribbons kissed by the grill, finished with extra virgin olive oil and sea salt.",
        "totalTime": "15 mins",
        "category": "Side Dish",
        "emoji": "🥒",
        "gradient": ("#10b981", "#047857"),
        "recipeCategory": [{"name": "Side Dish", "slug": "side-dish"}],
        "tools": [{"name": "Grill", "slug": "grill"}],
        "tags": [
            {"name": "vegetarian", "slug": "vegetarian"},
            {"name": "grill-bbq", "slug": "grill-bbq"},
            {"name": "gluten-free", "slug": "gluten-free"},
            {"name": "low-carb", "slug": "low-carb"},
        ],
    },
    {
        "id": "side-e4b1-007",
        "name": "Scalloped Potatoes",
        "slug": "scalloped-potatoes",
        "description": "Ultra-thin sliced russet potatoes layered in creamy garlic thyme sauce and baked bubbly golden.",
        "totalTime": "55 mins",
        "category": "Side Dish",
        "emoji": "🥔",
        "gradient": ("#eab308", "#a16207"),
        "recipeCategory": [{"name": "Side Dish", "slug": "side-dish"}],
        "tools": [{"name": "Baking Dish", "slug": "baking-dish"}],
        "tags": [
            {"name": "vegetarian", "slug": "vegetarian"},
            {"name": "baked-casserole", "slug": "baked-casserole"},
            {"name": "comfort-food", "slug": "comfort-food"},
            {"name": "american-classic", "slug": "american-classic"},
            {"name": "make-ahead", "slug": "make-ahead"},
        ],
    },
    {
        "id": "side-e4b1-008",
        "name": "Sweet Potato Fries (Crispy Baked)",
        "slug": "sweet-potato-fries-crispy-baked",
        "description": "Hand-cut sweet potato batons spiced with smoked paprika, sea salt, and garlic.",
        "totalTime": "30 mins",
        "category": "Side Dish",
        "emoji": "🍟",
        "gradient": ("#f97316", "#c2410c"),
        "recipeCategory": [{"name": "Side Dish", "slug": "side-dish"}],
        "tools": [{"name": "Sheet Pan", "slug": "sheet-pan"}],
        "tags": [
            {"name": "vegan", "slug": "vegan"},
            {"name": "sheet-pan", "slug": "sheet-pan"},
            {"name": "kid-friendly", "slug": "kid-friendly"},
            {"name": "american-classic", "slug": "american-classic"},
            {"name": "gluten-free", "slug": "gluten-free"},
        ],
    },
    {
        "id": "side-e4b1-009",
        "name": "Roasted Carrots with Spring Pesto",
        "slug": "roasted-carrots-with-spring-pesto",
        "description": "Caramelized rainbow carrots topped with vibrant fresh herb and pumpkin seed pesto.",
        "totalTime": "30 mins",
        "category": "Side Dish",
        "emoji": "🥕",
        "gradient": ("#f97316", "#ea580c"),
        "recipeCategory": [{"name": "Side Dish", "slug": "side-dish"}],
        "tools": [{"name": "Sheet Pan", "slug": "sheet-pan"}],
        "tags": [
            {"name": "vegan", "slug": "vegan"},
            {"name": "sheet-pan", "slug": "sheet-pan"},
            {"name": "light-fresh", "slug": "light-fresh"},
            {"name": "gluten-free", "slug": "gluten-free"},
            {"name": "dairy-free", "slug": "dairy-free"},
        ],
    },
    {
        "id": "side-e4b1-010",
        "name": "Mexican Red Rice",
        "slug": "mexican-red-rice",
        "description": "Fluffy long-grain rice toasted in oil and simmered in tomato broth with garlic, onion, and cumin.",
        "totalTime": "25 mins",
        "category": "Side Dish",
        "emoji": "🍚",
        "gradient": ("#ef4444", "#b91c1c"),
        "recipeCategory": [{"name": "Side Dish", "slug": "side-dish"}],
        "tools": [{"name": "Dutch Oven", "slug": "dutch-oven"}],
        "tags": [
            {"name": "vegetarian", "slug": "vegetarian"},
            {"name": "one-pot", "slug": "one-pot"},
            {"name": "quick-weeknight", "slug": "quick-weeknight"},
            {"name": "mexican-texmex", "slug": "mexican-texmex"},
            {"name": "gluten-free", "slug": "gluten-free"},
        ],
    },
]


def generate_recipe_svg(title: str, emoji: str = "🍽️", c1: str = "#f59e0b", c2: str = "#b45309") -> str:
    """Generate an elegant, high-quality SVG image placeholder for a recipe."""
    escaped_title = (
        title.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 500" width="100%" height="100%">
  <defs>
    <linearGradient id="grad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{c1}" />
      <stop offset="100%" stop-color="{c2}" />
    </linearGradient>
    <radialGradient id="glow" cx="50%" cy="40%" r="50%">
      <stop offset="0%" stop-color="rgba(255,255,255,0.25)" />
      <stop offset="100%" stop-color="rgba(0,0,0,0.3)" />
    </radialGradient>
    <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="8" stdDeviation="12" flood-color="rgba(0,0,0,0.3)"/>
    </filter>
  </defs>
  <!-- Background with warm gradient -->
  <rect width="800" height="500" fill="url(#grad)" />
  <rect width="800" height="500" fill="url(#glow)" />
  
  <!-- Subtle decorative geometric circles -->
  <circle cx="700" cy="80" r="180" fill="rgba(255,255,255,0.06)" />
  <circle cx="100" cy="420" r="220" fill="rgba(0,0,0,0.08)" />

  <!-- Center Cloche / Food Illustration Plate -->
  <g transform="translate(400, 200)">
    <circle cx="0" cy="0" r="95" fill="rgba(255,255,255,0.2)" stroke="rgba(255,255,255,0.4)" stroke-width="3" filter="url(#shadow)" />
    <circle cx="0" cy="0" r="80" fill="rgba(255,255,255,0.92)" />
    <text x="0" y="24" font-size="72" text-anchor="middle" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif">{emoji}</text>
  </g>

  <!-- Title Pill at bottom -->
  <g transform="translate(400, 390)">
    <rect x="-260" y="-24" width="520" height="48" rx="24" fill="rgba(15, 23, 42, 0.65)" stroke="rgba(255,255,255,0.2)" stroke-width="1.5" />
    <text x="0" y="6" font-size="20" font-weight="600" fill="#ffffff" text-anchor="middle" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" letter-spacing="0.5">
      {escaped_title}
    </text>
  </g>
</svg>"""
