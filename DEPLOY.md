# ViralClip Deployment Guide

## DigitalOcean App Platform Deployment

### Prerequisites
- DigitalOcean account
- GitHub repository connected to DigitalOcean
- API keys for services you want to use

### Quick Deploy

#### Option 1: Deploy via Dashboard
1. Go to [DigitalOcean App Platform](https://cloud.digitalocean.com/apps)
2. Click **Create App**
3. Select **GitHub** and choose this repository
4. DigitalOcean will auto-detect the Dockerfile
5. Configure environment variables (see below)
6. Choose your plan (recommended: **Basic $20/month** for video processing)
7. Click **Create Resources**

#### Option 2: Deploy via CLI
```bash
# Install doctl CLI
# https://docs.digitalocean.com/reference/doctl/how-to/install/

# Authenticate
doctl auth init

# Deploy using the app spec
doctl apps create --spec .do/app.yaml
```

### Environment Variables to Configure

| Variable | Required | Description |
|----------|----------|-------------|
| `GEMINI_API_KEY` | ✅ Yes | Google Gemini API key |
| `AWS_ACCESS_KEY_ID` | No | S3 backup access key |
| `AWS_SECRET_ACCESS_KEY` | No | S3 backup secret |
| `S3_BUCKET_NAME` | No | S3 bucket for clips |
| `ELEVENLABS_API_KEY` | No | Voice dubbing |
| `INSTAGRAM_ACCESS_TOKEN` | No | Instagram posting |
| `YOUTUBE_CLIENT_ID` | No | YouTube posting |

### Resource Sizing

| Plan | Specs | Cost | Use Case |
|------|-------|------|----------|
| Basic XXS | 1 vCPU, 512MB | $5/mo | Testing only |
| Basic XS | 1 vCPU, 1GB | $10/mo | Light usage |
| **Basic S** | 1 vCPU, 2GB | $20/mo | **Recommended** |
| Basic M | 2 vCPU, 4GB | $40/mo | Production |

### Verify Deployment
```bash
# Check health
curl https://your-app.ondigitalocean.app/api/settings/health

# View API docs
# https://your-app.ondigitalocean.app/docs
```

---

## Local Docker Testing

Before deploying, test locally:

```bash
# Build and run
docker-compose up --build

# Access at http://localhost:8000
```

---

## Troubleshooting

### Build fails
- Check `requirements.txt` for incompatible packages
- Ensure Python version matches (3.11)

### App crashes on startup
- Verify all required env vars are set
- Check logs: `doctl apps logs <app-id>`

### Video processing slow
- Upgrade to a larger instance (Basic M or Pro)
- Use `tiny` Whisper model for faster transcription
