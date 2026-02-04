# ViralClip Deployment Guide

## Railway Deployment (Recommended)

Railway offers the easiest deployment experience with automatic builds from GitHub.

### Quick Deploy

1. **Go to** [Railway](https://railway.app/)
2. **Sign in** with GitHub
3. **New Project** → **Deploy from GitHub repo**
4. **Select** this repository
5. **Add environment variables** (see below)
6. **Deploy!**

Railway will auto-detect the Dockerfile and deploy automatically.

### Environment Variables

Add these in Railway dashboard → Variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `GEMINI_API_KEY` | ✅ Yes | Google Gemini API key |
| `AWS_ACCESS_KEY_ID` | No | S3 backup access key |
| `AWS_SECRET_ACCESS_KEY` | No | S3 backup secret |
| `S3_BUCKET_NAME` | No | S3 bucket for clips |
| `ELEVENLABS_API_KEY` | No | Voice dubbing |
| `INSTAGRAM_ACCESS_TOKEN` | No | Instagram posting |
| `YOUTUBE_CLIENT_ID` | No | YouTube posting |

### Pricing

- **Free Tier**: $5 credit/month (good for testing)
- **Hobby**: $5/month + usage
- **Pro**: $20/month + usage (recommended for production)

### Custom Domain

1. Go to **Settings** → **Domains**
2. Add your domain
3. Update DNS records as shown

### Verify Deployment

```bash
# Check health
curl https://your-app.up.railway.app/api/settings/health

# View API docs
# https://your-app.up.railway.app/docs
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

## Railway CLI (Optional)

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login
railway login

# Link to project
railway link

# Deploy
railway up

# View logs
railway logs
```

---

## Troubleshooting

### Build fails
- Check `requirements.txt` for incompatible packages
- Ensure Python version matches (3.11)

### App crashes on startup
- Verify `GEMINI_API_KEY` is set
- Check logs in Railway dashboard

### Video processing slow
- Railway auto-scales, but consider Pro plan for more resources
- Use `tiny` Whisper model for faster transcription
