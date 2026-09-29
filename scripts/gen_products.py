"""
Generates 100 original, synthetic fashion products for Charkha Lifestyle.
Nothing here is copied from any real retailer — names/descriptions are
templated combinations, and images are placeholder photos from Lorem Picsum
(a free stock-placeholder service), not scraped product photography.

Output: a Python literal (list of dicts) written to
charkha-lifestyle-backend/app/seed_data.py, matching app/models.py's
Product fields exactly (snake_case, since local_dev.py / a seed script
writes these straight into DynamoDB via put_item).
"""
import os
import random
import pprint

random.seed(42)

CATEGORIES = ["Men", "Women", "Kids", "Accessories"]

FABRICS = ["Cotton", "Linen", "Silk", "Khadi", "Handloom Cotton", "Georgette",
           "Chanderi", "Merino Wool", "Denim", "Cotton-Blend", "Tussar Silk",
           "Viscose", "Cotton Twill", "Modal", "Chambray"]

COLORS = ["Ivory", "Charcoal", "Rust", "Forest Green", "Indigo", "Terracotta",
          "Slate Blue", "Mustard", "Maroon", "Olive", "Sand", "Onyx Black",
          "Blush Pink", "Deep Teal", "Warm Beige", "Burgundy", "Stone Grey",
          "Saffron", "Emerald", "Dusty Rose"]

MEN_ITEMS = [
    ("Kurta", 1400, 2600), ("Nehru Jacket", 2200, 3800),
    ("Tailored Shirt", 1500, 2400), ("Bandhgala Jacket", 4200, 7000),
    ("Sherwani", 6500, 12000), ("Cotton Chinos", 1600, 2400),
    ("Joggers", 1200, 1900), ("Polo T-Shirt", 900, 1500),
    ("Denim Jacket", 2800, 4200), ("Formal Trousers", 1700, 2600),
    ("Crew Neck Sweater", 1900, 2900), ("Waistcoat", 1800, 2900),
]

WOMEN_ITEMS = [
    ("Anarkali Suit", 3200, 6800), ("Handloom Saree", 3800, 9500),
    ("Wrap Midi Dress", 2600, 4200), ("Palazzo Co-ord Set", 2900, 4800),
    ("Kurti", 1300, 2400), ("Maxi Dress", 2800, 4600),
    ("Pleated Skirt", 1900, 3100), ("Blouse", 900, 1600),
    ("Dupatta", 800, 2200), ("Straight-Fit Kurta Set", 2400, 4000),
    ("Cape Jacket", 2600, 4400), ("Tunic Top", 1400, 2300),
]

KIDS_ITEMS = [
    ("Ethnic Set", 1400, 2400), ("Party Frock", 1600, 2800),
    ("Dungaree Set", 1200, 2000), ("Printed T-Shirt Set", 700, 1200),
    ("Pyjama Set", 800, 1400), ("Denim Jacket", 1500, 2400),
]

ACCESSORY_ITEMS = [
    ("Leather Belt", 900, 1800), ("Silk Scarf", 1100, 2200),
    ("Canvas Tote Bag", 1300, 2400), ("Embroidered Juttis", 1400, 2600),
    ("Statement Necklace", 900, 2100), ("Structured Clutch", 1600, 2900),
    ("Wayfarer Sunglasses", 1200, 2400), ("Wool Stole", 1500, 2800),
]

DESC_TEMPLATES = [
    "A {color_lower} {item_lower} in {fabric_lower}, cut for a considered, everyday silhouette.",
    "Finished in {fabric_lower}, this {item_lower} carries a quiet {color_lower} tone that layers easily.",
    "A studio staple: {fabric_lower} {item_lower} with clean lines and a fit built to last beyond a season.",
    "Soft-structured {item_lower} in {color_lower} {fabric_lower} — understated, versatile, made to repeat.",
    "An heirloom-leaning {item_lower}, woven in {fabric_lower} and finished in a muted {color_lower}.",
]

CATEGORY_ITEMS = {
    "Men": MEN_ITEMS,
    "Women": WOMEN_ITEMS,
    "Kids": KIDS_ITEMS,
    "Accessories": ACCESSORY_ITEMS,
}

# Roughly proportional split across 100 products
TARGET_COUNTS = {"Men": 28, "Women": 34, "Kids": 18, "Accessories": 20}


def slugify(*parts: str) -> str:
    s = "-".join(parts)
    s = s.lower().replace("'", "")
    out = []
    for ch in s:
        if ch.isalnum():
            out.append(ch)
        elif ch in (" ", "-", "_"):
            out.append("-")
    slug = "".join(out)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")


products = []
seen_slugs = set()

for category, count in TARGET_COUNTS.items():
    items = CATEGORY_ITEMS[category]
    for i in range(count):
        item_name, lo, hi = random.choice(items)
        color = random.choice(COLORS)
        fabric = random.choice(FABRICS)
        name = f"{color} {item_name}"
        base_slug = slugify(category, item_name, color)
        slug = base_slug
        n = 2
        while slug in seen_slugs:
            slug = f"{base_slug}-{n}"
            n += 1
        seen_slugs.add(slug)

        price = random.randrange(lo, hi, 50)
        stock = random.choice([0, 0] + list(range(3, 60)))  # occasional out-of-stock
        status = "live" if random.random() > 0.12 else "draft"

        desc_template = random.choice(DESC_TEMPLATES)
        description = desc_template.format(
            color_lower=color.lower(), item_lower=item_name.lower(), fabric_lower=fabric.lower()
        )
        description = description[0].upper() + description[1:]

        image_seed = slug
        image_keys = [f"https://picsum.photos/seed/{image_seed}/700/900"]

        products.append(
            {
                "product_id": slug,
                "name": name,
                "category": category,
                "price": float(price),
                "stock": stock,
                "description": description,
                "image_keys": image_keys,
                "status": status,
                "last_edited_by": None,
            }
        )

random.shuffle(products)

assert len(products) == 100, len(products)
assert len(set(p["product_id"] for p in products)) == 100

out_path = os.path.join(os.path.dirname(__file__), "..", "app", "seed_data.py")
with open(out_path, "w") as f:
    f.write('"""\n')
    f.write(
        "100 original, synthetic sample products for local/dev seeding and initial\n"
        "catalog population. Names/descriptions are generated templates, not copied\n"
        "from any retailer; images are placeholder photos from Lorem Picsum\n"
        "(https://picsum.photos), a free stock-placeholder service meant for exactly\n"
        "this kind of mockup/dev use — swap in real product photography before\n"
        "going live for real. Regenerate with scripts/gen_products.py if needed.\n"
    )
    f.write('"""\n\n')
    f.write("from __future__ import annotations\n\n")
    f.write("SEED_PRODUCTS: list[dict] = ")
    f.write(pprint.pformat(products, width=100, sort_dicts=False))
    f.write("\n")

print(f"Wrote {len(products)} products to {out_path}")

# Keep infra/seed_products_lambda/seed_data.json (the copy the CDK-deployed
# seed Custom Resource actually reads at deploy time) in sync with the same
# data, so there's exactly one generator and no risk of the two drifting
# apart. json.dumps is fine here (unlike seed_data.py above) since this
# file is read back with json.load, not imported as Python.
import json  # noqa: E402

json_out_path = os.path.join(
    os.path.dirname(__file__), "..", "infra", "seed_products_lambda", "seed_data.json"
)
os.makedirs(os.path.dirname(json_out_path), exist_ok=True)
with open(json_out_path, "w") as f:
    json.dump(products, f, indent=2)
print(f"Wrote {len(products)} products to {json_out_path}")

by_cat = {}
for p in products:
    by_cat[p["category"]] = by_cat.get(p["category"], 0) + 1
print(by_cat)