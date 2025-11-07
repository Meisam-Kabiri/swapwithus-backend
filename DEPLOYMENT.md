# SwapWithUs Backend - Cloud Run Deployment Guide

## Prerequisites

- Google Cloud SDK (`gcloud`) installed
- Authenticated with Google Cloud: `gcloud auth login`
- Docker installed (for local testing, optional)

## Project Setup

Your project ID: `swapwithus-project`
Storage bucket: `swapwithus-listing-images`
Service account: `swapwithus-backend-service@swapwithus-project.iam.gserviceaccount.com`

---

## Important Setup Files

### 1. Environment Variables File (`env.yaml`)

**Never commit this file to git!** It contains secrets.

```yaml
SWAPWITHUS_PROJECT_ID: "swapwithus-project"
SWAPWITHUS_SQL_REGION: "europe-north1"
SWAPWITHUS_SQL_INSTANCE: "swapwithus-db"
SWAPWITHUS_DATABASE_NAME: "swapwithusDB"
SWAPWITHUS_DB_USER: "postgres"
SWAPWITHUS_DB_PASSWORD: "your_secure_password_here"
SWAPWITHUS_DB_HOST: "YOUR_DB_IP_ADDRESS"
SWAPWITHUS_DATABASE_URL: "postgresql+asyncpg://postgres:your_password@YOUR_DB_IP:5432/swapwithusDB"
SWAPWITHUS_MAPS_API_KEY: "your_maps_api_key_here"
GOOGLE_CLOUD_STORAGE_BUCKET: "swapwithus-listing-images"
GOOGLE_CLOUD_CDN_SIGNING_KEY: "your_cdn_signing_key_here"
GOOGLE_CLOUD_CDN_KEY_NAME: "cdnkey"
REDIS_URL: "redis://default:your_redis_password@your-redis-host:port"
```

### 2. `.gitignore` entries

Make sure these are in your `.gitignore`:
```
.env
env.yaml
*.json  # Service account keys
```

### 3. Google Cloud Storage Client

**IMPORTANT:** Your Python code should use Application Default Credentials (ADC), NOT a service account JSON file.

✅ **Correct way (works in Cloud Run):**
```python
from google.cloud import storage

client = storage.Client()  # Uses service account automatically
```

❌ **Wrong way (doesn't work in Cloud Run):**
```python
from google.cloud import storage

# DON'T use this - the JSON file won't exist in Cloud Run
client = storage.Client.from_service_account_json('/path/to/key.json')
```

The `--service-account` flag in deployment automatically provides credentials.

---

## Initial Deployment Steps

### 1. Navigate to Backend Directory

```bash
cd /home/meisam/Desktop/swapwithus_backend
```

### 2. Set Google Cloud Project

```bash
gcloud config set project swapwithus-project
```

### 3. Enable Required APIs

```bash
# Enable APIs (first time only)
gcloud services enable cloudbuild.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable artifactregistry.googleapis.com
```

Or enable in console: https://console.cloud.google.com/apis/library?project=swapwithus-project

### 4. Build Container Image

This step builds your Docker image and uploads it to Google Container Registry.
**Time: 2-5 minutes**

```bash
gcloud builds submit --tag gcr.io/swapwithus-project/swapwithus-backend
```

**Note:** You may see "ERROR" about log streaming permissions - ignore it. The build is still running. Check status at:
https://console.cloud.google.com/cloud-build/builds?project=swapwithus-project

### 5. Deploy to Cloud Run

**Using environment variables file (recommended for secrets):**

```bash
gcloud run deploy swapwithus-backend \
  --image gcr.io/swapwithus-project/swapwithus-backend \
  --platform managed \
  --region europe-west1 \
  --allow-unauthenticated \
  --max-instances=10 \
  --memory=512Mi \
  --timeout=300 \
  --add-cloudsql-instances=swapwithus-project:europe-north1:swapwithus-db \
  --env-vars-file=env.yaml \
  --service-account=swapwithus-backend-service@swapwithus-project.iam.gserviceaccount.com
```

**Configuration explained:**
- `--allow-unauthenticated`: Makes API publicly accessible (required for your frontend)
- `--timeout=300`: 5 minute timeout (maximum allowed by Cloud Run)
- `--max-instances=10`: Limits scaling to prevent unexpected costs
- `--memory=512Mi`: Allocates 512MB RAM per instance
- `--env-vars-file`: Loads environment variables from YAML file (handles special characters in passwords)
- `--service-account`: Gives access to Cloud Storage bucket (no JSON key needed!)

### 6. Get Your Backend URL

After deployment, Cloud Run will output a URL like:
```
https://swapwithus-backend-928070808987.europe-west1.run.app
```

**Copy this URL!** You'll need it for the frontend.

---

## Update Frontend Configuration

### 1. Update Environment Variable

```bash
cd /home/meisam/Desktop/swapwithus

# Add to .env.local
echo "NEXT_PUBLIC_PYTHON_BACKEND_URL=https://YOUR_CLOUD_RUN_URL" >> .env.local
```

### 2. Restart Frontend Dev Server

```bash
# Stop current dev server (Ctrl+C)
npm run dev
```

---

## Updating Your Backend (After Code Changes)

When you make changes to your backend code:

### Quick Update (Build + Deploy)

```bash
cd /home/meisam/Desktop/swapwithus_backend

# Build new image
gcloud builds submit --tag gcr.io/swapwithus-project/swapwithus-backend

# Deploy (env vars already set, no need to repeat)
gcloud run deploy swapwithus-backend \
  --image gcr.io/swapwithus-project/swapwithus-backend \
  --platform managed \
  --region europe-west1 \
  --add-cloudsql-instances=swapwithus-project:europe-north1:swapwithus-db
```

**Time: 2-5 minutes**

### Update Environment Variables Only

If you only changed environment variables (not code):

```bash
# Edit env.yaml first, then:
gcloud run services update swapwithus-backend \
  --region=europe-west1 \
  --env-vars-file=env.yaml
```

**Time: 10-30 seconds**

---

## Monitoring & Debugging

### View Logs (Console - Easiest)

https://console.cloud.google.com/run/detail/europe-west1/swapwithus-backend/logs?project=swapwithus-project

### View Logs (Command Line)

```bash
gcloud run services logs tail swapwithus-backend --region=europe-west1
```

If you get permission errors, view in console instead.

### Check Service Status

```bash
gcloud run services describe swapwithus-backend --region=europe-west1
```

### Get Service URL

```bash
gcloud run services describe swapwithus-backend --region=europe-west1 --format='value(status.url)'
```

### Test Endpoint

```bash
# Test if backend is running
curl https://YOUR_CLOUD_RUN_URL/

# Test API endpoint
curl "https://YOUR_CLOUD_RUN_URL/api/homes?owner_firebase_uid=test"
```

---

## Common Issues & Solutions

### Issue: "Internal Server Error" on API calls

**Check logs first:** https://console.cloud.google.com/run/detail/europe-west1/swapwithus-backend/logs?project=swapwithus-project

**Common causes:**

1. **Database connection fails**
   - Cloud Run can't reach your PostgreSQL
   - If using Cloud SQL, you need to connect via Unix socket or Cloud SQL Proxy
   - See "Cloud SQL Connection" section below

2. **Missing Python dependencies**
   - Check `requirements.txt` has all packages
   - Rebuild: `gcloud builds submit --tag gcr.io/swapwithus-project/swapwithus-backend`

3. **Environment variables not set**
   - Verify: `gcloud run services describe swapwithus-backend --region=europe-west1`
   - Update: `gcloud run services update swapwithus-backend --region=europe-west1 --env-vars-file=env.yaml`

4. **Python code uses service account JSON file**
   - Change `storage.Client.from_service_account_json()` to `storage.Client()`

### Issue: Build timeout or fails

**Error**: Build takes too long
- Reduce dependencies in requirements.txt
- Use smaller base image

**Error**: Permission denied
- Enable APIs: https://console.cloud.google.com/apis/library?project=swapwithus-project
- Check IAM roles: https://console.cloud.google.com/iam-admin/iam?project=swapwithus-project

### Issue: Deployment permission errors

Add these IAM roles to your account (`msm.kabiri91@gmail.com`):
- Cloud Run Admin
- Cloud Build Editor
- Service Account User
- Storage Admin
- Service Usage Admin (to enable APIs)

Go to: https://console.cloud.google.com/iam-admin/iam?project=swapwithus-project

---

## Cloud SQL Connection (If Applicable)

If your PostgreSQL is on Cloud SQL (not a public IP), you need to connect differently:

### Option 1: Cloud SQL Proxy (Recommended)

```bash
gcloud run deploy swapwithus-backend \
  --image gcr.io/swapwithus-project/swapwithus-backend \
  --region europe-west1 \
  --add-cloudsql-instances=swapwithus-project:europe-north1:swapwithus-db \
  --env-vars-file=env.yaml \
  --service-account=swapwithus-backend-service@swapwithus-project.iam.gserviceaccount.com
```

Then update `SWAPWITHUS_DB_HOST` in `env.yaml`:
```yaml
SWAPWITHUS_DB_HOST: "/cloudsql/swapwithus-project:europe-north1:swapwithus-db"
```

### Option 2: Public IP with Authorized Networks

Add Cloud Run's IP ranges to Cloud SQL authorized networks:
https://console.cloud.google.com/sql/instances/swapwithus-db/connections?project=swapwithus-project

**Not recommended** - Cloud Run IPs change frequently.

---

## Cost Optimization

Cloud Run pricing (as of 2025):
- **Free tier**: 2 million requests/month
- **After free tier**: ~$0.40 per million requests
- **Memory**: $0.0000025 per GB-second
- **CPU**: $0.00001 per vCPU-second

**Expected cost for small app**: $0-5/month

### Reduce Costs

1. **Lower memory** if not needed:
   ```bash
   --memory=256Mi  # Instead of 512Mi
   ```

2. **Add min-instances=0** (default, scales to zero when idle):
   ```bash
   --min-instances=0
   ```

3. **Monitor usage**:
   https://console.cloud.google.com/run/detail/europe-west1/swapwithus-backend/metrics?project=swapwithus-project

---

## Environment Variables Reference

| Variable | Description | Example |
|----------|-------------|---------|
| `SWAPWITHUS_PROJECT_ID` | Google Cloud project ID | `swapwithus-project` |
| `SWAPWITHUS_DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://user:pass@host:5432/db` |
| `SWAPWITHUS_MAPS_API_KEY` | Google Maps API key for geocoding | `AIza...` |
| `GOOGLE_CLOUD_STORAGE_BUCKET` | GCS bucket name for images | `swapwithus-listing-images` |

**Add new variables to `env.yaml`, then redeploy:**
```bash
gcloud run services update swapwithus-backend \
  --region=europe-west1 \
  --env-vars-file=env.yaml
```

---

## Testing Locally with Docker (Optional)

### Build Docker Image

```bash
cd /home/meisam/Desktop/swapwithus_backend
docker build -t swapwithus-backend .
```

### Run Locally

```bash
docker run -p 8080:8080 \
  --env-file=.env \
  swapwithus-backend
```

### Test

```bash
curl http://localhost:8080/
```

---

## Rollback to Previous Version

If new deployment has issues:

```bash
# List revisions
gcloud run revisions list --service=swapwithus-backend --region=europe-west1

# Rollback to previous revision
gcloud run services update-traffic swapwithus-backend \
  --region=europe-west1 \
  --to-revisions=PREVIOUS_REVISION=100
```

---

## Custom Domain (Optional)

### Map Custom Domain

```bash
# Example: api.swapwithus.com
gcloud run domain-mappings create \
  --service=swapwithus-backend \
  --domain=api.swapwithus.com \
  --region=europe-west1
```

Then add DNS records as instructed by Google Cloud.

---

## Quick Reference Commands

| Task | Command |
|------|---------|
| Build image | `gcloud builds submit --tag gcr.io/swapwithus-project/swapwithus-backend` |
| Deploy | `gcloud run deploy swapwithus-backend --image gcr.io/swapwithus-project/swapwithus-backend --region europe-west1 --add-cloudsql-instances=swapwithus-project:europe-north1:swapwithus-db --env-vars-file=env.yaml --service-account=swapwithus-backend-service@swapwithus-project.iam.gserviceaccount.com` |
| View logs (console) | https://console.cloud.google.com/run/detail/europe-west1/swapwithus-backend/logs?project=swapwithus-project |
| Get URL | `gcloud run services describe swapwithus-backend --region=europe-west1 --format='value(status.url)'` |
| Update env vars | `gcloud run services update swapwithus-backend --region=europe-west1 --env-vars-file=env.yaml` |
| Delete service | `gcloud run services delete swapwithus-backend --region=europe-west1` |

---

## Files Structure

```
swapwithus_backend/
├── Dockerfile              # Container configuration
├── .dockerignore          # Files excluded from Docker build
├── requirements.txt       # Python dependencies
├── env.yaml              # Environment variables (DO NOT COMMIT!)
├── .env                  # Local env file (DO NOT COMMIT!)
├── .gitignore            # Excludes .env, env.yaml, *.json
├── app.py                # Your FastAPI application
└── DEPLOYMENT.md         # This file
```

**Files that should NEVER be in git:**
- `env.yaml` - Contains passwords and API keys
- `.env` - Local environment variables
- `*.json` - Service account keys

---

## Next Steps After Deployment

1. ✅ Deploy backend to Cloud Run
2. ✅ Copy Cloud Run URL
3. ✅ Update frontend `.env.local`
4. ✅ Test API endpoints: `curl https://YOUR_URL/api/homes?owner_firebase_uid=TEST`
5. ⬜ Fix any database connection issues (check logs)
6. ⬜ Deploy frontend to Vercel
7. ⬜ Update Vercel environment variables with Cloud Run URL

---

## Troubleshooting Checklist

When something doesn't work:

1. **Check logs**: https://console.cloud.google.com/run/detail/europe-west1/swapwithus-backend/logs?project=swapwithus-project
2. **Verify env vars**: `gcloud run services describe swapwithus-backend --region=europe-west1`
3. **Test endpoint**: `curl https://YOUR_URL/api/homes?owner_firebase_uid=test`
4. **Check service status**: `gcloud run services list --region=europe-west1`
5. **Review recent deployments**: https://console.cloud.google.com/run/detail/europe-west1/swapwithus-backend/revisions?project=swapwithus-project

---

## Support & Documentation

- **Cloud Run Docs**: https://cloud.google.com/run/docs
- **Pricing Calculator**: https://cloud.google.com/products/calculator
- **Quotas & Limits**: https://cloud.google.com/run/quotas
- **Best Practices**: https://cloud.google.com/run/docs/tips
- **Troubleshooting**: https://cloud.google.com/run/docs/troubleshooting

---

## Security Best Practices

1. **Never commit secrets**
   - Use `env.yaml` for environment variables
   - Add to `.gitignore`

2. **Use service accounts**
   - Don't use JSON keys in Cloud Run
   - Use `--service-account` flag instead

3. **Limit permissions**
   - Service account should only have necessary roles
   - Use principle of least privilege

4. **Monitor usage**
   - Set budget alerts
   - Review logs regularly
   - Check for unusual traffic

5. **Keep dependencies updated**
   - Regularly update `requirements.txt`
   - Rebuild and redeploy


---

## Service Account Permissions for Cloud SQL

**IMPORTANT:** If using Cloud SQL, your service account needs the **Cloud SQL Client** role.

### Add Cloud SQL Client Role

**Via Google Cloud Console:**

1. Go to: https://console.cloud.google.com/iam-admin/iam?project=swapwithus-project
2. Find: `swapwithus-backend-service@swapwithus-project.iam.gserviceaccount.com`
3. Click **Edit** (pencil icon)
4. Click **"+ ADD ANOTHER ROLE"**
5. Search for and add: **Cloud SQL Client**
6. Click **SAVE**

**Via command line:**

```bash
gcloud projects add-iam-policy-binding swapwithus-project \
  --member="serviceAccount:swapwithus-backend-service@swapwithus-project.iam.gserviceaccount.com" \
  --role="roles/cloudsql.client"
```

### Required Service Account Roles Summary

Your service account (`swapwithus-backend-service@swapwithus-project.iam.gserviceaccount.com`) needs:

- ✅ **Storage Admin** - Access to Cloud Storage bucket for images
- ✅ **Cloud SQL Client** - Connect to Cloud SQL database via Cloud SQL Proxy
- ✅ **Service Account Token Creator** - Generate signed URLs for private images (self-impersonation)

### Deploy with Cloud SQL Connection

After adding the role, deploy with Cloud SQL Proxy:

```bash
gcloud builds submit --tag gcr.io/swapwithus-project/swapwithus-backend
```
```bash
gcloud run deploy swapwithus-backend \
  --image gcr.io/swapwithus-project/swapwithus-backend \
  --platform managed \
  --region europe-west1 \
  --add-cloudsql-instances=swapwithus-project:europe-north1:swapwithus-db \
  --env-vars-file=env.yaml \
  --service-account=swapwithus-backend-service@swapwithus-project.iam.gserviceaccount.com
```

**Note:** You still use the public IP (`35.228.209.98`) in your `env.yaml` for `SWAPWITHUS_DB_HOST`. The Cloud SQL Proxy handles the secure connection automatically.

---

## Private Image Storage with Signed URLs

**CRITICAL:** All user images are stored in a **private** Cloud Storage bucket for security. To serve these images, the backend generates temporary signed URLs.

### The Problem

Cloud Run doesn't have private keys (by design for security). Standard signed URL generation requires a private key, which causes this error:

```
AttributeError: you need a private key to sign credentials
```

### The Solution: IAM signBlob API

Use Google's IAM Credentials API to sign URLs without a private key. The service account delegates signing to Google's IAM service.

**Requirements:**

1. **Enable IAM Credentials API:**
   ```bash
   gcloud services enable iamcredentials.googleapis.com --project=swapwithus-project
   ```

2. **Grant self-impersonation permission:**

   The service account needs permission to sign tokens **as itself**.

   **Via Console (CORRECT WAY):**

   a. Go to: https://console.cloud.google.com/iam-admin/serviceaccounts?project=swapwithus-project

   b. Click on: `swapwithus-backend-service@swapwithus-project.iam.gserviceaccount.com`

   c. Click the **PERMISSIONS** tab

   d. Scroll to "Principals with access to this service account"

   e. Click **GRANT ACCESS**

   f. In "New principals" enter: `swapwithus-backend-service@swapwithus-project.iam.gserviceaccount.com` (the same service account!)

   g. In "Role" select: **Service Account Token Creator**

   h. Click **SAVE**

   **⚠️ Important:** Adding the role via the main IAM page (not the service account page) will NOT work. The service account must be granted permission to impersonate itself.

3. **The code automatically detects Cloud Run** and uses IAM signBlob:
   ```python
   # In gcp_storage_and_api/image_upload.py
   if os.getenv('K_SERVICE'):  # Detects Cloud Run
       # Use IAM signBlob API (no private key needed)
       signed_url = blob.generate_signed_url(
           service_account_email='swapwithus-backend-service@swapwithus-project.iam.gserviceaccount.com',
           access_token=token
       )
   ```

### Verification

After deploying, check logs for successful signed URL generation. Images should load on the frontend.

**Test:**
```bash
curl "https://swapwithus-backend-928070808987.europe-west1.run.app/api/homes?owner_firebase_uid=YOUR_UID"
```

Look for `hero_image_url` with a signed URL (contains query parameters like `X-Goog-Algorithm`, `X-Goog-Signature`, etc.).

---

## Auto-Detection: Local vs Cloud Run

**IMPORTANT:** The backend automatically detects whether it's running locally or on Cloud Run.

### How It Works

The `db_connection/connection_to_db.py` file checks for the `K_SERVICE` environment variable (set by Cloud Run):

```python
IS_CLOUD_RUN = os.getenv('K_SERVICE') is not None

if IS_CLOUD_RUN:
    # Use Unix socket for Cloud SQL Proxy
    ASYNCPG_URL = f"postgresql://user:pass@/dbname?host=/cloudsql/swapwithus-project:europe-north1:swapwithus-db"
else:
    # Use public IP from env vars
    ASYNCPG_URL = f"postgresql://user:pass@{DB_HOST}:5432/dbname"
```

### What This Means

- **Local development**: Uses `SWAPWITHUS_DB_HOST` (35.228.209.98) from your `.bashrc` or `env.yaml`
- **Cloud Run**: Automatically uses Unix socket via Cloud SQL Proxy
- **No manual switching needed** - same code works everywhere!

### Your env.yaml Setup

Keep your `env.yaml` with the **public IP**:

```yaml
SWAPWITHUS_DB_HOST: "YOUR_DB_IP_ADDRESS"
SWAPWITHUS_DATABASE_URL: "postgresql+asyncpg://postgres:your_password@YOUR_DB_IP:5432/swapwithusDB"
```

The code will **ignore** these on Cloud Run and use the Unix socket instead.

---

## Testing Your Deployment

### Test Root Endpoint

```bash
curl https://swapwithus-backend-928070808987.europe-west1.run.app/
```

Expected response: `{"detail":"Not Found"}` ✅

### Test API Endpoint

```bash
curl "https://swapwithus-backend-928070808987.europe-west1.run.app/api/homes?owner_firebase_uid=test"
```

Expected response: `[]` (empty array) ✅

### Test With Real Data

```bash
curl "https://swapwithus-backend-928070808987.europe-west1.run.app/api/homes?owner_firebase_uid=YOUR_FIREBASE_UID"
```

Should return your listings in JSON format.

### Check Startup Logs

Look for one of these messages in the logs:

- 🌩️ `Cloud Run mode: Connecting via Cloud SQL Proxy`
- 💻 `Local development mode: Connecting to 35.228.209.98`

This confirms which mode the backend is running in.

---

## Complete Deployment Checklist

Before going to production, verify:

- ✅ Backend builds successfully: `gcloud builds submit --tag gcr.io/swapwithus-project/swapwithus-backend`
- ✅ Deployment succeeds: `gcloud run deploy swapwithus-backend ...`
- ✅ Service account has roles: Storage Admin + Cloud SQL Client
- ✅ Cloud SQL instance added: `--add-cloudsql-instances=swapwithus-project:europe-north1:swapwithus-db`
- ✅ Environment variables set: `--env-vars-file=env.yaml`
- ✅ API responds: `curl https://YOUR_URL/api/homes?owner_firebase_uid=test` returns `[]`
- ✅ Database connects: Check logs for "Cloud Run mode" message
- ✅ Frontend updated: `.env.local` has `NEXT_PUBLIC_PYTHON_BACKEND_URL=https://YOUR_URL`
- ✅ Local development works: `python app.py` connects to 35.228.209.98

---

## Your Deployed Backend

**Service URL:** `https://swapwithus-backend-928070808987.europe-west1.run.app`

**Service Name:** `swapwithus-backend`

**Region:** `europe-west1`

**Project:** `swapwithus-project`

**Quick Links:**
- **Logs:** https://console.cloud.google.com/run/detail/europe-west1/swapwithus-backend/logs?project=swapwithus-project
- **Metrics:** https://console.cloud.google.com/run/detail/europe-west1/swapwithus-backend/metrics?project=swapwithus-project
- **Revisions:** https://console.cloud.google.com/run/detail/europe-west1/swapwithus-backend/revisions?project=swapwithus-project

