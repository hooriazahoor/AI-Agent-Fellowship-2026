// ---------------------------------------------------------------------
// Productivity Agent - frontend controller. Talks to the Flask JSON API
// only; all agent/tool logic lives server-side.
// ---------------------------------------------------------------------

const chatWindow = document.getElementById('chat-window');
const chatForm = document.getElementById('chat-form');
const chatInput = document.getElementById('chat-input');
const statusPill = document.getElementById('status-pill');
const errorBanner = document.getElementById('error-banner');
const approvalModal = document.getElementById('approval-modal');
const approvalModalCard = document.getElementById('approval-modal-card');
const editModal = document.getElementById('edit-modal');

// ---------------- Tabs ----------------
document.querySelectorAll('.nav-tab').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.nav-tab').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
    if (btn.dataset.tab === 'tasks') loadTasks();
    if (btn.dataset.tab === 'notes') loadNotes();
    if (btn.dataset.tab === 'logs') loadLogs();
  });
});

// ---------------- Status pill ----------------
const STAGE_LABELS = {
  thinking: 'Thinking', selecting_tool: 'Selecting tool', executing_tool: 'Executing tool',
  validating_result: 'Validating result', waiting_approval: 'Waiting for approval',
  clarifying: 'Needs clarification', responding: 'Producing response', error: 'Error',
  done: 'Done', retrying_tool: 'Retrying', approval_resolved: 'Approval resolved',
};

function setStatusPill(stage) {
  statusPill.className = 'status-pill ' + stage;
  statusPill.textContent = STAGE_LABELS[stage] || stage;
}
function resetStatusPill() {
  statusPill.className = 'status-pill idle';
  statusPill.textContent = 'Idle';
}

// ---------------- Chat rendering ----------------
function inlineFormat(text) {
  text = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  text = text.replace(/`(.+?)`/g, '<code>$1</code>');
  return text;
}

// Minimal, safe markdown -> HTML: input is escaped FIRST, then a small set of
// markdown patterns (### headings, - bullets, **bold**, `code`) are converted.
// This never trusts raw HTML from tool output/LLM text.
function renderMarkdown(raw) {
  const lines = escapeHtml(raw).split('\n');
  let html = '';
  let inList = false;
  const closeList = () => { if (inList) { html += '</ul>'; inList = false; } };

  lines.forEach(line => {
    const t = line.trim();
    if (t.startsWith('### ')) {
      closeList();
      html += `<h4 class="msg-heading">${inlineFormat(t.slice(4))}</h4>`;
    } else if (t.startsWith('- ')) {
      if (!inList) { html += '<ul class="msg-list">'; inList = true; }
      html += `<li>${inlineFormat(t.slice(2))}</li>`;
    } else if (t === '') {
      closeList();
    } else {
      closeList();
      html += `<p class="msg-line">${inlineFormat(t)}</p>`;
    }
  });
  closeList();
  return html || '<p class="msg-line"></p>';
}

function appendMessage(role, text) {
  const wrap = document.createElement('div');
  wrap.className = 'msg ' + role;

  const bubble = document.createElement('div');
  bubble.className = 'msg-bubble';
  if (role === 'agent') {
    bubble.innerHTML = renderMarkdown(text);
  } else {
    bubble.textContent = text;
  }
  wrap.appendChild(bubble);
  chatWindow.appendChild(wrap);

  chatWindow.scrollTop = chatWindow.scrollHeight;
}

// ---------------- Agent Activity panel (separate from chat conversation) ----------------
const activityTimeline = document.getElementById('activity-timeline');
let _runCounter = 0;

function renderActivityRun(trail, label) {
  if (!trail || !trail.length) return;
  _runCounter += 1;
  if (activityTimeline.querySelector('.timeline-empty')) activityTimeline.innerHTML = '';

  const runDiv = document.createElement('div');
  runDiv.className = 'timeline-run';
  const labelDiv = document.createElement('div');
  labelDiv.className = 'timeline-run-label';
  labelDiv.textContent = `Run #${_runCounter}${label ? ' - ' + label : ''}`;
  runDiv.appendChild(labelDiv);

  trail.forEach(t => {
    const step = document.createElement('div');
    step.className = 'timeline-step ' + t.stage;
    step.innerHTML = `
      <div class="timeline-step-label">${STAGE_LABELS[t.stage] || t.stage}</div>
      ${t.detail ? `<div class="timeline-step-detail">${escapeHtml(t.detail)}</div>` : ''}
    `;
    runDiv.appendChild(step);
  });

  // newest run on top
  activityTimeline.insertBefore(runDiv, activityTimeline.firstChild);
  activityTimeline.scrollTop = 0;
}

function showError(msg) {
  errorBanner.className = 'error-banner';
  errorBanner.style.display = 'block';
  errorBanner.textContent = msg;
  setTimeout(() => { errorBanner.style.display = 'none'; }, 6000);
}

function showSuccess(msg) {
  errorBanner.className = 'error-banner success';
  errorBanner.style.display = 'block';
  errorBanner.textContent = msg;
  setTimeout(() => { errorBanner.style.display = 'none'; }, 6000);
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

// ---------------- Global approval modal ----------------
// Works from any tab: chat-triggered approvals AND Tasks-tab button-triggered approvals
// both flow through this same modal + the same /api/approve /api/reject endpoints.
let _onApprovalResolved = null;
let _currentApproval = null;

function openApprovalModal(approval, onResolved) {
  _onApprovalResolved = onResolved;
  _currentApproval = approval;
  approvalModalCard.innerHTML = `
    <h4>Approval required</h4>
    <div class="meta">Tool: ${escapeHtml(approval.tool_name)}</div>
    <div>${escapeHtml(approval.proposed_action)}</div>
    <label class="mini-label" style="display:block;margin-top:8px;">Input arguments (editable before approving)</label>
    <textarea class="approval-args-edit" id="approval-args-edit" rows="5">${escapeHtml(JSON.stringify(approval.tool_args || {}, null, 2))}</textarea>
    <div class="meta">Expected effect: ${escapeHtml(approval.expected_effect || '')}</div>
    <div class="approval-actions">
      <button class="btn-approve" id="approve-btn">Approve</button>
      <button class="btn-reject" id="reject-btn">Reject</button>
    </div>
  `;
  approvalModal.classList.remove('hidden');
  document.getElementById('approve-btn').addEventListener('click', () => {
    let editedArgs;
    try {
      editedArgs = JSON.parse(document.getElementById('approval-args-edit').value);
    } catch (e) {
      showError('The edited arguments are not valid JSON - fix the syntax or leave them as-is.');
      return;
    }
    resolveApproval(approval.id, true, editedArgs);
  });
  document.getElementById('reject-btn').addEventListener('click', () => resolveApproval(approval.id, false));
}

function closeApprovalModal() {
  approvalModal.classList.add('hidden');
  approvalModalCard.innerHTML = '';
}

async function resolveApproval(approvalId, approved, editedArgs) {
  setStatusPill('executing_tool');
  closeApprovalModal();
  try {
    const body = {approval_id: approvalId};
    if (approved && editedArgs) body.edited_args = editedArgs;
    const res = await fetch(approved ? '/api/approve' : '/api/reject', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok || data.status === 'error') {
      showError(data.message || 'Could not resolve approval.');
      setStatusPill('error');
      return;
    }
    renderActivityRun(data.status_trail, 'approval resolved');
    if (data.status_trail && data.status_trail.length) {
      setStatusPill(data.status_trail[data.status_trail.length - 1].stage);
    }
    if (_onApprovalResolved) _onApprovalResolved(data);
    _onApprovalResolved = null;
    setTimeout(resetStatusPill, 1200);
  } catch (err) {
    showError('Network error while resolving approval.');
    setStatusPill('error');
  }
}

// ---------------- Chat submission ----------------
chatForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const text = chatInput.value.trim();
  if (!text) return;
  appendMessage('user', text);
  chatInput.value = '';
  setStatusPill('thinking');

  try {
    const res = await fetch('/api/chat', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message: text}),
    });
    const data = await res.json();
    if (!res.ok || data.status === 'error') {
      showError(data.message || 'Something went wrong.');
      setStatusPill('error');
      appendMessage('agent', data.message || 'Something went wrong.');
      renderActivityRun(data.status_trail, text.slice(0, 40));
      return;
    }
    handleChatResponse(data, text);
  } catch (err) {
    showError('Network error while contacting the agent.');
    setStatusPill('error');
  }
});

function handleChatResponse(data, label, skipTrailRender) {
  if (data.status_trail && data.status_trail.length) {
    setStatusPill(data.status_trail[data.status_trail.length - 1].stage);
  }
  appendMessage('agent', data.message);
  if (!skipTrailRender) renderActivityRun(data.status_trail, label);

  if (data.status === 'waiting_approval') {
    openApprovalModal(data.pending_approval, (resolvedData) => {
      // resolveApproval() already rendered this trail into the activity panel.
      handleChatResponse(resolvedData, 'approval resolved', true);
    });
  }
  if (data.status === 'completed' || data.status === 'clarification_needed') {
    setTimeout(resetStatusPill, 1200);
  }
}

// ---------------- Tools tab (10 additional/bonus tools) ----------------
let _lastWeeklyReport = null;

function showToolResult(card, text, kind) {
  const box = card.querySelector('.tool-result');
  box.innerHTML = renderMarkdown(text);
  box.className = 'tool-result visible' + (kind ? ' ' + kind + '-result' : '');
}

function showToolResultRaw(card, dataOut) {
  const box = card.querySelector('.tool-result');
  box.innerHTML = `<pre style="white-space:pre-wrap;margin:0;">${escapeHtml(JSON.stringify(dataOut, null, 2))}</pre>`;
  box.className = 'tool-result visible success-result';
}

// Converts each tool's raw JSON output into a short markdown-formatted,
// human-readable summary instead of a raw JSON dump.
function formatToolResultHuman(toolName, data, message) {
  if (!data) return message || 'Done.';
  const fmtDate = (d) => d ? new Date(d).toLocaleDateString() : 'no due date';

  switch (toolName) {
    case 'detect_overdue_tasks': {
      const tasks = data.overdue_tasks || [];
      if (!tasks.length) return '### Overdue Tasks\n\nNo overdue tasks - you\'re all caught up.';
      return `### Overdue Tasks (${data.total_count})\n\n` +
        tasks.map(t => `- **${t.title}** (${t.priority}) - was due ${fmtDate(t.due_date)}`).join('\n');
    }
    case 'estimate_task_effort':
      return `### Effort Estimate\n\n**${data.estimated_effort_minutes} minutes** estimated.`;
    case 'identify_conflicting_deadlines': {
      const c = data.conflicts || [];
      if (!c.length) return '### Deadline Conflicts\n\nNo conflicting deadlines found.';
      return `### Deadline Conflicts (${data.total_count})\n\n` +
        c.map(x => `- **${x.task_a.title}** and **${x.task_b.title}** are only ${x.gap_hours}h apart`).join('\n');
    }
    case 'recommend_task_priorities': {
      const r = data.recommendations || [];
      if (!r.length) return '### Priority Recommendations\n\nNo changes recommended right now.';
      return `### Priority Recommendations (${data.total_count})\n\n` +
        r.map(x => `- **${x.title}**: ${x.current_priority} -> ${x.suggested_priority}`).join('\n');
    }
    case 'summarize_notes':
      return `### Note Summary\n\n${data.summary || '(nothing to summarize)'}\n\n` +
        `*${data.notes_considered} note(s) considered.*`;
    case 'draft_followup_email':
      return `### Email Draft\n\n**Subject:** ${data.subject}\n\n${(data.body || '').replace(/\n/g, '  \n')}`;
    case 'generate_weekly_report':
      return `### Weekly Report\n\n- Completed: ${data.completed_count}\n- Overdue: ${data.overdue_count}\n` +
        `- Blocked: ${data.blocked_count}\n\n**Next week priorities:**\n` +
        (data.recommended_next_week_priorities || []).map(p => `- ${p}`).join('\n');
    case 'convert_meeting_notes_to_tasks': {
      const created = data.created_tasks || [];
      return `### Tasks Created (${created.length})\n\n` + created.map(t => `- ${t.title}`).join('\n');
    }
    case 'export_report':
      return data.markdown || message;
    default: {
      // Generic fallback: turn top-level fields into readable bullets.
      const lines = Object.entries(data).map(([k, v]) => {
        const val = Array.isArray(v) ? `${v.length} item(s)` : (typeof v === 'object' && v !== null ? '' : v);
        return `- **${k.replace(/_/g, ' ')}:** ${val}`;
      });
      return `### Result\n\n${lines.join('\n')}`;
    }
  }
}

function showExportButtons(card, title, markdownText) {
  let box = card.querySelector('.export-buttons');
  if (!box) {
    box = document.createElement('div');
    box.className = 'export-buttons';
    card.appendChild(box);
  }
  box.innerHTML = '';
  const mdBtn = document.createElement('button');
  mdBtn.className = 'mini-btn edit'; mdBtn.textContent = '⬇ Download .md';
  mdBtn.addEventListener('click', () => {
    const blob = new Blob([markdownText], {type: 'text/markdown'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `${title.toLowerCase().replace(/[^a-z0-9]+/g, '_')}.md`;
    a.click(); URL.revokeObjectURL(url);
  });
  const pdfBtn = document.createElement('button');
  pdfBtn.className = 'mini-btn complete'; pdfBtn.textContent = '⬇ Download PDF';
  pdfBtn.addEventListener('click', async () => {
    pdfBtn.disabled = true; pdfBtn.textContent = 'Generating...';
    try {
      const res = await fetch('/api/export/pdf', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({title, markdown: markdownText}),
      });
      if (!res.ok) { showError('Could not generate PDF.'); return; }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = `${title.toLowerCase().replace(/[^a-z0-9]+/g, '_')}.pdf`;
      a.click(); URL.revokeObjectURL(url);
    } catch (err) {
      showError('Network error while generating PDF.');
    } finally {
      pdfBtn.disabled = false; pdfBtn.textContent = '⬇ Download PDF';
    }
  });
  box.appendChild(mdBtn); box.appendChild(pdfBtn);
}

async function runTool(toolName, toolArgs, card) {
  const btn = card.querySelector('.run-btn');
  const originalLabel = btn.textContent;
  btn.disabled = true; btn.textContent = 'Running...';
  setStatusPill('executing_tool');
  const existingExportBtns = card.querySelector('.export-buttons');
  if (existingExportBtns) existingExportBtns.remove();
  try {
    const res = await fetch('/api/tools/run', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({tool_name: toolName, tool_args: toolArgs}),
    });
    const data = await res.json();
    if (!res.ok || data.status === 'error') {
      showToolResult(card, data.message || 'Tool failed.', 'error');
      setStatusPill('error');
      return;
    }
    if (data.status === 'waiting_approval') {
      showToolResult(card, 'Waiting for your approval - see the popup.', null);
      openApprovalModal(data.pending_approval, (resolvedData) => {
        if (resolvedData.status === 'completed') {
          const rTool = (resolvedData.tool_calls && resolvedData.tool_calls[0]) ? resolvedData.tool_calls[0].result : null;
          showToolResult(card, formatToolResultHuman(toolName, rTool ? rTool.data : null, resolvedData.message), 'success');
          if (toolName === 'convert_meeting_notes_to_tasks') loadTasks();
        } else {
          showToolResult(card, resolvedData.message, 'error');
        }
      });
      return;
    }
    // completed
    const toolResult = (data.tool_calls && data.tool_calls[0]) ? data.tool_calls[0].result : null;
    const dataOut = toolResult ? toolResult.data : null;
    showToolResult(card, formatToolResultHuman(toolName, dataOut, data.message), 'success');

    if (toolName === 'generate_weekly_report' && dataOut) {
      _lastWeeklyReport = dataOut;
      const exportCard = document.querySelector('.tool-card[data-tool="export_report"]');
      exportCard.querySelector('.run-btn').disabled = false;
      showExportButtons(card, 'Weekly Report', formatToolResultHuman('generate_weekly_report', dataOut));
    }
    if (toolName === 'export_report' && dataOut && dataOut.markdown) {
      showExportButtons(card, 'Report', dataOut.markdown);
    }
  } catch (err) {
    showToolResult(card, 'Network error while running this tool.', 'error');
    setStatusPill('error');
  } finally {
    btn.disabled = false; btn.textContent = originalLabel;
    setTimeout(resetStatusPill, 1000);
  }
}

document.querySelectorAll('.tool-card').forEach(card => {
  const toolName = card.dataset.tool;
  const runBtn = card.querySelector('.run-btn');

  runBtn.addEventListener('click', () => {
    let args = {};
    if (toolName === 'estimate_task_effort') {
      args = {title: card.querySelector('.tf-title').value.trim(),
               description: card.querySelector('.tf-description').value.trim()};
    } else if (toolName === 'identify_conflicting_deadlines') {
      args = {window_hours: parseInt(card.querySelector('.tf-window').value, 10) || 4};
    } else if (toolName === 'summarize_notes') {
      const q = card.querySelector('.tf-query').value.trim();
      args = q ? {query: q} : {};
    } else if (toolName === 'create_reminder') {
      const remindAt = card.querySelector('.tf-remind-at').value;
      if (!card.querySelector('.tf-title').value.trim() || !remindAt) {
        showToolResult(card, 'Title and reminder date/time are required.', 'error'); return;
      }
      args = {title: card.querySelector('.tf-title').value.trim(), remind_at: remindAt,
               notes: card.querySelector('.tf-notes').value.trim()};
    } else if (toolName === 'draft_followup_email') {
      const notes = card.querySelector('.tf-meeting-notes').value.trim();
      if (!notes) { showToolResult(card, 'Meeting notes are required.', 'error'); return; }
      args = {meeting_notes: notes, recipient_name: card.querySelector('.tf-recipient').value.trim() || null,
               tone: card.querySelector('.tf-tone').value};
    } else if (toolName === 'generate_weekly_report') {
      const ws = card.querySelector('.tf-week-start').value;
      args = ws ? {week_start: ws} : {};
    } else if (toolName === 'convert_meeting_notes_to_tasks') {
      const t = card.querySelector('.tf-transcript').value.trim();
      if (!t) { showToolResult(card, 'Meeting notes are required.', 'error'); return; }
      args = {transcript: t, default_priority: card.querySelector('.tf-priority').value};
    } else if (toolName === 'export_report') {
      if (!_lastWeeklyReport) { showToolResult(card, 'Run "Generate Weekly Report" first.', 'error'); return; }
      args = {report_type: 'weekly', content: _lastWeeklyReport};
    }
    // detect_overdue_tasks and recommend_task_priorities take no args
    runTool(toolName, args, card);
  });
});

async function loadTasks() {
  const status = document.getElementById('filter-status').value;
  const priority = document.getElementById('filter-priority').value;
  const params = new URLSearchParams();
  if (status) params.set('status', status);
  if (priority) params.set('priority', priority);
  const res = await fetch('/api/tasks?' + params.toString());
  const data = await res.json();
  const grid = document.getElementById('task-grid');
  grid.innerHTML = '';
  if (!data.tasks || !data.tasks.length) {
    grid.innerHTML = '<p style="color:var(--muted);">No tasks yet. Try "Load sample data" or create one via chat.</p>';
    return;
  }
  data.tasks.forEach(t => {
    const card = document.createElement('div');
    card.className = 'task-card';
    const isDone = t.status === 'Completed' || t.status === 'Cancelled';
    card.innerHTML = `
      <h4>${escapeHtml(t.title)}</h4>
      <p>${escapeHtml(t.description || '')}</p>
      <div class="badge-row">
        <span class="badge priority-${t.priority}">${t.priority}</span>
        <span class="badge status">${t.status}</span>
        ${t.due_date ? `<span class="badge status">Due ${new Date(t.due_date).toLocaleDateString()}</span>` : ''}
      </div>
      <div class="task-card-actions">
        <button class="mini-btn complete" data-id="${t.id}" ${isDone ? 'disabled' : ''}>✓ Mark Complete</button>
        <button class="mini-btn edit" data-id="${t.id}">✎ Edit</button>
        <button class="mini-btn delete" data-id="${t.id}">🗑 Delete</button>
      </div>
    `;
    grid.appendChild(card);

    card.querySelector('.mini-btn.complete').addEventListener('click', () => requestCompleteTask(t.id));
    card.querySelector('.mini-btn.edit').addEventListener('click', () => openEditModal(t));
    card.querySelector('.mini-btn.delete').addEventListener('click', () => requestDeleteTask(t.id));
  });
}
document.getElementById('refresh-tasks').addEventListener('click', loadTasks);
document.getElementById('filter-status').addEventListener('change', loadTasks);
document.getElementById('filter-priority').addEventListener('change', loadTasks);

async function requestDeleteTask(taskId) {
  setStatusPill('waiting_approval');
  try {
    const res = await fetch(`/api/tasks/${taskId}/action`, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({action: 'delete'}),
    });
    const data = await res.json();
    if (!res.ok || data.status === 'error') {
      showError(data.message || 'Could not request deletion.');
      setStatusPill('error');
      return;
    }
    if (data.status === 'waiting_approval') {
      openApprovalModal(data.pending_approval, (resolvedData) => {
        if (resolvedData.status === 'completed') { showSuccess(resolvedData.message); } else { showError(resolvedData.message); }
        loadTasks();
      });
    }
  } catch (err) {
    showError('Network error while requesting task deletion.');
    setStatusPill('error');
  }
}

async function requestCompleteTask(taskId) {
  setStatusPill('waiting_approval');
  try {
    const res = await fetch(`/api/tasks/${taskId}/action`, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({action: 'complete'}),
    });
    const data = await res.json();
    if (!res.ok || data.status === 'error') {
      showError(data.message || 'Could not request completion.');
      setStatusPill('error');
      return;
    }
    if (data.status === 'waiting_approval') {
      openApprovalModal(data.pending_approval, (resolvedData) => {
        if (resolvedData.status === 'completed') { showSuccess(resolvedData.message); } else { showError(resolvedData.message); }
        loadTasks();
      });
    }
  } catch (err) {
    showError('Network error while requesting task completion.');
    setStatusPill('error');
  }
}

// ---------------- Edit modal ----------------
let _editingTaskId = null;

function openEditModal(task) {
  _editingTaskId = task.id;
  document.getElementById('edit-title').value = task.title || '';
  document.getElementById('edit-description').value = task.description || '';
  document.getElementById('edit-priority').value = task.priority || 'Medium';
  document.getElementById('edit-status').value = task.status || 'Pending';
  document.getElementById('edit-due-date').value = task.due_date ? task.due_date.slice(0, 10) : '';
  editModal.classList.remove('hidden');
}

document.getElementById('edit-cancel-btn').addEventListener('click', () => {
  editModal.classList.add('hidden');
  _editingTaskId = null;
});

document.getElementById('edit-save-btn').addEventListener('click', async () => {
  if (!_editingTaskId) return;
  const changes = {
    title: document.getElementById('edit-title').value.trim(),
    description: document.getElementById('edit-description').value.trim(),
    priority: document.getElementById('edit-priority').value,
    status: document.getElementById('edit-status').value,
  };
  const dueDate = document.getElementById('edit-due-date').value;
  if (dueDate) changes.due_date = dueDate;

  editModal.classList.add('hidden');
  setStatusPill('waiting_approval');
  try {
    const res = await fetch(`/api/tasks/${_editingTaskId}/action`, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({action: 'update', changes}),
    });
    const data = await res.json();
    if (!res.ok || data.status === 'error') {
      showError(data.message || 'Could not request update.');
      setStatusPill('error');
      return;
    }
    if (data.status === 'waiting_approval') {
      openApprovalModal(data.pending_approval, (resolvedData) => {
        if (resolvedData.status === 'completed') { showSuccess(resolvedData.message); } else { showError(resolvedData.message); }
        loadTasks();
      });
    }
  } catch (err) {
    showError('Network error while requesting task update.');
    setStatusPill('error');
  }
  _editingTaskId = null;
});

// ---------------- Notes panel ----------------
const noteDetailModal = document.getElementById('note-detail-modal');
const noteDetailCard = document.getElementById('note-detail-card');
const newNoteModal = document.getElementById('new-note-modal');

async function loadNotes(query) {
  const url = query ? `/api/notes?q=${encodeURIComponent(query)}` : '/api/notes';
  const res = await fetch(url);
  const data = await res.json();
  const grid = document.getElementById('note-grid');
  grid.innerHTML = '';
  if (!data.notes || !data.notes.length) {
    grid.innerHTML = `<p style="color:var(--muted);">${query ? 'No notes matched your search.' : 'No notes yet. Click "+ New Note" or "Load sample data".'}</p>`;
    return;
  }
  data.notes.forEach(n => {
    const card = document.createElement('div');
    card.className = 'note-card clickable';
    card.innerHTML = `<h4>${escapeHtml(n.title)}</h4><p>${escapeHtml(n.content)}</p>
      <div class="badge-row">
        <span class="badge status">${escapeHtml(n.category)}</span>
        ${n.match_score !== undefined ? `<span class="badge priority-Medium">match ${n.match_score}</span>` : ''}
        ${(n.tags || []).map(t => `<span class="badge status">#${escapeHtml(t)}</span>`).join('')}
      </div>`;
    card.addEventListener('click', () => openNoteDetail(n));
    grid.appendChild(card);
  });
}
document.getElementById('refresh-notes').addEventListener('click', () => loadNotes());
document.getElementById('note-search-btn').addEventListener('click', () => {
  loadNotes(document.getElementById('note-search').value.trim());
});
document.getElementById('note-search').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') loadNotes(document.getElementById('note-search').value.trim());
});

function openNoteDetail(note) {
  noteDetailCard.innerHTML = `
    <h4>${escapeHtml(note.title)}</h4>
    <div class="badge-row" style="margin-bottom:10px;">
      <span class="badge status">${escapeHtml(note.category)}</span>
      ${(note.tags || []).map(t => `<span class="badge status">#${escapeHtml(t)}</span>`).join('')}
    </div>
    <p style="font-size:13.5px;color:var(--ink);white-space:pre-wrap;line-height:1.6;">${escapeHtml(note.content)}</p>
    <div class="meta" style="margin-top:10px;">Created: ${note.created_date ? new Date(note.created_date).toLocaleString() : '-'}</div>
    <div id="note-summary-output" class="approval-args" style="display:none;"></div>
    <div class="edit-actions">
      <button class="ghost-btn-light" id="note-detail-close-btn">Close</button>
      <button class="mini-btn delete" id="note-delete-btn" style="flex:0;">🗑 Delete</button>
      <button class="btn-approve" id="note-summarize-btn">Summarize this note</button>
    </div>
  `;
  noteDetailModal.classList.remove('hidden');
  document.getElementById('note-detail-close-btn').addEventListener('click', () => {
    noteDetailModal.classList.add('hidden');
  });
  document.getElementById('note-delete-btn').addEventListener('click', async () => {
    setStatusPill('waiting_approval');
    try {
      const res = await fetch('/api/notes/action', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({action: 'delete', note_id: note.id}),
      });
      const data = await res.json();
      if (!res.ok || data.status === 'error') {
        showError(data.message || 'Could not request deletion.');
        setStatusPill('error');
        return;
      }
      if (data.status === 'waiting_approval') {
        openApprovalModal(data.pending_approval, (resolvedData) => {
          if (resolvedData.status === 'completed') { showSuccess(resolvedData.message); noteDetailModal.classList.add('hidden'); }
          else { showError(resolvedData.message); }
          loadNotes();
        });
      }
    } catch (err) {
      showError('Network error while requesting note deletion.');
      setStatusPill('error');
    }
  });
  document.getElementById('note-summarize-btn').addEventListener('click', async () => {
    const btn = document.getElementById('note-summarize-btn');
    btn.disabled = true; btn.textContent = 'Summarizing...';
    try {
      const res = await fetch('/api/notes/action', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({action: 'summarize', note_ids: [note.id]}),
      });
      const data = await res.json();
      const out = document.getElementById('note-summary-output');
      out.style.display = 'block';
      if (data.status === 'completed' && data.tool_calls && data.tool_calls.length) {
        out.textContent = data.tool_calls[0].result.data.summary || '(no summary produced)';
      } else {
        out.textContent = data.message || 'Could not summarize this note.';
      }
    } catch (err) {
      showError('Network error while summarizing.');
    } finally {
      btn.disabled = false; btn.textContent = 'Summarize this note';
    }
  });
}

document.getElementById('new-note-btn').addEventListener('click', () => {
  document.getElementById('note-title').value = '';
  document.getElementById('note-content').value = '';
  document.getElementById('note-category').value = '';
  document.getElementById('note-tags').value = '';
  newNoteModal.classList.remove('hidden');
});
document.getElementById('note-cancel-btn').addEventListener('click', () => {
  newNoteModal.classList.add('hidden');
});
document.getElementById('note-save-btn').addEventListener('click', async () => {
  const title = document.getElementById('note-title').value.trim();
  const content = document.getElementById('note-content').value.trim();
  const category = document.getElementById('note-category').value.trim() || 'general';
  const tags = document.getElementById('note-tags').value.split(',').map(t => t.trim()).filter(Boolean);
  if (!title || !content) {
    showError('Title and content are required.');
    return;
  }
  try {
    const res = await fetch('/api/notes/action', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({action: 'save', title, content, category, tags}),
    });
    const data = await res.json();
    if (!res.ok || data.status === 'error') {
      showError(data.message || 'Could not save note.');
      return;
    }
    newNoteModal.classList.add('hidden');
    showSuccess('Note saved.');
    loadNotes();
  } catch (err) {
    showError('Network error while saving note.');
  }
});

// ---------------- Logs panel ----------------
async function loadLogs() {
  const res = await fetch('/api/logs');
  const data = await res.json();
  const list = document.getElementById('log-list');
  list.innerHTML = '';
  if (!data.logs || !data.logs.length) {
    list.innerHTML = '<p style="color:var(--muted);">No runs yet in this session.</p>';
    return;
  }
  data.logs.forEach(l => {
    const entry = document.createElement('div');
    entry.className = 'log-entry';
    entry.innerHTML = `
      <div class="log-top"><span>${l.id}</span><span>${l.total_duration_ms ?? '-'} ms · ${l.step_count} step(s)</span></div>
      <div class="log-request">${escapeHtml(l.user_request)}</div>
      <div class="log-tools">${(l.tools_called || []).join(', ') || 'no tools called'}</div>
    `;
    list.appendChild(entry);
  });
}
document.getElementById('refresh-logs').addEventListener('click', loadLogs);

// ---------------- Seed sample data ----------------
document.getElementById('seed-btn').addEventListener('click', async () => {
  const res = await fetch('/api/seed', {method: 'POST'});
  const data = await res.json();
  showSuccess(`Sample data loaded: ${JSON.stringify(data.created)}`);
  loadTasks(); loadNotes();
});