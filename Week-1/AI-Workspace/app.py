"""
AI Workspace
A unified, professional interface for interacting with AI language models.

Built for: AI Summer Internship 2026 — Track 2: NLP & AI Agents (Week 1, Assignment 3)
Author: Hooria Zahoor
"""

import os
import json
import time
from datetime import datetime

import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI, AuthenticationError, APIConnectionError, RateLimitError, APIError

# --------------------------------------------------------------------------------
# CONFIG & CONSTANTS
# --------------------------------------------------------------------------------

load_dotenv()

st.set_page_config(
    page_title="AI Workspace",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# We use Google Gemini via its free, OpenAI-compatible endpoint.
# This means we can keep using the same `openai` Python library —
# we just point it at Gemini's base_url and use a Gemini API key instead.
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

AVAILABLE_MODELS = {
    "Gemini 2.5 Flash (fast, free-tier friendly)": "gemini-2.5-flash",
    "Gemini 2.5 Flash-Lite (fastest, lightweight)": "gemini-2.5-flash-lite",
    "Gemini 2.5 Pro (most capable)": "gemini-2.5-pro",
}

DEFAULT_TEMPLATES = {
    "📝 Summarize Text": "Summarize the following text concisely while preserving the key points:\n\n",
    "💻 Explain Code": "Explain what the following code does, step by step:\n\n",
    "💡 Generate Ideas": "Generate 5 creative ideas about the following topic:\n\n",
    "✍️ Rewrite Content": "Rewrite the following content to make it clearer and more engaging:\n\n",
    "🌐 Translate": "Translate the following text to [target language]:\n\n",
    "📧 Create Email": "Write a professional email about the following:\n\n",
    "🧩 Brainstorm": "Brainstorm a list of possibilities for the following:\n\n",
}

SYSTEM_PROMPT_PRESETS = {
    "Default Assistant": "You are a helpful, knowledgeable AI assistant.",
    "Professional Software Engineer": "You are a professional software engineer. Answer with technical precision, best practices, and clean code examples.",
    "AI Research Assistant": "You are an AI research assistant. Provide well-structured, evidence-based, academically rigorous answers.",
    "Custom": "",
}

# Minimal sparkle-mark icon used for branding (in place of an emoji, for a more
# premium, professional "AI product" feel).
SPARKLE_SVG = """<svg width="22" height="22" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M12 2.5L14.3 8.6L20.5 10.9L14.3 13.2L12 19.3L9.7 13.2L3.5 10.9L9.7 8.6L12 2.5Z" fill="white"/>
<circle cx="19" cy="4" r="1.4" fill="white" opacity="0.85"/>
<circle cx="4.5" cy="18.5" r="1" fill="white" opacity="0.7"/>
</svg>"""

# --------------------------------------------------------------------------------
# SESSION STATE INITIALIZATION
# --------------------------------------------------------------------------------

def init_state():
    defaults = {
        "dark_mode": False,
        "api_key": os.getenv("GEMINI_API_KEY", ""),
        "model_label": list(AVAILABLE_MODELS.keys())[0],
        "temperature": 0.7,
        "system_prompt_choice": "Default Assistant",
        "custom_system_prompt": "",
        "custom_templates": {},
        "compose_version": 0,
        "total_tokens": 0,
        "chats": {
            "Chat 1": {
                "history": [],
                "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
        },
        "current_chat": "Chat 1",
        "chat_counter": 1,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


init_state()

# --------------------------------------------------------------------------------
# STYLING (Light / Dark mode)
# --------------------------------------------------------------------------------

def inject_css():
    if st.session_state.dark_mode:
        bg_1, bg_2 = "#0A0E1A", "#131A2E"
        panel = "rgba(22, 27, 45, 0.65)"
        panel_solid = "#161B2D"
        text, subtext = "#EAEEFB", "#9BA3BF"
        border = "rgba(255, 255, 255, 0.08)"
        input_bg = "rgba(255, 255, 255, 0.06)"
        bubble_user = "rgba(108, 99, 255, 0.16)"
        bubble_ai = "rgba(255, 255, 255, 0.04)"
        blob_1, blob_2, blob_3, blob_4 = (
            "rgba(108, 99, 255, 0.55)", "rgba(168, 85, 247, 0.45)",
            "rgba(56, 189, 248, 0.40)", "rgba(236, 72, 153, 0.35)",
        )
    else:
        bg_1, bg_2 = "#F3F5FC", "#EAEEFC"
        panel = "rgba(255, 255, 255, 0.72)"
        panel_solid = "#FFFFFF"
        text, subtext = "#1B1F30", "#666F8C"
        border = "rgba(20, 25, 50, 0.08)"
        input_bg = "rgba(255, 255, 255, 0.9)"
        bubble_user = "rgba(108, 99, 255, 0.10)"
        bubble_ai = "rgba(255, 255, 255, 0.9)"
        blob_1, blob_2, blob_3, blob_4 = (
            "rgba(108, 99, 255, 0.40)", "rgba(168, 85, 247, 0.35)",
            "rgba(56, 189, 248, 0.30)", "rgba(236, 72, 153, 0.25)",
        )

    accent = "#6C63FF"
    accent_2 = "#A855F7"
    accent_particle = "#A855F7" if st.session_state.dark_mode else "#6C63FF"

    st.markdown(
        f"""
        <style>
        @keyframes floatBlobA {{
            0%, 100% {{ transform: translate(0, 0) scale(1); }}
            50% {{ transform: translate(110px, 90px) scale(1.2); }}
        }}
        @keyframes floatBlobB {{
            0%, 100% {{ transform: translate(0, 0) scale(1); }}
            50% {{ transform: translate(-120px, -80px) scale(1.15); }}
        }}
        @keyframes floatBlobC {{
            0%, 100% {{ transform: translate(0, 0) scale(1); }}
            50% {{ transform: translate(90px, -110px) scale(1.25); }}
        }}
        @keyframes floatBlobD {{
            0%, 100% {{ transform: translate(0, 0) scale(1); }}
            50% {{ transform: translate(-80px, 100px) scale(1.1); }}
        }}
        @keyframes particleFloat {{
            0% {{ transform: translateY(0) translateX(0); opacity: 0; }}
            10% {{ opacity: 1; }}
            90% {{ opacity: 1; }}
            100% {{ transform: translateY(-90vh) translateX(30px); opacity: 0; }}
        }}
        @keyframes heroShift {{
            0% {{ background-position: 0% 50%; }}
            50% {{ background-position: 100% 50%; }}
            100% {{ background-position: 0% 50%; }}
        }}

        .stApp {{
            background: linear-gradient(160deg, {bg_1} 0%, {bg_2} 100%);
            color: {text};
            position: relative;
            isolation: isolate;
        }}
        .ai-bg-layer {{
            position: fixed;
            inset: 0;
            z-index: -1;
            overflow: hidden;
            pointer-events: none;
        }}
        .ai-blob {{
            position: absolute;
            border-radius: 50%;
            filter: blur(60px);
        }}
        .ai-blob.b1 {{
            width: 420px; height: 420px;
            background: {blob_1};
            top: -100px; left: -80px;
            animation: floatBlobA 16s ease-in-out infinite;
        }}
        .ai-blob.b2 {{
            width: 460px; height: 460px;
            background: {blob_2};
            bottom: -120px; right: -100px;
            animation: floatBlobB 19s ease-in-out infinite;
        }}
        .ai-blob.b3 {{
            width: 340px; height: 340px;
            background: {blob_3};
            top: 35%; right: 8%;
            animation: floatBlobC 14s ease-in-out infinite;
        }}
        .ai-blob.b4 {{
            width: 300px; height: 300px;
            background: {blob_4};
            bottom: 15%; left: 12%;
            animation: floatBlobD 21s ease-in-out infinite;
        }}
        .ai-particle {{
            position: absolute;
            bottom: -20px;
            width: 5px;
            height: 5px;
            border-radius: 50%;
            background: {accent_particle};
            animation: particleFloat linear infinite;
        }}
        header[data-testid="stHeader"] {{
            background: transparent;
        }}

        /* Sidebar — frosted glass panel */
        section[data-testid="stSidebar"] {{
            background: {panel};
            backdrop-filter: blur(18px);
            -webkit-backdrop-filter: blur(18px);
            border-right: 1px solid {border};
            position: relative;
            z-index: 1;
        }}
        section[data-testid="stSidebar"] * {{
            color: {text};
        }}

        /* Main content sits above the blobs */
        div[data-testid="stAppViewContainer"] {{
            position: relative;
            z-index: 1;
        }}
        .main .block-container {{
            position: relative;
            z-index: 1;
        }}

        /* Top bar — minimal, professional branding */
        .ai-topbar {{
            display: flex;
            align-items: center;
            gap: 14px;
            padding: 2px 0 20px 0;
            border-bottom: 1px solid {border};
            margin-bottom: 24px;
        }}
        .ai-logo-mark {{
            width: 42px;
            height: 42px;
            min-width: 42px;
            border-radius: 12px;
            background: linear-gradient(135deg, {accent} 0%, {accent_2} 100%);
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 6px 16px rgba(108, 99, 255, 0.35);
        }}
        .ai-topbar-title {{
            font-size: 21px;
            font-weight: 800;
            color: {text};
            letter-spacing: -0.01em;
            display: flex;
            align-items: center;
            gap: 9px;
        }}
        .ai-version-badge {{
            font-size: 10.5px;
            font-weight: 700;
            color: {accent};
            background: {input_bg};
            border: 1px solid {border};
            padding: 2px 8px;
            border-radius: 20px;
            letter-spacing: 0.02em;
        }}
        .ai-topbar-sub {{
            font-size: 13px;
            color: {subtext};
            margin-top: 2px;
        }}

        /* Empty-state welcome card */
        .ai-empty-state {{
            text-align: center;
            padding: 48px 20px 26px 20px;
        }}
        .ai-empty-icon {{
            width: 60px;
            height: 60px;
            margin: 0 auto 18px auto;
            border-radius: 16px;
            background: linear-gradient(135deg, {accent} 0%, {accent_2} 100%);
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 10px 28px rgba(108, 99, 255, 0.3);
        }}
        .ai-empty-state h2 {{
            font-size: 21px;
            font-weight: 800;
            color: {text};
            margin: 0 0 8px 0;
        }}
        .ai-empty-state p {{
            font-size: 13.5px;
            color: {subtext};
            max-width: 460px;
            margin: 0 auto;
        }}

        /* Chat bubbles — glass cards */
        div[data-testid="stChatMessage"] {{
            background: {bubble_ai};
            border: 1px solid {border};
            border-radius: 14px;
            backdrop-filter: blur(10px);
        }}
        div[data-testid="stChatMessage"]:has(div[data-testid="stChatMessageAvatarUser"]) {{
            background: {bubble_user};
            border: 1px solid rgba(108, 99, 255, 0.25);
        }}
        .msg-meta {{
            font-size: 11px;
            color: {subtext};
            margin-top: -6px;
            margin-bottom: 8px;
        }}

        /* Buttons — unified accent gradient */
        .stButton>button {{
            border-radius: 10px;
            border: 1px solid {border};
            background: {input_bg};
            color: {text};
            font-weight: 500;
            transition: all 0.15s ease;
        }}
        .stButton>button:hover {{
            border-color: {accent};
            color: {accent};
            transform: translateY(-1px);
        }}
        button[kind="primary"], .stButton>button[kind="primary"] {{
            background: linear-gradient(120deg, {accent}, {accent_2}) !important;
            border: none !important;
            color: white !important;
            box-shadow: 0 6px 18px rgba(108, 99, 255, 0.35);
        }}
        button[kind="primary"]:hover {{
            filter: brightness(1.08);
            transform: translateY(-1px);
        }}
        .template-btn button {{
            width: 100%;
            text-align: left;
        }}

        /* Inputs / selects / textareas — theme-matched, no jarring white boxes */
        div[data-baseweb="select"] > div, div[data-baseweb="base-input"], textarea, input[type="text"], input[type="password"] {{
            background-color: {input_bg} !important;
            color: {text} !important;
            border-radius: 10px !important;
            border: 1px solid {border} !important;
        }}
        div[data-baseweb="popover"] li {{
            background-color: {panel_solid} !important;
            color: {text} !important;
        }}

        /* Radio pills for chat sessions */
        div[role="radiogroup"] label {{
            background: {input_bg};
            border: 1px solid {border};
            border-radius: 10px;
            padding: 6px 10px;
            margin-bottom: 4px;
        }}

        .sidebar-section-title {{
            font-size: 12px;
            font-weight: 700;
            letter-spacing: 0.05em;
            text-transform: uppercase;
            color: {accent};
            margin-top: 18px;
            margin-bottom: 6px;
            opacity: 0.85;
        }}
        .token-badge {{
            display: inline-block;
            background: linear-gradient(120deg, {accent}, {accent_2});
            color: white;
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
        }}

        /* Info / warning / error boxes — glass style */
        div[data-testid="stAlert"] {{
            background: {panel} !important;
            backdrop-filter: blur(10px);
            border: 1px solid {border} !important;
            border-radius: 12px;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def inject_background_layer():
    import random
    particles_html = ""
    for i in range(14):
        left = random.randint(2, 98)
        duration = random.randint(14, 26)
        delay = random.randint(0, 20)
        size = random.choice([3, 4, 5, 6])
        particles_html += (
            f'<div class="ai-particle" style="left:{left}%; width:{size}px; height:{size}px; '
            f'animation-duration:{duration}s; animation-delay:-{delay}s;"></div>'
        )

    st.markdown(
        f"""
        <div class="ai-bg-layer">
            <div class="ai-blob b1"></div>
            <div class="ai-blob b2"></div>
            <div class="ai-blob b3"></div>
            <div class="ai-blob b4"></div>
            {particles_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


inject_css()
inject_background_layer()
# --------------------------------------------------------------------------------

with st.sidebar:
    st.markdown("### 🧠 AI Workspace")
    st.caption("Your unified interface for AI models")

    # ---- API Key ----
    st.markdown('<div class="sidebar-section-title">API Configuration</div>', unsafe_allow_html=True)
    api_key_input = st.text_input(
        "Gemini API Key",
        value=st.session_state.api_key,
        type="password",
        placeholder="AIza...",
        help="Get a free key at aistudio.google.com/apikey. Loaded from .env if available; you can override it here for this session.",
    )
    st.session_state.api_key = api_key_input

    # ---- Model selection ----
    st.markdown('<div class="sidebar-section-title">Model Selection</div>', unsafe_allow_html=True)
    st.session_state.model_label = st.selectbox(
        "Choose a model",
        options=list(AVAILABLE_MODELS.keys()),
        index=list(AVAILABLE_MODELS.keys()).index(st.session_state.model_label),
        label_visibility="collapsed",
    )

    with st.expander("⚙️ Advanced settings"):
        st.session_state.temperature = st.slider(
            "Temperature (creativity)", 0.0, 1.5, st.session_state.temperature, 0.1
        )
        st.caption("Lower = more focused & predictable. Higher = more creative & varied.")

    # ---- System prompt ----
    st.markdown('<div class="sidebar-section-title">System Prompt</div>', unsafe_allow_html=True)
    st.session_state.system_prompt_choice = st.selectbox(
        "Preset",
        options=list(SYSTEM_PROMPT_PRESETS.keys()),
        index=list(SYSTEM_PROMPT_PRESETS.keys()).index(st.session_state.system_prompt_choice),
        label_visibility="collapsed",
    )
    if st.session_state.system_prompt_choice == "Custom":
        st.session_state.custom_system_prompt = st.text_area(
            "Define your custom system prompt",
            value=st.session_state.custom_system_prompt,
            placeholder='e.g. "You are a professional software engineer."',
            height=90,
        )
        active_system_prompt = st.session_state.custom_system_prompt
    else:
        active_system_prompt = SYSTEM_PROMPT_PRESETS[st.session_state.system_prompt_choice]
        st.caption(f"💬 {active_system_prompt}")

    # ---- Prompt templates ----
    st.markdown('<div class="sidebar-section-title">Prompt Templates</div>', unsafe_allow_html=True)
    all_templates = {**DEFAULT_TEMPLATES, **st.session_state.custom_templates}
    for name, text in all_templates.items():
        st.markdown('<div class="template-btn">', unsafe_allow_html=True)
        if st.button(name, key=f"tmpl_{name}"):
            st.session_state.compose_version += 1
            st.session_state[f"compose_box_{st.session_state.compose_version}"] = text
        st.markdown("</div>", unsafe_allow_html=True)

    with st.expander("➕ Save a custom template"):
        new_tmpl_name = st.text_input("Template name", key="new_tmpl_name")
        new_tmpl_text = st.text_area("Template text", key="new_tmpl_text", height=70)
        if st.button("Save template"):
            if new_tmpl_name.strip() and new_tmpl_text.strip():
                st.session_state.custom_templates[f"⭐ {new_tmpl_name.strip()}"] = new_tmpl_text
                st.success(f"Saved '{new_tmpl_name}'")
            else:
                st.warning("Please provide both a name and template text.")

    # ---- Chat sessions ----
    st.markdown('<div class="sidebar-section-title">Chat Sessions</div>', unsafe_allow_html=True)
    if st.button("➕ New Chat", use_container_width=True):
        st.session_state.chat_counter += 1
        new_name = f"Chat {st.session_state.chat_counter}"
        st.session_state.chats[new_name] = {
            "history": [],
            "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        st.session_state.current_chat = new_name
        st.rerun()

    chat_names = list(st.session_state.chats.keys())
    st.session_state.current_chat = st.radio(
        "Sessions", chat_names, index=chat_names.index(st.session_state.current_chat),
        label_visibility="collapsed",
    )

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("🗑️ Clear", use_container_width=True):
            st.session_state.chats[st.session_state.current_chat]["history"] = []
            st.rerun()
    with col_b:
        if len(chat_names) > 1 and st.button("❌ Delete", use_container_width=True):
            del st.session_state.chats[st.session_state.current_chat]
            st.session_state.current_chat = list(st.session_state.chats.keys())[0]
            st.rerun()

    # ---- Export chat ----
    st.markdown('<div class="sidebar-section-title">Export</div>', unsafe_allow_html=True)
    current_history = st.session_state.chats[st.session_state.current_chat]["history"]
    export_data = json.dumps(current_history, indent=2)
    st.download_button(
        "⬇️ Export chat (.json)",
        data=export_data,
        file_name=f"{st.session_state.current_chat.replace(' ', '_')}.json",
        mime="application/json",
        use_container_width=True,
    )

    # ---- Dark mode + stats ----
    st.markdown('<div class="sidebar-section-title">Preferences</div>', unsafe_allow_html=True)
    st.session_state.dark_mode = st.toggle("🌙 Dark Mode", value=st.session_state.dark_mode)
    st.markdown(
        f'<span class="token-badge">🔢 {st.session_state.total_tokens} tokens used this session</span>',
        unsafe_allow_html=True,
    )

# --------------------------------------------------------------------------------
# MAIN AREA — HEADER
# --------------------------------------------------------------------------------

st.markdown(
    f"""
    <div class="ai-topbar">
        <div class="ai-logo-mark">{SPARKLE_SVG}</div>
        <div>
            <div class="ai-topbar-title">AI Workspace <span class="ai-version-badge">v1.0</span></div>
            <div class="ai-topbar-sub">One clean interface to chat, prompt, and experiment with AI models.</div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

history = st.session_state.chats[st.session_state.current_chat]["history"]

# ---- Render conversation history ----
for msg in history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant" and "meta" in msg:
            st.markdown(f'<div class="msg-meta">{msg["meta"]}</div>', unsafe_allow_html=True)

if not history:
    st.markdown(
        f"""
        <div class="ai-empty-state">
            <div class="ai-empty-icon">{SPARKLE_SVG}</div>
            <h2>Start a conversation</h2>
            <p>Ask a question naturally, or drop in a prompt template to get going.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    quick_templates = list(DEFAULT_TEMPLATES.items())[:4]
    q_cols = st.columns(len(quick_templates))
    for q_col, (q_name, q_text) in zip(q_cols, quick_templates):
        with q_col:
            if st.button(q_name, key=f"quick_{q_name}", use_container_width=True):
                st.session_state.compose_version += 1
                st.session_state[f"compose_box_{st.session_state.compose_version}"] = q_text

# --------------------------------------------------------------------------------
# COMPOSE BOX
# --------------------------------------------------------------------------------

st.write("")
box_key = f"compose_box_{st.session_state.compose_version}"
compose_col, send_col = st.columns([6, 1])
with compose_col:
    user_input = st.text_area(
        "Message",
        placeholder="Ask anything, or select a template from the sidebar...",
        height=90,
        label_visibility="collapsed",
        key=box_key,
    )
with send_col:
    st.write("")
    st.write("")
    send_clicked = st.button("Send 🚀", use_container_width=True, type="primary")

# --------------------------------------------------------------------------------
# HANDLE SEND
# --------------------------------------------------------------------------------

def get_client():
    return OpenAI(api_key=st.session_state.api_key, base_url=GEMINI_BASE_URL)


if send_clicked:
    prompt_text = user_input.strip()

    # ---- Error handling: empty prompt ----
    if not prompt_text:
        st.warning("⚠️ Please enter a message before sending.")
    # ---- Error handling: missing API key ----
    elif not st.session_state.api_key:
        st.error("🔑 No API key found. Please enter your Gemini API key in the sidebar.")
    else:
        # Add user message to history
        history.append({"role": "user", "content": prompt_text})
        st.session_state.compose_version += 1

        # Build messages payload
        system_prompt = (
            st.session_state.custom_system_prompt
            if st.session_state.system_prompt_choice == "Custom"
            else SYSTEM_PROMPT_PRESETS[st.session_state.system_prompt_choice]
        )
        messages = [{"role": "system", "content": system_prompt}] if system_prompt else []
        messages += [{"role": m["role"], "content": m["content"]} for m in history]

        with st.spinner("🤔 Thinking..."):
            start_time = time.time()
            try:
                client = get_client()
                response = client.chat.completions.create(
                    model=AVAILABLE_MODELS[st.session_state.model_label],
                    messages=messages,
                    temperature=st.session_state.temperature,
                )
                elapsed = time.time() - start_time
                answer = response.choices[0].message.content
                tokens_used = getattr(response.usage, "total_tokens", 0) if response.usage else 0
                st.session_state.total_tokens += tokens_used

                meta = f"⏱️ {elapsed:.2f}s • 🔢 {tokens_used} tokens • 🧩 {AVAILABLE_MODELS[st.session_state.model_label]}"
                history.append({"role": "assistant", "content": answer, "meta": meta})

            # ---- Error handling: invalid API key ----
            except AuthenticationError:
                history.append({
                    "role": "assistant",
                    "content": "❌ **Authentication failed.** Your Gemini API key appears to be invalid or expired. Please check it in the sidebar.",
                })
            # ---- Error handling: connection failure ----
            except APIConnectionError:
                history.append({
                    "role": "assistant",
                    "content": "❌ **Connection failed.** Could not reach the AI service. Please check your internet connection and try again.",
                })
            except RateLimitError:
                history.append({
                    "role": "assistant",
                    "content": "⚠️ **Rate limit reached.** You've hit your usage limit or quota. Please wait a moment and try again.",
                })
            except APIError as e:
                history.append({
                    "role": "assistant",
                    "content": f"❌ **API error.** Something went wrong on the model provider's side: `{str(e)}`",
                })
            except Exception as e:
                history.append({
                    "role": "assistant",
                    "content": f"❌ **Unexpected error.** {str(e)}",
                })

        st.rerun()

# --------------------------------------------------------------------------------
# FOOTER
# --------------------------------------------------------------------------------

st.markdown("---")
st.caption("AI Workspace • Built with Streamlit + Google Gemini API • AI Summer Internship 2026, Track 2: NLP & AI Agents")