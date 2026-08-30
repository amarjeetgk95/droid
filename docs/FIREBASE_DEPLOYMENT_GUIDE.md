# 🚀 Firebase & Cloud Run Deployment Guide — DROID F&O Platform

This guide provides step-by-step instructions to deploy the **DROID Indian F&O Market Analysis Platform** to **Firebase** and **Google Cloud Run (asia-south1 Mumbai)**.

---

## 🏗️ Deployment Architecture

```text
               User Browser / Mobile
                         │
                         ▼
        ┌──────────────────────────────────┐
        │     Firebase Global CDN / SSL    │
        │     (Custom Domain / Hosting)    │
        └─────────────────┬────────────────┘
                          │
            ┌─────────────┴─────────────┐
            ▼                           ▼
 ┌─────────────────────┐     ┌─────────────────────┐
 │  Firebase Hosting   │     │  Google Cloud Run   │
 │   (Next.js 16 UI)   │     │  (FastAPI Backend)  │
 │   Static / Edge     │     │  asia-south1 Mumbai │
 └─────────────────────┘     └─────────────────────┘
                                        │
                                        ▼
                             Central Ingestion / WS
```

- **Frontend**: Hosted on **Firebase Hosting** / **Firebase App Hosting** with global edge CDN caching and automatic SSL.
- **Backend**: Hosted on **Google Cloud Run (asia-south1 Mumbai)** for ultra-low latency access to Indian exchange feeds, automatic scaling to zero when idle, and high-concurrency WebSocket support.
- **Unified Domain**: `firebase.json` automatically proxies `/api/**` and `/ws/**` traffic directly to Cloud Run, eliminating CORS issues and keeping cookies/JWTs secure.

---

## 📋 Prerequisites

1. **Firebase Account**: [https://firebase.google.com](https://firebase.google.com) (Create a new project, e.g. `droid-fno-platform`).
2. **Install Firebase CLI**:
   ```bash
   npm install -g firebase-tools
   ```
3. **Login to Firebase**:
   ```bash
   firebase login
   ```
4. **Google Cloud SDK (`gcloud`)** *(Optional for local Docker builds, or use Google Cloud Console)*:
   [https://cloud.google.com/sdk](https://cloud.google.com/sdk)

---

## ⚡ 1-Click Deployment Steps

### Step 1: Link Your Firebase Project
In the root directory `e:\Droid`:
```bash
firebase use --add
```
Select your Firebase project ID (or edit [`.firebaserc`](file:///e:/Droid/.firebaserc) with your project ID).

---

### Step 2: Deploy Backend to Google Cloud Run (Mumbai Region)

Build and deploy the containerized FastAPI backend to Cloud Run in `asia-south1` (Mumbai):

```bash
cd e:\Droid\backend

# Build and submit container via Cloud Build
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/droid-backend

# Deploy to Cloud Run with WebSocket & auto-scaling support
gcloud run deploy droid-backend \
  --image gcr.io/YOUR_PROJECT_ID/droid-backend \
  --platform managed \
  --region asia-south1 \
  --allow-unauthenticated \
  --min-instances 0 \
  --max-instances 2 \
  --memory 512Mi \
  --cpu 1 \
  --set-env-vars="APP_ENV=production,APP_MODE=production,MARKET_DATA_PROVIDER=mock"
```

> **Note**: Cloud Run automatically enables WebSocket session streaming and HTTPS termination.

---

### Step 3: Build & Deploy Frontend to Firebase Hosting

In the root directory `e:\Droid`:

```bash
# 1. Build optimized frontend production build
cd frontend
npm run build
cd ..

# 2. Deploy to Firebase Hosting
firebase deploy --only hosting
```

Your web application is now live at:
`https://YOUR_PROJECT_ID.web.app` or `https://YOUR_PROJECT_ID.firebaseapp.com`

---

## 🔒 Production Environment Variables (Optional)

Configure your production secrets in the Google Cloud Console or via CLI:

| Variable | Description | Recommended Value |
|---|---|---|
| `APP_ENV` | Environment mode | `production` |
| `MARKET_DATA_PROVIDER` | Ingestion provider | `mock` / `fyers` / `upstox` |
| `GEMINI_API_KEY` | Google Gemini AI Key | *(Your AI Studio Key)* |
| `SUPABASE_JWT_SECRET` | Supabase Auth validation | *(Optional JWT secret)* |

---

## 🌐 Custom Domain & Free SSL

1. Open **Firebase Console** $\rightarrow$ **Hosting** $\rightarrow$ **Add Custom Domain**.
2. Enter your domain (e.g. `fno.yourdomain.com`).
3. Add the provided DNS `A` or `CNAME` records to your domain provider (Cloudflare, GoDaddy, Namecheap).
4. Firebase will automatically issue a free Let's Encrypt SSL certificate within a few minutes.
