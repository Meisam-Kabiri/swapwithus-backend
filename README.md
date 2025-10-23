# SwapWithUs Backend

Backend service for [SwapWithUs.com](https://swapwithus.com) — a peer-to-peer platform for swapping homes and items.

Built with **FastAPI**, **PostgreSQL (asyncpg)**, and **Google Cloud Run**.  
Handles authentication, home listing management, image storage, and API communication with the frontend.

---

## Features

- FastAPI with async I/O  
- PostgreSQL with async connection pooling (`asyncpg`)  
- Firebase Authentication (JWT)  
- Google Cloud Storage integration for image uploads  
- CDN signed URL generation for secure image access  
- Rate limiting middleware (`slowapi`)  
- Dockerized for deployment on Google Cloud Run  
- Configured CORS and HTTPS support

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
| DevOps | Docker, Git |
| Caching | async-lru |

