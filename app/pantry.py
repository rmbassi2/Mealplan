"""Pantry Inventory Management & Recipe Matching Engine.

Provides lightweight, zero-friction ingredient availability tracking
using an embedded SQLite database. Evaluates whether recipes are 100%
pantry-ready or at most 1 ingredient away.
"""

import logging
import os
import re
import sqlite3
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from app.config import settings

logger = logging.getLogger("pantry")

# Default common kitchen staples that do not count as missing ingredients
DEFAULT_STAPLES: Set[str] = {
    "salt",
    "kosher salt",
    "sea salt",
    "table salt",
    "pepper",
    "black pepper",
    "freshly ground black pepper",
    "ground black pepper",
    "cracked pepper",
    "water",
    "tap water",
    "ice water",
    "olive oil",
    "extra virgin olive oil",
    "extra-virgin olive oil",
    "cooking oil",
    "vegetable oil",
    "canola oil",
    "cooking spray",
    "sugar",
    "granulated sugar",
    "white sugar",
    "brown sugar",
    "flour",
    "all-purpose flour",
}

# Baseline pantry staples permanently considered in stock so recipes are not blocked by a pinch of spice
ALWAYS_ON_STAPLES: Set[str] = {
    # Baseline fats & oils
    "bacon fat",
    "butter",
    "cooking oil",
    "neutral oil",
    "vegetable oil",
    "canola oil",
    "olive oil",
    "extra virgin olive oil",
    "sesame oil",
    # Baking basics
    "flour",
    "all purpose flour",
    "all-purpose flour",
    "bread flour",
    "sugar",
    "brown sugar",
    "granulated sugar",
    "baking soda",
    "baking powder",
    "cornstarch",
    "vanilla extract",
    "instant yeast",
    "active dry yeast",
    "yeast",
    # Basic vinegars & liquids
    "apple cider vinegar",
    "balsamic vinegar",
    "red wine vinegar",
    "rice vinegar",
    "white vinegar",
    "shaoxing wine",
    "soy sauce",
    "low sodium soy sauce",
    "fish sauce",
    "worcestershire",
    "honey",
    "tomato paste",
    # Dry spices & seasonings
    "allspice",
    "bay leaf",
    "black pepper",
    "cardamom",
    "cayenne pepper",
    "chili flake",
    "chili powder",
    "cinnamon",
    "clove",
    "coriander",
    "ground coriander",
    "cumin",
    "curry powder",
    "garlic powder",
    "ground ginger",
    "italian seasoning",
    "kashmiri chilli powder",
    "kasoori methi",
    "msg",
    "mustard powder",
    "nutmeg",
    "onion powder",
    "oregano",
    "paprika",
    "smoked paprika",
    "salt",
    "star anise",
    "thyme",
    "turmeric",
    # Grains & long-life staples
    "white rice",
    "rolled oats",
    "breadcrumb",
    "panko",
    "dried pasta",
    "pasta",
    "black bean",
    "cannellini",
    "chickpea",
    "canned tomato",
    "crushed tomato",
    "diced tomato",
    "whole peeled tomato",
}

# Measurement words and culinary stop words to strip during string cleaning
MEASUREMENT_WORDS = re.compile(
    r"\b(\d+([./]\d+)?|\d+-\d+)\s*"
    r"(cups?|tbsp|tablespoons?|tsp|teaspoons?|lbs?|pounds?|oz|ounces?|g|grams?|kg|"
    r"ml|liters?|cloves?|slices?|pinch(es)?|dash(es)?|cans?|jars?|packages?|pkgs?|"
    r"heads?|bunches?|stalks?|pieces?)\b",
    re.IGNORECASE,
)

UNIT_WORDS = re.compile(
    r"\b(cups?|c\.|c\b|tbsp|tbs|tablespoons?|tsp|teaspoons?|lbs?|pounds?|oz|ounces?|g|grams?|kg|"
    r"ml|liters?|litres?|cloves?|slices?|pinch(es)?|dash(es)?|cans?|jars?|packages?|pkgs?|"
    r"heads?|bunches?|stalks?|pieces?|sprigs?|handfuls?)\b",
    re.IGNORECASE,
)

PREP_WORDS = re.compile(
    r"\b(organic|diced|chopped|minced|sliced|crushed|grated|shredded|melted|softened|"
    r"warm|cold|fresh|freshly|dried|ground|boneless|skinless|cooked|uncooked|"
    r"to taste|divided|optional|room temperature)\b",
    re.IGNORECASE,
)

FRACTION_MAP: Dict[str, str] = {
    "¼": " 1/4 ", "½": " 1/2 ", "¾": " 3/4 ",
    "⅓": " 1/3 ", "⅔": " 2/3 ",
    "⅛": " 1/8 ", "⅜": " 3/8 ", "⅝": " 5/8 ", "⅞": " 7/8 ",
    "¹": "1", "²": "2", "³": "3", "⁴": "4",
    "₁": "1", "₂": "2", "₃": "3", "₄": "4",
}

DISCARD_PATTERNS = [
    re.compile(r"could\s+not\s+detect", re.I),
    re.compile(r"unable\s+to\s+detect", re.I),
    re.compile(r"check\s+the\s+notes?", re.I),
    re.compile(r"^\s*\*{2,}", re.I),
    re.compile(r"recommend\s+doubling", re.I),
    re.compile(r"^other\s+ideas\b", re.I),
    re.compile(r"^tips?\s*:", re.I),
    re.compile(r"^substitutions?\s*:", re.I),
    re.compile(r"^variations?\s*:", re.I),
    re.compile(r"^instructions?\s*:", re.I),
    re.compile(r"^directions?\s*:", re.I),
    re.compile(r"^step\s*\d+", re.I),
    re.compile(r"^for\s+greasing\b", re.I),
    re.compile(r"^recipe\s+(guacamole|pico\s+de\s+gallo)\b", re.I),
    re.compile(r"for\s+serving,?\s+if\s+desired", re.I),
    re.compile(r"^vegetables?\s+of\s+choice", re.I),
    re.compile(r"^skewers?\b", re.I),
    re.compile(r".*\bcount\s+size\b.*", re.I),
    re.compile(r"^seasoning\s+package\b", re.I),
    re.compile(r"^lettuce,\s*tomato.*", re.I),
    re.compile(r"^thai\s+basil,\s*mi[nt].*", re.I),
    re.compile(r"^lemon\s+wedges,?\s*(?:fresh\s+)?oregano.*", re.I),
    re.compile(r"^peas\s+and\s+carrots\b", re.I),
    re.compile(r"^broccoli\s+and\s+cauliflower\b", re.I),
    re.compile(r"^length\s+ginger\b", re.I),
    re.compile(r"^to\s+15\s+green\s+beans?\b", re.I),
    re.compile(r"^to\s+2\s+scotch\s+bonnet\b", re.I),
    re.compile(r"^scotch\s+bonnet\s+peppers?\s+or\s+habanero\b", re.I),
    re.compile(r"^ginger\s+chill?i\s+garlic\b", re.I),
    re.compile(r"^pickled\s+jalapeno\s+juice\b", re.I),
    re.compile(r"^(?:bone\s+)?broth$", re.I),
    re.compile(r"^(?:bone\s+)?stock$", re.I),
    re.compile(r"^pecans?\s+or\s+walnuts?\b", re.I),
    re.compile(r"^cheese$", re.I),
]

PREP_WORDS_PATTERN = (
    r"\b(finely|coarsely|roughly|thinly|fresh-squeezed|squeezed|freshly|fresh|lightly|"
    r"chopped|diced|minced|sliced|crushed|grated|shredded|peeled|halved|quartered|"
    r"drained|juiced|zested|cooked|uncooked|packed|melted|softened|warm|cold|hot|"
    r"trimmed|cored|stemmed|cleaned|thawed|cut\s+into|cut\s+in|boneless|skinless|"
    r"organic|dried|cloves?|unsalted|salted|ripe|mashed|beaten|crumbled|pressed)\b"
)
PREP_REGEX = re.compile(PREP_WORDS_PATTERN, re.I)

PREP_TRAILING_CHECK = re.compile(
    r"\b(cut|peeled|sliced|chopped|diced|minced|grated|shredded|crushed|cored|"
    r"stem|halved|quartered|drained|juiced|zested|cooked|thawed|trimmed|cleaned|"
    r"packed|finely|roughly|coarsely|lightly|plus|for garnish|for serving|to serve|"
    r"to taste|divided|optional|not spicy|any brand|brand fine|seeds removed|about|"
    r"browned|room temp|room temperature|warmed up|softened|melted|cubed|very cold|"
    r"beaten|crumbled|pressed|bubbly|fridge|preferably)\b",
    re.I,
)

FOOD_NOUN_CHECK = re.compile(
    r"\b(chicken|beef|pork|lamb|turkey|meat|fish|shrimp|salmon|tuna|steak|bacon|sausage|"
    r"onion|garlic|tomato|potato|carrot|cabbage|pepper|chile|zucchini|cucumber|"
    r"basil|parsley|cilantro|rosemary|thyme|sage|dill|lemon|lime|spinach|lettuce|"
    r"beans|lentils|rice|pasta|noodle|spaghetti|cheese|milk|cream|butter|yogurt|"
    r"broth|stock|oil|flour|sugar|sauce|powder|spice|curry|sprouts|ginger|fillets?|"
    r"pecans?|walnuts?|almonds?|cashews?|peanuts?|tofu|paneer|oats?|bread|bun|buns)\b",
    re.I,
)

UNIT_PREFIX_REGEX = re.compile(
    r"^\s*(?:"
    r"(\d+(\.\d+)?\s*[-–—/]\s*\d+(\.\d+)?|\d+([./]\d+)?)\s*|"
    r"(th|rd|st|nd)\s+|"
    r"(\d+(\.\d+)?\s*)?(gm|g|grams?|kg|kgs|kilos?|ml|mls|milliliters?|litres?|liters?|l)\b\/?\/?\s*|"
    r"(\d+(\.\d+)?\s*)?(cups?|c\.|c|tbsp|tbs|tablespoons?|tsp|teaspoons?|t)\b\s*|"
    r"(\d+(\.\d+)?\s*)?(lbs?|lb\.|pounds?|oz|oz\.|ounces?)\b\/?\/?\s*|"
    r"(\d+(\.\d+)?\s*)?(cans?|jars?|pkgs?|packages?|heads?|bunches?|bunch|stalks?|pieces?|piece|sprigs?|springs?|handfuls?|sticks?|stick|quarts?|qt|gallons?|gal|containers?|container|box(?:es)?|bottles?|knobs?|slices?|cloves?|ribs?)\b\s*|"
    r"(pinch(?:es)?|tiny\s+pinch|dash(?:es)?)\b\s*(?:of\s+)?|"
    r"(large|medium|small|medium-small|extra-large|xl|big|tiny|inch(?:es)?|knob)\b\s*|"
    r"(x|of|about|or|and|plus|with)\b\s*|"
    r"i\s+use\b\s*|"
    r"\/\s*\d+(\.\d+)?\s*(kg|g|gm|lb|lbs|oz|ml|l)\b\s*"
    r")",
    re.I,
)

PLURAL_MAP: Dict[str, str] = {
    "breasts": "breast",
    "cutlets": "cutlet",
    "fillets": "fillet",
    "steaks": "steak",
    "patties": "patty",
    "ribs": "rib",
    "wings": "wing",
    "drumsticks": "drumstick",
    "sausages": "sausage",
    "shrimps": "shrimp",
    "tomatoes": "tomato",
    "potatoes": "potato",
    "onions": "onion",
    "carrots": "carrot",
    "cucumbers": "cucumber",
    "limes": "lime",
    "lemons": "lemon",
    "cloves": "garlic",
    "scallions": "scallion",
    "shallots": "shallot",
    "mushrooms": "mushroom",
    "bananas": "banana",
    "apples": "apple",
    "peaches": "peach",
    "berries": "berry",
    "strawberries": "strawberry",
    "blueberries": "blueberry",
    "avocados": "avocado",
    "peppers": "pepper",
    "chiles": "chile",
    "chillies": "chilli",
    "chilies": "chili",
    "beans": "bean",
    "peas": "pea",
    "sprouts": "sprout",
    "radishes": "radish",
    "zucchinis": "zucchini",
    "eggplants": "eggplant",
    "leaves": "leaf",
    "eggs": "egg",
    "yolks": "yolk",
    "whites": "white",
    "cheeses": "cheese",
    "buns": "bun",
    "rolls": "roll",
    "tortillas": "tortilla",
    "crackers": "cracker",
    "crumbs": "crumb",
    "breadcrumbs": "breadcrumb",
    "noodles": "noodle",
    "wafers": "wafer",
    "cookies": "cookie",
    "pretzels": "pretzel",
    "seeds": "seed",
    "walnuts": "walnut",
    "pecans": "pecan",
    "almonds": "almond",
    "peanuts": "peanut",
    "cashews": "cashew",
    "pistachios": "pistachio",
    "oils": "oil",
    "chips": "chip",
}

HERB_LEAF_PATTERNS = re.compile(
    r"^(basil|rosemary|thyme|oregano|parsley|spinach|cilantro|mint|coriander)\s+leaves$", re.I
)
CHEESE_BASE_PATTERNS = re.compile(
    r"^(cheddar|mozzarella|parmesan|feta|gruyère|gruyere|monterey\s+jack|provolone|swiss|gouda|asiago)\s+cheese$", re.I
)

SYNONYMS: Dict[str, Tuple[str, str]] = {
    "bicarbonate of soda": ("baking soda", "Baking Soda"),
    "all spice powder": ("allspice", "Allspice"),
    "mayonnaise": ("mayo", "Mayo"),
    "beansprouts": ("bean sprout", "Bean Sprouts"),
    "fresno chili": ("fresno chile", "Fresno Chile"),
    "jalapeno pepper": ("jalapeno", "Jalapeno"),
    "chardonnay wine": ("chardonnay", "Chardonnay"),
    "dry bay leaf": ("bay leaf", "Bay Leaf"),
    "dry thyme": ("thyme", "Thyme"),
    "dry linguine": ("linguine", "Linguine"),
    "regular breadcrumbs": ("breadcrumb", "Breadcrumbs"),
    "whole fully cooked bone in ham": ("ham", "Ham"),
    "active sourdough starter": ("sourdough starter", "Sourdough Starter"),
    "unfed sourdough starter": ("sourdough starter", "Sourdough Starter"),
    "sourdough starter ripe": ("sourdough starter", "Sourdough Starter"),
    "sourdough discard": ("sourdough starter", "Sourdough Starter"),
    "levain": ("sourdough starter", "Sourdough Starter"),
    "sourdough starter": ("sourdough starter", "Sourdough Starter"),
    "black bean": ("black bean", "Black Beans"),
    "black beans": ("black bean", "Black Beans"),
    "canned black bean": ("black bean", "Black Beans"),
    "canned black beans": ("black bean", "Black Beans"),
    "canned chickpeas": ("chickpea", "Chickpeas"),
    "canned black olives": ("black olive", "Black Olives"),

    # Meat & Seafood consolidations
    "beef chuck or brisket": ("beef chuck roast", "Beef Chuck Roast"),
    "guanciale or smoked pancetta": ("pancetta", "Pancetta"),
    "firm tofu or paneer": ("tofu", "Tofu"),
    "firm tofu": ("tofu", "Tofu"),
    "extra firm tofu": ("tofu", "Tofu"),
    "extra-firm tofu": ("tofu", "Tofu"),
    "tofu": ("tofu", "Tofu"),
    "black tiger shrimp": ("shrimp", "Shrimp"),
    "shrimps": ("shrimp", "Shrimp"),
    "shrimp": ("shrimp", "Shrimp"),
    "lean ground meat like ground beef or ground turkey": ("ground beef", "Ground Beef"),
    "ground beef chuck": ("ground beef", "Ground Beef"),
    "lean ground beef": ("ground beef", "Ground Beef"),
    "chicken cutlet": ("chicken breast", "Chicken Breast"),
    "chicken cutlets": ("chicken breast", "Chicken Breast"),
    "thin slices prosciutto": ("prosciutto", "Prosciutto"),

    # Produce consolidations
    "baby yellow potato": ("baby potato", "Baby Potatoes"),
    "baby yellow potatoes": ("baby potato", "Baby Potatoes"),
    "baby yukon gold potato": ("baby yukon gold potato", "Baby Yukon Gold Potatoes"),
    "baby yukon gold potatoes": ("baby yukon gold potato", "Baby Yukon Gold Potatoes"),
    "red potato": ("potato", "Potatoes"),
    "red potatoes": ("potato", "Potatoes"),
    "baby tomato": ("cherry tomato", "Cherry Tomatoes"),
    "baby tomatoes": ("cherry tomato", "Cherry Tomatoes"),
    "grape or cherry tomato": ("cherry tomato", "Cherry Tomatoes"),
    "grape or cherry tomatoes": ("cherry tomato", "Cherry Tomatoes"),
    "whole peeled tomato": ("tomato", "Tomato"),
    "whole peeled tomatoes": ("tomato", "Tomato"),
    "sweet onion": ("yellow onion", "Yellow Onion"),
    "white onion": ("onion", "Onion"),
    "small red onion": ("red onion", "Red Onion"),
    "yellow or red onion": ("yellow onion", "Yellow Onion"),
    "green onion": ("scallion", "Scallions"),
    "cauliflower head": ("cauliflower", "Cauliflower"),
    "corn kernels": ("corn", "Corn"),
    "english cucumber": ("cucumber", "Cucumber"),
    "fennel bulb": ("fennel", "Fennel"),
    "flat leaf parsley": ("parsley", "Parsley"),
    "ginger root": ("ginger", "Ginger"),
    "green pepper": ("green bell pepper", "Green Bell Pepper"),
    "red pepper": ("red bell pepper", "Red Bell Pepper"),
    "red or green bell pepper": ("red bell pepper", "Red Bell Pepper"),
    "green chile peppers": ("green chile", "Green Chiles"),
    "green chile pepper": ("green chile", "Green Chiles"),
    "green chile": ("green chile", "Green Chiles"),
    "green chiles": ("green chile", "Green Chiles"),
    "green chillies": ("green chile", "Green Chiles"),
    "green chilli": ("green chile", "Green Chiles"),
    "green chili": ("green chile", "Green Chiles"),
    "green chilis": ("green chile", "Green Chiles"),
    "lime wedges": ("lime", "Lime"),
    "lemon juice": ("lemon", "Lemon"),
    "lemon zest": ("lemon", "Lemon"),
    "zest of lemon": ("lemon", "Lemon"),
    "juice of lemon": ("lemon", "Lemon"),
    "fresh lemon juice": ("lemon", "Lemon"),
    "fresh squeezed lemon juice": ("lemon", "Lemon"),
    "lemon": ("lemon", "Lemon"),
    "lemons": ("lemon", "Lemon"),
    "lime juice": ("lime", "Lime"),
    "lime zest": ("lime", "Lime"),
    "zest of lime": ("lime", "Lime"),
    "juice of lime": ("lime", "Lime"),
    "fresh lime juice": ("lime", "Lime"),
    "fresh squeezed lime juice": ("lime", "Lime"),
    "lime": ("lime", "Lime"),
    "limes": ("lime", "Lime"),
    "pomegranate arils": ("pomegranate", "Pomegranate"),
    "sliced peaches": ("peach", "Peaches"),
    "parsley or chives": ("parsley", "Parsley"),
    "serrano or jalapeno pepper": ("serrano", "Serrano"),
    "slaw mix or thin cabbage": ("cabbage", "Cabbage"),
    "slaw mix or thin sliced cabbage": ("cabbage", "Cabbage"),
    "scotch bonnet peppers or habanero chile": ("scotch bonnet habanero", "Scotch Bonnet / Habanero"),
    "scotch bonnet peppers or habanero chiles": ("scotch bonnet habanero", "Scotch Bonnet / Habanero"),
    "green cabbage": ("cabbage", "Cabbage"),
    "english cucumber": ("cucumber", "Cucumbers"),
    "persian cucumber": ("cucumber", "Cucumbers"),
    "persian cucumbers": ("cucumber", "Cucumbers"),
    "cucumber": ("cucumber", "Cucumbers"),
    "chilli peppers": ("chili pepper", "Chili Peppers"),
    "chilli pepper": ("chili pepper", "Chili Peppers"),
    "chili pepper": ("chili pepper", "Chili Peppers"),
    "chili peppers": ("chili pepper", "Chili Peppers"),
    "red chillies": ("red chile", "Red Chiles"),
    "red chilli": ("red chile", "Red Chiles"),
    "frozen peas": ("pea", "Peas (Frozen)"),
    "frozen pea": ("pea", "Peas (Frozen)"),
    "frozen/fresh green peas": ("pea", "Peas (Frozen)"),
    "frozen green peas": ("pea", "Peas (Frozen)"),
    "frozen green pea": ("pea", "Peas (Frozen)"),
    "green peas": ("pea", "Peas (Frozen)"),
    "green pea": ("pea", "Peas (Frozen)"),
    "peas": ("pea", "Peas (Frozen)"),
    "pea": ("pea", "Peas (Frozen)"),

    # Dairy & Eggs
    "danish creamery butter": ("butter", "Butter"),
    "sharp white cheddar": ("cheddar", "Cheddar"),
    "sharp yellow cheddar": ("cheddar", "Cheddar"),
    "white or yellow sharp cheddar": ("cheddar", "Cheddar"),
    "mozzarella ball": ("mozzarella", "Mozzarella"),
    "ciliegine": ("mozzarella", "Mozzarella"),
    "bocconcini": ("mozzarella", "Mozzarella"),
    "ciliegine or bocconcini": ("mozzarella", "Mozzarella"),
    "egg yolk": ("egg", "Eggs"),
    "egg yolks": ("egg", "Eggs"),
    "egg white": ("egg", "Eggs"),
    "egg whites": ("egg", "Eggs"),
    "yolk": ("egg", "Eggs"),
    "yolks": ("egg", "Eggs"),
    "egg": ("egg", "Eggs"),
    "eggs": ("egg", "Eggs"),
    "shaved parmesan": ("parmesan", "Parmesan"),
    "whole milk": ("milk", "Milk"),
    "full fat brick cream cheese": ("cream cheese", "Cream Cheese"),
    "full fat cream cheese": ("cream cheese", "Cream Cheese"),
    "full fat sour cream": ("sour cream", "Sour Cream"),
    "plain greek yogurt": ("greek yogurt", "Greek Yogurt"),
    "whole milk plain strained yogurt": ("greek yogurt", "Greek Yogurt"),
    "plain unflavored yogurt": ("plain yogurt", "Plain Yogurt"),
    "plain yogurt or sour cream": ("plain yogurt", "Plain Yogurt"),
    "yogurt": ("plain yogurt", "Plain Yogurt"),
    "heavy cream or coconut milk": ("heavy cream", "Heavy Cream"),
    "oat milk or milk of choice": ("oat milk", "Oat Milk"),
    "to 7 tbsp buttermilk": ("buttermilk", "Buttermilk"),

    # Grains & Bakery
    "caputo 00 americana flour": ("flour", "Flour"),
    "king arthur bread flour": ("bread flour", "Bread Flour"),
    "all purpose or bread flour": ("bread flour", "Bread Flour"),
    "chang s pad thai dried rice sticks": ("rice noodle", "Rice Noodles"),
    "chang s pad thai dried rice stick": ("rice noodle", "Rice Noodles"),
    "chang s pad thai rice sticks": ("rice noodle", "Rice Noodles"),
    "chang s pad thai rice stick": ("rice noodle", "Rice Noodles"),
    "rice noodles": ("rice noodle", "Rice Noodles"),
    "rice noodle": ("rice noodle", "Rice Noodles"),
    "pad thai rice sticks": ("rice noodle", "Rice Noodles"),
    "pad thai rice stick": ("rice noodle", "Rice Noodles"),
    "pad thai noodles": ("rice noodle", "Rice Noodles"),
    "pad thai noodle": ("rice noodle", "Rice Noodles"),
    "panko breadcrumbs": ("panko", "Panko"),
    "panko breadcrumb": ("panko", "Panko"),
    "panko": ("panko", "Panko"),
    "regular breadcrumbs": ("breadcrumb", "Breadcrumbs"),
    "regular breadcrumb": ("breadcrumb", "Breadcrumbs"),
    "breadcrumbs": ("breadcrumb", "Breadcrumbs"),
    "breadcrumb": ("breadcrumb", "Breadcrumbs"),
    "crushed ritz crackers": ("ritz crackers", "Ritz Crackers"),
    "carnaroli risotto rice": ("risotto rice", "Risotto Rice"),
    "rice": ("white rice", "White Rice"),
    "white rice": ("white rice", "White Rice"),
    "long grain white rice": ("white rice", "White Rice"),
    "short grain rice": ("white rice", "White Rice"),
    "risoni orzo": ("orzo", "Orzo"),
    "risoni or orzo": ("orzo", "Orzo"),
    "greek pita bread pockets or flatbreads": ("pita bread", "Pita Bread"),
    "tortillas of choice": ("tortilla", "Tortillas"),
    "rolled oats or quick oats": ("rolled oats", "Rolled Oats"),
    "old fashioned rolled oats": ("rolled oats", "Rolled Oats"),
    "old fashioned whole rolled oats": ("rolled oats", "Rolled Oats"),

    # Sauces & Condiments
    "beef or chicken broth stock": ("beef broth", "Beef Broth"),
    "chicken or vegetable broth": ("chicken broth", "Chicken Broth"),
    "chicken stock": ("chicken broth", "Chicken Broth"),
    "low sodium chicken broth": ("chicken broth", "Chicken Broth"),
    "low sodium chicken stock": ("chicken broth", "Chicken Broth"),
    "bouillon cube": ("chicken broth", "Chicken Broth"),
    "chicken boulion": ("chicken broth", "Chicken Broth"),
    "browning sauce or dark molasses": ("browning sauce", "Browning Sauce"),
    "butter or extra virgin olive oil": ("butter", "Butter"),
    "chili crisp or your favorite chili oil": ("chili crisp", "Chili Crisp"),
    "cooking oil of your choice": ("cooking oil", "Cooking Oil"),
    "neutral oil": ("cooking oil", "Cooking Oil"),
    "oil": ("cooking oil", "Cooking Oil"),
    "asian sesame oil": ("sesame oil", "Sesame Oil"),
    "toasted sesame oil": ("sesame oil", "Sesame Oil"),
    "country style dijon mustard": ("dijon mustard", "Dijon Mustard"),
    "grainy dijon mustard": ("dijon mustard", "Dijon Mustard"),
    "american yellow mustard": ("yellow mustard", "Yellow Mustard"),
    "creamy unsweetened peanut butter": ("peanut butter", "Peanut Butter"),
    "smooth natural peanut butter": ("peanut butter", "Peanut Butter"),
    "honey or maple syrup": ("honey", "Honey"),
    "hot sauce or ketchup optional": ("hot sauce", "Hot Sauce"),
    "sauce or ketchup optional": ("hot sauce", "Hot Sauce"),
    "reduced sodium soy sauce": ("low sodium soy sauce", "Low-Sodium Soy Sauce"),
    "remaining caramel sauce": ("caramel sauce", "Caramel Sauce"),
    "remaining salted caramel sauce": ("caramel sauce", "Caramel Sauce"),
    "sweet white miso": ("miso paste", "Miso Paste"),
    "sriracha sauce": ("sriracha", "Sriracha"),
    "white wine vinegar or champagne vinegar": ("white wine vinegar", "White Wine Vinegar"),
    "to 2 tablespoons olive oil": ("olive oil", "Olive Oil"),
    "to 3 tbsp ketchup": ("ketchup", "Ketchup"),
    "to 3 tbsp. ketchup": ("ketchup", "Ketchup"),

    # Spices & Seasonings
    "barbecue rub or spice mix": ("barbecue rub", "Barbecue Rub"),
    "cayenne": ("cayenne pepper", "Cayenne Pepper"),
    "chili flakes": ("chili flake", "Chili Flakes / Red Pepper Flakes"),
    "chili flake": ("chili flake", "Chili Flakes / Red Pepper Flakes"),
    "red pepper flakes": ("chili flake", "Chili Flakes / Red Pepper Flakes"),
    "red pepper flake": ("chili flake", "Chili Flakes / Red Pepper Flakes"),
    "crushed red pepper": ("chili flake", "Chili Flakes / Red Pepper Flakes"),
    "crushed red pepper flakes": ("chili flake", "Chili Flakes / Red Pepper Flakes"),
    "coriander": ("cilantro", "Cilantro"),
    "coriander leaves": ("cilantro", "Cilantro"),
    "coriander leaf": ("cilantro", "Cilantro"),
    "coriander cilantro": ("cilantro", "Cilantro"),
    "coriander cilantro leaf": ("cilantro", "Cilantro"),
    "coriander powder": ("ground coriander", "Ground Coriander"),
    "cumin seed": ("cumin", "Cumin"),
    "ginger powder": ("ground ginger", "Ground Ginger"),
    "green cardamoms": ("cardamom", "Cardamom"),
    "ground allspice": ("allspice", "Allspice"),
    "ground cardamom": ("cardamom", "Cardamom"),
    "ground chilli or cayenne pepper": ("cayenne pepper", "Cayenne Pepper"),
    "ground cinnamon": ("cinnamon", "Cinnamon"),
    "ground cumin": ("cumin", "Cumin"),
    "ground mace or nutmeg": ("nutmeg", "Nutmeg"),
    "kashmiri red chilli powder": ("kashmiri chilli powder", "Kashmiri Chilli Powder"),
    "onion or garlic powder": ("onion powder", "Onion Powder"),
    "onion powder or garlic powder": ("onion powder", "Onion Powder"),
    "regular or smoked paprika": ("smoked paprika", "Smoked Paprika"),
    "rosemary or thyme": ("rosemary", "Rosemary"),
    "smoked paprika or paprika for a little color": ("smoked paprika", "Smoked Paprika"),
    "spanish paprika": ("paprika", "Paprika"),
    "sweet paprika": ("paprika", "Paprika"),
    "turmeric powder": ("turmeric", "Turmeric"),

    # Pantry Staples
    "cashew nuts": ("cashew", "Cashews"),
    "instant rise yeast": ("instant yeast", "Instant Yeast"),
    "dark brown sugar": ("brown sugar", "Brown Sugar"),
    "light brown sugar": ("brown sugar", "Brown Sugar"),
    "light or dark brown sugar": ("brown sugar", "Brown Sugar"),
    "chocolate chip": ("chocolate chip", "Chocolate Chips"),
    "chocolate chips": ("chocolate chip", "Chocolate Chips"),
    "semisweet chocolate chips": ("chocolate chip", "Chocolate Chips"),
    "semisweet chocolate chip": ("chocolate chip", "Chocolate Chips"),
    "dark or semisweet chocolate chips": ("chocolate chip", "Chocolate Chips"),
    "dark or semisweet chocolate chip": ("chocolate chip", "Chocolate Chips"),
    "dark chocolate chips": ("chocolate chip", "Chocolate Chips"),
    "dark chocolate chip": ("chocolate chip", "Chocolate Chips"),
    "pure vanilla extract": ("vanilla extract", "Vanilla Extract"),
    "vanilla": ("vanilla extract", "Vanilla Extract"),
    "almonds": ("almond", "Almonds"),
    "raw almonds": ("almond", "Almonds"),
    "slivered almonds": ("almond", "Almonds"),
    "raw almond": ("almond", "Almonds"),
    "slivered almond": ("almond", "Almonds"),
    "walnut piece": ("walnut", "Walnuts"),
    "whole cloves": ("clove", "Cloves"),
    "ground cloves": ("clove", "Cloves"),
    "tamarind puree not concentrate": ("tamarind puree", "Tamarind Puree"),
    "dr pepper or coke": ("cola", "Cola"),
    "chardonnay": ("white wine", "White Wine"),
    "chardonnay wine": ("white wine", "White Wine"),
    "white wine": ("white wine", "White Wine"),
    "wine": ("white wine", "White Wine"),
}


def is_staple_ingredient(norm: str, raw: str = "") -> bool:
    """Identify common staples like salt, pepper, water, pan spray, plain sugar, and flour."""
    n = norm.lower().strip()
    r = raw.lower().strip() if raw else ""

    # 1. Salt variants: salt present, but not salt pork, salt cod, salted pretzels, salted caramel
    if "salt" in n or "salt" in r:
        if not any(k in n or k in r for k in ["pork", "cod", "beef", "pretzel", "caramel", "cracker", "butter"]):
            return True

    # 2. Pepper (black/white/ground pepper, cracked pepper - not bell pepper, chile pepper, cayenne)
    if "pepper" in n or "pepper" in r:
        if any(k in n or k in r for k in ["black pepper", "white pepper", "ground pepper", "freshly ground pepper", "cracked pepper", "ground black pepper"]) or n in ("pepper", "salt and pepper", "salt & pepper"):
            return True

    # 3. Water variants: plain water, filtered, ice cubes (not watermelon, coconut water, etc.)
    if "water" in n or "ice cubes" in n or "water" in r or "ice cubes" in r:
        if not any(k in n or k in r for k in ["chestnut", "melon", "coconut", "cress", "rose"]):
            return True

    # 4. Cooking spray / pan greasing
    if any(k in n or k in r for k in ["cooking spray", "vegetable spray", "greasing"]):
        return True

    # 5. Plain sugar (not brown sugar, coconut sugar, confectioners sugar)
    if n in ("sugar", "granulated sugar", "white sugar", "white granulated sugar"):
        return True

    # 6. Plain all-purpose flour
    if n in ("all purpose flour", "all-purpose flour", "plain flour", "unbleached all purpose flour"):
        return True

    return False


def clean_ingredient_name(raw: str) -> Optional[Tuple[str, str]]:
    """Sanitize messy scraped recipe ingredient strings into clean canonical names and display labels.

    Returns (normalized_name, display_name) or None if discarded.
    """
    if not raw or not raw.strip():
        return None

    # 1. Discard non-ingredient instructions, scraper errors, or blog notes
    for pat in DISCARD_PATTERNS:
        if pat.search(raw):
            return None

    text = raw.strip()

    # 2. Normalize fractions (vulgar fractions, superscripts/subscripts)
    for k, v in FRACTION_MAP.items():
        text = text.replace(k, v)
    text = re.sub(r"¹\s*\/\s*₂", " 1/2 ", text)

    # 3. Remove empty parens/brackets
    text = re.sub(r"\(\s*\)", " ", text)
    text = re.sub(r"\[\s*\]", " ", text)

    # 4. Remove parenthetical expressions (notes, measurements, preps)
    while "(" in text and ")" in text:
        new_text = re.sub(r"\([^()]*\)", " ", text)
        if new_text == text:
            break
        text = new_text

    # Strip unmatched dangling parens
    text = re.sub(r"[()]", " ", text)

    # 5. Strip em-dash / hyphen explanatory clauses (e.g. "Avocado Oil – Helps Keep The Crumb Tender")
    text = re.sub(r"\s+[–—-]\s+.*$", "", text)

    # Strip trailing "+ more"
    text = re.sub(r"\s*\+\s*more.*$", "", text, flags=re.I)

    # Strip trailing pipe or noise
    text = re.sub(r"[\s\|\&\+]+$", "", text)

    # 6. Strip leading noise characters: (), [], ., /, -, *, &, +, |, (Or ), (And )
    text = re.sub(r"^[\s\(\)\[\]\.\/\,\-\*\:\;\#\~\&\+\|]+", "", text)
    text = re.sub(r"^\(?\s*or\b\s*\)?\s*", "", text, flags=re.I)
    text = re.sub(r"^\(?\s*and\b\s*\)?\s*", "", text, flags=re.I)
    text = re.sub(r"^optional\s*:\s*", "", text, flags=re.I)
    text = re.sub(r"^(?:fresh-squeezed|-squeezed|squeezed|ly\s+)\s*", "", text, flags=re.I)
    text = re.sub(r"^\s*to\s+(\d+(\.\d+)?\s*[-–—/]\s*\d+|\d+([./]\d+)?)\s*", "", text, flags=re.I)
    text = re.sub(r"^\s*to\s+(\d+\s*)?(tbsp|tablespoons?|tsp|teaspoons?|cups?)\b\.?\s*", "", text, flags=re.I)
    text = re.sub(r"^\s*to\s+", "", text, flags=re.I)
    text = re.sub(r"^\s*(?:remaining|leftover)\s+", "", text, flags=re.I)
    text = re.sub(r"^\s*danish\s+creamery\s+", "", text, flags=re.I)
    text = re.sub(r"^\s*caputo\s+00\s+americana\s+", "", text, flags=re.I)
    text = re.sub(r"^\s*king\s+arthur\s+", "", text, flags=re.I)
    text = re.sub(r"^\s*length\s+(?=ginger\b)", "", text, flags=re.I)
    text = re.sub(r"^\s*canned\s+", "", text, flags=re.I)
    text = re.sub(r"^\s*more\s+", "", text, flags=re.I)
    text = re.sub(r"^\s*(?:active|unfed)\s+(?=sourdough\s+starter)", "", text, flags=re.I)
    text = re.sub(r"^\s*dry\s+(?=(?:linguine|pasta|thyme|bay\s+leaf)\b)", "", text, flags=re.I)
    text = re.sub(r"^\s*regular\s+(?=breadcrumbs?\b)", "", text, flags=re.I)
    text = re.sub(r"^\s*old[- ]fashioned\s+(?:whole\s+)?(?=rolled\s+oats\b)", "", text, flags=re.I)
    text = re.sub(r"^\s*whole\s+fully\s+cooked\s+bone[- ]in\s+(?=ham\b)", "", text, flags=re.I)
    text = re.sub(r"^\s*mashed\s+(?=ripe\s+)?(?=bananas?\b)", "", text, flags=re.I)
    text = re.sub(r"^\s*ripe\s+(?=bananas?\b)", "", text, flags=re.I)

    # Normalize citrus juice and zest -> root fruit (Lemon / Lime)
    text = re.sub(r"^(?:juice|zest)\s+(?:of|from)\s+(\d+\s*)?lemons?", "lemon", text, flags=re.I)
    text = re.sub(r"^(?:juice|zest)\s+(?:of|from)\s+(\d+\s*)?limes?", "lime", text, flags=re.I)
    text = re.sub(r"^\s*(?:fresh\s+|freshly\s+)?lemon\s+(?:juice|zest)\b", "lemon", text, flags=re.I)
    text = re.sub(r"^\s*(?:fresh\s+|freshly\s+)?lime\s+(?:juice|zest)\b", "lime", text, flags=re.I)

    # 6. Strip trailing prep and instructions after commas from the right
    parts = [p.strip() for p in text.split(",") if p.strip()]
    while len(parts) > 1:
        last = parts[-1].lower()
        if (
            PREP_TRAILING_CHECK.search(last)
            or re.search(r"\b(minced|diced|chopped|grated|sliced|peeled|beaten|warmed|ripe|cooked|halved|quartered|drained|melted|softened|crumbled|fed|unfed|bubbly|fridge|seeds|ribs|knob|preferably|about|tablespoon|tbsp|teaspoon|tsp|cup|oz|gram)\b", last)
            or re.match(r"^(from\s+\d+|from\s+a\b|\d+\s*(tbsp|tsp|cup|oz|tablespoon))", last)
        ) and not FOOD_NOUN_CHECK.search(last):
            parts.pop()
        else:
            break
    text = ", ".join(parts)

    # 7. Strip trailing notes and quantity alternatives
    text = re.sub(r"\s+or\b\s+(\d+\s*)?(large|medium|small|each)?\s*$", "", text, flags=re.I)
    text = re.sub(r"\s+or\b\s+of\s+each\s*$", "", text, flags=re.I)
    text = re.sub(r"\s+or\b\s+\.\s+each\s*$", "", text, flags=re.I)
    text = re.sub(r"\s+(for garnish|for serving|to serve|to taste|if desired|as needed|as desired)\s*$", "", text, flags=re.I)
    text = re.sub(r"\s+(cut into\b.*|chopped into\b.*|pressed and\b.*|beaten to blend|beaten|crumbled.*|seeds and ribs removed|seeds removed|ground into\b.*|for the grill grates|for cooking|for frying|from above|fed or unfed is fine|straight from the fridge|bubbly and active)\s*$", "", text, flags=re.I)
    text = re.sub(r"\s+(finely\s+chopped|finely\s+diced|coarsely\s+ground|thinly\s+sliced|minced|grated|peeled)\s*$", "", text, flags=re.I)

    # 8. Strip leading quantities, metric units, units, sizing, ordinals in a loop
    while True:
        prev = text
        text = UNIT_PREFIX_REGEX.sub("", text)
        text = re.sub(r"^[\s\.\,\/\-\:\;\&\+\|]+", "", text)
        if text == prev:
            break

    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()

    # Discard if too short or lacking alphabetic substance
    if not re.search(r"[a-zA-Z]{2,}", text):
        return None

    # Discard if only a measurement unit word remains
    if re.fullmatch(r"(cups?|tbsp|tsp|tablespoons?|teaspoons?|oz|ounces?|grams?|g|kg|ml|litres?|liters?|pinch|dash|c|t|lb|lbs|pound|pounds)", text, re.I):
        return None

    # Clean leading prep adjectives from display name for a clean UI presentation
    clean_display = text
    clean_display = re.sub(r"^(?:fresh-squeezed|-squeezed|squeezed|ly\s+)\s*", "", clean_display, flags=re.I)
    clean_display = re.sub(
        r"^(?:(finely|coarsely|roughly|thinly|freshly\b|fresh\b|lightly|packed|chopped|diced|minced|"
        r"grated|shredded|peeled|cooked|boneless|skinless|unsalted|salted|chopped\s+or\s+halved|halved|quartered|or\b|"
        r"ripe|mashed|beaten|crumbled|pressed)\s*,?\s*)+",
        "",
        clean_display,
        flags=re.I,
    ).strip()
    clean_display = re.sub(r"^[\s\-\,\.\:\;\/]+", "", clean_display)
    if not clean_display or len(clean_display) < 2:
        clean_display = text

    display = clean_display.title()

    # Herb leaf normalization: "Basil Leaves" -> "Basil"
    herb_base = None
    m_herb = HERB_LEAF_PATTERNS.match(display)
    if m_herb:
        display = m_herb.group(1).title()
        herb_base = m_herb.group(1).lower()

    # Cheese base normalization: "Cheddar Cheese" -> "Cheddar"
    cheese_base = None
    m_cheese = CHEESE_BASE_PATTERNS.match(display)
    if m_cheese:
        display = m_cheese.group(1).title()
        cheese_base = m_cheese.group(1).lower()

    if display == "Chicken Breasts":
        display = "Chicken Breast"
    elif display == "Egg":
        display = "Eggs"
    elif display == "Scallion":
        display = "Scallions"
    elif display == "Oils":
        display = "Oil"
    elif display in ("Garlic Cloves", "Large Garlic Cloves"):
        display = "Garlic"

    # Normalize accents for clean UI and grouping
    display = display.replace("ñ", "n").replace("Ñ", "N").replace("è", "e").replace("é", "e")

    # Normalized name: lowercased, prep words and punctuation removed for grouping
    if herb_base:
        norm = herb_base
    elif cheese_base:
        norm = cheese_base
    else:
        norm = text.lower()
        norm = norm.replace("ñ", "n").replace("è", "e").replace("é", "e")
        norm = re.sub(r"[-–—]", " ", norm)
        norm = PREP_REGEX.sub(" ", norm)
        norm = re.sub(r"[^\w\s]", " ", norm)
        norm = re.sub(r"\s+", " ", norm).strip()

        # Singularize common end words for tighter grouping
        tokens = norm.split()
        if tokens:
            last_tok = tokens[-1]
            if last_tok in PLURAL_MAP:
                tokens[-1] = PLURAL_MAP[last_tok]
                norm = " ".join(tokens)

    if norm in ("cloves", "garlic cloves"):
        norm = "garlic"

    if norm in SYNONYMS:
        syn_norm, syn_disp = SYNONYMS[norm]
        norm = syn_norm
        display = syn_disp

    if not norm or len(norm) < 2:
        return None

    return norm, display


def normalize_ingredient_name(raw: str) -> str:
    """Clean and normalize an ingredient name for fuzzy matching."""
    cleaned = clean_ingredient_name(raw)
    if cleaned:
        return cleaned[0]
    return ""


def categorize_ingredient(name: str) -> str:
    """Smart heuristic categorization for pantry items."""
    n = name.lower()

    # 1. Vinegars MUST be routed to sauces & condiments (avoid false match with "wine" in pantry)
    if "vinegar" in n:
        return "sauces & condiments"

    # 2. Pickles / relishes in sauces & condiments (before dill check in spices)
    if "pickle" in n or "relish" in n:
        return "sauces & condiments"

    # 3. Chili crisp in sauces & condiments (before chili check in produce)
    if "chili crisp" in n or "chilli crisp" in n:
        return "sauces & condiments"

    # 4. Curry paste in sauces & condiments (before curry powder in spices)
    if "curry paste" in n:
        return "sauces & condiments"

    # 5. Baking soda & baking powder in spices & herbs (before drink soda check in pantry)
    if "baking soda" in n or "baking powder" in n:
        return "spices & herbs"

    # 6. Ground ginger / ginger powder in spices (before ginger check in produce)
    if "ground ginger" in n or "ginger powder" in n:
        return "spices & herbs"

    # 7. Green beans / snap beans in produce (before bean check in pantry)
    if "green bean" in n or "string bean" in n or "snap bean" in n:
        return "produce"

    # 8. Cilantro in produce (before coriander check in spices)
    if "cilantro" in n:
        return "produce"

    # 9. Fresh apples in produce (before honey in sauces)
    if "apple" in n and "applesauce" not in n and "cider" not in n:
        return "produce"

    # 10. Special Pantry items (canned beans, pulses, sodas, tomato paste/soup, seeds/nuts, wines, canned soups)
    if any(k in n for k in [
        "black bean", "canned black bean", "cannellini", "chickpea",
        "tomato paste", "tomato soup", "cream of chicken", "cream of mushroom",
        "canned soup", "cola", "club soda", "wine", "chardonnay",
        "tequila", "triple sec", "sugar", "yeast", "cornstarch",
        "chocolate chip", "almond", "pecan", "walnut", "cashew", "peanut",
        "flax seed", "chia seed", "sunflower seed", "msg", "old bay", "tamarind",
        "shortening"
    ]):
        return "pantry"

    # 10. Spices & Seasonings
    if any(k in n for k in [
        "powder", "paprika", "cumin", "oregano", "cinnamon", "spice", "nutmeg",
        "curry", "seasoning", "allspice", "cardamom", "clove", "cloves",
        "turmeric", "cayenne", "chili flake", "red pepper flake", "mace", "peppercorn",
        "bay leaf", "bay leaves", "kasoori methi", "marjoram", "thyme", "star anise",
        "fennel seed", "baking soda", "baking powder"
    ]) or re.search(r"\b(rubs?|dill|coriander)\b", n):
        return "spices & herbs"

    # 10. Sauces & Condiments (including cooking oils)
    if any(k in n for k in [
        "broth", "stock", "bouillon", "boulion", "sauce", "hoisin",
        "peanut butter", "miso", "mustard", "mayo", "ketchup",
        "sriracha", "worcestershire", "tahini", "dressing", "syrup",
        "oil", "oils", "anchovy"
    ]) or re.search(r"\bhoney\b", n):
        return "sauces & condiments"

    # 11. Dairy & Eggs
    if (
        any(k in n for k in [
            "milk", "cream", "cheese", "butter", "yogurt", "mozzarella", "parmesan",
            "cheddar", "feta", "boursin", "pecorino", "gruyere",
            "gruyère", "jack", "ricotta", "half and half", "half-and-half", "buttermilk",
            "ciliegine", "bocconcini"
        ])
        or (re.search(r"\b(eggs?|yolks?)\b", n) and "eggplant" not in n)
    ):
        return "dairy"

    # 12. Grains & Bakery
    if any(k in n for k in [
        "rice", "noodle", "pasta", "bread", "dough", "tortilla", "spaghetti",
        "orzo", "quinoa", "flour", "pita", "starter", "risotto",
        "crumbs", "cracker", "tagliatelle", "cereal", "linguine", "panko",
        "pretzel", "cookie", "biscuit"
    ]) or re.search(r"\b(buns?|rolls?|oats?|oatmeal)\b", n):
        return "grains & bakery"

    # 13. Protein
    if any(k in n for k in [
        "chicken", "beef", "pork", "steak", "turkey", "lamb", "bacon", "salmon",
        "shrimp", "fish", "tuna", "patty", "patties", "meat", "sausage", "chorizo",
        "pancetta", "guanciale", "prosciutto", "salami", "tofu", "paneer", "mince"
    ]) or re.search(r"\b(ham|cod)\b", n):
        return "protein"

    # 14. Produce & Fresh
    if any(k in n for k in [
        "tomato", "onion", "garlic", "spinach", "lettuce", "basil", "parsley",
        "lemon", "lime", "potato", "carrot", "broccoli", "zucchini", "cucumber", "cabbage",
        "sprout", "sprouts", "sage", "rosemary", "chile", "chili", "chilli", "pepper", "peppers",
        "avocado", "herb", "mint", "scallion", "shallot", "leek", "celery", "fennel", "mushroom",
        "kale", "ginger", "cauliflower", "rhubarb", "edamame", "eggplant",
        "chive", "jalapeno", "serrano", "romaine", "apple", "banana", "berry",
        "berries", "mango", "peach", "fruit", "slaw", "artichoke", "pomegranate", "cranberr",
        "fig", "raisin", "olive", "brussels", "green bean"
    ]) or re.search(r"\b(peas?|corn|peppers?|chillies?|chillis?)\b", n):
        return "produce"

    return "pantry"


# Three-tier ingredient classification keywords for Dinner Availability
ANCHOR_PROTEIN_KEYWORDS: Set[str] = {
    "chicken", "beef", "pork", "lamb", "turkey", "salmon", "cod", "tuna",
    "shrimp", "fish", "sausage", "chorizo", "steak", "bacon", "pancetta",
    "guanciale", "prosciutto", "ham", "tofu", "paneer", "meatball", "mince",
    "duck", "scallop", "lobster", "crab", "ground meat", "flank steak",
    "chuck roast", "tenderloin", "cutlet", "thigh", "breast", "ribeye", "sirloin"
}

ANCHOR_REGEX = re.compile(
    r"\b(" + "|".join(ANCHOR_PROTEIN_KEYWORDS) + r")\b",
    re.IGNORECASE,
)

ANCHOR_EXCLUDE_KEYWORDS: Set[str] = {
    "broth", "stock", "bouillon", "boulion", "fat", "sauce", "powder", "seasoning",
    "dripping", "drippings", "cream of", "soup", "crumb", "cracker", "graham"
}

PERISHABLE_EXCLUDE_KEYWORDS: Set[str] = {
    "powder", "dried", "dry", "canned", "paste", "puree", "sauce", "soup",
    "seed", "seeds", "nut", "nuts", "oil", "extract", "flake", "flakes",
    "ground", "chip", "chips", "butter", "cooking spray", "raisin", "fig",
    "cranberr", "prune", "date", "sun-dried", "candied", "olive", "artichoke heart",
    "condensed milk", "evaporated milk", "whole peeled tomato", "san marzano",
    "crushed tomato", "diced tomato", "guajillo", "ancho", "dr pepper", "soda", "cola"
}

PERISHABLE_PRODUCE_KEYWORDS: Set[str] = {
    "onion", "garlic", "shallot", "scallion", "green onion", "leek", "ginger",
    "celery", "carrot", "spinach", "kale", "lettuce", "cabbage", "broccoli",
    "cauliflower", "zucchini", "cucumber", "bell pepper", "jalapeno", "serrano", "habanero", "scotch bonnet",
    "poblano", "mushroom", "asparagus", "green bean", "snap bean", "string bean",
    "corn", "sprout", "sprouts", "edamame", "eggplant", "artichoke",
    "brussels", "fennel", "radish", "beet", "avocado", "tomato", "cherry tomato",
    "cilantro", "basil", "parsley", "mint", "dill", "rosemary", "thyme", "sage",
    "chive", "chives", "tarragon", "lemon", "lime", "apple", "banana", "berry",
    "berries", "strawberry", "blueberry", "raspberry", "blackberry", "peach",
    "mango", "pomegranate", "slaw", "potato", "baby potato", "sweet potato"
}

PERISHABLE_DAIRY_KEYWORDS: Set[str] = {
    "heavy cream", "sour cream", "cream cheese", "ricotta", "buttermilk", "yogurt",
    "greek yogurt", "plain yogurt", "half and half", "milk", "mozzarella", "feta",
    "boursin", "burrata", "goat cheese", "egg", "eggs", "yolk", "yolks"
}


def get_ingredient_tier(norm: str, category: Optional[str] = None) -> str:
    """Classify an ingredient into one of three Dinner Availability tiers:
    - 'anchor': Centerpiece protein (Chicken, Beef, Pork, Salmon, Tofu, Shrimp, etc.)
    - 'perishable': Crisper produce, fresh herbs, short-shelf dairy
    - 'staple': Dry spices, oils, vinegars, baking goods, canned beans, grains, pasta, broths
    """
    n = norm.lower().strip()
    cat = (category or categorize_ingredient(n)).lower()

    # 1. Check for Anchor Proteins
    if not any(ex in n for ex in ANCHOR_EXCLUDE_KEYWORDS):
        if ANCHOR_REGEX.search(n) or (cat == "protein" and not any(ex in n for ex in ("fat", "broth", "stock"))):
            return "anchor"

    # 2. Check for Ambient Staples
    if n in ALWAYS_ON_STAPLES or n in DEFAULT_STAPLES or is_staple_ingredient(n):
        return "staple"

    if any(ex in n for ex in PERISHABLE_EXCLUDE_KEYWORDS):
        return "staple"

    if cat in ("spices & herbs", "sauces & condiments", "grains & bakery", "pantry"):
        # Fresh herbs might occasionally be placed in spices & herbs
        if any(h in n for h in ("cilantro", "fresh basil", "fresh parsley", "fresh mint", "fresh rosemary", "fresh thyme")):
            return "perishable"
        return "staple"

    # 3. Check for Fresh Perishables (Produce & Short-shelf Dairy)
    if any(p in n for p in PERISHABLE_PRODUCE_KEYWORDS):
        return "perishable"

    if any(d in n for d in PERISHABLE_DAIRY_KEYWORDS):
        return "perishable"

    if cat in ("produce", "dairy"):
        return "perishable"

    return "staple"


class PantryManager:
    """Manages pantry item persistence and recipe matching logic."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or getattr(settings, "pantry_db_path", "data/pantry.db")
        self._ensure_db_dir()
        self._in_stock_cache: Optional[Set[str]] = None
        self._cache_timestamp: float = 0.0
        self.init_db()

    def _ensure_db_dir(self):
        dir_name = os.path.dirname(self.db_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        """Initialize pantry SQLite schema and perform automatic migrations."""
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pantry_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    display_name TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'pantry',
                    tier TEXT NOT NULL DEFAULT 'staple',
                    in_stock INTEGER NOT NULL DEFAULT 1,
                    is_staple INTEGER NOT NULL DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            try:
                conn.execute("ALTER TABLE pantry_items ADD COLUMN tier TEXT NOT NULL DEFAULT 'staple'")
                conn.commit()
            except sqlite3.OperationalError:
                pass

            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_pantry_name ON pantry_items (name)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_pantry_tier ON pantry_items (tier)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_pantry_in_stock ON pantry_items (in_stock)"
            )
            conn.commit()

        self.cleanup_existing_items()

    def cleanup_existing_items(self) -> int:
        """Sanitize, deduplicate, assign tiers, and remove staples/junk from existing SQLite rows in-place."""
        self._invalidate_cache()
        cleaned_count = 0
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT id, name, display_name, category, in_stock FROM pantry_items")
            items = [dict(r) for r in cursor.fetchall()]

            for row in items:
                # 1. Remove staples
                if is_staple_ingredient(row["name"], row["display_name"]):
                    conn.execute("DELETE FROM pantry_items WHERE id = ?", (row["id"],))
                    cleaned_count += 1
                    continue

                # 2. Re-clean name using display_name or name
                cleaned = clean_ingredient_name(row["display_name"]) or clean_ingredient_name(row["name"])
                if not cleaned:
                    conn.execute("DELETE FROM pantry_items WHERE id = ?", (row["id"],))
                    cleaned_count += 1
                    continue

                clean_norm, clean_disp = cleaned
                if is_staple_ingredient(clean_norm, clean_disp):
                    conn.execute("DELETE FROM pantry_items WHERE id = ?", (row["id"],))
                    cleaned_count += 1
                    continue

                clean_cat = categorize_ingredient(clean_norm)
                clean_tier = get_ingredient_tier(clean_norm, clean_cat)
                is_staple_val = 1 if (clean_tier == "staple" or clean_norm in ALWAYS_ON_STAPLES) else 0
                in_stock_val = 1 if clean_tier == "staple" else row["in_stock"]

                if clean_norm != row["name"]:
                    # Check if another row already exists with clean_norm
                    cursor = conn.execute(
                        "SELECT id, in_stock, display_name FROM pantry_items WHERE name = ? AND id != ?",
                        (clean_norm, row["id"]),
                    )
                    existing = cursor.fetchone()
                    if existing:
                        # Merge stock status
                        merged_stock = 1 if (in_stock_val == 1 or existing["in_stock"] == 1 or clean_tier == "staple" or clean_norm in ALWAYS_ON_STAPLES) else 0
                        merged_staple = 1 if (is_staple_val or clean_tier == "staple") else 0
                        conn.execute(
                            "UPDATE pantry_items SET in_stock = ?, is_staple = ?, tier = ? WHERE id = ?",
                            (merged_stock, merged_staple, clean_tier, existing["id"]),
                        )
                        conn.execute("DELETE FROM pantry_items WHERE id = ?", (row["id"],))
                        cleaned_count += 1
                    else:
                        conn.execute(
                            """
                            UPDATE pantry_items 
                            SET name = ?, display_name = ?, category = ?, tier = ?, in_stock = ?, is_staple = ?, updated_at = CURRENT_TIMESTAMP 
                            WHERE id = ?
                            """,
                            (clean_norm, clean_disp, clean_cat, clean_tier, in_stock_val, is_staple_val, row["id"]),
                        )
                        cleaned_count += 1
                else:
                    conn.execute(
                        """
                        UPDATE pantry_items 
                        SET display_name = ?, category = ?, tier = ?, in_stock = ?, is_staple = ?, updated_at = CURRENT_TIMESTAMP 
                        WHERE id = ?
                        """,
                        (clean_disp, clean_cat, clean_tier, in_stock_val, is_staple_val, row["id"]),
                    )
                    cleaned_count += 1

            conn.commit()

        if cleaned_count:
            logger.info(f"Cleaned up / migrated {cleaned_count} pantry items in database.")
        return cleaned_count

    def _invalidate_cache(self):
        self._in_stock_cache = None

    def get_in_stock_set(self) -> Set[str]:
        """Return the cached set of in-stock (or staple) normalized ingredient names."""
        now = time.time()
        if self._in_stock_cache is not None and (now - self._cache_timestamp < 10.0):
            return self._in_stock_cache

        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT name FROM pantry_items WHERE in_stock = 1 OR is_staple = 1"
            )
            in_stock = {row["name"].lower() for row in cursor.fetchall()}

        # Merge with built-in default staples and Always-On staples
        in_stock.update(DEFAULT_STAPLES)
        in_stock.update(ALWAYS_ON_STAPLES)

        self._in_stock_cache = in_stock
        self._cache_timestamp = now
        return in_stock

    def get_all_items(
        self,
        category: Optional[str] = None,
        search: Optional[str] = None,
        in_stock: Optional[bool] = None,
        tier: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List pantry items with optional filtering."""
        query = "SELECT id, name, display_name, category, tier, in_stock, is_staple, updated_at FROM pantry_items WHERE 1=1"
        params: List[Any] = []

        if category:
            query += " AND category = ?"
            params.append(category.lower())
        if tier:
            query += " AND tier = ?"
            params.append(tier.lower())
        if in_stock is not None:
            query += " AND in_stock = ?"
            params.append(1 if in_stock else 0)
        if search:
            query += " AND (name LIKE ? OR display_name LIKE ?)"
            term = f"%{search.strip().lower()}%"
            params.extend([term, term])

        query += " ORDER BY category ASC, display_name ASC"

        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_stats(self) -> Dict[str, int]:
        """Return counts of total, in_stock, out_of_stock, staple, and tiered items."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN in_stock = 1 THEN 1 ELSE 0 END) as in_stock,
                    SUM(CASE WHEN in_stock = 0 AND is_staple = 0 AND tier != 'staple' THEN 1 ELSE 0 END) as out_of_stock,
                    SUM(CASE WHEN is_staple = 1 OR tier = 'staple' THEN 1 ELSE 0 END) as staples,
                    SUM(CASE WHEN tier = 'anchor' THEN 1 ELSE 0 END) as anchors_total,
                    SUM(CASE WHEN tier = 'anchor' AND in_stock = 1 THEN 1 ELSE 0 END) as anchors_in_stock,
                    SUM(CASE WHEN tier = 'perishable' THEN 1 ELSE 0 END) as perishables_total,
                    SUM(CASE WHEN tier = 'perishable' AND in_stock = 1 THEN 1 ELSE 0 END) as perishables_in_stock
                FROM pantry_items
                """
            )
            row = cursor.fetchone()
            return {
                "total": row["total"] or 0,
                "in_stock": row["in_stock"] or 0,
                "out_of_stock": row["out_of_stock"] or 0,
                "staples": row["staples"] or 0,
                "anchors_total": row["anchors_total"] or 0,
                "anchors_in_stock": row["anchors_in_stock"] or 0,
                "perishables_total": row["perishables_total"] or 0,
                "perishables_in_stock": row["perishables_in_stock"] or 0,
            }

    def toggle_item(
        self,
        item_id: Optional[int] = None,
        name: Optional[str] = None,
        in_stock: Optional[bool] = None,
    ) -> Optional[Dict[str, Any]]:
        """Toggle or explicitly set the stock status of an item."""
        self._invalidate_cache()
        with self._get_connection() as conn:
            if item_id:
                cursor = conn.execute(
                    "SELECT id, in_stock FROM pantry_items WHERE id = ?", (item_id,)
                )
            elif name:
                norm_name = normalize_ingredient_name(name)
                cursor = conn.execute(
                    "SELECT id, in_stock FROM pantry_items WHERE name = ?", (norm_name,)
                )
            else:
                return None

            row = cursor.fetchone()
            if not row:
                return None

            new_status = (
                (1 if in_stock else 0)
                if in_stock is not None
                else (0 if row["in_stock"] == 1 else 1)
            )

            conn.execute(
                """
                UPDATE pantry_items 
                SET in_stock = ?, updated_at = CURRENT_TIMESTAMP 
                WHERE id = ?
                """,
                (new_status, row["id"]),
            )
            conn.commit()

            cursor = conn.execute(
                "SELECT id, name, display_name, category, tier, in_stock, is_staple FROM pantry_items WHERE id = ?",
                (row["id"],),
            )
            return dict(cursor.fetchone())

    def upsert_item(
        self,
        name: str,
        display_name: Optional[str] = None,
        category: Optional[str] = None,
        tier: Optional[str] = None,
        in_stock: bool = True,
        is_staple: bool = False,
    ) -> Dict[str, Any]:
        """Add or update a pantry item."""
        self._invalidate_cache()
        cleaned = clean_ingredient_name(name)
        if cleaned:
            norm_name, default_display = cleaned
            clean_display = (display_name or default_display).strip()
        else:
            norm_name = normalize_ingredient_name(name)
            clean_display = (display_name or name).strip().title()

        if not norm_name:
            norm_name = name.strip().lower()

        cat = category or categorize_ingredient(norm_name)
        tier_val = tier or get_ingredient_tier(norm_name, cat)
        if tier_val == "staple":
            is_staple = True
            in_stock = True

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO pantry_items (name, display_name, category, tier, in_stock, is_staple, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(name) DO UPDATE SET
                    display_name = excluded.display_name,
                    category = excluded.category,
                    tier = excluded.tier,
                    in_stock = excluded.in_stock,
                    is_staple = excluded.is_staple,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (norm_name, clean_display, cat, tier_val, 1 if in_stock else 0, 1 if is_staple else 0),
            )
            conn.commit()

            cursor = conn.execute(
                "SELECT id, name, display_name, category, tier, in_stock, is_staple FROM pantry_items WHERE name = ?",
                (norm_name,),
            )
            return dict(cursor.fetchone())

    def delete_item(self, item_id: int) -> bool:
        """Delete an item by ID."""
        self._invalidate_cache()
        with self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM pantry_items WHERE id = ?", (item_id,))
            conn.commit()
            return cursor.rowcount > 0

    def seed_from_recipes(
        self, recipes: List[Dict[str, Any]], mark_in_stock: bool = True
    ) -> int:
        """Extract ingredients from recipes, sanitize them, and populate pantry."""
        self.cleanup_existing_items()
        added_count = 0
        self._invalidate_cache()

        for r in recipes:
            raw_ingredients = r.get("recipeIngredient") or r.get("ingredients") or []
            for item in raw_ingredients:
                raw_name = ""
                if isinstance(item, dict):
                    raw_name = (
                        item.get("food", {}).get("name")
                        if isinstance(item.get("food"), dict) and item.get("food", {}).get("name")
                        else (
                            item.get("name")
                            or item.get("display")
                            or item.get("note")
                            or item.get("originalText")
                            or ""
                        )
                    )
                elif isinstance(item, str):
                    raw_name = item

                if not raw_name:
                    continue

                cleaned = clean_ingredient_name(raw_name)
                if not cleaned:
                    continue

                norm, clean_display = cleaned
                if not norm or norm in DEFAULT_STAPLES or is_staple_ingredient(norm, raw_name):
                    continue

                cat = categorize_ingredient(norm)
                tier_val = get_ingredient_tier(norm, cat)

                with self._get_connection() as conn:
                    cursor = conn.execute(
                        "SELECT id, display_name FROM pantry_items WHERE name = ?", (norm,)
                    )
                    row = cursor.fetchone()
                    if not row:
                        is_staple_val = 1 if (tier_val == "staple" or norm in ALWAYS_ON_STAPLES) else 0
                        in_stock_val = 1 if (mark_in_stock or is_staple_val) else 0
                        conn.execute(
                            """
                            INSERT INTO pantry_items (name, display_name, category, tier, in_stock, is_staple, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                            """,
                            (norm, clean_display, cat, tier_val, in_stock_val, is_staple_val),
                        )
                        conn.commit()
                        added_count += 1
                    else:
                        # If existing display_name is much messier or longer, upgrade to clean title
                        old_disp = row["display_name"]
                        if len(clean_display) < len(old_disp) and not re.search(r"[\(\)\[\]\/]", clean_display):
                            conn.execute(
                                "UPDATE pantry_items SET display_name = ?, tier = ? WHERE id = ?",
                                (clean_display, tier_val, row["id"]),
                            )
                            conn.commit()

        logger.info(f"Seeded {added_count} new ingredients into pantry database.")
        return added_count

    def clear_all_items(self) -> int:
        """Clear all pantry items from the database."""
        self._invalidate_cache()
        with self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM pantry_items")
            conn.commit()
            deleted = cursor.rowcount
        logger.info(f"Cleared {deleted} items from pantry database.")
        return deleted

    def seed_from_foods(
        self, foods: List[Dict[str, Any]], mark_in_stock: bool = True
    ) -> int:
        """Populate pantry from Mealie food database items."""
        added_count = 0
        self._invalidate_cache()

        for item in foods:
            raw_name = ""
            if isinstance(item, dict):
                raw_name = item.get("name") or item.get("display") or item.get("title") or ""
            elif isinstance(item, str):
                raw_name = item

            if not raw_name:
                continue

            cleaned = clean_ingredient_name(raw_name)
            if not cleaned:
                continue

            norm, clean_display = cleaned
            if not norm or norm in DEFAULT_STAPLES or is_staple_ingredient(norm, raw_name):
                continue

            cat = categorize_ingredient(norm)
            tier_val = get_ingredient_tier(norm, cat)
            is_staple_val = 1 if (tier_val == "staple" or norm in ALWAYS_ON_STAPLES) else 0

            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT id, display_name FROM pantry_items WHERE name = ?", (norm,)
                )
                row = cursor.fetchone()
                if not row:
                    conn.execute(
                        """
                        INSERT INTO pantry_items (name, display_name, category, tier, in_stock, is_staple, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                        """,
                        (norm, clean_display, cat, tier_val, 1 if mark_in_stock else 0, is_staple_val),
                    )
                    conn.commit()
                    added_count += 1
                elif len(clean_display) < len(row["display_name"]):
                    conn.execute(
                        "UPDATE pantry_items SET display_name = ?, tier = ? WHERE id = ?",
                        (clean_display, tier_val, row["id"]),
                    )
                    conn.commit()

        logger.info(f"Seeded {added_count} new foods into pantry database.")
        return added_count

    def get_tiered_dashboard(self) -> Dict[str, Any]:
        """Return categorized items grouped into the three Dinner Availability tiers."""
        all_items = self.get_all_items()
        anchors = []
        perishables = []
        staples = []

        for it in all_items:
            tier = it.get("tier") or get_ingredient_tier(it["name"], it.get("category"))
            if tier == "anchor":
                anchors.append(it)
            elif tier == "perishable":
                perishables.append(it)
            else:
                staples.append(it)

        anchors.sort(key=lambda x: (-x["in_stock"], x["display_name"]))
        perishables.sort(key=lambda x: (-x["in_stock"], x["display_name"]))
        staples.sort(key=lambda x: (-x["in_stock"], x["display_name"]))

        return {
            "anchors": anchors,
            "perishables": perishables,
            "staples": staples,
            "tier_stats": {
                "anchors_total": len(anchors),
                "anchors_in_stock": sum(1 for a in anchors if a["in_stock"] == 1),
                "perishables_total": len(perishables),
                "perishables_in_stock": sum(1 for p in perishables if p["in_stock"] == 1),
                "staples_total": len(staples),
                "staples_in_stock": sum(1 for s in staples if s["in_stock"] == 1),
            },
        }

    def evaluate_recipe(
        self, recipe: Dict[str, Any], in_stock_set: Optional[Set[str]] = None
    ) -> Dict[str, Any]:
        """Evaluate recipe dinner availability against Tier 1 (anchors), Tier 2 (perishables), and Tier 3 (staples).

        Availability model:
        - Tier 1: Centerpiece proteins. Hard blocker: if present and missing, recipe is unavailable.
        - Tier 2: Fresh perishables. Soft tolerance: 0 missing -> ready, 1-2 missing -> almost_ready, >2 missing -> unavailable.
        - Tier 3: Ambient staples. Never gatekeeps; always assumed in stock.

        Returns:
            Dict containing:
                status: 'ready' | 'almost_ready' | 'unavailable'
                is_ready: bool (status in ('ready', 'almost_ready'))
                is_full_pantry: bool (status == 'ready')
                anchor_protein: Optional[str]
                anchor_satisfied: bool
                missing_anchor: Optional[str]
                missing_perishables: List[str]
                missing_perishables_count: int
                missing_items: List[str] (missing_anchor + missing_perishables)
                missing_count: int
                in_stock_items: List[str]
                total_ingredients: int
                reason: str
        """
        if in_stock_set is None:
            in_stock_set = self.get_in_stock_set()

        raw_ingredients = (
            recipe.get("recipeIngredient") or recipe.get("ingredients") or []
        )

        anchor_proteins: List[str] = []
        missing_anchors: List[str] = []
        perishables: List[str] = []
        missing_perishables: List[str] = []
        in_stock_items: List[str] = []
        total_count = 0

        for item in raw_ingredients:
            raw_name = ""
            display_name = ""

            if isinstance(item, dict):
                raw_name = (
                    item.get("food", {}).get("name")
                    if isinstance(item.get("food"), dict) and item.get("food", {}).get("name")
                    else (
                        item.get("name")
                        or item.get("note")
                        or item.get("display")
                        or item.get("originalText")
                        or ""
                    )
                )
                display_name = item.get("display") or item.get("name") or raw_name
            elif isinstance(item, str):
                raw_name = item
                display_name = item

            if not raw_name:
                continue

            cleaned = clean_ingredient_name(raw_name)
            if not cleaned:
                # Discard non-ingredient notes or scraper artifacts
                continue

            norm, clean_display = cleaned
            if not norm:
                continue

            total_count += 1
            tier = get_ingredient_tier(norm)

            # Check matching in in_stock_set
            has_match = (
                norm in in_stock_set
                or any(s in norm or norm in s for s in in_stock_set)
                or norm in ALWAYS_ON_STAPLES
                or norm in DEFAULT_STAPLES
                or is_staple_ingredient(norm, raw_name)
            )

            if tier == "anchor":
                anchor_proteins.append(clean_display)
                if has_match:
                    in_stock_items.append(clean_display)
                else:
                    missing_anchors.append(clean_display)
            elif tier == "perishable":
                perishables.append(clean_display)
                if has_match:
                    in_stock_items.append(clean_display)
                else:
                    missing_perishables.append(clean_display)
            else:
                # Ambient staple: always treated as in-stock!
                in_stock_items.append(clean_display)

        # Deduplicate
        unique_missing_anchors = list(dict.fromkeys(missing_anchors))
        unique_missing_perishables = list(dict.fromkeys(missing_perishables))
        primary_anchor = anchor_proteins[0] if anchor_proteins else None

        # Anchor evaluation:
        # If the recipe specifies centerpiece protein(s), any missing anchor is a hard blocker
        if unique_missing_anchors:
            anchor_satisfied = False
            missing_anchor = unique_missing_anchors[0]
            status = "unavailable"
            reason = f"Missing {missing_anchor}"
        else:
            anchor_satisfied = True
            missing_anchor = None
            if len(unique_missing_perishables) == 0:
                status = "ready"
                reason = "Ready to cook"
            elif len(unique_missing_perishables) <= 2:
                status = "almost_ready"
                reason = f"Need: {unique_missing_perishables[0]}"
            else:
                status = "unavailable"
                reason = f"Missing {len(unique_missing_perishables)} fresh items"

        all_missing = unique_missing_anchors + unique_missing_perishables
        is_ready = (status in ("ready", "almost_ready"))
        is_full_pantry = (status == "ready")

        return {
            "status": status,
            "is_ready": is_ready,
            "is_full_pantry": is_full_pantry,
            "anchor_protein": primary_anchor,
            "anchor_satisfied": anchor_satisfied,
            "missing_anchor": missing_anchor,
            "missing_perishables": unique_missing_perishables,
            "missing_perishables_count": len(unique_missing_perishables),
            "missing_items": all_missing,
            "missing_count": len(all_missing),
            "in_stock_items": list(dict.fromkeys(in_stock_items)),
            "total_ingredients": total_count,
            "reason": reason,
        }


pantry_manager = PantryManager()
