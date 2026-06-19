#!/usr/bin/env python3
"""
One-time local seed script for manual frontend testing.

Creates NUM_USERS real Firebase Auth Emulator accounts (so you can actually log
in through the frontend) plus matching `users` rows, then NUM_LISTINGS listings
spread across homes/books/caravans/clothes with category-appropriate fake data
and real (hotlinked) LoremFlickr photos.

Requires:
- Local Docker Postgres running (docker compose up -d) with migrations applied
- Firebase Auth Emulator running and reachable at FIREBASE_AUTH_EMULATOR_HOST
  e.g. `firebase emulators:start --only auth,firestore --project test-project`

Usage: python scripts/seed_fake_data.py
(Normally invoked via scripts/seed-local.sh, which sets up the env vars first.)
"""

import asyncio
import os
import random
import sys

import aiohttp

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.database.connection import create_asyncpg_pool  # noqa: E402
from test.factories import add_listing, add_user, fake  # noqa: E402

FIREBASE_AUTH_EMULATOR_HOST = os.environ.get("FIREBASE_AUTH_EMULATOR_HOST", "localhost:9099")
SIGNUP_URL = (
    f"http://{FIREBASE_AUTH_EMULATOR_HOST}/identitytoolkit.googleapis.com/v1/accounts:signUp"
    "?key=fake-api-key"
)

SEED_EMAIL_DOMAIN = "fakeswap.test"
SEED_PASSWORD = "Password123!"
NUM_USERS = 100
NUM_LISTINGS = 300

CATEGORIES = ["homes", "books", "caravans", "clothes"]
CATEGORY_KEYWORDS = {
    "homes": "house",
    "books": "book",
    "caravans": "caravan",
    "clothes": "clothing",
}

# Curated real-world data so listings actually look like what they claim to be.
BOOKS = [
    ("1984", "George Orwell"),
    ("To Kill a Mockingbird", "Harper Lee"),
    ("The Great Gatsby", "F. Scott Fitzgerald"),
    ("Pride and Prejudice", "Jane Austen"),
    ("The Hobbit", "J.R.R. Tolkien"),
    ("Brave New World", "Aldous Huxley"),
    ("Fahrenheit 451", "Ray Bradbury"),
    ("The Catcher in the Rye", "J.D. Salinger"),
    ("Crime and Punishment", "Fyodor Dostoevsky"),
    ("One Hundred Years of Solitude", "Gabriel Garcia Marquez"),
    ("The Lord of the Rings", "J.R.R. Tolkien"),
    ("Moby-Dick", "Herman Melville"),
    ("War and Peace", "Leo Tolstoy"),
    ("The Alchemist", "Paulo Coelho"),
    ("Animal Farm", "George Orwell"),
    ("Jane Eyre", "Charlotte Bronte"),
    ("Wuthering Heights", "Emily Bronte"),
    ("The Picture of Dorian Gray", "Oscar Wilde"),
    ("Dune", "Frank Herbert"),
    ("The Kite Runner", "Khaled Hosseini"),
]

CARAVANS = [
    ("Swift", "Sprite"),
    ("Bailey", "Unicorn"),
    ("Hymer", "B-Class"),
    ("Adria", "Twin"),
    ("Elddis", "Avante"),
    ("Coachman", "Pastiche"),
    ("Lunar", "Clubman"),
    ("Knaus", "Sport"),
    ("Burstner", "Ixeo"),
    ("Compass", "Camino"),
    ("Auto-Trail", "Tribute"),
    ("Fiat", "Ducato Motorhome"),
]

CLOTHING_BRANDS = [
    "Zara", "H&M", "Levi's", "Uniqlo", "Nike", "Adidas",
    "Mango", "Gap", "Ralph Lauren", "Tommy Hilfiger", "Calvin Klein", "Patagonia",
]


def loremflickr_url(category: str, seed: int) -> str:
    keyword = CATEGORY_KEYWORDS[category]
    return f"https://loremflickr.com/640/480/{keyword}?lock={seed}"


async def create_emulator_user(session: aiohttp.ClientSession, email: str, password: str) -> str:
    async with session.post(
        SIGNUP_URL,
        json={"email": email, "password": password, "returnSecureToken": True},
    ) as resp:
        if resp.status != 200:
            text = await resp.text()
            raise RuntimeError(f"Failed to create emulator user {email}: {resp.status} {text}")
        data = await resp.json()
        return data["localId"]


async def seed_images(pool, owner_uid: str, listing_id: str, category: str, count: int) -> None:
    for i in range(count):
        url = loremflickr_url(category, hash(f"{listing_id}_{i}") % 100_000)
        await pool.execute(
            """
            INSERT INTO images (
                owner_firebase_uid, listing_id, category,
                public_url, cdn_url, tag, caption, sort_order, is_hero
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (listing_id, public_url) DO NOTHING
            """,
            owner_uid, listing_id, category, url, url,
            fake.word(), fake.sentence(nb_words=5), i, i == 0,
        )


def listing_overrides(category: str) -> dict:
    if category == "books":
        title, author = random.choice(BOOKS)
        return {
            "title": title,
            "author": author,
            "country": fake.country()[:100],
            "city": fake.city()[:100],
        }
    if category == "caravans":
        make, model = random.choice(CARAVANS)
        return {
            "title": f"{make} {model}",
            "make": make,
            "model": model,
            "country": fake.country()[:100],
            "city": fake.city()[:100],
        }
    if category == "clothes":
        brand = random.choice(CLOTHING_BRANDS)
        return {
            "title": f"{brand} {fake.word()}",
            "brand": brand,
            "country": fake.country()[:100],
            "city": fake.city()[:100],
        }
    # homes
    return {
        "country": fake.country()[:20],
        "city": fake.city()[:50],
    }


async def main() -> None:
    print("Connecting to local Postgres...")
    pool = await create_asyncpg_pool()

    already_seeded = await pool.fetchval(
        f"SELECT COUNT(*) FROM users WHERE email LIKE 'seed_user_%@{SEED_EMAIL_DOMAIN}'"
    )
    if already_seeded:
        print(
            f"Found {already_seeded} existing seed users — this script is meant to run once."
        )
        print("Aborting to avoid duplicates. Clear seed data manually first if you want to reseed.")
        await pool.close()
        return

    print(f"Creating {NUM_USERS} users in Firebase Auth Emulator ({FIREBASE_AUTH_EMULATOR_HOST}) + Postgres...")
    user_uids = []
    async with aiohttp.ClientSession() as session:
        for i in range(NUM_USERS):
            email = f"seed_user_{i:03d}@{SEED_EMAIL_DOMAIN}"
            uid = await create_emulator_user(session, email, SEED_PASSWORD)
            await add_user(pool, uid=uid, email=email, name=fake.name())
            user_uids.append(uid)
            if (i + 1) % 20 == 0:
                print(f"  {i + 1}/{NUM_USERS} users created")

    print(f"Seeding {NUM_LISTINGS} listings across {', '.join(CATEGORIES)}...")
    per_category = NUM_LISTINGS // len(CATEGORIES)
    for category in CATEGORIES:
        for _ in range(per_category):
            owner_uid = random.choice(user_uids)
            listing_id = await add_listing(
                pool, owner_uid, category, num_images=0, **listing_overrides(category)
            )
            await seed_images(pool, owner_uid, listing_id, category, count=random.randint(2, 4))
        print(f"  {per_category} {category} listings seeded")

    await pool.close()

    print("\nDone.")
    print(f"Sign in to the frontend with any of seed_user_000..{NUM_USERS - 1:03d}@{SEED_EMAIL_DOMAIN}")
    print(f"Password for all seed users: {SEED_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(main())
