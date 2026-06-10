# Document Generator

Flask web app that generates project documents (Approach, Impact, UAT, Release Deployment, System Test Cases) from a BRS upload.

## Run locally

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000

## Deploy with GitHub + Render

GitHub stores your code; [Render](https://render.com) hosts the live Flask app and redeploys on every push.

### 1. Push to GitHub

```bash
cd Document-maker-main
git init
git add .
git commit -m "Initial commit: document generator web app"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/document-generator.git
git push -u origin main
```

Create the empty repo first on GitHub: **New repository** → name it `document-generator` → do not add a README.

### 2. Deploy on Render

1. Sign in at [render.com](https://render.com) with your GitHub account.
2. **New** → **Blueprint** (or **Web Service**).
3. Connect the `document-generator` repository.
4. Render reads `render.yaml` automatically. Confirm and create the service.
5. After the build finishes, open the URL Render gives you (e.g. `https://document-generator.onrender.com`).

### Environment variables (optional)

| Variable | Purpose |
|----------|---------|
| `FLASK_SECRET_KEY` | Session/flash message signing (auto-generated on Render) |
| `FLASK_DEBUG` | Set to `0` in production |

### Notes

- Free Render services sleep after ~15 minutes of inactivity; the first visit may take ~30 seconds to wake up.
- Uploaded files are stored temporarily on the server and are not persisted across redeploys.
