"""
Enterprise Document Intelligence Platform
Hooria Zahoor - AI Summer Internship 2026 (NLP & AI Agents Track)

A RAG-powered enterprise knowledge assistant built with Streamlit,
ChromaDB, Sentence-Transformers, and Google Gemini.
"""

import os
import io
import re
import uuid
import random
import datetime

import streamlit as st
import chromadb
from sentence_transformers import SentenceTransformer
import pypdf
from langchain_text_splitters import RecursiveCharacterTextSplitter
from dotenv import load_dotenv

# Optional dependencies (bonus features degrade gracefully if missing)
try:
    import docx
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

load_dotenv()
os.environ["USE_TF"] = "0"  # avoid TensorFlow/Keras conflict with sentence-transformers

# ============================================================
# CONFIG
# ============================================================
APP_TITLE = "Enterprise Document Intelligence Platform"
MODEL_NAME = "gemini-2.5-flash"          # update if you have access to a different model
EMBED_MODEL_NAME = "all-MiniLM-L6-v2"
CHUNK_SIZE = 800
CHUNK_OVERLAP = 150
TOP_K = 4
COST_PER_1K_TOKENS = 0.00035             # rough placeholder estimate

st.set_page_config(page_title=APP_TITLE, page_icon="🧠", layout="wide", initial_sidebar_state="expanded")

# ============================================================
# SESSION STATE
# ============================================================
def init_state():
    defaults = {
        "authenticated": False,
        "username": "",
        "dark_mode": True,
        "documents": {},        # doc_id -> metadata dict
        "messages": [],         # chat history: list of {role, content, hits}
        "total_tokens": 0,
        "total_cost": 0.0,
        "api_key": os.getenv("GOOGLE_API_KEY", ""),
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()

# ============================================================
# STYLING
# ============================================================
def inject_css():
    if st.session_state.dark_mode:
        base = "#05060f"
        panel = "rgba(255,255,255,0.045)"
        panel_border = "rgba(255,255,255,0.10)"
        text = "#eef1fb"
        subtext = "#aab2cc"
        accent = "#8b8bff"
        accent2 = "#34e0c0"
        accent3 = "#ff6fd8"
        panel_glow = "0.05"
        input_bg = "rgba(255,255,255,0.07)"
    else:
        base = "#0a0518"
        panel = "rgba(255,255,255,0.09)"
        panel_border = "rgba(255,255,255,0.16)"
        text = "#fdfaf6"
        subtext = "#d8cdf0"
        accent = "#ffb454"
        accent2 = "#ff7ac6"
        accent3 = "#7ad9ff"
        panel_glow = "0.11"
        input_bg = "rgba(255,255,255,0.12)"

    st.markdown(f"""
    <style>
        @keyframes gradientShift {{
            0%   {{ background-position: 0% 50%; }}
            50%  {{ background-position: 100% 50%; }}
            100% {{ background-position: 0% 50%; }}
        }}
        @keyframes nebulaDrift {{
            0%   {{ background-position: 0% 0%, 100% 0%, 50% 100%; }}
            50%  {{ background-position: 100% 100%, 0% 100%, 50% 0%; }}
            100% {{ background-position: 0% 0%, 100% 0%, 50% 100%; }}
        }}
        @keyframes twinkle {{
            0%, 100% {{ opacity: 0.4; }}
            50% {{ opacity: 1; }}
        }}
        @keyframes fadeInUp {{
            from {{ opacity: 0; transform: translateY(10px); }}
            to   {{ opacity: 1; transform: translateY(0); }}
        }}
        @keyframes floatY {{
            0%, 100% {{ transform: translateY(0px); }}
            50% {{ transform: translateY(-22px); }}
        }}
        @keyframes spin3d {{
            0%   {{ transform: rotateY(0deg) rotateX(8deg); }}
            100% {{ transform: rotateY(360deg) rotateX(8deg); }}
        }}
        @keyframes ringSpin {{
            0%   {{ transform: translate(-50%,-50%) rotate(0deg); }}
            100% {{ transform: translate(-50%,-50%) rotate(360deg); }}
        }}
        @keyframes holePulse {{
            0%, 100% {{ box-shadow: 0 0 40px 10px rgba(180,140,255,0.35); }}
            50% {{ box-shadow: 0 0 60px 18px rgba(180,140,255,0.55); }}
        }}
        @keyframes tumble {{
            0%   {{ transform: translate(0,0) rotateX(0deg) rotateY(0deg); }}
            100% {{ transform: translate(38vw, 14vh) rotateX(720deg) rotateY(540deg); }}
        }}

        .stApp {{
            background: linear-gradient(135deg, {base}, #14163a, {base}, #1a0f2e, {base});
            background-size: 400% 400%;
            animation: gradientShift 30s ease infinite;
            color: {text};
            position: relative;
            overflow-x: hidden;
        }}

        /* ---- Galaxy layer: nebula clouds + stars (behind everything, scales with page) ---- */
        .galaxy-layer {{
            position: absolute; top: 0; left: 0; width: 100%; height: 100%;
            min-height: 100vh; z-index: 0; pointer-events: none; overflow: hidden;
        }}
        .nebula {{
            position: absolute; inset: 0;
            background:
                radial-gradient(ellipse 55% 40% at 15% 18%, rgba(139,110,255,0.30), transparent 60%),
                radial-gradient(ellipse 50% 50% at 85% 12%, rgba(255,111,216,0.22), transparent 60%),
                radial-gradient(ellipse 60% 45% at 50% 85%, rgba(52,200,224,0.18), transparent 60%);
            background-size: 200% 200%;
            animation: nebulaDrift 40s ease-in-out infinite;
        }}
        .stars {{
            position: absolute; inset: 0;
            background-image:
                radial-gradient(1.5px 1.5px at 8% 12%, #fff, transparent 60%),
                radial-gradient(1px 1px at 18% 45%, #fff, transparent 60%),
                radial-gradient(2px 2px at 27% 8%, #fff, transparent 60%),
                radial-gradient(1px 1px at 35% 62%, #cdd4ff, transparent 60%),
                radial-gradient(1.5px 1.5px at 44% 25%, #fff, transparent 60%),
                radial-gradient(1px 1px at 52% 78%, #fff, transparent 60%),
                radial-gradient(2px 2px at 61% 15%, #fff, transparent 60%),
                radial-gradient(1px 1px at 68% 52%, #cdd4ff, transparent 60%),
                radial-gradient(1.5px 1.5px at 76% 35%, #fff, transparent 60%),
                radial-gradient(1px 1px at 84% 68%, #fff, transparent 60%),
                radial-gradient(2px 2px at 91% 22%, #fff, transparent 60%),
                radial-gradient(1px 1px at 12% 82%, #fff, transparent 60%),
                radial-gradient(1.5px 1.5px at 58% 92%, #fff, transparent 60%),
                radial-gradient(1px 1px at 95% 88%, #cdd4ff, transparent 60%);
            background-repeat: repeat; background-size: 100% 100%;
            animation: twinkle 5s ease-in-out infinite;
        }}

        /* ---- Lightning: occasional cosmic energy flashes ---- */
        .lightning {{
            position: absolute; inset: 0; pointer-events: none;
            background: radial-gradient(ellipse 40% 30% at 70% 25%, rgba(196,180,255,0.9), transparent 60%);
            opacity: 0; mix-blend-mode: screen;
            animation: lightningFlash 9s ease-in-out infinite;
        }}
        .lightning.bolt2 {{
            background: radial-gradient(ellipse 35% 25% at 20% 65%, rgba(150,220,255,0.85), transparent 60%);
            animation: lightningFlash 13s ease-in-out infinite;
            animation-delay: -5s;
        }}
        @keyframes lightningFlash {{
            0%, 92%, 100% {{ opacity: 0; }}
            93% {{ opacity: 0.9; }}
            94% {{ opacity: 0.15; }}
            95% {{ opacity: 0.75; }}
            96%, 100% {{ opacity: 0; }}
        }}

        /* ---- Planets: real 3D rotation via perspective + rotateY ---- */
        .planet-wrap {{ position: absolute; pointer-events: none; z-index: 0; perspective: 500px; }}
        .planet-wrap.p1 {{ top: 8%; right: 10%; width: 70px; height: 70px; animation: floatY 9s ease-in-out infinite; }}
        .planet-wrap.p2 {{ bottom: 12%; left: 6%; width: 44px; height: 44px; animation: floatY 12s ease-in-out infinite reverse; }}
        .planet {{
            width: 100%; height: 100%; border-radius: 50%;
            transform-style: preserve-3d; animation: spin3d 14s linear infinite;
        }}
        .p1 .planet {{ background: radial-gradient(circle at 32% 32%, #ffd9a0, #d9762e 55%, #7a3b12 100%); }}
        .p2 .planet {{ background: radial-gradient(circle at 32% 32%, #a6d0ff, #3c6fd9 55%, #16276b 100%); }}
        .planet-wrap.p1::after {{
            content: ""; position: absolute; top: 50%; left: 50%;
            width: 130%; height: 24px; border: 2px solid rgba(255,255,255,0.35);
            border-radius: 50%; transform: translate(-50%,-50%) rotateX(80deg);
        }}

        /* ---- Black hole: dark core + spinning accretion disk ---- */
        .blackhole-wrap {{
            position: absolute; top: 34%; left: 78%; width: 90px; height: 90px;
            z-index: 0; pointer-events: none; perspective: 600px;
            animation: floatY 16s ease-in-out infinite;
        }}
        .blackhole-core {{
            position: absolute; top: 50%; left: 50%; width: 42%; height: 42%;
            transform: translate(-50%,-50%); border-radius: 50%;
            background: radial-gradient(circle, #000 55%, #05010a 100%);
            animation: holePulse 5s ease-in-out infinite; z-index: 2;
        }}
        .blackhole-disk {{
            position: absolute; top: 50%; left: 50%; width: 100%; height: 34%;
            border-radius: 50%; transform: translate(-50%,-50%) rotateX(78deg);
            background: conic-gradient(from 0deg, transparent 0%, {accent3} 15%, transparent 35%, {accent} 55%, transparent 75%, {accent2} 90%, transparent 100%);
            animation: ringSpin 6s linear infinite;
            filter: blur(0.5px);
        }}

        /* ---- Asteroids: small tumbling 3D rocks drifting across ---- */
        .asteroid {{
            position: absolute; z-index: 0; pointer-events: none; border-radius: 40% 60% 55% 45%;
            background: linear-gradient(135deg, #cfcfe0, #6f6f85);
            animation: tumble linear infinite;
        }}
        .asteroid.a1 {{ top: 15%; left: -3%; width: 12px; height: 10px; animation-duration: 26s; }}
        .asteroid.a2 {{ top: 55%; left: -3%; width: 8px; height: 8px; animation-duration: 34s; animation-delay: -10s; }}
        .asteroid.a3 {{ top: 75%; left: -3%; width: 10px; height: 9px; animation-duration: 42s; animation-delay: -22s; }}

        /* ---------- Typography & contrast hardening ---------- */
        .stApp, .stApp p, .stApp span, .stApp li, .stApp label,
        .stMarkdown, [data-testid="stCaptionContainer"],
        [data-testid="stMetricLabel"], [data-testid="stMetricValue"],
        h1, h2, h3, h4, h5, h6 {{
            color: {text} !important;
        }}
        [data-testid="stCaptionContainer"] {{ color: {subtext} !important; }}
        section[data-testid="stSidebar"] {{
            background: {panel}; backdrop-filter: blur(18px);
            border-right: 1px solid {panel_border};
        }}
        section[data-testid="stSidebar"] * {{ color: {text} !important; }}
        .stTextInput input, .stTextArea textarea, .stMultiSelect div[data-baseweb="select"] {{
            background: {input_bg} !important; color: {text} !important;
            border-radius: 10px !important;
        }}

        /* Keep all real app content above the decorative galaxy layer */
        [data-testid="stAppViewContainer"] {{ position: relative; z-index: 1; }}
        [data-testid="stHeader"] {{ background: transparent; }}

        /* ---------- Header ---------- */
        .main-header {{
            display: flex; align-items: center; gap: 1rem;
            background: {panel}; backdrop-filter: blur(20px);
            border: 1px solid {panel_border};
            padding: 0.9rem 1.4rem; border-radius: 18px; margin-bottom: 1.2rem;
            box-shadow: 0 8px 30px rgba(0,0,0,0.25);
            animation: fadeInUp 0.6s ease;
            position: relative; z-index: 1;
        }}
        .main-header .logo-orb {{
            width: 46px; height: 46px; border-radius: 50%; flex-shrink: 0;
            display: flex; align-items: center; justify-content: center; font-size: 1.4rem;
            background: linear-gradient(135deg, {accent}, {accent3});
            box-shadow: 0 0 18px {accent}88;
        }}
        .main-header h1 {{
            margin: 0; font-size: 1.35rem; font-weight: 800; letter-spacing: -0.01em;
            background: linear-gradient(90deg, {accent}, {accent3} 60%, {accent2});
            -webkit-background-clip: text; background-clip: text; color: transparent !important;
        }}
        .main-header p {{ margin: 0.1rem 0 0 0; color: {subtext} !important; font-size: 0.85rem; }}

        /* ---------- Cards ---------- */
        .metric-card, .doc-card, .citation-chip {{
            background: {panel}; backdrop-filter: blur(14px);
            border: 1px solid {panel_border}; border-radius: 14px;
            transition: transform 0.25s ease, box-shadow 0.25s ease, border-color 0.25s ease;
            position: relative; z-index: 1;
        }}
        .metric-card {{ padding: 1rem 1.1rem; text-align: center; }}
        .metric-card:hover, .doc-card:hover {{
            transform: translateY(-4px) scale(1.015);
            box-shadow: 0 14px 34px rgba(139,139,255,0.28);
            border-color: {accent}77;
        }}
        .metric-card .value {{ font-size: 1.55rem; font-weight: 800; color: {accent} !important; }}
        .metric-card .label {{ font-size: 0.72rem; color: {subtext} !important; text-transform: uppercase; letter-spacing: 0.06em; margin-top: 0.15rem; }}

        .doc-card {{ padding: 0.85rem 1rem; margin-bottom: 0.6rem; }}
        .badge {{
            display: inline-block; padding: 0.15rem 0.6rem; border-radius: 999px;
            font-size: 0.7rem; font-weight: 700; background: {accent}33; color: {accent} !important;
            margin-right: 0.35rem;
        }}
        .badge-green {{ background: {accent2}33; color: {accent2} !important; }}
        .citation-chip {{ padding: 0.55rem 0.85rem; margin: 0.35rem 0; font-size: 0.85rem; }}
        .citation-chip:hover {{ border-color: {accent}66; }}
        .subtext {{ color: {subtext} !important; font-size: 0.85rem; }}

        /* Buttons */
        .stButton button {{
            border-radius: 10px !important; border: 1px solid {panel_border} !important;
            background: {panel} !important; backdrop-filter: blur(10px);
            color: {text} !important;
            transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
            position: relative; z-index: 1;
        }}
        .stButton button p, .stButton button span, .stButton button div {{ color: {text} !important; }}
        .stButton button:hover {{
            transform: translateY(-2px); box-shadow: 0 8px 20px {accent}44;
            border-color: {accent}88 !important;
        }}
        .stDownloadButton button {{
            border-radius: 10px !important; border: 1px solid {panel_border} !important;
            background: {panel} !important; color: {text} !important;
        }}
        .stDownloadButton button p, .stDownloadButton button span {{ color: {text} !important; }}
        button[kind="primary"], .stButton button[kind="primary"] {{
            background: linear-gradient(135deg, {accent}, {accent3}) !important;
            border: none !important; color: #ffffff !important;
        }}
        button[kind="primary"] p, button[kind="primary"] span {{ color: #ffffff !important; }}

        /* Tabs */
        .stTabs {{ position: relative; z-index: 1; }}
        .stTabs [data-baseweb="tab"] {{ color: {subtext} !important; }}
        .stTabs [aria-selected="true"] {{ color: {accent} !important; }}
    </style>

    <div class="galaxy-layer">
        <div class="nebula"></div>
        <div class="stars"></div>
        <div class="lightning"></div>
        <div class="lightning bolt2"></div>
        <div class="planet-wrap p1"><div class="planet"></div></div>
        <div class="planet-wrap p2"><div class="planet"></div></div>
        <div class="blackhole-wrap">
            <div class="blackhole-disk"></div>
            <div class="blackhole-core"></div>
        </div>
        <div class="asteroid a1"></div>
        <div class="asteroid a2"></div>
        <div class="asteroid a3"></div>
    </div>
    """, unsafe_allow_html=True)

# ============================================================
# CACHED RESOURCES
# ============================================================
@st.cache_resource(show_spinner="Loading embedding model...")
def get_embedder():
    return SentenceTransformer(EMBED_MODEL_NAME)

@st.cache_resource
def get_chroma_client():
    return chromadb.PersistentClient(path="./chroma_store")

def get_collection():
    client = get_chroma_client()
    return client.get_or_create_collection(name="enterprise_documents", metadata={"hnsw:space": "cosine"})

# ============================================================
# DOCUMENT EXTRACTION
# ============================================================
def extract_pdf(file_bytes):
    reader = pypdf.PdfReader(io.BytesIO(file_bytes))
    pages = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        pages.append({"page": i + 1, "text": text})
    return pages

def extract_txt(file_bytes):
    return [{"page": 0, "text": file_bytes.decode("utf-8", errors="ignore")}]

def extract_md(file_bytes):
    return [{"page": 0, "text": file_bytes.decode("utf-8", errors="ignore")}]

def extract_docx(file_bytes):
    if not DOCX_AVAILABLE:
        raise RuntimeError("python-docx not installed. Run: pip install python-docx")
    d = docx.Document(io.BytesIO(file_bytes))
    text = "\n".join(p.text for p in d.paragraphs)
    return [{"page": 0, "text": text}]

def clean_text(text):
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^\x20-\x7E\n\u0600-\u06FF]", "", text)
    return text.strip()

def chunk_document(pages, doc_name):
    splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    chunks = []
    for p in pages:
        cleaned = clean_text(p["text"])
        if not cleaned:
            continue
        for idx, s in enumerate(splitter.split_text(cleaned)):
            chunks.append({"text": s, "page": p["page"], "chunk_index": idx, "doc_name": doc_name})
    return chunks

# ============================================================
# PROCESSING PIPELINE
# ============================================================
def process_document(uploaded_file):
    filename = uploaded_file.name
    ext = filename.split(".")[-1].lower()
    file_bytes = uploaded_file.read()

    extractors = {"pdf": extract_pdf, "txt": extract_txt, "md": extract_md, "docx": extract_docx}
    if ext not in extractors:
        return None, f"Unsupported file type: .{ext}"

    try:
        pages = extractors[ext](file_bytes)
    except Exception as e:
        return None, f"Extraction failed: {e}"

    chunks = chunk_document(pages, filename)
    if not chunks:
        return None, "No extractable text found in this document."

    embedder = get_embedder()
    texts = [c["text"] for c in chunks]
    embeddings = embedder.encode(texts, show_progress_bar=False).tolist()

    collection = get_collection()
    ids = [f"{filename}__{i}__{uuid.uuid4().hex[:8]}" for i in range(len(chunks))]
    metadatas = [{"doc_name": filename, "page": c["page"], "chunk_index": c["chunk_index"]} for c in chunks]
    collection.add(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)

    doc_id = str(uuid.uuid4())
    st.session_state.documents[doc_id] = {
        "name": filename,
        "type": ext,
        "pages": len(pages) if ext == "pdf" else 0,
        "chunk_count": len(chunks),
        "status": "Processed",
        "uploaded_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "chunks": chunks,
        "ids": ids,
        "summary": None,
        "suggested_questions": None,
    }
    return doc_id, None

def delete_document(doc_id):
    doc = st.session_state.documents.get(doc_id)
    if not doc:
        return
    get_collection().delete(ids=doc["ids"])
    del st.session_state.documents[doc_id]

def refresh_embeddings(doc_id):
    doc = st.session_state.documents.get(doc_id)
    if not doc:
        return
    collection = get_collection()
    collection.delete(ids=doc["ids"])
    embedder = get_embedder()
    texts = [c["text"] for c in doc["chunks"]]
    embeddings = embedder.encode(texts, show_progress_bar=False).tolist()
    ids = [f"{doc['name']}__{i}__{uuid.uuid4().hex[:8]}" for i in range(len(texts))]
    metadatas = [{"doc_name": doc["name"], "page": c["page"], "chunk_index": c["chunk_index"]} for c in doc["chunks"]]
    collection.add(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)
    doc["ids"] = ids
    doc["status"] = "Refreshed"

# ============================================================
# SEARCH (Semantic + Hybrid)
# ============================================================
def semantic_search(query, top_k=TOP_K, doc_filter=None):
    embedder = get_embedder()
    collection = get_collection()
    if collection.count() == 0:
        return []
    q_emb = embedder.encode([query]).tolist()
    where = {"doc_name": {"$in": doc_filter}} if doc_filter else None
    results = collection.query(query_embeddings=q_emb, n_results=min(top_k, collection.count()), where=where)
    hits = []
    if results["ids"] and results["ids"][0]:
        for i in range(len(results["ids"][0])):
            hits.append({
                "text": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i],
            })
    return hits

def keyword_score(query, text):
    q_terms = set(re.findall(r"\w+", query.lower()))
    t_terms = re.findall(r"\w+", text.lower())
    if not t_terms:
        return 0.0
    return sum(1 for t in t_terms if t in q_terms) / len(t_terms)

def hybrid_search(query, top_k=TOP_K, doc_filter=None):
    hits = semantic_search(query, top_k=top_k * 2, doc_filter=doc_filter)
    for h in hits:
        sem_score = max(0.0, 1 - h["distance"]) if h["distance"] is not None else 0.0
        h["hybrid_score"] = 0.7 * sem_score + 0.3 * keyword_score(query, h["text"])
    hits.sort(key=lambda x: x["hybrid_score"], reverse=True)
    return hits[:top_k]

# ============================================================
# LLM / RAG
# ============================================================
def estimate_tokens(text):
    return max(1, len(text) // 4)

def track_usage(prompt_tokens, response_tokens):
    total = prompt_tokens + response_tokens
    st.session_state.total_tokens += total
    st.session_state.total_cost += (total / 1000) * COST_PER_1K_TOKENS

def call_llm(prompt):
    if not GEMINI_AVAILABLE:
        return "⚠️ `google-generativeai` is not installed. Run: `pip install google-generativeai`"
    api_key = st.session_state.api_key
    if not api_key:
        return "⚠️ No API key set. Please enter your GOOGLE_API_KEY in the sidebar."
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(MODEL_NAME)
        response = model.generate_content(prompt)
        answer = response.text
    except Exception as e:
        return f"⚠️ LLM error: {e}"
    track_usage(estimate_tokens(prompt), estimate_tokens(answer))
    return answer

def build_context(hits):
    parts = []
    for i, h in enumerate(hits):
        meta = h["metadata"]
        page_label = "N/A" if meta["page"] == 0 else str(meta["page"])
        parts.append(f"[Chunk {i+1} | Source: {meta['doc_name']} | Page: {page_label}]\n{h['text']}")
    return "\n\n".join(parts)

def generate_answer(query, history, doc_filter=None, search_mode="Semantic"):
    hits = hybrid_search(query, doc_filter=doc_filter) if search_mode == "Hybrid" else semantic_search(query, doc_filter=doc_filter)
    if not hits:
        return "I couldn't find an answer to that in the uploaded documents. Try uploading a relevant document or rephrasing your question.", []

    context = build_context(hits)
    history_text = "".join(
        f"{'User' if m['role']=='user' else 'Assistant'}: {m['content']}\n" for m in history[-6:]
    )
    prompt = f"""You are an enterprise document assistant. Answer strictly using the CONTEXT below.
If the answer isn't in the context, clearly say "This information is not available in the uploaded documents" — do not make anything up (no hallucination).

Conversation History:
{history_text}

CONTEXT:
{context}

Current Question: {query}

Give a clear, concise answer, and end by stating which document/page the information came from.
"""
    answer = call_llm(prompt)
    return answer, hits

def generate_summary(doc):
    sample = " ".join(c["text"] for c in doc["chunks"][:6])
    return call_llm(f"Write a professional 3-4 sentence summary of the following document excerpt:\n\n{sample}")

def generate_suggested_questions(doc):
    sample = " ".join(c["text"] for c in doc["chunks"][:6])
    return call_llm(f"Based on the following document excerpt, suggest 4 useful questions a user could ask about it. Return only a numbered list, no extra text.\n\n{sample}")

def compare_documents(doc1, doc2):
    t1 = " ".join(c["text"] for c in doc1["chunks"][:5])
    t2 = " ".join(c["text"] for c in doc2["chunks"][:5])
    return call_llm(f"""Below are excerpts from two documents. Compare them — highlight key similarities and differences as bullet points.

Document 1 ({doc1['name']}):
{t1}

Document 2 ({doc2['name']}):
{t2}
""")

# ============================================================
# UI: LOGIN
# ============================================================
def login_screen():
    inject_css()
    st.markdown(f"""
    <div class="main-header" style="justify-content:center; text-align:center;">
        <span class="logo-orb">🧠</span>
        <div>
            <h1>{APP_TITLE}</h1>
            <p>Sign in to access your enterprise knowledge assistant</p>
        </div>
    </div>
    """, unsafe_allow_html=True)
    _, col, _ = st.columns([1, 1.1, 1])
    with col:
        with st.form("login_form"):
            username = st.text_input("Username", placeholder="e.g. hooria.zahoor")
            st.text_input("Password", type="password", placeholder="demo mode — any password works")
            submitted = st.form_submit_button("🔐 Login", use_container_width=True)
            if submitted:
                if username.strip():
                    st.session_state.authenticated = True
                    st.session_state.username = username.strip()
                    st.rerun()
                else:
                    st.error("Username is required.")
        st.caption("This is a simulated session for demo purposes — no real credentials are stored.")

# ============================================================
# UI: SIDEBAR
# ============================================================
def sidebar():
    with st.sidebar:
        st.markdown(f"### 👋 {st.session_state.username}")
        c1, c2 = st.columns(2)
        with c1:
            st.session_state.dark_mode = st.toggle("🌙 Dark", value=st.session_state.dark_mode)
        with c2:
            if st.button("🚪 Logout", use_container_width=True):
                st.session_state.authenticated = False
                st.rerun()

        st.divider()
        st.markdown("#### 🔑 Gemini API Key")
        key_input = st.text_input("GOOGLE_API_KEY", value=st.session_state.api_key, type="password", label_visibility="collapsed")
        st.session_state.api_key = key_input
        if not GEMINI_AVAILABLE:
            st.warning("`google-generativeai` not installed.")

        st.divider()
        st.markdown("#### 📊 Quick Stats")
        docs = st.session_state.documents
        total_chunks = sum(d["chunk_count"] for d in docs.values())
        s1, s2 = st.columns(2)
        s1.markdown(f"<div class='metric-card'><div class='value'>{len(docs)}</div><div class='label'>Documents</div></div>", unsafe_allow_html=True)
        s2.markdown(f"<div class='metric-card'><div class='value'>{total_chunks}</div><div class='label'>Chunks</div></div>", unsafe_allow_html=True)
        st.write("")
        s3, s4 = st.columns(2)
        s3.markdown(f"<div class='metric-card'><div class='value'>{st.session_state.total_tokens}</div><div class='label'>Tokens</div></div>", unsafe_allow_html=True)
        s4.markdown(f"<div class='metric-card'><div class='value'>${st.session_state.total_cost:.4f}</div><div class='label'>Est. Cost</div></div>", unsafe_allow_html=True)

        st.divider()
        st.markdown("#### 📚 Document Library")
        if not docs:
            st.caption("No documents uploaded yet.")
        for doc_id, doc in docs.items():
            st.markdown(f"""<div class="doc-card">
                <b>{doc['name']}</b><br>
                <span class="badge">{doc['type'].upper()}</span>
                <span class="badge badge-green">{doc['chunk_count']} chunks</span>
                <div class="subtext">{doc['status']} · {doc['uploaded_at']}</div>
            </div>""", unsafe_allow_html=True)
            bc1, bc2 = st.columns(2)
            if bc1.button("🗑️ Delete", key=f"del_{doc_id}", use_container_width=True):
                delete_document(doc_id)
                st.rerun()
            if bc2.button("🔄 Refresh", key=f"ref_{doc_id}", use_container_width=True):
                refresh_embeddings(doc_id)
                st.rerun()

# ============================================================
# UI: TABS
# ============================================================
def tab_upload():
    st.subheader("📤 Upload Documents")
    st.caption("Supported formats: PDF, TXT, Markdown" + (", DOCX" if DOCX_AVAILABLE else " (install python-docx for DOCX support)"))

    types = ["pdf", "txt", "md"] + (["docx"] if DOCX_AVAILABLE else [])
    files = st.file_uploader("Drop files here", type=types, accept_multiple_files=True)

    if files and st.button("⚙️ Process Documents", type="primary"):
        progress = st.progress(0, text="Starting...")
        results = []
        for i, f in enumerate(files):
            progress.progress((i) / len(files), text=f"Processing {f.name}...")
            doc_id, err = process_document(f)
            results.append((f.name, doc_id, err))
        progress.progress(1.0, text="Done!")

        for name, doc_id, err in results:
            if err:
                st.error(f"❌ {name}: {err}")
            else:
                doc = st.session_state.documents[doc_id]
                st.success(f"✅ {name} — {doc['pages'] or 'N/A'} pages, {doc['chunk_count']} chunks")

    if st.session_state.documents:
        st.divider()
        st.markdown("##### Processing Summary")
        rows = [{
            "Document": d["name"], "Type": d["type"].upper(), "Pages": d["pages"] or "N/A",
            "Chunks": d["chunk_count"], "Status": d["status"], "Uploaded": d["uploaded_at"]
        } for d in st.session_state.documents.values()]
        st.dataframe(rows, use_container_width=True, hide_index=True)

def tab_chat():
    st.subheader("💬 Chat with Your Documents")

    doc_names = [d["name"] for d in st.session_state.documents.values()]
    c1, c2 = st.columns([2, 1])
    with c1:
        doc_filter = st.multiselect("🔍 Search within specific documents (optional)", doc_names, placeholder="All documents")
    with c2:
        search_mode = st.radio("Search mode", ["Semantic", "Hybrid"], horizontal=True)

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("hits"):
                with st.expander("📎 Sources & Retrieved Chunks"):
                    for h in msg["hits"]:
                        meta = h["metadata"]
                        page_label = "N/A" if meta["page"] == 0 else meta["page"]
                        st.markdown(f"""<div class="citation-chip">
                            <b>{meta['doc_name']}</b> · Page {page_label} · Chunk #{meta['chunk_index']}<br>
                            <span class="subtext">{h['text'][:220]}...</span>
                        </div>""", unsafe_allow_html=True)

    if prompt := st.chat_input("Ask a question about your documents..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Searching documents & generating answer..."):
                answer, hits = generate_answer(prompt, st.session_state.messages, doc_filter or None, search_mode)
            st.markdown(answer)
            if hits:
                with st.expander("📎 Sources & Retrieved Chunks"):
                    for h in hits:
                        meta = h["metadata"]
                        page_label = "N/A" if meta["page"] == 0 else meta["page"]
                        st.markdown(f"""<div class="citation-chip">
                            <b>{meta['doc_name']}</b> · Page {page_label} · Chunk #{meta['chunk_index']}<br>
                            <span class="subtext">{h['text'][:220]}...</span>
                        </div>""", unsafe_allow_html=True)
        st.session_state.messages.append({"role": "assistant", "content": answer, "hits": hits})

    st.divider()
    e1, e2 = st.columns(2)
    with e1:
        if st.session_state.messages and st.button("📥 Export Chat as Markdown"):
            lines = [f"# Chat Export — {st.session_state.username}", f"_{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}_\n"]
            for m in st.session_state.messages:
                lines.append(f"**{m['role'].capitalize()}:** {m['content']}\n")
            st.download_button("⬇️ Download .md", "\n".join(lines), file_name="chat_export.md", mime="text/markdown")
    with e2:
        if st.session_state.messages and st.button("🧹 Clear Chat History"):
            st.session_state.messages = []
            st.rerun()

def tab_library():
    st.subheader("📚 Document Management")
    docs = st.session_state.documents
    if not docs:
        st.info("No documents uploaded yet — go to the Upload tab to get started.")
        return

    for doc_id, doc in docs.items():
        with st.expander(f"📄 {doc['name']}  ·  {doc['chunk_count']} chunks  ·  {doc['status']}"):
            m1, m2, m3 = st.columns(3)
            m1.markdown(f"<div class='metric-card'><div class='value'>{doc['pages'] or 'N/A'}</div><div class='label'>Pages</div></div>", unsafe_allow_html=True)
            m2.markdown(f"<div class='metric-card'><div class='value'>{doc['chunk_count']}</div><div class='label'>Chunks</div></div>", unsafe_allow_html=True)
            m3.markdown(f"<div class='metric-card'><div class='value'>{doc['type'].upper()}</div><div class='label'>Format</div></div>", unsafe_allow_html=True)

            st.write("")
            b1, b2, b3, b4 = st.columns(4)
            if b1.button("📝 Summarize", key=f"sum_{doc_id}"):
                with st.spinner("Generating summary..."):
                    doc["summary"] = generate_summary(doc)
            if b2.button("❓ Suggest Questions", key=f"sq_{doc_id}"):
                with st.spinner("Generating suggested questions..."):
                    doc["suggested_questions"] = generate_suggested_questions(doc)
            if b3.button("🔄 Refresh Embeddings", key=f"refl_{doc_id}"):
                refresh_embeddings(doc_id)
                st.success("Embeddings refreshed.")
            if b4.button("🗑️ Delete", key=f"dell_{doc_id}"):
                delete_document(doc_id)
                st.rerun()

            if doc.get("summary"):
                st.markdown("**Summary:**")
                st.info(doc["summary"])
            if doc.get("suggested_questions"):
                st.markdown("**Suggested Questions:**")
                st.success(doc["suggested_questions"])

def tab_analytics():
    st.subheader("📊 Analytics & Token Usage")
    docs = st.session_state.documents
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(f"<div class='metric-card'><div class='value'>{len(docs)}</div><div class='label'>Documents</div></div>", unsafe_allow_html=True)
    c2.markdown(f"<div class='metric-card'><div class='value'>{sum(d['chunk_count'] for d in docs.values())}</div><div class='label'>Total Chunks</div></div>", unsafe_allow_html=True)
    c3.markdown(f"<div class='metric-card'><div class='value'>{st.session_state.total_tokens}</div><div class='label'>Tokens Used</div></div>", unsafe_allow_html=True)
    c4.markdown(f"<div class='metric-card'><div class='value'>${st.session_state.total_cost:.4f}</div><div class='label'>Est. Cost</div></div>", unsafe_allow_html=True)

    st.write("")
    if docs:
        st.markdown("##### Chunks per Document")
        chart_data = {d["name"]: d["chunk_count"] for d in docs.values()}
        st.bar_chart(chart_data)
    else:
        st.caption("Upload documents to see analytics.")

    st.divider()
    st.markdown("##### Session Info")
    st.json({
        "user": st.session_state.username,
        "messages_exchanged": len(st.session_state.messages),
        "embedding_model": EMBED_MODEL_NAME,
        "llm_model": MODEL_NAME,
    })

def tab_compare():
    st.subheader("🔍 Document Comparison")
    docs = st.session_state.documents
    if len(docs) < 2:
        st.info("Upload at least 2 documents to use comparison.")
        return
    names = {d["name"]: doc_id for doc_id, d in docs.items()}
    c1, c2 = st.columns(2)
    d1 = c1.selectbox("Document 1", list(names.keys()), key="cmp1")
    d2 = c2.selectbox("Document 2", list(names.keys()), index=min(1, len(names) - 1), key="cmp2")
    if st.button("⚖️ Compare Documents", type="primary"):
        if d1 == d2:
            st.warning("Please select two different documents.")
        else:
            with st.spinner("Comparing documents..."):
                result = compare_documents(docs[names[d1]], docs[names[d2]])
            st.markdown(result)

# ============================================================
# MAIN
# ============================================================
def main_app():
    inject_css()
    st.markdown(f"""
    <div class="main-header">
        <span class="logo-orb">🧠</span>
        <div>
            <h1>{APP_TITLE}</h1>
            <p>Upload documents, ask questions, and get grounded answers with citations.</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    sidebar()

    tabs = st.tabs(["📤 Upload", "💬 Chat", "📚 Library", "📊 Analytics", "🔍 Compare"])
    with tabs[0]:
        tab_upload()
    with tabs[1]:
        tab_chat()
    with tabs[2]:
        tab_library()
    with tabs[3]:
        tab_analytics()
    with tabs[4]:
        tab_compare()

# ============================================================
# ENTRY POINT
# ============================================================
if not st.session_state.authenticated:
    login_screen()
else:
    main_app()