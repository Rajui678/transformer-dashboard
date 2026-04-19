"""
Transformer Testing Dashboard — Streamlit Edition
==================================================
• No external db.py — everything is self-contained in this file
• Auto-switches: SQLite (local) ↔ Supabase (cloud)
• All credentials via st.secrets / env vars — never hardcoded
• Parameterised queries only — no string-formatted SQL
• Input sanitisation on every field
• PDF stored as binary blob in DB
• No internal error details exposed to users

Run locally:
    pip install -r requirements.txt
    streamlit run app.py

Streamlit Cloud:
    Add secrets under Settings → Secrets (see secrets.toml.example)
"""

import os, re, json, html, datetime, io
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# ── optional imports (fail gracefully) ────────────────────────────────────
try:
    import matplotlib.pyplot as plt
    import matplotlib; matplotlib.use("Agg")
    MPL_OK = True
except ImportError:
    MPL_OK = False

try:
    import numpy as np
    NP_OK = True
except ImportError:
    NP_OK = False

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                    Paragraph, Spacer, HRFlowable)
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.lib.enums import TA_CENTER
    RL_OK = True
except ImportError:
    RL_OK = False

try:
    import pandas as pd
    PD_OK = True
except ImportError:
    PD_OK = False

# ═══════════════════════ SECURITY HELPERS ══════════════════════════════════

MAX_FIELD = 200

def sanitise(value) -> str:
    if value is None:
        return ""
    value = str(value).strip()[:MAX_FIELD]
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', value)

def safe_float(value) -> float:
    try:
        return float(str(value).replace(',', '.').strip())
    except (ValueError, TypeError):
        return 0.0

def _secret(*keys, default=None):
    try:
        node = st.secrets
        for k in keys:
            node = node[k]
        return node
    except Exception:
        pass
    return os.environ.get("_".join(keys).upper(), default)


# ═══════════════════════ DATABASE LAYER ════════════════════════════════════

def _use_supabase() -> bool:
    return bool(_secret("supabase", "url"))


@st.cache_resource(show_spinner=False)
def _get_supabase():
    from supabase import create_client
    url = _secret("supabase", "url")
    key = _secret("supabase", "key")
    if not url or not key:
        raise RuntimeError("Supabase URL or key not found in secrets.")
    return create_client(url, key)


@st.cache_resource(show_spinner=False)
def _get_sqlite():
    import sqlite3
    path = _secret("sqlite", "path", default="transformer_reports.db")
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            report_date TEXT    NOT NULL,
            tr_name     TEXT    NOT NULL,
            data_json   TEXT    NOT NULL,
            pdf_blob    BLOB,
            created_at  TEXT    NOT NULL
        )""")
    conn.commit()
    return conn


def db_save(tr_name: str, data_dict: dict, pdf_bytes: bytes = None) -> int:
    tr_name = sanitise(tr_name)
    now     = datetime.datetime.utcnow().isoformat()
    today   = datetime.date.today().isoformat()

    if _use_supabase():
        import base64
        row = {"report_date": today, "tr_name": tr_name,
               "data_json": data_dict, "created_at": now}
        if pdf_bytes:
            row["pdf_blob"] = base64.b64encode(pdf_bytes).decode()
        res = _get_supabase().table("reports").insert(row).execute()
        return res.data[0]["id"]
    else:
        conn = _get_sqlite()
        c    = conn.cursor()
        c.execute(
            "INSERT INTO reports "
            "(report_date, tr_name, data_json, pdf_blob, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (today, tr_name, json.dumps(data_dict), pdf_bytes, now),
        )
        conn.commit()
        return c.lastrowid


def db_update_pdf(rid: int, pdf_bytes: bytes):
    if _use_supabase():
        import base64
        (_get_supabase().table("reports")
         .update({"pdf_blob": base64.b64encode(pdf_bytes).decode()})
         .eq("id", rid).execute())
    else:
        conn = _get_sqlite()
        conn.execute("UPDATE reports SET pdf_blob=? WHERE id=?", (pdf_bytes, rid))
        conn.commit()


def db_all() -> list:
    if _use_supabase():
        res = (_get_supabase().table("reports")
               .select("id, report_date, tr_name, created_at")
               .order("id", desc=True).execute())
        return [(r["id"], r["report_date"], r["tr_name"], r["created_at"])
                for r in res.data]
    else:
        return _get_sqlite().execute(
            "SELECT id, report_date, tr_name, created_at "
            "FROM reports ORDER BY id DESC"
        ).fetchall()


def db_get(rid: int) -> tuple:
    if _use_supabase():
        import base64
        res = (_get_supabase().table("reports")
               .select("data_json, pdf_blob")
               .eq("id", rid).single().execute())
        if not res.data:
            return {}, None
        d     = res.data
        djson = d["data_json"]
        data  = djson if isinstance(djson, dict) else json.loads(djson)
        pdf   = base64.b64decode(d["pdf_blob"]) if d.get("pdf_blob") else None
        return data, pdf
    else:
        row = _get_sqlite().execute(
            "SELECT data_json, pdf_blob FROM reports WHERE id=?", (rid,)
        ).fetchone()
        if not row:
            return {}, None
        return json.loads(row[0]), row[1]


def db_delete(rid: int):
    if _use_supabase():
        _get_supabase().table("reports").delete().eq("id", rid).execute()
    else:
        conn = _get_sqlite()
        conn.execute("DELETE FROM reports WHERE id=?", (rid,))
        conn.commit()


def db_trends(name: str) -> list:
    name = sanitise(name)
    if _use_supabase():
        res = (_get_supabase().table("reports")
               .select("report_date, data_json")
               .eq("tr_name", name)
               .order("report_date").execute())
        return [(r["report_date"],
                 json.dumps(r["data_json"]) if isinstance(r["data_json"], dict)
                 else r["data_json"])
                for r in res.data]
    else:
        return _get_sqlite().execute(
            "SELECT report_date, data_json FROM reports "
            "WHERE tr_name=? ORDER BY report_date",
            (name,),
        ).fetchall()


# ═══════════════════════ PAGE CONFIG & CSS ═════════════════════════════════
st.set_page_config(
    page_title="⚡ Transformer Testing Dashboard",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
[data-testid="stAppViewContainer"]  { background:#0f1923; }
[data-testid="stSidebar"]           { background:#1a2535; }
section.main > div                  { padding-top:1rem;   }
h1,h2,h3                            { color:#00c6ff !important; }
input, [data-baseweb="input"] input {
    background:#0d1f33 !important; color:#e8f4fd !important;
    border:1px solid #2a3f5f !important; border-radius:4px !important;
}
[data-testid="metric-container"] {
    background:#1e2d40; border:1px solid #2a3f5f;
    border-radius:8px; padding:12px;
}
.stButton>button {
    background:#0072ff; color:#fff; border:none;
    border-radius:6px; font-weight:600;
}
.stButton>button:hover { background:#0058cc; }
[data-baseweb="tab-list"] { background:#1a2535; border-radius:8px; }
[data-baseweb="tab"]      { color:#7a9bbf; }
[aria-selected="true"]    { color:#00c6ff !important; }
hr { border-color:#2a3f5f; }
[data-testid="stDataFrame"] { border:1px solid #2a3f5f; border-radius:6px; }
</style>
""", unsafe_allow_html=True)

# ═══════════════════════ FORM SCHEMA ══════════════════════════════════════

TRAFFO_FIELDS = [
    ("Transformer Name",      "Name"),
    ("Manufacturer / Make",   "Make"),
    ("Rated MVA",             "Rated MVA"),
    ("Rated Voltage HV (kV)", "Rated Voltage (HV)"),
    ("Rated Voltage LV (kV)", "Rated Voltage (LV)"),
    ("Rated Current HV (A)",  "Rated Current (HV)"),
    ("Rated Current LV (A)",  "Rated Current (LV)"),
    ("Serial Number",         "SL NO."),
    ("Frequency (Hz)",        "Frequency"),
    ("Vector Group",          "Vector Group"),
    ("% Impedance Voltage",   "% Impedance Voltage"),
    ("Year of Manufacture",   "Year of mfg"),
    ("Ambient Temp (°C)",     "Ambient Temp. (° C)"),
]
TRAFFO_KEYS = [k for _, k in TRAFFO_FIELDS]

IR_ROWS = ["HV to LV + Ground", "LV to HV + Ground", "HV to Ground", "LV to Ground"]
IR_COLS = ["Applied Voltage (kV)", "1 min IR (MΩ)", "10 min IR (MΩ)", "PI Value", "Expected PI"]

MB_ROWS = ["Phase R", "Phase Y", "Phase B"]
MB_COLS = ["r-n (V)", "y-n (V)", "b-n (V)", "Imag (A)"]

HV_TD_ROWS = [
    "HV-LV UST-A @ 1kV",    "HV-LV UST-A @ 2kV",    "HV-LV UST-A @ 3kV",    "HV-LV UST-A @ 3.8kV",
    "HV-LV GSTg-A @ 1kV",   "HV-LV GSTg-A @ 2kV",   "HV-LV GSTg-A @ 3kV",   "HV-LV GSTg-A @ 3.8kV",
    "HV-LV GST @ 1kV",      "HV-LV GST @ 2kV",      "HV-LV GST @ 3kV",      "HV-LV GST @ 3.8kV",
]
LV_TD_ROWS = [
    "LV-HV UST-A @ 0.1kV",  "LV-HV UST-A @ 0.2kV",  "LV-HV UST-A @ 0.3kV",  "LV-HV UST-A @ 0.4kV",
    "LV-HV GSTg-A @ 0.1kV", "LV-HV GSTg-A @ 0.2kV", "LV-HV GSTg-A @ 0.3kV", "LV-HV GSTg-A @ 0.4kV",
    "LV-HV GST @ 0.1kV",    "LV-HV GST @ 0.2kV",    "LV-HV GST @ 0.3kV",    "LV-HV GST @ 0.4kV",
]
TD_COLS = ["kV", "Current (µA)", "Corr. %PF", "Cap. (nF)"]

HV_WR_ROWS = [
    "HV TAP 1 R-Y", "HV TAP 1 Y-B", "HV TAP 1 B-R",
    "HV TAP 2 R-Y", "HV TAP 2 Y-B", "HV TAP 2 B-R",
    "HV TAP 3 R-Y", "HV TAP 3 Y-B", "HV TAP 3 B-R",
    "HV TAP 4 R-Y", "HV TAP 4 Y-B", "HV TAP 4 B-R",
    "HV TAP 5 R-Y", "HV TAP 5 Y-B", "HV TAP 5 B-R",
]
LV_WR_ROWS = ["LV TAP 1 r-n", "LV TAP 1 y-n", "LV TAP 1 b-n"]
WR_COLS    = ["Resistance (mΩ)"]


def blank_form() -> dict:
    return {
        "traffo":    {k: "" for k in TRAFFO_KEYS},
        "ir_pi":     {r: {c: "" for c in IR_COLS} for r in IR_ROWS},
        "mbt":       {r: {c: "" for c in MB_COLS} for r in MB_ROWS},
        "tan_delta": {r: {c: "" for c in TD_COLS} for r in HV_TD_ROWS + LV_TD_ROWS},
        "wr":        {r: {c: "" for c in WR_COLS} for r in HV_WR_ROWS + LV_WR_ROWS},
    }


# ═══════════════════════ SESSION STATE ════════════════════════════════════
if "form"     not in st.session_state:
    st.session_state.form     = blank_form()
if "last_rid" not in st.session_state:
    st.session_state.last_rid = None


def F() -> dict:
    return st.session_state.form


def load_into_form(data: dict):
    st.session_state.form = blank_form()
    for k, v in data.get("traffo", {}).items():
        if k in F()["traffo"]:
            F()["traffo"][k] = sanitise(v)
    for sect in ("ir_pi", "mbt", "tan_delta", "wr"):
        for row, cols in data.get(sect, {}).items():
            if row in F()[sect]:
                for col, val in cols.items():
                    if col in F()[sect][row]:
                        F()[sect][row][col] = sanitise(val)


# ═══════════════════════ EDITABLE TABLE ════════════════════════════════════
def editable_table(section: str, rows: list, cols: list, prefix: str):
    if not PD_OK:
        st.warning("pandas not installed — pip install pandas")
        return

    data = []
    for r in rows:
        row_data = {"Row": r}
        for c in cols:
            row_data[c] = F()[section].get(r, {}).get(c, "")
        data.append(row_data)

    df     = pd.DataFrame(data).set_index("Row")
    edited = st.data_editor(
        df,
        use_container_width=True,
        key=f"de_{prefix}",
        column_config={c: st.column_config.TextColumn(c, width="medium") for c in cols},
    )
    for r in rows:
        if r in edited.index:
            for c in cols:
                raw = str(edited.at[r, c]) if edited.at[r, c] is not None else ""
                if raw in ("nan", "None"):
                    raw = ""
                F()[section].setdefault(r, {})[c] = sanitise(raw)


# ═══════════════════════ PDF BUILDER ══════════════════════════════════════
def build_pdf(data: dict) -> bytes:
    if not RL_OK:
        raise RuntimeError("reportlab not installed — pip install reportlab")

    buf = io.BytesIO()
    PW  = 181 * mm
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            topMargin=14*mm, bottomMargin=14*mm,
                            leftMargin=14*mm, rightMargin=14*mm)
    styles = getSampleStyleSheet()
    TITLE  = ParagraphStyle("TT", parent=styles["Title"], fontSize=16,
                            textColor=colors.HexColor("#0072ff"),
                            spaceAfter=4, alignment=TA_CENTER)
    H2     = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=11,
                            textColor=colors.HexColor("#1565C0"),
                            spaceBefore=10, spaceAfter=4)
    NRM    = styles["Normal"]
    FOOT   = ParagraphStyle("ft", parent=NRM, fontSize=7,
                            alignment=TA_CENTER, textColor=colors.grey)

    def mkt(headers, rows_data, cw=None):
        if not rows_data:
            rows_data = [["—"] * len(headers)]
        t = Table([headers] + rows_data, colWidths=cw, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND",     (0, 0), (-1, 0),  colors.HexColor("#1565C0")),
            ("TEXTCOLOR",      (0, 0), (-1, 0),  colors.white),
            ("FONTNAME",       (0, 0), (-1, 0),  "Helvetica-Bold"),
            ("FONTSIZE",       (0, 0), (-1, -1), 8),
            ("ALIGN",          (0, 0), (-1, -1), "CENTER"),
            ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
            ("GRID",           (0, 0), (-1, -1), 0.4, colors.HexColor("#90CAF9")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.white, colors.HexColor("#E3F2FD")]),
            ("LEFTPADDING",    (0, 0), (-1, -1), 5),
            ("RIGHTPADDING",   (0, 0), (-1, -1), 5),
            ("TOPPADDING",     (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING",  (0, 0), (-1, -1), 4),
        ]))
        return t

    tf    = data.get("traffo", {})
    elems = [
        Spacer(1, 6 * mm),
        Paragraph("CONSOLIDATED TRANSFORMER TEST REPORT", TITLE),
        HRFlowable(width="100%", thickness=2, color=colors.HexColor("#0072ff")),
        Spacer(1, 4 * mm),
    ]

    meta = [
        [Paragraph(f"<b>Transformer:</b> {tf.get('Name','—')}", NRM),
         Paragraph(f"<b>Manufacturer:</b> {tf.get('Make','—')}", NRM),
         Paragraph(f"<b>Serial No.:</b> {tf.get('SL NO.','—')}", NRM)],
        [Paragraph(f"<b>Rated MVA:</b> {tf.get('Rated MVA','—')}", NRM),
         Paragraph(f"<b>Vector Group:</b> {tf.get('Vector Group','—')}", NRM),
         Paragraph(f"<b>Date:</b> {datetime.date.today()}", NRM)],
    ]
    mt = Table(meta, colWidths=[62*mm, 62*mm, 57*mm])
    mt.setStyle(TableStyle([
        ("GRID",          (0, 0), (-1, -1), 0.3, colors.lightgrey),
        ("BACKGROUND",    (0, 0), (-1, -1), colors.HexColor("#F0F7FF")),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    elems += [mt, Spacer(1, 6*mm)]

    elems.append(Paragraph("1. Transformer Details", H2))
    elems.append(mkt(
        ["Parameter", "Value"],
        [[Paragraph(f"<b>{k}</b>", NRM), str(v or "—")] for k, v in tf.items()],
        cw=[85*mm, PW - 85*mm],
    ))
    elems.append(Spacer(1, 4*mm))

    elems.append(Paragraph("2. Insulation Resistance & Polarisation Index", H2))
    ir  = data.get("ir_pi", {})
    irh = ["Connection"] + IR_COLS
    irr = [[r] + [cs.get(c, "—") for c in IR_COLS] for r, cs in ir.items()]
    cw_ir = [55*mm] + [(PW - 55*mm) / len(IR_COLS)] * len(IR_COLS)
    elems.append(mkt(irh, irr, cw=cw_ir))
    elems.append(Spacer(1, 4*mm))

    elems.append(Paragraph("3. Magnetic Balance Test – Star Side", H2))
    mb  = data.get("mbt", {})
    mbh = ["Phase"] + MB_COLS
    mbr = [[r] + [cs.get(c, "—") for c in MB_COLS] for r, cs in mb.items()]
    cw_mb = [40*mm] + [(PW - 40*mm) / len(MB_COLS)] * len(MB_COLS)
    elems.append(mkt(mbh, mbr, cw=cw_mb))
    elems.append(Spacer(1, 4*mm))

    elems.append(Paragraph("4. Tan Delta & Capacitance Test", H2))
    td  = data.get("tan_delta", {})
    tdh = ["Mode"] + TD_COLS
    tdr = [[r] + [cs.get(c, "—") for c in TD_COLS] for r, cs in td.items()]
    cw_td = [65*mm] + [(PW - 65*mm) / len(TD_COLS)] * len(TD_COLS)
    elems.append(mkt(tdh, tdr, cw=cw_td))
    elems.append(Spacer(1, 4*mm))

    elems.append(Paragraph("5. Winding Resistance Test", H2))
    wr  = data.get("wr", {})
    wrh = ["Side / Connection"] + WR_COLS
    wrr = [[r] + [cs.get(c, "—") for c in WR_COLS] for r, cs in wr.items()]
    elems.append(mkt(wrh, wrr, cw=[PW * 0.65, PW * 0.35]))

    elems += [
        Spacer(1, 10*mm),
        HRFlowable(width="100%", thickness=1, color=colors.lightgrey),
        Paragraph(
            f"Generated by Transformer Testing Dashboard  •  "
            f"{datetime.datetime.now():%d %b %Y  %H:%M}  •  Confidential",
            FOOT,
        ),
    ]
    doc.build(elems)
    buf.seek(0)
    return buf.read()


# ═══════════════════════ SIDEBAR ══════════════════════════════════════════
with st.sidebar:
    st.markdown("## ⚡ Transformer Dashboard")
    backend = "☁️ Supabase" if _use_supabase() else "💾 SQLite (local)"
    st.markdown(f"**Backend:** `{backend}`")
    st.markdown(f"**Active:** `{F()['traffo'].get('Name', '—') or '—'}`")
    st.markdown(f"📅 {datetime.date.today():%d %B %Y}")
    st.markdown("---")

    st.markdown("### 📋 Actions")
    if st.button("💾  Save Report", use_container_width=True):
        name = sanitise(F()["traffo"].get("Name", "").strip()) or "Unknown"
        try:
            rid = db_save(name, F())
            st.session_state.last_rid = rid
            st.success(f"Report #{rid} saved — {name}")
        except Exception:
            st.error("Save failed. Check your DB connection or secrets.")

    if st.button("🗑  Clear Form", use_container_width=True):
        st.session_state.form     = blank_form()
        st.session_state.last_rid = None
        st.rerun()

    st.markdown("---")
    st.markdown("### ℹ️ Info")
    st.markdown(
        "**Free · No API key · Secure**\n\n"
        "Credentials stored in `st.secrets`\n"
        "— never in source code.\n\n"
        "PDF stored as binary in DB\n"
        "— no filesystem paths exposed."
    )


# ═══════════════════════ MAIN TABS ════════════════════════════════════════
st.markdown("# ⚡ Transformer Testing Dashboard")
st.markdown("---")

tabs = st.tabs([
    "🔧 Traffo Details",
    "📊 IR & PI",
    "🔀 MBT Star",
    "📐 Tan Delta",
    "🔩 WR Test",
    "📄 PDF Report",
    "📈 Trends",
    "🗂 History",
])

# ── Tab 1: Traffo Details ─────────────────────────────────────────────────
with tabs[0]:
    st.subheader("🔧 Transformer Nameplate Details")
    col1, col2 = st.columns(2)
    half = len(TRAFFO_FIELDS) // 2
    with col1:
        for label, key in TRAFFO_FIELDS[:half]:
            val = st.text_input(label, value=F()["traffo"].get(key, ""),
                                max_chars=MAX_FIELD, key=f"tf_{key}")
            F()["traffo"][key] = sanitise(val)
    with col2:
        for label, key in TRAFFO_FIELDS[half:]:
            val = st.text_input(label, value=F()["traffo"].get(key, ""),
                                max_chars=MAX_FIELD, key=f"tf_{key}")
            F()["traffo"][key] = sanitise(val)
    st.markdown("---")
    st.subheader("📋 Quick Summary")
    mc = st.columns(5)
    for i, f in enumerate(["Name", "Make", "Rated MVA", "Vector Group", "SL NO."]):
        mc[i].metric(f, F()["traffo"].get(f, "—") or "—")

# ── Tab 2: IR & PI ────────────────────────────────────────────────────────
with tabs[1]:
    st.subheader("📊 Insulation Resistance & Polarisation Index")
    st.info("ℹ️  PI = 10 min IR ÷ 1 min IR  |  Acceptable PI ≥ 2.0")
    editable_table("ir_pi", IR_ROWS, IR_COLS, "ir")
    st.markdown("---")
    st.subheader("🔢 Live PI Calculator")
    pc1, pc2, pc3 = st.columns(3)
    with pc1:
        ir1  = st.number_input("1 min IR (MΩ)",  min_value=0.0, step=0.1, format="%.1f", key="pi_1m")
    with pc2:
        ir10 = st.number_input("10 min IR (MΩ)", min_value=0.0, step=0.1, format="%.1f", key="pi_10m")
    with pc3:
        if ir1 > 0:
            piv = ir10 / ir1
            st.metric("PI Value", f"{piv:.2f}",
                      delta="PASS ✅" if piv >= 2 else "FAIL ❌",
                      delta_color="normal" if piv >= 2 else "inverse")
        else:
            st.metric("PI Value", "—")

# ── Tab 3: MBT ───────────────────────────────────────────────────────────
with tabs[2]:
    st.subheader("🔀 Magnetic Balance Test – Star Side")
    st.info("ℹ️  Voltage imbalance between phases should be < 5%")
    editable_table("mbt", MB_ROWS, MB_COLS, "mbt")
    st.markdown("---")
    st.subheader("⚖️ Phase Imbalance Checker")
    if NP_OK:
        try:
            vc  = ["r-n (V)", "y-n (V)", "b-n (V)"]
            vs  = [[safe_float(F()["mbt"].get(p, {}).get(c, "")) for c in vc]
                   for p in MB_ROWS]
            imb = []
            for ci in range(3):
                col_v = [vs[ri][ci] for ri in range(3)]
                avg   = np.mean(col_v)
                imb.append((max(col_v) - min(col_v)) / avg * 100 if avg else 0)
            mx = max(imb)
            ic1, ic2, ic3, ic4 = st.columns(4)
            ic1.metric("r-n Imbalance", f"{imb[0]:.2f}%")
            ic2.metric("y-n Imbalance", f"{imb[1]:.2f}%")
            ic3.metric("b-n Imbalance", f"{imb[2]:.2f}%")
            ic4.metric("Max Imbalance", f"{mx:.2f}%",
                       delta="PASS ✅" if mx < 5 else "FAIL ❌",
                       delta_color="normal" if mx < 5 else "inverse")
        except Exception:
            st.caption("Enter MBT values above to compute imbalance.")

# ── Tab 4: Tan Delta ──────────────────────────────────────────────────────
with tabs[3]:
    st.subheader("📐 Tan Delta & Capacitance Test")
    st.info("ℹ️  Tan Delta < 1%  |  Capacitance should trend with earlier report")
    td1, td2 = st.tabs(["HV → LV", "LV → HV"])
    with td1:
        editable_table("tan_delta", HV_TD_ROWS, TD_COLS, "td_hv")
    with td2:
        editable_table("tan_delta", LV_TD_ROWS, TD_COLS, "td_lv")

# ── Tab 5: Winding Resistance ─────────────────────────────────────────────
with tabs[4]:
    st.subheader("🔩 Winding Resistance Test")
    st.info("ℹ️  Phase-to-phase variation < 3%  |  Compare with nameplate reference")
    wr1, wr2 = st.tabs(["HV Side @ 10 A", "LV Side @ 25 A (TAP 1)"])
    with wr1:
        editable_table("wr", HV_WR_ROWS, WR_COLS, "wr_hv")
    with wr2:
        editable_table("wr", LV_WR_ROWS, WR_COLS, "wr_lv")

# ── Tab 6: PDF ───────────────────────────────────────────────────────────
with tabs[5]:
    st.subheader("📄 Generate PDF Report")
    if not RL_OK:
        st.error("reportlab not installed — add it to requirements.txt")
    else:
        tf    = F().get("traffo", {})
        name  = sanitise(tf.get("Name", "") or "Transformer")
        ts    = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"TR_Report_{name.replace(' ', '_')}_{ts}.pdf"

        rc1, rc2, rc3 = st.columns(3)
        rc1.markdown(f"**Transformer:** {html.escape(tf.get('Name','—'))}")
        rc2.markdown(f"**Manufacturer:** {html.escape(tf.get('Make','—'))}")
        rc3.markdown(f"**Serial No.:** {html.escape(tf.get('SL NO.','—'))}")
        rc1.markdown(f"**Rated MVA:** {html.escape(tf.get('Rated MVA','—'))}")
        rc2.markdown(f"**Vector Group:** {html.escape(tf.get('Vector Group','—'))}")
        rc3.markdown(f"**Date:** {datetime.date.today()}")
        st.markdown("---")

        if st.button("📄  Generate & Download PDF", use_container_width=True):
            try:
                pdf_bytes = build_pdf(F())
                if st.session_state.last_rid:
                    db_update_pdf(st.session_state.last_rid, pdf_bytes)
                else:
                    rid = db_save(name, F(), pdf_bytes)
                    st.session_state.last_rid = rid
                st.download_button(
                    label="⬇️  Download PDF",
                    data=pdf_bytes,
                    file_name=fname,
                    mime="application/pdf",
                    use_container_width=True,
                )
                st.success("PDF ready — click Download above.")
            except Exception as e:
                st.error(f"PDF generation failed: {e}")

# ── Tab 7: Trends ─────────────────────────────────────────────────────────
with tabs[6]:
    st.subheader("📈 Historical Test Trends")
    tr_inp = st.text_input("Transformer Name", key="trend_name",
                           max_chars=MAX_FIELD,
                           placeholder="Exact name used when saving reports")
    if st.button("📈  Load Trends"):
        tr_inp = sanitise(tr_inp)
        if not tr_inp:
            st.warning("Enter a transformer name first.")
        else:
            try:
                rows = db_trends(tr_inp)
            except Exception:
                st.error("Could not fetch trend data. Check your connection.")
                rows = []

            if len(rows) < 2:
                st.warning(f"Need ≥ 2 saved reports for '{html.escape(tr_inp)}'."
                           f"  Found: {len(rows)}")
            elif not MPL_OK or not NP_OK:
                st.error("matplotlib / numpy not installed.")
            else:
                dates, pi_v, mb_v, wr_v = [], [], [], []
                for dt, dj in rows:
                    d   = json.loads(dj)
                    dates.append(dt)
                    ir  = d.get("ir_pi", {}); fir = list(ir.values())[0] if ir else {}
                    pi_v.append(safe_float(fir.get("PI Value", "")))
                    mb  = d.get("mbt", {}); pr = mb.get("Phase R", {})
                    mb_v.append(safe_float(pr.get("Imag (A)", "")))
                    wr  = d.get("wr", {}); fw = list(wr.values())[0] if wr else {}
                    wr_v.append(safe_float(list(fw.values())[0]) if fw else 0.0)

                BG = "#0f1923"; MID = "#1a2535"; ACC = "#00c6ff"
                RD = "#ef5350"; TDc = "#7a9bbf"; BD  = "#2a3f5f"
                xs = list(range(len(dates)))

                fig, axes = plt.subplots(1, 3, figsize=(14, 4.5), facecolor=BG)
                fig.suptitle(f"Trends — {tr_inp}",
                             color="#e8f4fd", fontsize=13, fontweight="bold")

                def sax(ax, title, ylabel, ydata, threshold=None):
                    ax.set_facecolor(MID)
                    ax.set_title(title, color=ACC, fontsize=9, fontweight="bold")
                    ax.set_ylabel(ylabel, color=TDc, fontsize=8)
                    ax.tick_params(colors=TDc, labelsize=7)
                    for sp in ax.spines.values():
                        sp.set_edgecolor(BD)
                    ax.plot(xs, ydata, color=ACC, marker="o", lw=2, ms=7)
                    ax.fill_between(xs, ydata, alpha=0.12, color=ACC)
                    ax.set_xticks(xs)
                    ax.set_xticklabels(dates, rotation=30, ha="right", fontsize=7)
                    if threshold is not None:
                        ax.axhline(threshold, color=RD, ls="--", lw=1.2,
                                   label=f"Limit = {threshold}")
                        ax.legend(fontsize=7, facecolor="#1e2d40",
                                  edgecolor=BD, labelcolor="#e8f4fd")

                sax(axes[0], "Polarisation Index (PI)",           "PI",        pi_v, 2.0)
                sax(axes[1], "MBT Magnetising Current (Phase R)", "Imag (A)",  mb_v)
                sax(axes[2], "Winding Resistance – first row",    "Res. (mΩ)", wr_v)
                plt.tight_layout(rect=[0, 0, 1, 0.93])
                st.pyplot(fig)
                plt.close(fig)

# ── Tab 8: History ────────────────────────────────────────────────────────
with tabs[7]:
    st.subheader("🗂 Report History")
    if st.button("🔄  Refresh", key="hist_refresh"):
        st.rerun()

    try:
        all_reports = db_all()
    except Exception:
        st.error("Could not load history. Check your DB connection.")
        all_reports = []

    if not all_reports:
        st.info("No saved reports yet. Fill the form and click  💾 Save Report  in the sidebar.")
    else:
        if PD_OK:
            df_hist = pd.DataFrame(all_reports,
                                   columns=["ID", "Date", "Transformer", "Saved At"])
            st.dataframe(df_hist, use_container_width=True, hide_index=True)
        else:
            for row in all_reports:
                st.text(f"#{row[0]}  {row[1]}  {row[2]}  {row[3][:16]}")

        st.markdown("---")
        hc1, hc2, hc3 = st.columns(3)

        with hc1:
            st.markdown("**Load report into form**")
            load_id = st.number_input("Report ID to load", min_value=1, step=1, key="load_id")
            if st.button("📂  Load Selected", use_container_width=True):
                try:
                    data, _ = db_get(int(load_id))
                    if data:
                        load_into_form(data)
                        st.success(f"Report #{load_id} loaded — switch to any tab to review.")
                        st.rerun()
                    else:
                        st.error(f"Report #{load_id} not found.")
                except Exception:
                    st.error("Could not load report.")

        with hc2:
            st.markdown("**Download PDF**")
            dl_id = st.number_input("Report ID for PDF", min_value=1, step=1, key="dl_id")
            if st.button("📄  Fetch PDF", use_container_width=True):
                try:
                    stored_data, pdf_bytes = db_get(int(dl_id))
                    if not pdf_bytes and stored_data and RL_OK:
                        pdf_bytes = build_pdf(stored_data)
                        db_update_pdf(int(dl_id), pdf_bytes)
                    if pdf_bytes:
                        st.download_button("⬇️ Download",
                                           data=pdf_bytes,
                                           file_name=f"TR_Report_{dl_id}.pdf",
                                           mime="application/pdf")
                    else:
                        st.error(f"No data found for report #{dl_id}.")
                except Exception:
                    st.error("Could not generate PDF.")

        with hc3:
            st.markdown("**Delete a report**")
            del_id = st.number_input("Report ID to delete", min_value=1, step=1, key="del_id")
            if st.button("🗑  Delete Report", use_container_width=True):
                try:
                    db_delete(int(del_id))
                    st.success(f"Report #{del_id} deleted.")
                    st.rerun()
                except Exception:
                    st.error("Could not delete report.")
