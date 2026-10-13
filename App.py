import streamlit as st
import pandas as pd
import periodictable
import datetime
import io
import re
from pathlib import Path

# PDF imports
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

# ==========================================
# PATHS
# ==========================================
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"

MW_FILE      = DATA_DIR / "mw_reference.csv"
IU_FILE      = DATA_DIR / "iu_reference.csv"
ATE_FILE     = DATA_DIR / "ate_reference.csv"
NRV_FILE     = DATA_DIR / "nrv_reference.csv"
BASE_MW_FILE = DATA_DIR / "base_mw_reference.csv"
DETECT_FILE  = DATA_DIR / "detection_rules.csv"

# ==========================================
# APP CONFIG
# ==========================================
st.set_page_config(page_title="Supplement Converter", page_icon="💊", layout="wide")
st.markdown("""
<style>
    .main-header { font-size: 2.5rem; color: #1f77b4; text-align: center; margin-bottom: 0.5rem; }
    .sub-header { text-align: center; color: #666; margin-bottom: 2rem; }
</style>
""", unsafe_allow_html=True)
st.markdown('<h1 class="main-header">💊 Supplement Converter</h1>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Fully config-driven — all data lives in data/*.csv.</p>', unsafe_allow_html=True)

# ==========================================
# SPELLING NORMALIZATION
# ==========================================
SPELLING_VARIANTS = {
    "sulfate": "sulphate", "sulfide": "sulphide", "sulfite": "sulphite",
    "sulfur": "sulphur", "sulfuric": "sulphuric", "sulfurous": "sulphurous",
    "aluminum": "aluminium", "cesium": "caesium",
    "mold": "mould", "color": "colour", "fiber": "fibre",
    "meter": "metre", "liter": "litre",
    "estrogen": "oestrogen", "hemoglobin": "haemoglobin",
}

def normalize_spelling(text):
    if text is None:
        return ""
    result = str(text).lower().strip()
    result = re.sub(r"\s+", " ", result).strip()
    for us, uk in SPELLING_VARIANTS.items():
        result = re.sub(rf'\b{us}\b', uk, result)
    return result

def force_british(text):
    if not text:
        return ""
    result = str(text)
    for us, uk in SPELLING_VARIANTS.items():
        result = re.sub(rf'\b{us}\b', uk, result, flags=re.IGNORECASE)
    return result

def collapse_ws(text):
    return re.sub(r"\s+", "", str(text))

# ==========================================
# CSV LOADERS
# ==========================================
@st.cache_data(ttl=60)
def load_csv(path, columns):
    if not path.exists():
        return pd.DataFrame(columns=columns)
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame(columns=columns)

def load_mw_reference():
    df = load_csv(MW_FILE, ["Material_Name", "Molecular_Weight", "Formula", "Target_Element", "Category", "Preferred_Form", "Notes"])
    if not df.empty:
        df["_key"] = df["Material_Name"].astype(str).apply(normalize_spelling)
        df["_collapsed"] = df["_key"].apply(collapse_ws)
        if "Preferred_Form" not in df.columns:
            df["Preferred_Form"] = ""
    return df

def load_iu_reference():
    df = load_csv(IU_FILE, ["Material_Name", "IU_Per_Mg", "Common_Name", "Regulatory_Standard", "Notes"])
    if not df.empty:
        df["_key"] = df["Material_Name"].astype(str).apply(normalize_spelling)
        df["_collapsed"] = df["_key"].apply(collapse_ws)
    return df

def load_ate_reference():
    df = load_csv(ATE_FILE, ["Material_Name", "ATE_Per_Mg", "Common_Name", "Regulatory_Standard", "Notes"])
    if not df.empty:
        df["_key"] = df["Material_Name"].astype(str).apply(normalize_spelling)
        df["_collapsed"] = df["_key"].apply(collapse_ws)
    return df

def load_nrv_reference():
    df = load_csv(NRV_FILE, ["Nutrient_Name", "NRV_Value", "NRV_Unit", "Reference"])
    if not df.empty:
        df["_key"] = df["Nutrient_Name"].astype(str).apply(normalize_spelling)
    return df

def load_base_mw_reference():
    return load_csv(BASE_MW_FILE, ["Base_Name", "Base_MW", "Formula", "Target_Class", "Notes"])

def load_detection_rules():
    df = load_csv(DETECT_FILE, ["Keyword", "Detected_Target", "Rule_Type", "Priority", "Notes"])
    if not df.empty:
        df["Priority"] = pd.to_numeric(df["Priority"], errors="coerce").fillna(0).astype(int)
        df["_key"] = df["Keyword"].astype(str).apply(normalize_spelling)
        df = df.sort_values("Priority", ascending=False)
    return df

# ==========================================
# HELPERS
# ==========================================
def extract_inner_compound(material_name):
    m = re.search(r"\(([^)]+)\)", str(material_name))
    return m.group(1).strip() if m else str(material_name).strip()

def clean_material_name(name):
    n = normalize_spelling(str(name))
    n = re.sub(r"\([^)]*\)", " ", n)
    n = re.sub(r"\d+\s*%", " ", n)
    for suffix in [" dc", " coated", " granular", " powder", " anhydrous", " monohydrate",
                   " heptahydrate", " pentahydrate", " hcl", " hydrochloride"]:
        n = n.replace(suffix, " ")
    return re.sub(r"\s+", " ", n).strip()

VITAMIN_NAMES = [
    ("retinyl palmitate", "Vitamin A"), ("retinol", "Vitamin A"), ("retinyl acetate", "Vitamin A"),
    ("beta carotene", "Beta Carotene"),
    ("cholecalciferol", "Vitamin D3"), ("vitamin d3", "Vitamin D3"),
    ("ergocalciferol", "Vitamin D2"), ("vitamin d2", "Vitamin D2"),
    ("tocopheryl acetate", "Vitamin E"), ("tocopherol", "Vitamin E"), ("vitamin e", "Vitamin E"),
    ("ascorbic acid", "Vitamin C"), ("vitamin c", "Vitamin C"),
    ("thiamine", "Thiamine"), ("riboflavin", "Riboflavin"),
    ("niacinamide", "Niacinamide"), ("nicotinamide", "Niacinamide"), ("niacin", "Niacinamide"),
    ("pantothenate", "Pantothenic Acid"), ("pantothenic", "Pantothenic Acid"),
    ("pyridoxine", "Pyridoxine"), ("pyridoxal", "Pyridoxine"), ("pyridoxamine", "Pyridoxine"),
    ("biotin", "Biotin"),
    ("folic acid", "Folic Acid"), ("folate", "Folic Acid"),
    ("cyanocobalamin", "Cyanocobalamin"), ("methylcobalamin", "Cyanocobalamin"),
    ("hydroxocobalamin", "Cyanocobalamin"), ("adenosylcobalamin", "Cyanocobalamin"),
    ("phytonadione", "Phytonadione"), ("menaquinone", "Vitamin K2"), ("menadione", "Vitamin K3"),
    ("choline", "Choline"), ("inositol", "Inositol"),
]

def get_vitamin_name(material_name):
    name_lower = str(material_name).lower()
    for keyword, vit_name in VITAMIN_NAMES:
        if keyword in name_lower:
            return vit_name
    return None

# ==========================================
# KNOWN FORMS
# ==========================================
KNOWN_FORMS = [
    "Anhydrous",
    "Monohydrate", "Dihydrate", "Trihydrate", "Tetrahydrate",
    "Pentahydrate", "Hexahydrate", "Heptahydrate", "Octahydrate", "Decahydrate",
    "Nitrate", "Mononitrate", "Dinitrate",
    "Hydrochloride", "Chloride", "Sulphate", "Sulfate", "Phosphate", "Carbonate",
    "Acetate", "Succinate", "Fumarate", "Citrate", "Gluconate", "Lactate", "Malate",
    "Orotate", "Picolinate", "Bisglycinate", "Glycinate", "Taurate",
    "Calcium", "Sodium", "Magnesium", "Potassium",
    "Palmitate", "Propionate",
    "Base", "Free Base",
]

def get_preferred_form(material_name):
    ref = load_mw_reference()
    if ref.empty:
        return ""
    ref["_pref"] = ref["Preferred_Form"].astype(str).str.upper().str.strip() == "YES"
    base_norm = normalize_spelling(str(material_name))
    for f in sorted(KNOWN_FORMS, key=len, reverse=True):
        base_norm = re.sub(rf"\s+{f.lower()}\b", "", base_norm).strip()
    for _, row in ref.iterrows():
        row_key = str(row["_key"]).strip()
        if (row_key.startswith(base_norm + " ") or row_key == base_norm) and bool(row["_pref"]):
            suffix = row_key[len(base_norm):].strip()
            if suffix:
                return " ".join(w.capitalize() for w in suffix.split())
    return ""

# ==========================================
# SUGGESTION ENGINE
# ==========================================
def find_similar_materials(material_name, max_results=6):
    ref = load_mw_reference()
    if ref.empty:
        return []
    name_norm = normalize_spelling(str(material_name))
    skip = {"vitamin", "the", "and", "with", "coated", "grade", "usp", "bp", "ph", "hcl", "dc"}
    words = [w for w in re.findall(r"[a-z]{4,}", name_norm) if w not in skip]
    if not words:
        return []
    scored = []
    for _, row in ref.iterrows():
        row_key = str(row["_key"])
        score = sum(1 for w in words if w in row_key)
        if score > 0:
            scored.append((score, row))
    scored.sort(key=lambda x: (
        -x[0],
        -(str(x[1].get("Preferred_Form", "")).upper().strip() == "YES"),
        -len(str(x[1]["_key"]))
    ))
    results = []
    seen = set()
    for _, row in scored:
        mw = row["Molecular_Weight"]
        if pd.isna(mw) or str(mw) == "Variable":
            continue
        nm = str(row["Material_Name"])
        if nm in seen:
            continue
        seen.add(nm)
        is_pref = str(row.get("Preferred_Form", "")).upper().strip() == "YES"
        results.append({"name": nm, "mw": float(mw), "preferred": is_pref})
        if len(results) >= max_results:
            break
    return results

def format_suggestions(suggestions, material_name):
    if not suggestions:
        return f"❌ '{material_name}' not found in data/mw_reference.csv"
    lines = [f"❌ '{material_name}' not found. Available forms / close matches:"]
    for s in suggestions:
        star = " ★ preferred" if s["preferred"] else ""
        lines.append(f"    • {s['name']} (MW {s['mw']:.2f}){star}")
    return "\n".join(lines)

# ==========================================
# MW LOOKUP
# ==========================================
def lookup_mw_from_reference(material_name, form_value=""):
    ref = load_mw_reference()
    if ref.empty:
        return None, None, None, False, False
    ref["_pref"] = ref["Preferred_Form"].astype(str).str.upper().str.strip() == "YES"
    name_full = re.sub(r"\s+", " ", str(material_name)).strip()
    form_clean = re.sub(r"\s+", " ", str(form_value)).strip() if form_value else ""

    if form_clean:
        base_for_forced = name_full
        for f in sorted(KNOWN_FORMS, key=len, reverse=True):
            base_for_forced = re.sub(rf"\s*{re.escape(f)}\b", "", base_for_forced, flags=re.IGNORECASE)
        base_for_forced = re.sub(r"\s+", " ", base_for_forced).strip()
        base_fixed = force_british(base_for_forced)
        form_fixed = force_british(form_clean)
        forced_target = re.sub(r"\s+", " ", f"{base_fixed} {form_fixed}".lower().strip())
        forced_collapsed = collapse_ws(forced_target)

        hits = ref[ref["_key"] == forced_target]
        if not hits.empty:
            row = hits.iloc[0]
            mw = row["Molecular_Weight"]
            if pd.notna(mw) and str(mw) != "Variable":
                return (float(mw), row.get("Formula"), row["Material_Name"], False, True)
        hits = ref[ref["_collapsed"] == forced_collapsed]
        if not hits.empty:
            row = hits.iloc[0]
            mw = row["Molecular_Weight"]
            if pd.notna(mw) and str(mw) != "Variable":
                return (float(mw), row.get("Formula"), row["Material_Name"], False, True)
        alt_target = re.sub(r"\s+", " ", f"{form_fixed} {base_fixed}".lower().strip())
        hits = ref[ref["_key"] == alt_target]
        if not hits.empty:
            row = hits.iloc[0]
            mw = row["Molecular_Weight"]
            if pd.notna(mw) and str(mw) != "Variable":
                return (float(mw), row.get("Formula"), row["Material_Name"], False, True)
        for _, row in ref.iterrows():
            row_collapsed = str(row["_collapsed"])
            if forced_collapsed and (forced_collapsed in row_collapsed or row_collapsed in forced_collapsed):
                mw = row["Molecular_Weight"]
                if pd.notna(mw) and str(mw) != "Variable":
                    return (float(mw), row.get("Formula"), row["Material_Name"], False, True)
        words = [w for w in re.findall(r"[a-z]{4,}", forced_target)]
        if words:
            best_score = 0
            best_row = None
            for _, row in ref.iterrows():
                row_key = str(row["_key"])
                score = sum(1 for w in words if w in row_key)
                if score > best_score:
                    best_score = score
                    best_row = row
            if best_row is not None and best_score == len(words):
                mw = best_row["Molecular_Weight"]
                if pd.notna(mw) and str(mw) != "Variable":
                    return (float(mw), best_row.get("Formula"), best_row["Material_Name"], False, True)
        return None, None, f"{base_fixed} {form_fixed}", False, True

    # AUTO MODE
    inner = extract_inner_compound(name_full)
    candidates = set()
    for c in [name_full, inner, clean_material_name(name_full), clean_material_name(inner)]:
        n = normalize_spelling(c)
        if n and n not in ['nan', 'none', '']:
            candidates.add(n)
            candidates.add(collapse_ws(n))
    for c in candidates:
        hits = ref[(ref["_key"] == c) | (ref["_collapsed"] == c)]
        if not hits.empty:
            pref_hits = hits[hits["_pref"]]
            row = pref_hits.iloc[0] if not pref_hits.empty else hits.iloc[0]
            mw = row["Molecular_Weight"]
            if pd.notna(mw) and str(mw) != "Variable":
                return (float(mw), row.get("Formula"), row["Material_Name"], bool(row["_pref"]), False)
    ref_sorted = ref.assign(_len=ref["_key"].str.len()).sort_values(
        ["_pref", "_len"], ascending=[False, False]
    )
    for c in sorted(candidates, key=len, reverse=True):
        for _, row in ref_sorted.iterrows():
            if row["_key"] and c in row["_key"]:
                mw = row["Molecular_Weight"]
                if pd.notna(mw) and str(mw) != "Variable":
                    return (float(mw), row.get("Formula"), row["Material_Name"], bool(row["_pref"]), False)
    for c in sorted(candidates, key=len, reverse=True):
        for _, row in ref_sorted.iterrows():
            if row["_key"] and row["_key"] in c:
                mw = row["Molecular_Weight"]
                if pd.notna(mw) and str(mw) != "Variable":
                    return (float(mw), row.get("Formula"), row["Material_Name"], bool(row["_pref"]), False)
    return None, None, None, False, False

def lookup_factor_from_reference(material_name, ref_df, value_col, name_col="Common_Name"):
    if ref_df.empty:
        return None, None
    name_full = str(material_name).strip()
    inner = extract_inner_compound(name_full)
    candidates = set()
    for c in [name_full, inner, clean_material_name(name_full), clean_material_name(inner)]:
        n = normalize_spelling(c)
        if n and n not in ['nan', 'none', '']:
            candidates.add(n)
            candidates.add(collapse_ws(n))
    for c in sorted(candidates, key=len, reverse=True):
        for _, row in ref_df.iterrows():
            if row["_key"] and (row["_key"] == c or row["_collapsed"] == c or row["_key"] in c or c in row["_key"]):
                return float(row[value_col]), row.get(name_col)
    return None, None

def lookup_iu_from_reference(material_name):
    return lookup_factor_from_reference(material_name, load_iu_reference(), "IU_Per_Mg")

def lookup_ate_from_reference(material_name):
    return lookup_factor_from_reference(material_name, load_ate_reference(), "ATE_Per_Mg")

def is_vitamin_e(material_name):
    name = normalize_spelling(str(material_name))
    return any(k in name for k in ["tocopherol", "tocopheryl", "vitamin e"])

def lookup_base_mw(base_name):
    ref = load_base_mw_reference()
    if ref.empty:
        return None
    target = str(base_name).lower().strip()
    for _, row in ref.iterrows():
        if str(row["Base_Name"]).lower().strip() == target:
            return float(row["Base_MW"])
    return None

def is_base_target(target):
    return lookup_base_mw(target) is not None

def get_element_data(element_symbol):
    try:
        el = getattr(periodictable, element_symbol)
        return el.mass, el.name
    except AttributeError:
        return None, None

def parse_qty(value):
    if pd.isna(value):
        return 0.0
    s = str(value).replace('mg', '').replace('MG', '').replace(',', '').strip()
    try:
        return float(s) if s else 0.0
    except ValueError:
        return 0.0

# ==========================================
# FORMATTERS
# ==========================================
def format_active_amount(value_mg):
    if value_mg is None or (isinstance(value_mg, float) and pd.isna(value_mg)):
        return "N/A"
    try:
        return f"{float(value_mg):.3f}"
    except (TypeError, ValueError):
        return "N/A"

def format_converted_amount(value_mg):
    if value_mg is None or (isinstance(value_mg, float) and pd.isna(value_mg)):
        return "N/A", "-"
    try:
        v = float(value_mg)
    except (TypeError, ValueError):
        return "N/A", "-"
    if v < 1:
        return f"{v * 1000:.2f}", "µg"
    return f"{v:.2f}", "mg"

def format_pct(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "N/A"
    try:
        return f"{float(value):.2f}%"
    except (TypeError, ValueError):
        return "N/A"

# ==========================================
# AUTO-DETECT TARGET
# ==========================================
def auto_detect_target(material_name):
    rules = load_detection_rules()
    if rules.empty:
        return None
    name_norm = normalize_spelling(str(material_name))
    for _, rule in rules.iterrows():
        keyword = normalize_spelling(str(rule["Keyword"]))
        if keyword and keyword in name_norm:
            return str(rule["Detected_Target"]).strip()
    return None

# ==========================================
# NRV CALCULATION
# ==========================================
def calculate_nrv(nutrient_name, value_mg):
    if not nutrient_name:
        return None
    ref = load_nrv_reference()
    if ref.empty:
        return None
    cleaned_name = re.sub(r"\s*\([^)]*\)\s*", " ", str(nutrient_name)).strip()
    name_lower = normalize_spelling(cleaned_name)
    match = ref[ref["_key"] == name_lower]
    if match.empty:
        for _, row in ref.iterrows():
            if row["_key"] and row["_key"] in name_lower:
                match = ref[ref["_key"] == row["_key"]]
                break
    if match.empty:
        return None
    row = match.iloc[0]
    try:
        nrv_value = float(row["NRV_Value"])
        nrv_unit = str(row["NRV_Unit"]).strip()
    except (ValueError, TypeError):
        return None
    value_in_nrv_unit = value_mg * 1000 if nrv_unit == "µg" else value_mg
    if nrv_value == 0:
        return None
    return round((value_in_nrv_unit / nrv_value) * 100, 2)

# ==========================================
# PDF REPORT
# ==========================================
def generate_pdf_report(clean_df, batch_info):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=12*mm, rightMargin=12*mm,
        topMargin=15*mm, bottomMargin=15*mm,
        title=f"Formulation Report — {batch_info.get('Batch No', '')}",
        author="Supplement Converter",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("Title", parent=styles["Heading1"], fontSize=16,
                                 spaceAfter=6, alignment=1, textColor=colors.HexColor("#1f77b4"))
    subtitle_style = ParagraphStyle("Subtitle", parent=styles["Normal"], fontSize=9,
                                    alignment=1, textColor=colors.HexColor("#666666"), spaceAfter=12)
    cell_style = ParagraphStyle("Cell", parent=styles["Normal"], fontSize=7.5, leading=9)
    cell_style_bold = ParagraphStyle("CellBold", parent=styles["Normal"], fontSize=7.5,
                                     leading=9, fontName="Helvetica-Bold")

    story = []
    story.append(Paragraph("Supplement Formulation Report", title_style))
    story.append(Paragraph(
        f"Batch: <b>{batch_info.get('Batch No', 'N/A')}</b> &nbsp;|&nbsp; "
        f"Operator: <b>{batch_info.get('Operator', 'N/A')}</b> &nbsp;|&nbsp; "
        f"Date: <b>{batch_info.get('Date', 'N/A')}</b> &nbsp;|&nbsp; "
        f"Vitamin E Mode: <b>{batch_info.get('Vitamin E Mode', 'IU')}</b>",
        subtitle_style))

    headers = ["Raw Material", "Nutrient", "Active\n(mg)", "Converted", "Unit", "NRV %", "Status"]
    table_data = [[Paragraph(f"<b>{h}</b>", cell_style_bold) for h in headers]]
    for _, row in clean_df.iterrows():
        table_data.append([
            Paragraph(str(row.get("Raw Material", "")), cell_style),
            Paragraph(str(row.get("Nutrient Name", "")), cell_style),
            Paragraph(str(row.get("Active Amount", "")), cell_style),
            Paragraph(str(row.get("Converted Amount", "")), cell_style),
            Paragraph(str(row.get("Unit", "")), cell_style),
            Paragraph(str(row.get("NRV %", "")), cell_style),
            Paragraph(str(row.get("Status", "")).replace("\n", "<br/>"), cell_style),
        ])

    col_widths = [32*mm, 26*mm, 18*mm, 20*mm, 22*mm, 14*mm, 40*mm]
    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f77b4")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cccccc")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6f8fa")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(table)
    story.append(Spacer(1, 8*mm))
    story.append(Paragraph(
        "Generated by Supplement Converter — Powered by PubChem & Python",
        ParagraphStyle("footer", parent=styles["Normal"], fontSize=7,
                       alignment=1, textColor=colors.HexColor("#888888"))))
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

# ==========================================
# SESSION STATE
# ==========================================
if 'results' not in st.session_state:
    st.session_state.results = []
if 'batch_info' not in st.session_state:
    st.session_state.batch_info = {}
if 'input_rows' not in st.session_state:
    st.session_state.input_rows = pd.DataFrame(columns=[
        "Material Name", "Form", "Target", "Qty (mg)", "Conc (%)", "Overage (%)", "MW (optional)"
    ])
if 'file_loaded' not in st.session_state:
    st.session_state.file_loaded = False
if 'current_file_name' not in st.session_state:
    st.session_state.current_file_name = ""

# ==========================================
# SIDEBAR
# ==========================================
with st.sidebar:
    st.header("⚙️ Global Settings")
    vitamin_e_standard = st.radio(
        "Vitamin E Standard",
        options=["IU (US/International)", "α-TE (EU/EFSA)"],
        index=0,
    )
    ve_mode = "α-TE" if vitamin_e_standard.startswith("α-TE") else "IU"
    st.caption(f"Active mode: **{ve_mode}**")
    st.markdown("---")
    st.header("📂 Reference Data")
    st.metric("MW reference rows", len(load_mw_reference()))
    st.metric("IU reference rows", len(load_iu_reference()))
    st.metric("α-TE reference rows", len(load_ate_reference()))
    st.metric("NRV reference rows", len(load_nrv_reference()))
    st.metric("Base MW rows", len(load_base_mw_reference()))
    st.metric("Detection rules", len(load_detection_rules()))
    if st.button("🔄 Reload Reference Files"):
        st.cache_data.clear()
        st.rerun()

# ==========================================
# BATCH INFO
# ==========================================
st.markdown("### 📋 Batch Information")
col1, col2, col3 = st.columns(3)
with col1:
    batch_no = st.text_input("Batch Number", value="BATCH-2026-001")
with col2:
    operator = st.text_input("Operator Name", value="Production Manager")
with col3:
    batch_date = st.date_input("Date", datetime.date.today())

# ==========================================
# BULK UPLOAD
# ==========================================
st.markdown("---")
st.markdown("### 📤 Bulk Upload")
col_a, col_b = st.columns([1, 2])

with col_a:
    template_df = pd.DataFrame({
        "Material Name": [
            "Retinyl Palmitate", "Beta Carotene", "DL-alpha Tocopheryl Acetate",
            "Cholecalciferol", "Ascorbic Acid", "Pyridoxine Hydrochloride",
            "Cyanocobalamin", "Folic Acid", "Calcium Pantothenate",
            "Ferrous Fumarate", "Magnesium Oxide", "Zinc Sulphate",
            "Copper Sulphate", "Manganese Sulphate", "Chromium Trichloride",
            "Sodium Molybdate", "Sodium Selenate", "Potassium Iodide",
            "Choline Bitartrate"],
        "Form": [""] * 19,
        "Target": ["IU", "µg", "IU", "IU", "None", "Pyridoxine", "µg", "µg", "Pantothenic Acid",
                   "Fe", "Mg", "Zn", "Cu", "Mn", "Cr", "Mo", "Se", "I", "Choline"],
        "Qty (mg)": ["0.55", "15.00", "18.00", "0.015", "100.00", "6.14", "0.009", "1.00", "16.30",
                     "82.20", "83.96", "32.10", "3.26", "10.53", "0.178", "0.221", "0.132", "0.287", "100.00"],
        "Conc (%)": [90.0, 10.0, 59.0, 100.0, 100.0, 98.0, 100.0, 100.0, 100.0,
                     100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0],
        "Overage (%)": [0.0] * 19,
        "MW (optional)": [""] * 19,
    })
    tpl_buffer = io.BytesIO()
    with pd.ExcelWriter(tpl_buffer, engine='openpyxl') as writer:
        template_df.to_excel(writer, index=False, sheet_name='Template')
    st.download_button("📥 Download Template (.xlsx)", data=tpl_buffer.getvalue(),
        file_name="Supplement_Converter_Template.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True)

with col_b:
    uploaded_file = st.file_uploader("Upload your filled template (Excel or CSV)", type=["csv", "xlsx"])
    if uploaded_file is not None:
        if not st.session_state.file_loaded or st.session_state.current_file_name != uploaded_file.name:
            try:
                df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
                rename_map = {
                    "Material": "Material Name", "Material_Name": "Material Name",
                    "Hydrate": "Form", "Hydrate_Form": "Form", "Hydrate Form": "Form",
                    "Salt_Form": "Form", "Form": "Form",
                    "Qty": "Qty (mg)", "Qty_mg": "Qty (mg)",
                    "Conc": "Conc (%)", "Conc_%": "Conc (%)",
                    "Overage": "Overage (%)", "Overage_%": "Overage (%)",
                    "MW": "MW (optional)", "Molecular Weight": "MW (optional)",
                }
                df = df.rename(columns=rename_map)
                required_cols = ["Material Name", "Target", "Qty (mg)", "Conc (%)", "Overage (%)", "MW (optional)"]
                for col in required_cols:
                    if col not in df.columns:
                        df[col] = 100.0 if col == "Conc (%)" else (0.0 if col == "Overage (%)" else '')
                if "Form" not in df.columns:
                    df["Form"] = ""
                df = df[["Material Name", "Form", "Target", "Qty (mg)", "Conc (%)", "Overage (%)", "MW (optional)"]]
                for col in ["Material Name", "Form", "Target", "Qty (mg)"]:
                    df[col] = df[col].fillna('').astype(str)

                auto_filled = 0
                form_filled = 0
                for i, row in df.iterrows():
                    detected = auto_detect_target(row['Material Name'])
                    if detected:
                        existing = str(row['Target']).strip()
                        if existing.lower() != detected.lower():
                            df.at[i, 'Target'] = detected
                            auto_filled += 1
                    else:
                        if str(row['Target']).strip() in ['', 'nan']:
                            df.at[i, 'Target'] = 'None'

                    if not str(row.get('Form', '')).strip():
                        mw_test, _f, _m, _p, _fo = lookup_mw_from_reference(row['Material Name'], "")
                        if mw_test is None:
                            pref = get_preferred_form(row['Material Name'])
                            if pref:
                                df.at[i, 'Form'] = pref
                                form_filled += 1

                st.session_state.input_rows = df
                st.session_state.file_loaded = True
                st.session_state.current_file_name = uploaded_file.name
                st.success(f"✅ Loaded {len(df)} rows. Auto-detected {auto_filled} targets, filled {form_filled} forms.")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Error: {e}")

    if st.session_state.file_loaded:
        if st.button("Clear uploaded data", use_container_width=True):
            st.session_state.input_rows = pd.DataFrame(columns=[
                "Material Name", "Form", "Target", "Qty (mg)", "Conc (%)", "Overage (%)", "MW (optional)"
            ])
            st.session_state.file_loaded = False
            st.session_state.current_file_name = ""
            st.rerun()

st.markdown("---")
st.markdown("### 🧪 Review & Edit")

base_targets = list(load_base_mw_reference()["Base_Name"].astype(str).tolist()) if not load_base_mw_reference().empty else []
target_options = ["None", "IU", "µg"] + base_targets + ["Fe","Zn","Mg","Ca","Cu","Mn","Cr","Mo","Se","I","K","Na","B","Si","V","Ni"]
form_options = [""] + KNOWN_FORMS

edited_input = st.data_editor(
    st.session_state.input_rows,
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "Material Name": st.column_config.TextColumn("Material Name", required=True, width="large"),
        "Form": st.column_config.SelectboxColumn("Form", options=form_options, width="small"),
        "Target": st.column_config.SelectboxColumn("Target", options=target_options, required=True, width="small"),
        "Qty (mg)": st.column_config.TextColumn("Qty (mg)", width="small"),
        "Conc (%)": st.column_config.NumberColumn("Conc (%)", min_value=0.0, max_value=100.0, format="%.1f", width="small"),
        "Overage (%)": st.column_config.NumberColumn("Overage (%)", min_value=0.0, format="%.1f", width="small"),
        "MW (optional)": st.column_config.NumberColumn("MW (optional)", format="%.2f", width="small"),
    }
)
st.session_state.input_rows = edited_input

# ==========================================
# PROCESS
# ==========================================
st.markdown("---")
if st.button("🚀 Convert All Materials", type="primary", use_container_width=True):
    if st.session_state.input_rows.empty:
        st.warning("Please add materials first.")
    else:
        with st.spinner("Processing..."):
            results = []
            for _, row in st.session_state.input_rows.iterrows():
                material = str(row['Material Name']).strip()
                target = str(row['Target']).strip() if pd.notna(row['Target']) else "None"
                form_value = str(row.get('Form', '')).strip()
                if form_value.lower() == 'nan':
                    form_value = ''
                if not material or material in ['nan', '']:
                    continue
                try:
                    qty = parse_qty(row['Qty (mg)'])
                    conc = float(row['Conc (%)']) if pd.notna(row['Conc (%)']) else 100.0
                    overage = float(row['Overage (%)']) if pd.notna(row['Overage (%)']) else 0.0
                    actual_active = qty * (conc / 100.0) * (1 + (overage / 100.0))

                    manual = row.get('MW (optional)')
                    manual_mw = None
                    if pd.notna(manual) and str(manual).strip() not in ['', 'nan']:
                        try:
                            manual_mw = float(manual)
                        except ValueError:
                            pass

                    active_str = format_active_amount(actual_active)
                    vit_name = get_vitamin_name(material)

                    # ELEMENTAL
                    if target in ["Fe","Zn","Mg","Ca","Cu","Mn","Cr","Mo","Se","I","K","Na","B","Si","V","Ni"]:
                        atomic_w, el_name = get_element_data(target)
                        if atomic_w is None:
                            results.append({"Material": material, "Target": target,
                                "Product Name": f"Unknown ({target})",
                                "Active Amount": active_str, "Converted Amount": "N/A",
                                "Unit": "-", "NRV %": "N/A",
                                "Status": f"❌ Unknown element '{target}'"})
                            continue
                        if manual_mw is not None:
                            mw = manual_mw; matched_name = "Manual"
                            pref_used = False; forced = False
                        else:
                            mw, _f, matched_name, pref_used, forced = lookup_mw_from_reference(material, form_value)
                        if mw:
                            fraction = atomic_w / mw
                            converted_mg = actual_active * fraction
                            conv_str, conv_unit = format_converted_amount(converted_mg)
                            nrv_pct = calculate_nrv(el_name, converted_mg)
                            source = "Manual" if manual_mw is not None else "Reference CSV"
                            hint = " (user-forced form)" if forced else (" (preferred form)" if pref_used else "")
                            results.append({
                                "Material": material, "Target": target,
                                "Product Name": el_name,
                                "Active Amount": active_str,
                                "Converted Amount": conv_str,
                                "Unit": f"{conv_unit} {el_name}",
                                "NRV %": format_pct(nrv_pct),
                                "Status": f"✅ Matched '{matched_name}'{hint} · MW={mw:.2f} ({source}) · fraction={fraction:.4f}"
                            })
                        else:
                            attempt = f"{material} {form_value}".strip() if form_value else material
                            suggestions = find_similar_materials(attempt)
                            results.append({
                                "Material": material, "Target": target,
                                "Product Name": el_name,
                                "Active Amount": active_str,
                                "Converted Amount": "N/A", "Unit": "-", "NRV %": "N/A",
                                "Status": format_suggestions(suggestions, attempt)
                            })

                    # SALT-TO-BASE
                    elif is_base_target(target):
                        base_mw = lookup_base_mw(target)
                        if manual_mw is not None:
                            mw = manual_mw; matched_name = "Manual"
                        else:
                            mw, _f, matched_name, _p, _fo = lookup_mw_from_reference(material, form_value)
                        if mw and base_mw:
                            fraction = base_mw / mw
                            converted_mg = actual_active * fraction
                            conv_str, conv_unit = format_converted_amount(converted_mg)
                            nrv_pct = calculate_nrv(target, converted_mg)
                            results.append({
                                "Material": material, "Target": target,
                                "Product Name": target,
                                "Active Amount": active_str,
                                "Converted Amount": conv_str,
                                "Unit": f"{conv_unit} {target}",
                                "NRV %": format_pct(nrv_pct),
                                "Status": f"✅ Matched '{matched_name}' · Salt MW={mw:.2f} · base MW={base_mw} · fraction={fraction:.4f}"
                            })
                        else:
                            suggestions = find_similar_materials(material)
                            results.append({
                                "Material": material, "Target": target,
                                "Product Name": target,
                                "Active Amount": active_str,
                                "Converted Amount": "N/A", "Unit": "-", "NRV %": "N/A",
                                "Status": format_suggestions(suggestions, material)
                            })

                    # IU / α-TE
                    elif target == "IU":
                        if is_vitamin_e(material) and ve_mode == "α-TE":
                            ate_per_mg, common_name = lookup_ate_from_reference(material)
                            if ate_per_mg:
                                converted = actual_active * ate_per_mg
                                nrv_pct = calculate_nrv(common_name or "Vitamin E", converted)
                                results.append({
                                    "Material": material, "Target": "IU",
                                    "Product Name": (common_name or material) + " (α-TE)",
                                    "Active Amount": active_str,
                                    "Converted Amount": f"{converted:.2f}",
                                    "Unit": "mg α-TE",
                                    "NRV %": format_pct(nrv_pct),
                                    "Status": f"✅ {ate_per_mg} mg α-TE/mg (EFSA, ate_reference.csv)"
                                })
                            else:
                                results.append({
                                    "Material": material, "Target": "IU",
                                    "Product Name": vit_name or material,
                                    "Active Amount": active_str,
                                    "Converted Amount": active_str,
                                    "Unit": "mg", "NRV %": "N/A",
                                    "Status": f"⚠️ '{material}' not in ate_reference.csv"
                                })
                        else:
                            iu_per_mg, common_name = lookup_iu_from_reference(material)
                            if iu_per_mg:
                                converted = actual_active * iu_per_mg
                                results.append({
                                    "Material": material, "Target": "IU",
                                    "Product Name": common_name or vit_name or material,
                                    "Active Amount": active_str,
                                    "Converted Amount": f"{converted:.2f}",
                                    "Unit": "IU",
                                    "NRV %": "N/A (IU)",
                                    "Status": f"✅ {iu_per_mg} IU/mg (iu_reference.csv)"
                                })
                            else:
                                results.append({
                                    "Material": material, "Target": "IU",
                                    "Product Name": vit_name or material,
                                    "Active Amount": active_str,
                                    "Converted Amount": active_str,
                                    "Unit": "mg", "NRV %": "N/A",
                                    "Status": f"⚠️ '{material}' not in iu_reference.csv"
                                })

                    # µG
                    elif target == "µg":
                        converted = actual_active * 1000
                        product_name = vit_name if vit_name else material
                        nrv_pct = calculate_nrv(product_name, actual_active)
                        results.append({
                            "Material": material, "Target": "µg",
                            "Product Name": product_name,
                            "Active Amount": active_str,
                            "Converted Amount": f"{converted:.2f}",
                            "Unit": "µg",
                            "NRV %": format_pct(nrv_pct),
                            "Status": "✅ mg → µg ×1000"
                        })

                    # NONE
                    else:
                        product_name = vit_name if vit_name else material
                        nrv_pct = calculate_nrv(product_name, actual_active)
                        results.append({
                            "Material": material, "Target": "None",
                            "Product Name": product_name,
                            "Active Amount": active_str,
                            "Converted Amount": active_str,
                            "Unit": "mg",
                            "NRV %": format_pct(nrv_pct),
                            "Status": "✅ No conversion"
                        })

                except Exception as e:
                    results.append({
                        "Material": material, "Target": target, "Product Name": material,
                        "Active Amount": "N/A", "Converted Amount": "N/A",
                        "Unit": "-", "NRV %": "N/A", "Status": f"❌ {str(e)}"
                    })

            st.session_state.results = results
            st.session_state.batch_info = {"Batch No": batch_no, "Operator": operator, "Date": str(batch_date), "Vitamin E Mode": ve_mode}
            st.success(f"✅ Done — {len(results)} materials processed in {ve_mode} mode.")
            st.rerun()

# ==========================================
# RESULTS
# ==========================================
if st.session_state.results:
    st.markdown("---")
    st.markdown("### 📊 Conversion Results")
    info = st.session_state.batch_info
    st.info(f"**Batch:** {info.get('Batch No')} | **Operator:** {info.get('Operator')} | **Date:** {info.get('Date')} | **Vitamin E Mode:** {info.get('Vitamin E Mode', 'IU')}")
    clean_df = pd.DataFrame(st.session_state.results).rename(columns={
        "Material": "Raw Material", "Product Name": "Nutrient Name",
    })
    st.dataframe(clean_df, use_container_width=True, hide_index=True)

    st.markdown("### 📥 Download Report")
    col1, col2, col3 = st.columns(3)

    with col1:
        export_df = clean_df.copy()
        export_df.insert(0, "Batch No", info.get('Batch No'))
        export_df.insert(1, "Operator", info.get('Operator'))
        export_df.insert(2, "Date", info.get('Date'))
        export_df.insert(3, "Vitamin E Mode", info.get('Vitamin E Mode', 'IU'))
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            export_df.to_excel(writer, index=False, sheet_name='Results')
            ws = writer.sheets['Results']
            for i, col in enumerate(export_df.columns):
                ml = max(export_df[col].astype(str).map(len).max(), len(str(col))) + 3
                ws.column_dimensions[chr(65 + i)].width = min(ml, 55)
                if col == "Status":
                    from openpyxl.styles import Alignment
                    for row_cells in ws.iter_rows(min_col=i+1, max_col=i+1):
                        for cell in row_cells:
                            cell.alignment = Alignment(wrap_text=True, vertical="top")
        st.download_button("📥 Download Excel", data=buffer.getvalue(),
            file_name=f"Conversion_{info.get('Batch No')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True)

    with col2:
        st.download_button("📥 Download CSV",
            data=clean_df.to_csv(index=False).encode('utf-8'),
            file_name=f"Conversion_{info.get('Batch No')}.csv",
            mime="text/csv", use_container_width=True)

    with col3:
        try:
            pdf_bytes = generate_pdf_report(clean_df, info)
            st.download_button("📄 Download PDF", data=pdf_bytes,
                file_name=f"Conversion_{info.get('Batch No')}.pdf",
                mime="application/pdf",
                use_container_width=True)
        except Exception as e:
            st.button("📄 PDF unavailable", disabled=True, use_container_width=True)
            st.caption(f"PDF error: {e}")

    if st.button("🗑️ Clear All Data", use_container_width=True):
        st.session_state.results = []
        st.session_state.input_rows = pd.DataFrame(columns=st.session_state.input_rows.columns)
        st.session_state.file_loaded = False
        st.session_state.current_file_name = ""
        st.rerun()