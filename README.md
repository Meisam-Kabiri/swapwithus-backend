# SwapWithUs Backend

Backend service for [SwapWithUs.com](https://swapwithus.com) — a peer-to-peer platform for swapping homes and items.

Built with **FastAPI**, **PostgreSQL (asyncpg)**, and **Google Cloud Run**.  
Handles authentication, home listing management, image storage, and API communication with the frontend.

---

## Features

- FastAPI with async I/O
- PostgreSQL with async connection pooling (`asyncpg`)
- Firebase Authentication (JWT)
- Firestore for real-time messaging
- Google Cloud Storage + CDN for images
- Rate limiting on all endpoints (Redis-backed)
- Swap system with reviews and ratings
- Admin dashboard and moderation tools
- User reporting system
- Database migrations with Alembic
- Deployed on Google Cloud Run

---

## Tech Stack

| Component | Technology |
|------------|-------------|
| Language | Python 3.12 |
| Framework | FastAPI |
| Database | PostgreSQL (asyncpg) |
| Auth | Firebase |
| Cloud | Google Cloud Run, Cloud SQL, Cloud Storage |
| Validation | Pydantic v2 |
| DevOps | Docker, Terraform, Git |
| Caching | async-lru |
| Messaging | Firestore |
| Migrations | Alembic |
| Rate Limiting | SlowAPI + Redis |

---

## Architecture

- **Database Pool:** Stored in `app.state` for dependency injection
- **Rate Limiting:** Per-user (authenticated) or per-IP (anonymous)
- **Image Pipeline:** Upload → GCS → CDN with signed URLs
- **Messaging:** Backend-validated writes to Firestore
- **Migrations:** Alembic for schema versioning
- **Infrastructure:** Terraform manages GCP resources (Cloud Run, SQL, Storage, CDN, IAM)

