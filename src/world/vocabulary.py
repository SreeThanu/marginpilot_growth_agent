"""Controlled vocabulary and templates for a world's semantic context.

Split out of :mod:`src.world.generator` because it is ~200 lines of data with no
logic, and mixing it into the generator would bury the sampling code.

**No LLM is called here or anywhere in the generator.** Semantic context is
assembled from these tables so that worlds stay deterministic, free to
regenerate, and reproducible offline — an LLM-written world would be none of
those, and regenerating one would not reproduce it.

The vocabulary is written to be *genuinely informative but not decisive*: some
context points at a promising intervention, some is a red herring, and none of
it names the answer. That is what makes reading it a reasoning task rather than
a lookup.
"""

from __future__ import annotations

from typing import Final

# --------------------------------------------------------------------------- #
# Merchant identity
# --------------------------------------------------------------------------- #

#: vertical -> (name fragments, category list, product noun list)
VERTICALS: Final[dict[str, dict[str, tuple[str, ...]]]] = {
    "home_and_kitchen": {
        "brand_words": ("Nestwell", "Ghar", "Copperleaf", "Anvi Home", "Terra Kitchen"),
        "categories": ("Cookware", "Storage", "Dining", "Home Decor", "Cleaning"),
        "nouns": (
            "cast iron skillet",
            "steel storage set",
            "ceramic dinner plate set",
            "cotton table runner",
            "bamboo dish rack",
            "copper water bottle",
            "nonstick tawa",
            "glass spice jar set",
        ),
    },
    "apparel": {
        "brand_words": ("Indigo Thread", "Kala", "Nine Yards", "Loomfolk", "Suti"),
        "categories": ("Womenswear", "Menswear", "Kidswear", "Accessories", "Footwear"),
        "nouns": (
            "cotton kurta",
            "linen shirt",
            "block-print dupatta",
            "denim jacket",
            "handloom saree",
            "canvas sneakers",
            "silk scarf",
            "chino trousers",
        ),
    },
    "beauty_and_personal_care": {
        "brand_words": ("Vanya", "Aura Botanics", "Neem & Co", "Saanjh", "Petal Lab"),
        "categories": ("Skincare", "Haircare", "Fragrance", "Bath & Body", "Grooming"),
        "nouns": (
            "vitamin C serum",
            "cold-pressed hair oil",
            "sandalwood soap bar",
            "clay face mask",
            "beard grooming kit",
            "rose face mist",
            "sheet mask pack",
            "sulphate-free shampoo",
        ),
    },
    "packaged_foods": {
        "brand_words": ("Millet Mill", "Farmveda", "Chai Chapter", "Dhaanya", "Nutbox"),
        "categories": ("Snacks", "Beverages", "Staples", "Breakfast", "Gifting"),
        "nouns": (
            "roasted makhana pack",
            "single-estate tea tin",
            "cold brew concentrate",
            "millet muesli",
            "peanut butter jar",
            "dry fruit gift box",
            "jaggery cookies",
            "filter coffee blend",
        ),
    },
    "consumer_electronics_accessories": {
        "brand_words": ("Voltway", "Circuit & Co", "Portly", "Amp India", "Nodewire"),
        "categories": ("Audio", "Charging", "Wearables", "Computer Accessories", "Mobile"),
        "nouns": (
            "wireless earbuds",
            "65W GaN charger",
            "braided USB-C cable",
            "laptop sleeve",
            "smartwatch strap",
            "bluetooth speaker",
            "phone gimbal",
            "mechanical keyboard",
        ),
    },
}

MERCHANT_SUFFIXES: Final[tuple[str, ...]] = ("", " Co.", " India", " Studio", " & Sons", " Labs")

MERCHANT_DESCRIPTION_TEMPLATES: Final[tuple[str, ...]] = (
    "{name} is a {age}-year-old direct-to-consumer {vertical_phrase} brand selling mostly through "
    "its own storefront, with a catalogue of {n_products} SKUs and a repeat-purchase habit "
    "concentrated in {top_category}.",
    "{name} started as a {top_category} specialist and has since widened into {vertical_phrase}. "
    "{n_products} active SKUs, {age} years trading, and a customer base that skews toward "
    "{skew_phrase}.",
    "A {vertical_phrase} brand, {name} runs a lean {n_products}-SKU catalogue and has grown "
    "largely on word of mouth over {age} years. Margins are thinnest in {thin_category}.",
)

VERTICAL_PHRASES: Final[dict[str, str]] = {
    "home_and_kitchen": "home and kitchen",
    "apparel": "apparel",
    "beauty_and_personal_care": "beauty and personal care",
    "packaged_foods": "packaged foods",
    "consumer_electronics_accessories": "consumer electronics accessories",
}

SKEW_PHRASES: Final[tuple[str, ...]] = (
    "metro buyers placing small, frequent orders",
    "tier-2 buyers placing larger, less frequent orders",
    "first-time buyers arriving from social ads",
    "a long-tenured repeat base with low discount exposure",
    "gift buyers who spike around festivals",
)

# --------------------------------------------------------------------------- #
# Products
# --------------------------------------------------------------------------- #

PRODUCT_DESCRIPTION_TEMPLATES: Final[tuple[str, ...]] = (
    "{name} — {detail}. {movement}.",
    "{name}. {detail}, and {movement_lower}.",
    "{name}: {detail}. Stocked since {age_phrase}; {movement_lower}.",
)

PRODUCT_DETAILS: Final[tuple[str, ...]] = (
    "one of the catalogue's steadier sellers",
    "bought most often as a gift",
    "frequently added to a larger basket rather than bought alone",
    "the entry-price item most new customers start with",
    "a premium line with a narrow but loyal following",
    "returned more often than the catalogue average, mostly for fit or finish",
    "seasonal — it sells in bursts and sits flat in between",
    "a repeat-purchase staple with a short replacement cycle",
)

STOCK_STATUS_NOTES: Final[dict[str, tuple[str, ...]]] = {
    "fresh": (
        "restocked recently and moving at the expected rate",
        "newly listed, still finding its audience",
    ),
    "steady": (
        "turning over at roughly the rate it is reordered",
        "no stock pressure either way",
    ),
    "aging": (
        "sitting longer than it used to",
        "cover has crept up over the last two months",
    ),
    "overstocked": (
        "over-ordered ahead of last season and still deep in stock",
        "holding several months of cover at the current run rate",
    ),
    "clearance": (
        "flagged for clearance to free up warehouse space",
        "being wound down; the line is not being reordered",
    ),
}

# --------------------------------------------------------------------------- #
# Segments — archetypes with qualitative notes
# --------------------------------------------------------------------------- #

#: Each archetype carries behaviour multipliers *and* the prose the agent reads.
#: The prose is consistent with the multipliers — a "price-insensitive" note
#: always accompanies a low elasticity multiplier — because context that
#: contradicts the simulator would make the reasoning task unlearnable rather
#: than hard.
SEGMENT_ARCHETYPES: Final[tuple[dict[str, object], ...]] = (
    {
        "name": "Bulk regulars",
        "notes": (
            "Bulk buyers, price-insensitive, order on salary week. They buy the same "
            "four or five SKUs on a near-fixed cycle and rarely browse."
        ),
        "tags": ("high_frequency", "price_insensitive", "salary_week_cycle"),
        "conversion_multiplier": 1.6,
        "elasticity_multiplier": 0.45,
        "aov_multiplier": 1.5,
        "responsiveness_mean": 0.5,
    },
    {
        "name": "Deal seekers",
        "notes": (
            "Wait for sales and stack coupons where they can. High traffic, low "
            "conversion at full price, and they clear the cart the moment a code lands."
        ),
        "tags": ("coupon_stacking", "price_sensitive", "sale_waiting"),
        "conversion_multiplier": 0.55,
        "elasticity_multiplier": 1.7,
        "aov_multiplier": 0.85,
        "responsiveness_mean": 1.9,
    },
    {
        "name": "New arrivals",
        "notes": (
            "First order placed in the last 30 days, mostly from social ads. Undecided "
            "on the brand; a bad first delivery loses them permanently."
        ),
        "tags": ("first_purchase", "ad_sourced", "undecided"),
        "conversion_multiplier": 0.8,
        "elasticity_multiplier": 1.25,
        "aov_multiplier": 0.75,
        "responsiveness_mean": 1.3,
    },
    {
        "name": "Lapsing loyalists",
        "notes": (
            "Two years of steady orders, then nothing for a quarter. They know the "
            "catalogue well, so a discount tells them little they do not already know."
        ),
        "tags": ("lapsing", "long_tenure", "catalogue_literate"),
        "conversion_multiplier": 0.45,
        "elasticity_multiplier": 0.9,
        "aov_multiplier": 1.15,
        "responsiveness_mean": 0.9,
    },
    {
        "name": "Gift buyers",
        "notes": (
            "Order in festival windows, ship to addresses other than their own, and "
            "care more about delivery date than price."
        ),
        "tags": ("seasonal", "gifting", "delivery_sensitive"),
        "conversion_multiplier": 0.9,
        "elasticity_multiplier": 0.6,
        "aov_multiplier": 1.35,
        "responsiveness_mean": 0.7,
    },
    {
        "name": "Cart abandoners",
        "notes": (
            "Reach checkout and stop. Support tickets from this group mention shipping "
            "cost more than product price."
        ),
        "tags": ("checkout_dropoff", "shipping_sensitive"),
        "conversion_multiplier": 0.5,
        "elasticity_multiplier": 1.35,
        "aov_multiplier": 0.95,
        "responsiveness_mean": 1.5,
    },
    {
        "name": "Small-basket regulars",
        "notes": (
            "Order often but small — single items, rarely bundles. Free-shipping "
            "thresholds are the main thing standing between them and a bigger basket."
        ),
        "tags": ("high_frequency", "small_basket", "threshold_sensitive"),
        "conversion_multiplier": 1.25,
        "elasticity_multiplier": 1.0,
        "aov_multiplier": 0.6,
        "responsiveness_mean": 1.15,
    },
)

# --------------------------------------------------------------------------- #
# Calendar, competitors, support
# --------------------------------------------------------------------------- #

SEASONAL_EVENTS: Final[tuple[tuple[str, float], ...]] = (
    ("Ganesh Chaturthi gifting peak — regional, strongest in the west", 1.15),
    ("Onam sales window in Kerala", 1.10),
    ("Navratri and Durga Puja run-up", 1.20),
    ("Diwali gifting season; the single largest trading window of the year", 1.35),
    ("Post-Diwali lull; demand falls back hard for about three weeks", 0.85),
    ("End-of-financial-year clearance in March", 1.05),
    ("Monsoon slowdown in logistics across the east", 0.9),
    ("Wedding season demand for gifting SKUs", 1.18),
    ("Republic Day sale weekend across marketplaces", 1.08),
    ("Back-to-school restocking in June", 1.06),
    ("A quiet stretch with no festival anchor", 0.95),
    ("Summer peak for cooling and travel-adjacent lines", 1.07),
)

#: --- COUPLED SIGNALS ---------------------------------------------------------
#:
#: These four strings are emitted from hidden latents at partial fidelity rather
#: than drawn at random (see `_sample_semantic`). They are held out of the
#: distractor pools below so that a false positive really is a false positive.
#: Each one points at a latent the agent-facing view does not expose — market
#: elasticity, per-intervention response affinity, true baseline conversion —
#: rather than at an observable number like margin or AOV, which structural
#: features already capture and which text would only restate.
SIGNAL_COMPETITOR_PRICE_WAR: Final[str] = (
    "A larger competitor has been running 20% off sitewide for three weeks."
)
SIGNAL_SHIPPING_THRESHOLD: Final[str] = (
    "Repeated questions about whether shipping is free above a threshold."
)
SIGNAL_CONVERSION_DRIFT: Final[str] = (
    "Revenue is flat quarter on quarter while sessions are up, so conversion is drifting down."
)
SIGNAL_CLEARS_WHEN_DISCOUNTED: Final[str] = (
    "it cleared fast the last time it was discounted"
)

COMPETITOR_EVENTS: Final[tuple[str, ...]] = (
    "A marketplace seller has undercut the two best-selling SKUs by about 12%.",
    "A well-funded new entrant is spending heavily on the same ad audiences.",
    "The nearest competitor raised prices ~8% and has not lost visible share.",
    "A competitor's free-shipping threshold dropped to Rs.399, below this merchant's.",
    "Two competitors have pulled back on discounting since the last festival window.",
    "A regional competitor is bundling accessories free with every order.",
    "Nothing unusual from competitors this quarter.",
)

CUSTOMER_SERVICE_THEMES: Final[tuple[str, ...]] = (
    "Complaints that delivery took longer than the estimate in tier-2 cities.",
    "Requests for a smaller trial size before committing to the full product.",
    "Customers asking whether a discount code from last month still works.",
    "Sizing confusion driving a visible share of returns.",
    "Requests to bundle two SKUs that customers already buy together.",
    "Several customers reported seeing a lower price on a marketplace listing.",
    "Questions about restock dates for a line that has been out of stock.",
    "Feedback that packaging arrives damaged on the heavier SKUs.",
    "Customers asking for cash on delivery, which the merchant does not offer.",
)

TRADING_NOTES: Final[tuple[str, ...]] = (
    "Average order value has fallen for two straight months.",
    "Repeat rate is holding but new-customer acquisition cost has risen sharply.",
    "Last month's blanket 15% off cleared stock but the finance sheet looked worse after it.",
    "Traffic is increasingly mobile and increasingly bounce-heavy.",
    "The top three SKUs now account for over half of revenue.",
    "Margins slipped after the last freight rate increase.",
    "A previous free-shipping trial was called a success on conversion; nobody checked contribution.",
    "Discount depth has crept up over three quarters without a corresponding revenue trend.",
    "Refund rate is stable, which rules out quality as the cause of the conversion drift.",
)

INVENTORY_NOTE_TEMPLATES: Final[tuple[str, ...]] = (
    "{product} has {age} days of stock age and is {status_note}.",
    "{age} days on hand for {product}; {status_note}.",
    "Warehouse flags {product} — {status_note} (age {age} days).",
)
