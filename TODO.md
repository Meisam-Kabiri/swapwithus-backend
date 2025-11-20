# TODO: Add Prometheus Metrics (Optional)

## What is it?
Prometheus tracks API metrics like request count, latency, and error rates automatically.

## Why add it?
- Monitor which endpoints are slow
- Track error rates in production
- See traffic patterns
- Set up alerts for issues

## How to implement:

### 1. Install
```bash
pip install prometheus-fastapi-instrumentator
```

### 2. Add to app/main.py

**IMPORTANT: Don't expose /metrics publicly!**

```python
from fastapi import Request, HTTPException, Response
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_client import REGISTRY, generate_latest

# After creating app
Instrumentator().instrument(app)  # Track metrics

# Protected endpoint - only allow your Prometheus server
@app.get("/metrics")
async def metrics(request: Request):
    allowed_ips = ["127.0.0.1", "YOUR_PROMETHEUS_SERVER_IP"]

    if request.client.host not in allowed_ips:
        raise HTTPException(status_code=403, detail="Forbidden")

    return Response(content=generate_latest(REGISTRY), media_type="text/plain")
```

### 3. Access metrics
Visit: `http://localhost:8000/metrics` (only from allowed IPs)

### 4. Optional: Set up Prometheus + Grafana
```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'swapwithus'
    static_configs:
      - targets: ['your-api:8000']
```

```bash
docker run -p 9090:9090 -v ./prometheus.yml:/etc/prometheus/prometheus.yml prom/prometheus
docker run -p 3000:3000 grafana/grafana
```

## Security Warning
⚠️ Never use `expose(app)` in production without protection - it makes /metrics public and attackers can see your traffic patterns, endpoints, and error rates.

## Alternative
Instead of Prometheus, you can use Google Cloud Monitoring (already built into Cloud Run).
