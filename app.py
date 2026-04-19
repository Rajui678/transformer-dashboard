"""
Transformer Testing Dashboard — Streamlit / Supabase Edition
Run locally  :  streamlit run app.py
Deploy       :  Push to GitHub → share.streamlit.io or Supabase
"""
import streamlit as st
import os, json, datetime, io
import matplotlib.pyplot as plt
import matplotlib; matplotlib.use("Agg")
import numpy as np
import pandas as pd

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass



from reportlab.lib.pagesizes import A4
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                Paragraph, Spacer, HRFlowable)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_CENTER

# ── Page config ──────────────────────────────────────────────────────────
st.set_page_config(page_title="⚡ Transformer Dashboard",
                   page_icon="⚡", layout="wide",
                   initial_sidebar_state="expanded")

st.markdown("""
<style>
[data-testid="stAppViewContainer"]{background:#0f1923}
[data-testid="stSidebar"]{background:#1a2535}
section.main>div{padding-top:1rem}
h1,h2,h3{color:#00c6ff!important}
input,textarea,[data-baseweb="input"] input{
  background:#0d1f33!important;color:#e8f4fd!important;
  border:1px solid #2a3f5f!important;border-radius:4px!important}
[data-testid="metric-container"]{
  background:#1e2d40;border:1px solid #2a3f5f;border-radius:8px;padding:12px}
.stButton>button{background:#0072ff;color:white;border:none;
  border-radius:6px;font-weight:600}
.stButton>button:hover{background:#0058cc}
[data-baseweb="tab-list"]{background:#1a2535;border-radius:8px}
[data-baseweb="tab"]{color:#7a9bbf}
[aria-selected="true"]{color:#00c6ff!important}
hr{border-color:#2a3f5f}
</style>
""", unsafe_allow_html=True)

# ── DB init ───────────────────────────────────────────────────────────────
try:
    db.init_db()
except Exception as e:
    st.error(f"Database connection failed:\n{e}")
    st.stop()

# ── Schema constants ──────────────────────────────────────────────────────
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
    ("Ambient Temp (deg C)",  "Ambient Temp. (° C)"),
]
TRAFFO_KEYS = [k for _,k in TRAFFO_FIELDS]

IR_ROWS = ["HV to LV + Ground","LV to HV + Ground","HV to Ground","LV to Ground"]
IR_COLS = ["Applied Voltage (kV)","1 min IR (MO)","10 min IR (MO)","PI Value","Expected PI"]

MB_ROWS = ["Phase R","Phase Y","Phase B"]
MB_COLS = ["r-n (V)","y-n (V)","b-n (V)","Imag (A)"]

HV_TD = ["HV-LV UST-A @ 1kV","HV-LV UST-A @ 2kV","HV-LV UST-A @ 3kV","HV-LV UST-A @ 3.8kV",
         "HV-LV GSTg-A @ 1kV","HV-LV GSTg-A @ 2kV","HV-LV GSTg-A @ 3kV","HV-LV GSTg-A @ 3.8kV",
         "HV-LV GST @ 1kV","HV-LV GST @ 2kV","HV-LV GST @ 3kV","HV-LV GST @ 3.8kV"]
LV_TD = ["LV-HV UST-A @ 0.1kV","LV-HV UST-A @ 0.2kV","LV-HV UST-A @ 0.3kV","LV-HV UST-A @ 0.4kV",
         "LV-HV GSTg-A @ 0.1kV","LV-HV GSTg-A @ 0.2kV","LV-HV GSTg-A @ 0.3kV","LV-HV GSTg-A @ 0.4kV",
         "LV-HV GST @ 0.1kV","LV-HV GST @ 0.2kV","LV-HV GST @ 0.3kV","LV-HV GST @ 0.4kV"]
TD_COLS = ["kV","Current (uA)","Corr. %PF","Cap. (nF)"]

HV_WR = ["HV TAP 1 R-Y","HV TAP 1 Y-B","HV TAP 1 B-R",
         "HV TAP 2 R-Y","HV TAP 2 Y-B","HV TAP 2 B-R",
         "HV TAP 3 R-Y","HV TAP 3 Y-B","HV TAP 3 B-R",
         "HV TAP 4 R-Y","HV TAP 4 Y-B","HV TAP 4 B-R",
         "HV TAP 5 R-Y","HV TAP 5 Y-B","HV TAP 5 B-R"]
LV_WR   = ["LV TAP 1 r-n","LV TAP 1 y-n","LV TAP 1 b-n"]
WR_COLS = ["Resistance (mO)"]

# ── Session state ─────────────────────────────────────────────────────────
def blank_form():
    return {
        "traffo":    {k:"" for k in TRAFFO_KEYS},
        "ir_pi":     {r:{c:"" for c in IR_COLS}  for r in IR_ROWS},
        "mbt":       {r:{c:"" for c in MB_COLS}  for r in MB_ROWS},
        "tan_delta": {r:{c:"" for c in TD_COLS}  for r in HV_TD+LV_TD},
        "wr":        {r:{c:"" for c in WR_COLS}  for r in HV_WR+LV_WR},
    }

if "form"     not in st.session_state: st.session_state.form     = blank_form()
if "last_rid" not in st.session_state: st.session_state.last_rid = None

def F(): return st.session_state.form

def load_into_form(data):
    st.session_state.form = blank_form()
    for k,v in data.get("traffo",{}).items():
        if k in F()["traffo"]: F()["traffo"][k]=v
    for sect in ["ir_pi","mbt","tan_delta","wr"]:
        for row,cols in data.get(sect,{}).items():
            if row in F()[sect]:
                for col,val in cols.items():
                    if col in F()[sect][row]: F()[sect][row][col]=val

# ── Editable table ────────────────────────────────────────────────────────
def editable_table(section, rows, cols, ukey):
    data = [{"Row":r,**{c:F()[section].get(r,{}).get(c,"") for c in cols}} for r in rows]
    df   = pd.DataFrame(data).set_index("Row")
    edited = st.data_editor(df, use_container_width=True, key=f"de_{ukey}",
                            column_config={c:st.column_config.TextColumn(c,width="medium") for c in cols})
    for r in rows:
        if r in edited.index:
            for c in cols:
                raw = edited.at[r,c]
                val = "" if (raw is None or str(raw) in ("nan","None")) else str(raw)
                F()[section].setdefault(r,{})[c] = db.sanitise(val)

# ── PDF builder ───────────────────────────────────────────────────────────
def build_pdf(data):
    buf = io.BytesIO()
    PW  = 181*mm
    doc = SimpleDocTemplate(buf,pagesize=A4,
                            topMargin=14*mm,bottomMargin=14*mm,
                            leftMargin=14*mm,rightMargin=14*mm)
    sty   = getSampleStyleSheet()
    TITLE = ParagraphStyle("TT",parent=sty["Title"],fontSize=16,
                           textColor=colors.HexColor("#0072ff"),
                           spaceAfter=4,alignment=TA_CENTER)
    H2    = ParagraphStyle("H2",parent=sty["Heading2"],fontSize=11,
                           textColor=colors.HexColor("#1565C0"),
                           spaceBefore=10,spaceAfter=4)
    NRM   = sty["Normal"]
    FOOT  = ParagraphStyle("ft",parent=NRM,fontSize=7,
                           alignment=TA_CENTER,textColor=colors.grey)

    def mkt(headers,rows_data,cw=None):
        if not rows_data: rows_data=[["—"]*len(headers)]
        t=Table([headers]+rows_data,colWidths=cw,repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#1565C0")),
            ("TEXTCOLOR",(0,0),(-1,0),colors.white),
            ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
            ("FONTSIZE",(0,0),(-1,-1),8),
            ("ALIGN",(0,0),(-1,-1),"CENTER"),
            ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
            ("GRID",(0,0),(-1,-1),0.4,colors.HexColor("#90CAF9")),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#E3F2FD")]),
            ("LEFTPADDING",(0,0),(-1,-1),5),("RIGHTPADDING",(0,0),(-1,-1),5),
            ("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4),
        ]))
        return t

    tf=data.get("traffo",{})
    elems=[Spacer(1,6*mm),
           Paragraph("CONSOLIDATED TRANSFORMER TEST REPORT",TITLE),
           HRFlowable(width="100%",thickness=2,color=colors.HexColor("#0072ff")),
           Spacer(1,4*mm)]
    meta=[[Paragraph(f"<b>Transformer:</b> {tf.get('Name','—')}",NRM),
           Paragraph(f"<b>Manufacturer:</b> {tf.get('Make','—')}",NRM),
           Paragraph(f"<b>Serial No.:</b> {tf.get('SL NO.','—')}",NRM)],
          [Paragraph(f"<b>Rated MVA:</b> {tf.get('Rated MVA','—')}",NRM),
           Paragraph(f"<b>Vector Group:</b> {tf.get('Vector Group','—')}",NRM),
           Paragraph(f"<b>Date:</b> {datetime.date.today()}",NRM)]]
    mt=Table(meta,colWidths=[62*mm,62*mm,57*mm])
    mt.setStyle(TableStyle([("GRID",(0,0),(-1,-1),0.3,colors.lightgrey),
        ("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#F0F7FF")),
        ("LEFTPADDING",(0,0),(-1,-1),8),("TOPPADDING",(0,0),(-1,-1),5),
        ("BOTTOMPADDING",(0,0),(-1,-1),5)]))
    elems+=[mt,Spacer(1,6*mm)]

    elems.append(Paragraph("1. Transformer Details",H2))
    elems.append(mkt(["Parameter","Value"],
                     [[Paragraph(f"<b>{k}</b>",NRM),str(v or "—")] for k,v in tf.items()],
                     cw=[85*mm,PW-85*mm]))
    elems.append(Spacer(1,4*mm))

    ir=data.get("ir_pi",{})
    irh=["Connection"]+IR_COLS
    irr=[[r]+[cs.get(c,"—") for c in IR_COLS] for r,cs in ir.items()]
    elems.append(Paragraph("2. Insulation Resistance & PI",H2))
    elems.append(mkt(irh,irr,cw=[55*mm]+[(PW-55*mm)/len(IR_COLS)]*len(IR_COLS)))
    elems.append(Spacer(1,4*mm))

    mb=data.get("mbt",{})
    mbh=["Phase"]+MB_COLS
    mbr=[[r]+[cs.get(c,"—") for c in MB_COLS] for r,cs in mb.items()]
    elems.append(Paragraph("3. Magnetic Balance Test",H2))
    elems.append(mkt(mbh,mbr,cw=[40*mm]+[(PW-40*mm)/len(MB_COLS)]*len(MB_COLS)))
    elems.append(Spacer(1,4*mm))

    td=data.get("tan_delta",{})
    tdh=["Mode"]+TD_COLS
    tdr=[[r]+[cs.get(c,"—") for c in TD_COLS] for r,cs in td.items()]
    elems.append(Paragraph("4. Tan Delta & Capacitance",H2))
    elems.append(mkt(tdh,tdr,cw=[65*mm]+[(PW-65*mm)/len(TD_COLS)]*len(TD_COLS)))
    elems.append(Spacer(1,4*mm))

    wr=data.get("wr",{})
    wrh=["Side / Connection"]+WR_COLS
    wrr=[[r]+[cs.get(c,"—") for c in WR_COLS] for r,cs in wr.items()]
    elems.append(Paragraph("5. Winding Resistance",H2))
    elems.append(mkt(wrh,wrr,cw=[PW*0.65,PW*0.35]))

    elems+=[Spacer(1,10*mm),
            HRFlowable(width="100%",thickness=1,color=colors.lightgrey),
            Paragraph(f"Generated by Transformer Testing Dashboard  "
                      f"\u2022  {datetime.datetime.now():%d %b %Y %H:%M}  "
                      f"\u2022  Confidential",FOOT)]
    doc.build(elems)
    buf.seek(0); return buf.read()

# ── Sidebar ───────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## Transformer Dashboard")
    st.markdown("---")
    be=db.backend_name()
    st.caption(f"{'Supabase/PG' if 'Postgres' in be else 'Local SQLite'} backend")
    st.markdown(f"**Active:** `{F()['traffo'].get('Name','—') or '—'}`")
    st.markdown(f"Date: {datetime.date.today():%d %B %Y}")
    st.markdown("---")
    st.markdown("### Actions")
    if st.button("Save Report", use_container_width=True):
        name=db.sanitise(F()["traffo"].get("Name","")) or "Unknown"
        try:
            rid=db.save_report(name,F())
            st.session_state.last_rid=rid
            st.success(f"Report #{rid} saved")
        except Exception as e: st.error(f"Save failed: {e}")
    if st.button("Clear Form", use_container_width=True):
        st.session_state.form=blank_form()
        st.session_state.last_rid=None
        st.rerun()
    st.markdown("---")
    st.caption("No hardcoded credentials.\nSecrets from .env or st.secrets only.")

# ── Main tabs ─────────────────────────────────────────────────────────────
st.markdown("# Transformer Testing Dashboard")
st.markdown("---")
tabs=st.tabs(["Traffo Details","IR & PI","MBT Star","Tan Delta",
              "WR Test","PDF Report","Trends","History"])

with tabs[0]:
    st.subheader("Transformer Nameplate Details")
    c1,c2=st.columns(2)
    half=len(TRAFFO_FIELDS)//2+len(TRAFFO_FIELDS)%2
    with c1:
        for lbl,key in TRAFFO_FIELDS[:half]:
            v=st.text_input(lbl,value=F()["traffo"].get(key,""),key=f"tf_{key}")
            F()["traffo"][key]=db.sanitise(v)
    with c2:
        for lbl,key in TRAFFO_FIELDS[half:]:
            v=st.text_input(lbl,value=F()["traffo"].get(key,""),key=f"tf_{key}")
            F()["traffo"][key]=db.sanitise(v)
    st.markdown("---")
    st.subheader("Quick Summary")
    sc=st.columns(5)
    for i,f in enumerate(["Name","Make","Rated MVA","Vector Group","SL NO."]):
        sc[i].metric(f,F()["traffo"].get(f,"—") or "—")

with tabs[1]:
    st.subheader("Insulation Resistance & Polarisation Index")
    st.info("PI = 10 min IR / 1 min IR  |  Acceptable PI >= 2.0")
    editable_table("ir_pi",IR_ROWS,IR_COLS,"ir")
    st.markdown("---"); st.subheader("Live PI Calculator")
    pc1,pc2,pc3=st.columns(3)
    ir1=pc1.number_input("1 min IR (MO)",min_value=0.0,step=0.1,format="%.1f",key="pi_1m")
    ir10=pc2.number_input("10 min IR (MO)",min_value=0.0,step=0.1,format="%.1f",key="pi_10m")
    with pc3:
        if ir1>0:
            piv=ir10/ir1
            pc3.metric("PI",f"{piv:.2f}",delta="PASS" if piv>=2 else "FAIL",
                       delta_color="normal" if piv>=2 else "inverse")
        else: pc3.metric("PI","—")

with tabs[2]:
    st.subheader("Magnetic Balance Test – Star Side")
    st.info("Voltage imbalance between phases should be < 5%")
    editable_table("mbt",MB_ROWS,MB_COLS,"mbt")
    st.markdown("---"); st.subheader("Phase Imbalance Checker")
    try:
        vc=["r-n (V)","y-n (V)","b-n (V)"]
        vs=[[float(F()["mbt"].get(p,{}).get(c,0) or 0) for c in vc] for p in MB_ROWS]
        imb=[]
        for ci in range(3):
            cv=[vs[ri][ci] for ri in range(3)]; avg=np.mean(cv)
            imb.append((max(cv)-min(cv))/avg*100 if avg else 0)
        mx=max(imb); ic=st.columns(4)
        for i,(lbl,v) in enumerate(zip(["r-n","y-n","b-n","Max"],[*imb,mx])):
            ic[i].metric(f"{lbl} Imbalance",f"{v:.2f}%",
                         delta=("PASS" if mx<5 else "FAIL") if i==3 else None,
                         delta_color=("normal" if mx<5 else "inverse") if i==3 else "off")
    except: st.caption("Enter MBT values above.")

with tabs[3]:
    st.subheader("Tan Delta & Capacitance Test")
    st.info("Tan Delta < 1%  |  Cap. should trend with earlier report")
    t1,t2=st.tabs(["HV to LV","LV to HV"])
    with t1: editable_table("tan_delta",HV_TD,TD_COLS,"td_hv")
    with t2: editable_table("tan_delta",LV_TD,TD_COLS,"td_lv")

with tabs[4]:
    st.subheader("Winding Resistance Test")
    st.info("Phase-to-phase variation < 3%")
    w1,w2=st.tabs(["HV Side @ 10A","LV Side @ 25A"])
    with w1: editable_table("wr",HV_WR,WR_COLS,"wr_hv")
    with w2: editable_table("wr",LV_WR,WR_COLS,"wr_lv")

with tabs[5]:
    st.subheader("Generate PDF Report")
    tf=F().get("traffo",{})
    name=tf.get("Name","Transformer") or "Transformer"
    ts=datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    fname=f"TR_Report_{name.replace(' ','_')}_{ts}.pdf"
    rc=st.columns(3)
    rc[0].markdown(f"**Transformer:** {tf.get('Name','—')}")
    rc[1].markdown(f"**Manufacturer:** {tf.get('Make','—')}")
    rc[2].markdown(f"**Serial No.:** {tf.get('SL NO.','—')}")
    rc[0].markdown(f"**Rated MVA:** {tf.get('Rated MVA','—')}")
    rc[1].markdown(f"**Vector Group:** {tf.get('Vector Group','—')}")
    rc[2].markdown(f"**Date:** {datetime.date.today()}")
    st.markdown("---")
    if st.button("Generate PDF",use_container_width=True):
        try:
            pdf=build_pdf(F())
            if st.session_state.last_rid: db.update_pdf(st.session_state.last_rid,pdf)
            else:
                rid=db.save_report(name,F(),pdf); st.session_state.last_rid=rid
            st.download_button("Download PDF",data=pdf,file_name=fname,
                               mime="application/pdf",use_container_width=True)
            st.success("PDF ready.")
        except Exception as e: st.error(f"PDF failed: {e}")

with tabs[6]:
    st.subheader("Historical Test Trends")
    tr_inp=st.text_input("Transformer Name (exact match)",key="trend_name")
    if st.button("Load Trends"):
        if not tr_inp.strip(): st.warning("Enter a name.")
        else:
            rows=db.trend_data(tr_inp.strip())
            if len(rows)<2: st.warning(f"Need >= 2 reports. Found: {len(rows)}")
            else:
                dates,pi_v,mb_v,wr_v=[],[],[],[]
                for row in rows:
                    dt=row[0] if isinstance(row,(list,tuple)) else row["report_date"]
                    dj=row[1] if isinstance(row,(list,tuple)) else row["data_json"]
                    d=dj if isinstance(dj,dict) else json.loads(dj)
                    dates.append(dt)
                    ir=d.get("ir_pi",{}); fir=list(ir.values())[0] if ir else {}
                    try: pi_v.append(float(fir.get("PI Value","0") or 0))
                    except: pi_v.append(0)
                    mb=d.get("mbt",{}); pr=mb.get("Phase R",{})
                    try: mb_v.append(float(pr.get("Imag (A)","0") or 0))
                    except: mb_v.append(0)
                    wr=d.get("wr",{}); fw=list(wr.values())[0] if wr else {}
                    try: wr_v.append(float(list(fw.values())[0] or 0))
                    except: wr_v.append(0)
                BG="#0f1923";MID="#1a2535";ACC="#00c6ff";RD="#ef5350"
                TD_C="#7a9bbf";BD="#2a3f5f";xs=list(range(len(dates)))
                fig,axes=plt.subplots(1,3,figsize=(14,4.5),facecolor=BG)
                fig.suptitle(f"Trends — {tr_inp}",color="#e8f4fd",fontsize=13,fontweight="bold")
                def sax(ax,title,ylabel,ydata,threshold=None):
                    ax.set_facecolor(MID); ax.set_title(title,color=ACC,fontsize=9,fontweight="bold")
                    ax.set_ylabel(ylabel,color=TD_C,fontsize=8); ax.tick_params(colors=TD_C,labelsize=7)
                    for sp in ax.spines.values(): sp.set_edgecolor(BD)
                    ax.plot(xs,ydata,color=ACC,marker="o",lw=2,ms=7)
                    ax.fill_between(xs,ydata,alpha=0.12,color=ACC)
                    ax.set_xticks(xs); ax.set_xticklabels(dates,rotation=30,ha="right",fontsize=7)
                    if threshold is not None:
                        ax.axhline(threshold,color=RD,ls="--",lw=1.2,label=f"Limit={threshold}")
                        ax.legend(fontsize=7,facecolor="#1e2d40",edgecolor=BD,labelcolor="#e8f4fd")
                sax(axes[0],"Polarisation Index (PI)","PI",pi_v,threshold=2.0)
                sax(axes[1],"MBT Magnetising Current (Phase R)","Imag (A)",mb_v)
                sax(axes[2],"Winding Resistance – first row","Res. (mO)",wr_v)
                plt.tight_layout(rect=[0,0,1,0.93])
                st.pyplot(fig); plt.close(fig)

with tabs[7]:
    st.subheader("Report History")
    if st.button("Refresh"): st.rerun()
    all_reps=db.all_reports()
    if not all_reps: st.info("No saved reports yet.")
    else:
        df_h=pd.DataFrame([(r[0],r[1],r[2],r[3]) for r in all_reps],
                          columns=["ID","Date","Transformer","Saved At"])
        st.dataframe(df_h,use_container_width=True,hide_index=True)
        st.markdown("---")
        hc1,hc2,hc3=st.columns(3)
        with hc1:
            st.markdown("**Load into form**")
            lid=st.number_input("Report ID",min_value=1,step=1,key="load_id")
            if st.button("Load",use_container_width=True):
                data,_=db.get_report(int(lid))
                if data: load_into_form(data); st.success(f"Loaded #{lid}"); st.rerun()
                else: st.error("Not found.")
        with hc2:
            st.markdown("**Download PDF**")
            did=st.number_input("Report ID",min_value=1,step=1,key="dl_id")
            if st.button("Get PDF",use_container_width=True):
                stored,pdf=db.get_report(int(did))
                if not pdf and stored:
                    try: pdf=build_pdf(stored); db.update_pdf(int(did),pdf)
                    except Exception as e: st.error(f"PDF failed: {e}")
                if pdf:
                    st.download_button("Download",data=pdf,
                                       file_name=f"TR_Report_{did}.pdf",
                                       mime="application/pdf")
                else: st.error("Not found.")
        with hc3:
            st.markdown("**Delete report**")
            deid=st.number_input("Report ID",min_value=1,step=1,key="del_id")
            if st.button("Delete",use_container_width=True):
                db.delete_report(int(deid)); st.success(f"Deleted #{deid}"); st.rerun()
