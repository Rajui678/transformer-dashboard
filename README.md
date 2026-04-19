# ⚡ Transformer Testing Dashboard

A free, open-source Streamlit app for recording, saving and analysing
power transformer field test results — IR & PI, MBT, Tan Delta, WR.

## Features

- 📊 IR & PI Test with live PI calculator
- 🔀 Magnetic Balance Test with phase imbalance checker
- 📐 Tan Delta & Capacitance (HV and LV sides)
- 🔩 Winding Resistance (all taps)
- 📄 PDF report generation (in-browser download)
- 📈 Historical trends over multiple test dates
- 🗂 Full report history — save, load, delete

## Quick Start (local, no database setup needed)

```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git
cd YOUR_REPO
pip install -r requirements.txt
streamlit run app.py
```

Data is saved to `transformer_reports.db` (SQLite) in the project folder.

## Deploy on Streamlit Cloud (free, persistent storage via Supabase)

### Step 1 — Push to GitHub
```bash
git init && git add . && git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

### Step 2 — Create a free Supabase project
1. Go to [supabase.com](https://supabase.com) → New project
2. Project Settings → Database → copy the **Connection string (URI)**

### Step 3 — Deploy on Streamlit Cloud
1. Go to [share.streamlit.io](https://share.streamlit.io) → New app
2. Select your GitHub repo, branch `main`, file `app.py`
3. **App Settings → Secrets** — paste:
   ```toml
   SUPABASE_DB_URL = "postgresql://postgres:[PASSWORD]@db.[REF].supabase.co:5432/postgres"
   ```
4. Click **Deploy**

### Local development with Supabase
```bash
cp .env.example .env
# Edit .env and set SUPABASE_DB_URL
streamlit run app.py
```

## Security

| What | How |
|---|---|
| No hardcoded credentials | All secrets via `.env` or `st.secrets` |
| SQL injection prevention | Parameterised queries throughout |
| Input sanitisation | All user input stripped before DB write |
| Secrets excluded from git | `.gitignore` covers `.env` and `secrets.toml` |
| TLS-only DB connection | `sslmode=require` for all PostgreSQL connections |
| XSRF protection | Enabled in `config.toml` |

## Project Structure

```
your-repo/
├── app.py                          # Streamlit UI
├── db.py                           # DB layer (SQLite ↔ Supabase auto-switch)
├── requirements.txt
├── .env.example                    # Template — copy to .env for local dev
├── .gitignore
├── README.md
└── .streamlit/
    ├── config.toml                 # Theme + server settings
    └── secrets.toml.example        # Template — real file excluded by .gitignore
```
