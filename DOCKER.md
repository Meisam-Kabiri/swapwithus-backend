# Docker Guide for SwapWithUs Backend

## Quick Start

```bash
# Start all services (PostgreSQL + Redis)
docker-compose up -d

# Stop all services (keeps data)
docker-compose stop

# Stop and remove containers (keeps data in volumes)
docker-compose down

# Stop and remove containers AND volumes (⚠️ DATA LOSS)
docker-compose down -v

# View logs
docker-compose logs -f

# View logs for specific service
docker-compose logs -f postgres
```

## Understanding Data Persistence

### Scenario 1: Stop Container (Data Safe ✅)
```bash
docker-compose stop postgres
# Container stopped, data remains in volume
docker-compose start postgres
# Container starts, all data is there!
```

### Scenario 2: Remove Container (Data Safe with Volumes ✅)
```bash
docker-compose down
# Containers removed, but volumes remain
docker-compose up
# New containers created, same data!
```

### Scenario 3: Remove Volumes (⚠️ DATA LOST)
```bash
docker-compose down -v
# Containers AND volumes removed
docker-compose up
# Fresh database, all data gone!
```

## Volume Types

### Named Volumes (Current Setup)
```yaml
volumes:
  - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

**Pros:**
- ✅ Docker manages storage location
- ✅ Works same on Windows/Mac/Linux
- ✅ Easy backup with `docker volume` commands
- ✅ Survives container removal

**Location:**
- Linux: `/var/lib/docker/volumes/swapwithus-backend_postgres_data/_data`
- Mac: Inside Docker Desktop VM
- Windows: Inside Docker Desktop VM

**Commands:**
```bash
# List volumes
docker volume ls

# Inspect volume location
docker volume inspect swapwithus-backend_postgres_data

# Backup volume
docker run --rm -v swapwithus-backend_postgres_data:/data -v $(pwd):/backup alpine tar czf /backup/postgres-backup.tar.gz -C /data .

# Restore volume
docker run --rm -v swapwithus-backend_postgres_data:/data -v $(pwd):/backup alpine tar xzf /backup/postgres-backup.tar.gz -C /data
```

### Bind Volumes (Alternative)
```yaml
volumes:
  - ./postgres-data:/var/lib/postgresql/data
```

**Pros:**
- ✅ Data visible in your project folder
- ✅ Easy to backup (just copy folder)
- ✅ Can edit files directly

**Cons:**
- ⚠️ Permission issues (especially Linux)
- ⚠️ Path format differs by OS
- ⚠️ Slower on Mac/Windows

**To use bind volumes:**
```yaml
# In docker-compose.yml, change:
volumes:
  - postgres_data:/var/lib/postgresql/data
# To:
volumes:
  - ./postgres-data:/var/lib/postgresql/data
```

## Environment Variables

### What Happens to Env Vars

| Action | Env Vars | Data |
|--------|----------|------|
| `docker-compose stop` | Kept | Kept |
| `docker-compose down` | Lost | Kept (in volume) |
| `docker-compose up` | Re-read from .env | Restored from volume |

### Setting Env Vars

**Method 1: .env file (Recommended)**
```bash
cp .env.local.example .env.local
# Edit .env.local with your values
docker-compose --env-file .env.local up
```

**Method 2: Inline in docker-compose.yml**
```yaml
environment:
  POSTGRES_DB: swapwithus
  POSTGRES_USER: postgres
```

**Method 3: From host environment**
```bash
export SWAPWITHUS_DB_PASSWORD=secret
docker-compose up
```

## Common Tasks

### Connect to PostgreSQL

```bash
# From host machine
psql -h localhost -U postgres -d swapwithus

# From inside container
docker-compose exec postgres psql -U postgres -d swapwithus

# Using connection string
psql postgresql://postgres:devpassword@localhost:5432/swapwithus
```

### View Database Files

```bash
# With named volumes
docker volume inspect swapwithus-backend_postgres_data

# Enter container
docker-compose exec postgres bash
cd /var/lib/postgresql/data
ls -la
```

### Reset Database

```bash
# Stop and remove everything
docker-compose down -v

# Start fresh
docker-compose up -d

# Run migrations
alembic upgrade head
```

### Backup Database

```bash
# Using pg_dump
docker-compose exec -T postgres pg_dump -U postgres swapwithus > backup.sql

# Restore
docker-compose exec -T postgres psql -U postgres swapwithus < backup.sql
```

### Check Container Status

```bash
# View running containers
docker-compose ps

# View resource usage
docker stats

# Check health
docker-compose exec postgres pg_isready -U postgres
```

## Development Workflow

### Option 1: Run DB in Docker, App Locally
```bash
# Start only database services
docker-compose up -d postgres redis

# Run app locally (in virtual environment)
source venv/bin/activate
uvicorn app.main:app --reload

# Stop when done
docker-compose stop
```

### Option 2: Everything in Docker
```bash
# Start all services including app
docker-compose up

# App runs in container with hot-reload
# Edit code, changes auto-reload!
```

## Troubleshooting

### Port Already in Use
```bash
# Find what's using port 5432
lsof -i :5432

# Kill the process
kill -9 <PID>

# Or change port in docker-compose.yml
ports:
  - "5433:5432"  # Host:Container
```

### Permission Denied (Bind Volumes)
```bash
# On Linux, fix ownership
sudo chown -R $(id -u):$(id -g) ./postgres-data

# Or use named volumes instead
```

### Can't Connect to Database
```bash
# Check if container is running
docker-compose ps

# Check logs
docker-compose logs postgres

# Test connection
docker-compose exec postgres pg_isready -U postgres

# Check network
docker network ls
docker network inspect swapwithus-network
```

### Data Not Persisting
```bash
# Verify volume exists
docker volume ls | grep postgres

# Check if volume is mounted
docker-compose exec postgres df -h

# Inspect volume
docker volume inspect swapwithus-backend_postgres_data
```

## Best Practices

1. **Use named volumes for development** - Less permission issues
2. **Never use `-v` flag carelessly** - It deletes all data!
3. **Use `.env` files** - Don't commit secrets
4. **Regular backups** - Especially before `docker-compose down -v`
5. **Use health checks** - Ensures services are ready
6. **Tag your volumes** - For easier management

## Production Considerations

For production, don't use Docker volumes for PostgreSQL:
- ✅ Use managed database (Cloud SQL, RDS, etc.)
- ✅ Or use persistent disks with backups
- ❌ Don't rely on Docker volumes in production
