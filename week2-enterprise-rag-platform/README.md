# 🧠 Enterprise Document Intelligence Platform — Week 2

A RAG-powered enterprise knowledge assistant built for the **AI Summer Internship 2026 (NLP & AI Agents Track)**. Upload multiple documents, ask questions in natural language, and get grounded, cited answers — powered by a full retrieval-augmented generation pipeline built from scratch.

**Author:** Hooria Zahoor
**Program:** BS Artificial Intelligence, The University of Faisalabad (Session 2023–2027)
**Supervisor:** Sir Arham
**Track:** NLP & AI Agents — AI Summer Internship 2026

---

## 📋 Table of Contents

- [Overview](#-overview)
- [Week 2 Assignments](#-week-2-assignments)
- [Features](#-features)
- [Tech Stack](#-tech-stack)
- [Architecture](#-architecture)
- [Quick Start](#-quick-start)
- [Repository Structure](#-repository-structure)
- [Screenshots](#-screenshots)
- [Demo Video](#-demo-video)
- [Key Learnings](#-key-learnings)

---

## 🔍 Overview

This project is a full-stack **Retrieval-Augmented Generation (RAG)** application — an "Enterprise Document Intelligence Platform" that lets a user upload internal documents (policies, manuals, reports) and chat with them naturally, with every answer traceable back to its exact source document and page. It was built end-to-end across Week 2 of the internship: from architecture design, through implementation, to controlled experiments measuring what actually improves retrieval quality.

---

## 📚 Week 2 Assignments

| # | Assignment | Description | Deliverable |
|---|---|---|---|
| 1 | **Enterprise Document Intelligence Platform** | Full-stack RAG application: multi-document upload, processing, chunking, embeddings, semantic + hybrid search, conversational chat with citations, document management, and an analytics dashboard. | [`app.py`](./app.py) |
| 2 | **Technical Research Report** | 4-page research report on designing enterprise RAG systems — covers architecture, embeddings, chunking, retrieval, prompt construction, vector databases, hallucination reduction, and future improvements, with original diagrams. | [`docs/Enterprise_RAG_Technical_Report.docx`](./docs/Enterprise_RAG_Technical_Report.docx) |
| 3 | **Architecture Documentation** | 3-page system architecture write-up tracing the full pipeline — User → Frontend → Backend → Document Processing → Chunking → Embedding Generation → Vector Database → Retriever → LLM → Response — with a diagram and a worked example for every component. | [`docs/Architecture_Documentation.docx`](./docs/Architecture_Documentation.docx) · [`docs/architecture_diagram.png`](./docs/architecture_diagram.png) |
| 4 | **Experiments** | Four controlled experiments run with real code (not simulated) on a test corpus: chunk size, chunk overlap, prompt template comparison, and embedding model comparison, each with measured retrieval accuracy. | [`docs/RAG_Experiments_Report.docx`](./docs/RAG_Experiments_Report.docx) · runnable notebook: [`docs/RAG_Experiments.ipynb`](./docs/RAG_Experiments.ipynb) · raw code: [`experiments/`](./experiments) |
| 5 | **Builder Journal** | Reflective journal on what worked, what didn't, how problems were debugged, and what the process taught about RAG systems in practice. | [`docs/Builder_Journal.docx`](./docs/Builder_Journal.docx) |

---

## ✨ Features

**Core**
- 📤 Multi-document upload — PDF, TXT, Markdown, DOCX
- ⚙️ Automatic processing — text extraction, cleaning, chunking, with live page/chunk stats
- 🧬 Embeddings via `sentence-transformers`, persisted in ChromaDB
- 🔍 Semantic search with a visible "retrieved chunks" panel
- 💬 Conversational chat — history-aware follow-ups
- 📎 Source citations on every answer — document name, page, chunk reference
- 🗂️ Document management — view, delete, refresh embeddings

**Bonus**
- 🔀 Hybrid search (semantic + keyword)
- 🎯 Metadata filtering — search within specific documents
- ⚖️ Document comparison
- 📝 Automatic summarization + suggested questions per document
- 📥 Chat export to Markdown
- 💰 Token usage & cost dashboard
- 🌌 Dark mode with an animated galaxy-themed UI

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Frontend / UI | Streamlit |
| Backend orchestration | Python |
| Document parsing | pypdf, python-docx |
| Chunking | LangChain text splitters |
| Embeddings | sentence-transformers (`all-MiniLM-L6-v2`) |
| Vector database | ChromaDB |
| LLM | Google Gemini API |
| Experiments | scikit-learn (TF-IDF / LSA), NumPy, Matplotlib |

---

## 🏗️ Architecture

```
User → Frontend → Backend → Document Processing → Chunking →
Embedding Generation → Vector Database → Retriever → LLM → Response
```

Full breakdown of every component (with examples) is in [`docs/Architecture_Documentation.docx`](./docs/Architecture_Documentation.docx); the diagram alone is at [`docs/architecture_diagram.png`](./docs/architecture_diagram.png).

---

## 🚀 Quick Start

```bash
# 1. Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate            # Windows
# source venv/bin/activate       # Mac/Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Add your Gemini API key
copy .env.example .env           # Windows: copy | Mac/Linux: cp
# then open .env and set GOOGLE_API_KEY=your_actual_key

# 4. Run the app
streamlit run app.py
```

Full step-by-step guide (with troubleshooting for common install errors): [`docs/Installation_Guide.md`](./docs/Installation_Guide.md)

Get a free Gemini API key: https://aistudio.google.com/apikey

---

## 📁 Repository Structure

```
week2-enterprise-rag-platform/
├── app.py                                  # main Streamlit application (source code)
├── requirements.txt
├── .env.example
├── README.md                               # you are here
│
├── docs/
│   ├── architecture_diagram.png
│   ├── Architecture_Documentation.docx      # Assignment 3
│   ├── Enterprise_RAG_Technical_Report.docx # Assignment 2
│   ├── RAG_Experiments_Report.docx          # Assignment 4
│   ├── RAG_Experiments.ipynb                # Assignment 4 (runnable)
│   ├── Builder_Journal.docx                 # Assignment 5
│   └── Installation_Guide.md
│
├── experiments/                             # reproducible code behind Assignment 4
│   ├── corpus.py
│   ├── retrieval_utils.py
│   ├── exp1_chunk_size.py
│   ├── exp2_overlap.py
│   ├── exp4_embeddings.py
│   ├── make_charts.py
│   └── *_results.json
│
├── screenshots/
└── demo/
    └── DEMO_VIDEO_LINK.md
```

---

## 🖼️ Screenshots

*(Add screenshots to `screenshots/` and reference them below)*

| Chat with Citations | Document Library | Analytics |
|---|---|---|
| ![Chat](screenshots/03_chat.png) | ![Library](screenshots/04_library.png) | ![Analytics](screenshots/05_analytics.png) |

---

## 🎥 Demo Video

See [`demo/DEMO_VIDEO_LINK.md`](./demo/DEMO_VIDEO_LINK.md)

---

## 💡 Key Learnings

- **Retrieval quality, not the LLM, is usually the real bottleneck** — a perfectly grounded prompt can't fix a wrong or incomplete chunk retrieved in the first place.
- **Chunk overlap has a measurable effect** — a small overlap (~10–20% of chunk size) meaningfully improved retrieval accuracy over zero overlap in controlled testing.
- **Hallucination reduction is layered, not a single fix** — grounding, explicit instructions, citation requirements, and a real "I don't know" path all have to work together.
- **Embedding choice matters most on paraphrased queries** — a system can look perfect on in-vocabulary test questions and still fail the moment a real user phrases something in their own words.

Full reflection: [`docs/Builder_Journal.docx`](./docs/Builder_Journal.docx)