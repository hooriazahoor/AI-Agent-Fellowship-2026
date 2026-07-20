"""
Flask application entry point. Owns ONLY the HTTP/UI layer -- all agent
logic lives in app/agent, all persistence in app/database, all tools in
app/tools. This file wires them together and handles error responses.
"""
from __future__ import annotations

import uuid
import traceback

from flask import Flask, render_template, request, jsonify, session

from app.config import settings
from app.database.repository import init_db
from app.database import repository as repo
from app.agent.controller import agent_controller
from app.logging.run_logger import logger


def create_app() -> Flask:
    app = Flask(__name__, template_folder="../templates", static_folder="../static")
    app.secret_key = settings.flask_secret_key
    init_db()

    def _session_id() -> str:
        if "session_id" not in session:
            session["session_id"] = str(uuid.uuid4())
        return session["session_id"]

    def _error_response(message: str, status_code: int = 400):
        return jsonify({"status": "error", "message": message}), status_code

    @app.errorhandler(Exception)
    def handle_uncaught(e):
        logger.error("Unhandled exception: %s\n%s", e, traceback.format_exc())
        return _error_response("An unexpected server error occurred. Please try again.", 500)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    @app.route("/")
    def index():
        _session_id()
        return render_template(
            "index.html",
            llm_provider=agent_controller_provider(),
            max_steps=settings.max_agent_steps,
        )

    def agent_controller_provider():
        from app.services.llm_service import llm_service
        return llm_service.provider

    # ------------------------------------------------------------------
    # Chat / Agent
    # ------------------------------------------------------------------
    @app.route("/api/chat", methods=["POST"])
    def chat():
        payload = request.get_json(silent=True) or {}
        message = (payload.get("message") or "").strip()
        if not message:
            return _error_response("Empty user input. Please type a request.")
        sid = _session_id()
        response = agent_controller.handle_message(sid, message)
        return jsonify(response.to_dict())

    @app.route("/api/approve", methods=["POST"])
    def approve():
        payload = request.get_json(silent=True) or {}
        approval_id = payload.get("approval_id")
        edited_args = payload.get("edited_args")  # optional: user tweaked the proposed arguments
        if not approval_id:
            return _error_response("Missing approval_id.")
        sid = _session_id()
        response = agent_controller.resume_after_approval(sid, approval_id, approved=True, edited_args=edited_args)
        return jsonify(response.to_dict())

    @app.route("/api/reject", methods=["POST"])
    def reject():
        payload = request.get_json(silent=True) or {}
        approval_id = payload.get("approval_id")
        if not approval_id:
            return _error_response("Missing approval_id.")
        sid = _session_id()
        response = agent_controller.resume_after_approval(sid, approval_id, approved=False)
        return jsonify(response.to_dict())

    @app.route("/api/pending_approvals")
    def pending_approvals():
        sid = _session_id()
        return jsonify(repo.list_pending_approvals(sid))

    # ------------------------------------------------------------------
    # Tasks & Notes panels
    # ------------------------------------------------------------------
    @app.route("/api/tools/run", methods=["POST"])
    def run_tool():
        payload = request.get_json(silent=True) or {}
        tool_name = payload.get("tool_name")
        tool_args = payload.get("tool_args") or {}
        if not tool_name:
            return _error_response("Missing tool_name.")
        sid = _session_id()
        response = agent_controller.request_action(sid, tool_name, tool_args)
        return jsonify(response.to_dict())

    @app.route("/api/tasks/<task_id>/action", methods=["POST"])
    def task_action(task_id):
        payload = request.get_json(silent=True) or {}
        action = payload.get("action")
        sid = _session_id()
        if action == "complete":
            tool_name, tool_args = "complete_task", {"task_id": task_id}
        elif action == "update":
            changes = dict(payload.get("changes") or {})
            changes["task_id"] = task_id
            tool_name, tool_args = "update_task", changes
        elif action == "delete":
            tool_name, tool_args = "delete_task", {"task_id": task_id}
        else:
            return _error_response("Unsupported action. Use 'complete', 'update', or 'delete'.")
        response = agent_controller.request_action(sid, tool_name, tool_args)
        return jsonify(response.to_dict())

    @app.route("/api/tasks")
    def api_tasks():
        try:
            tasks = repo.list_tasks(
                status=request.args.get("status"),
                priority=request.args.get("priority"),
                tag=request.args.get("tag"),
            )
            return jsonify({"tasks": tasks, "total_count": len(tasks)})
        except Exception as e:
            return _error_response(str(e), 500)

    @app.route("/api/notes")
    def api_notes():
        try:
            query = request.args.get("q")
            if query:
                return jsonify({"notes": repo.search_notes(query)})
            return jsonify({"notes": repo.list_notes()})
        except Exception as e:
            return _error_response(str(e), 500)

    @app.route("/api/notes/action", methods=["POST"])
    def notes_action():
        payload = request.get_json(silent=True) or {}
        action = payload.get("action")
        sid = _session_id()
        if action == "save":
            tool_name, tool_args = "save_note", {
                "title": payload.get("title", ""),
                "content": payload.get("content", ""),
                "category": payload.get("category", "general"),
                "tags": payload.get("tags", []),
            }
        elif action == "summarize":
            tool_name, tool_args = "summarize_notes", {"note_ids": payload.get("note_ids")}
        elif action == "delete":
            tool_name, tool_args = "delete_note", {"note_id": payload.get("note_id")}
        else:
            return _error_response("Unsupported action. Use 'save', 'summarize', or 'delete'.")
        response = agent_controller.request_action(sid, tool_name, tool_args)
        return jsonify(response.to_dict())

    # ------------------------------------------------------------------
    # Execution log viewer
    # ------------------------------------------------------------------
    @app.route("/api/logs")
    def api_logs():
        sid = _session_id()
        scope = request.args.get("scope", "session")
        logs = repo.list_execution_logs(session_id=sid if scope == "session" else None)
        return jsonify({"logs": logs})

    @app.route("/api/logs/<run_id>")
    def api_log_detail(run_id):
        log = repo.get_execution_log(run_id)
        if not log:
            return _error_response("Log not found.", 404)
        return jsonify(log)

    # ------------------------------------------------------------------
    # Sample data seeding (for demo / onsite evaluation)
    # ------------------------------------------------------------------
    @app.route("/api/seed", methods=["POST"])
    def seed():
        from app.seed_data import seed_sample_data
        created = seed_sample_data()
        return jsonify({"status": "ok", "created": created})

    @app.route("/api/export/pdf", methods=["POST"])
    def export_pdf():
        from io import BytesIO
        import re as _re
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.units import inch
        from reportlab.lib import colors as _colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from flask import send_file

        payload = request.get_json(silent=True) or {}
        title = payload.get("title", "Report")
        markdown_text = payload.get("markdown", "")
        if not markdown_text.strip():
            return _error_response("Nothing to export.")

        buf = BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=0.7 * inch, rightMargin=0.7 * inch,
                                topMargin=0.7 * inch, bottomMargin=0.6 * inch)
        styles = getSampleStyleSheet()
        h1 = ParagraphStyle("H1x", fontName="Helvetica-Bold", fontSize=16,
                            textColor=_colors.HexColor("#1E2530"), spaceAfter=10)
        h4 = ParagraphStyle("H4x", fontName="Helvetica-Bold", fontSize=12,
                            textColor=_colors.HexColor("#1F7A67"), spaceBefore=8, spaceAfter=4)
        body = ParagraphStyle("Bodyx", fontName="Helvetica", fontSize=10, leading=14, spaceAfter=3)
        bullet = ParagraphStyle("Bulletx", fontName="Helvetica", fontSize=10, leading=14,
                                leftIndent=14, spaceAfter=2)

        def inline(t):
            t = _re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
            return t

        story = [Paragraph(title, h1)]
        for line in markdown_text.split("\n"):
            t = line.strip()
            if not t:
                continue
            if t.startswith("# "):
                story.append(Paragraph(inline(t[2:]), h1))
            elif t.startswith(("## ", "### ")):
                story.append(Paragraph(inline(t.lstrip("#").strip()), h4))
            elif t.startswith(("- ", "* ")):
                story.append(Paragraph("\u2022 " + inline(t[2:]), bullet))
            else:
                story.append(Paragraph(inline(t), body))
        doc.build(story)
        buf.seek(0)
        safe_name = _re.sub(r"[^a-zA-Z0-9]+", "_", title.lower()).strip("_") or "report"
        return send_file(buf, mimetype="application/pdf", as_attachment=True,
                         download_name=f"{safe_name}.pdf")

    @app.route("/health")
    def health():
        return jsonify({"status": "ok", "llm_provider": agent_controller_provider()})

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=settings.port, debug=settings.flask_debug)