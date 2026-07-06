# 🧠 AI Workspace

A unified, professional interface for interacting with AI language models — built as part of the **AI Summer Internship 2026, Track 2: NLP & AI Agents (Week 1, Assignment 3)**.

> Chat naturally, define custom system prompts, switch models, use ready-made prompt templates, and keep a full conversation history — all in one clean workspace.

---

## ✨ Features

### Required
- **Chat Interface** — natural, multi-turn conversation with the AI.
- **System Prompt** — choose a preset (e.g. *Professional Software Engineer*, *AI Research Assistant*) or define your own custom system prompt.
- **Model Selection** — switch between `gemini-2.5-flash`, `gemini-2.5-flash-lite`, and `gemini-2.5-pro` from the sidebar.
- **Prompt Templates** — one-click templates: Summarize Text, Explain Code, Generate Ideas, Rewrite Content, Translate, Create Email, Brainstorm.
- **Conversation History** — all messages persist for the duration of the session, per chat.
- **Markdown Rendering** — responses render with proper formatting (bold, lists, code blocks, etc.).
- **Error Handling** — graceful handling of invalid API keys, connection failures, and empty prompts.
- **Responsive, Professional UI** — clean layout with a custom-styled sidebar and hero header.

### Bonus
- 🌙 **Dark Mode** — toggle in the sidebar.
- ⬇️ **Export Chat** — download the current conversation as a `.json` file.
- ⭐ **Save Prompt Templates** — create and save your own custom templates.
- 🔢 **Token Usage Counter** — running total of tokens used in the session.
- ⏱️ **Response Time Measurement** — shown under every AI response.
- 🗂️ **Multiple Chat Sessions** — create, switch between, and delete separate chats.

---

## 🏗️ Architecture

```
User Input (Chat / Template)
        ↓
   Frontend (Streamlit UI)
        ↓
  Backend Logic (app.py)
   - builds messages payload
   - attaches system prompt
   - applies model + temperature settings
        ↓
     Google Gemini API (LLM)
        ↓
   Response returned → parsed → rendered as Markdown
        ↓
  Stored in session conversation history
```

**Request flow:** user types a message (or picks a template) → clicks **Send** → the app validates the input → builds a message list (system prompt + full chat history) → sends it to Google's Gemini API (via its OpenAI-compatible Chat Completions endpoint) → receives a response.

> **Why Gemini?** This app uses the standard `openai` Python library pointed at Google's OpenAI-compatible Gemini endpoint (`base_url="https://generativelanguage.googleapis.com/v1beta/openai/"`). This means the exact same code pattern used for OpenAI works here — Gemini is simply a **free** alternative, since Google's free tier requires no credit card.

**Response flow:** the response text is rendered with Markdown formatting, response time and token usage are calculated and displayed, and the message is appended to that session's history.

**Error handling:** every API call is wrapped in a `try/except` block that catches `AuthenticationError` (invalid key), `APIConnectionError` (network issues), `RateLimitError` (quota/rate limits), and generic `APIError`/`Exception` as a fallback — each shown to the user as a friendly, readable message instead of a crash.

---

## 📦 Installation Guide

### 1. Clone or download this folder
```bash
cd AI-Workspace
```

### 2. (Recommended) Create a virtual environment
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Get a free Gemini API key

1. Go to **[aistudio.google.com/apikey](https://aistudio.google.com/apikey)**
2. Sign in with any Google account (no credit card required)
3. Click **"Create API key"**
4. Choose **"Create API key in new project"** (or select an existing project)
5. Copy the key that appears (starts with `AIza...`)

### 5. Set up your API key

Copy `.env.example` to `.env` and add your real Gemini API key:
```bash
cp .env.example .env
```
Then edit `.env`:
```
GEMINI_API_KEY=AIza-your-real-key-here
```
> You can also paste your API key directly into the sidebar at runtime if you prefer not to use a `.env` file.

### 6. Run the app
```bash
streamlit run app.py
```

The app will open automatically at `http://localhost:8501`.

---

## 🗂️ Project Structure

```
AI-Workspace/
├── app.py              # Main Streamlit application
├── requirements.txt    # Python dependencies
├── .env.example         # Environment variable template
└── README.md            # This file
```

---

## 🧪 How to Test Error Handling

- **Empty prompt** → click "Send" with nothing typed → shows a warning, no API call is made.
- **Invalid API key** → enter a fake key in the sidebar → shows an authentication error message.
- **Connection failure** → disconnect your internet and send a message → shows a connection error message.

---

## 👩‍💻 Author

**Hooria Zahoor**
BS Artificial Intelligence, The University of Faisalabad
AI Summer Internship 2026 — Track 2: NLP & AI Agents

## Demo Video

Watch the Week 1 demo video here: [AI Workspace — Week 1 Demo](https://youtu.be/eEVOQno8nTA)