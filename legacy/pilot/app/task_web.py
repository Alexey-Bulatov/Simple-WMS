from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.page_shell import standard_page


router = APIRouter()


@router.get("/tasks", response_class=HTMLResponse, include_in_schema=False)
@standard_page("tasks")
def tasks_page() -> str:
    return """<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Диспетчер заданий WMS</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #edf1f2;
      --panel: #fff;
      --soft: #f6f8f9;
      --line: #d5dde1;
      --text: #17242c;
      --muted: #65727a;
      --accent: #087a70;
      --accent-dark: #075f58;
      --accent-soft: #e7f6f3;
      --warn: #9a5b0a;
      --warn-soft: #fff6e5;
      --danger: #b42318;
      --danger-soft: #fff0ee;
      --ok: #087443;
      --ok-soft: #eaf8ef;
      --dark: #111820;
    }
    * { box-sizing: border-box; }
    body { margin: 0; background: var(--bg); color: var(--text); font: 14px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    button, input, select { font: inherit; }
    button:focus-visible, input:focus-visible, select:focus-visible, a:focus-visible { outline: 3px solid #f4b740; outline-offset: 2px; }
    main { width: min(1320px, 100%); margin: 0 auto; padding: 20px; }
    .page-head { margin-bottom: 14px; display: flex; align-items: flex-end; justify-content: space-between; gap: 18px; }
    .page-head > div:first-child { min-width: 280px; flex: 1 1 340px; }
    h1, h2, h3, p { margin-top: 0; }
    h1 { margin-bottom: 4px; font-size: 26px; letter-spacing: 0; }
    h2 { margin-bottom: 0; font-size: 17px; letter-spacing: 0; }
    h3 { margin-bottom: 8px; font-size: 15px; letter-spacing: 0; }
    .lead, .meta { color: var(--muted); }
    .lead { margin-bottom: 0; }
    .filters { min-width: 0; flex: 2 1 720px; display: grid; grid-template-columns: 150px 140px 140px minmax(170px, 1fr) auto; gap: 8px; }
    label { display: block; margin-bottom: 4px; color: var(--muted); font-size: 10px; font-weight: 900; text-transform: uppercase; }
    input, select, button { min-height: 40px; border: 1px solid var(--line); border-radius: 5px; padding: 8px 10px; background: #fff; color: var(--text); }
    input, select { width: 100%; }
    button { cursor: pointer; font-weight: 800; }
    button.primary { border-color: var(--accent); background: var(--accent); color: #fff; }
    button.primary:hover { background: var(--accent-dark); }
    button.secondary { border-color: #9bcfc8; background: var(--accent-soft); color: var(--accent-dark); }
    button.danger { border-color: #efb3ad; background: var(--danger-soft); color: var(--danger); }
    button:disabled { cursor: not-allowed; border-color: var(--line); background: #e7ecee; color: #89969d; }
    .summary { margin-bottom: 14px; display: grid; grid-template-columns: repeat(4, 1fr); border: 1px solid var(--line); background: var(--panel); }
    .summary-item { min-width: 0; padding: 12px 14px; border-right: 1px solid var(--line); }
    .summary-item:last-child { border-right: 0; }
    .summary-item b { display: block; color: var(--muted); font-size: 10px; text-transform: uppercase; }
    .summary-item span { display: block; margin-top: 3px; font-size: 20px; font-weight: 900; }
    .layout { display: grid; grid-template-columns: 330px minmax(0, 1fr); border: 1px solid var(--line); background: var(--panel); }
    aside { padding: 16px; border-right: 1px solid var(--line); background: var(--soft); }
    .form-stack { display: grid; gap: 10px; }
    .two { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
    .queue { min-width: 0; }
    .queue-head { padding: 14px 16px; display: flex; align-items: center; justify-content: space-between; gap: 10px; border-bottom: 1px solid var(--line); }
    .queue-list { max-height: 500px; overflow-y: auto; }
    .task-row { min-height: 78px; padding: 11px 16px; display: grid; grid-template-columns: 8px minmax(0, 1fr) 130px 100px; align-items: center; gap: 11px; border-bottom: 1px solid var(--line); }
    .task-row:last-child { border-bottom: 0; }
    .task-row.selected { background: #f2fbf9; }
    .priority-mark { width: 8px; height: 44px; border-radius: 3px; background: #98a6ad; }
    .priority-mark.normal { background: var(--accent); }
    .priority-mark.high { background: #d89725; }
    .priority-mark.urgent { background: var(--danger); }
    .task-title { font-weight: 900; overflow-wrap: anywhere; }
    .task-code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; font-weight: 800; overflow-wrap: anywhere; }
    .badge { display: inline-flex; width: fit-content; padding: 3px 7px; border-radius: 4px; color: #40515a; background: #e8edef; font-size: 10px; font-weight: 900; }
    .badge.new { color: var(--accent-dark); background: var(--accent-soft); }
    .badge.in_progress { color: var(--warn); background: var(--warn-soft); }
    .badge.completed { color: var(--ok); background: var(--ok-soft); }
    .badge.cancelled { color: var(--danger); background: var(--danger-soft); }
    .empty { padding: 28px 16px; color: var(--muted); text-align: center; }
    .detail { display: none; grid-column: 1 / -1; border-top: 1px solid var(--line); background: var(--panel); }
    .detail.visible { display: grid; grid-template-columns: minmax(0, 1fr) minmax(360px, .9fr); }
    .detail-main, .history { min-width: 0; padding: 16px; }
    .history { border-left: 1px solid var(--line); background: var(--soft); }
    .detail-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
    .detail-facts { margin: 12px 0; display: grid; grid-template-columns: repeat(4, 1fr); border: 1px solid var(--line); }
    .fact { min-width: 0; padding: 9px; border-right: 1px solid var(--line); }
    .fact:last-child { border-right: 0; }
    .fact b { display: block; color: var(--muted); font-size: 9px; text-transform: uppercase; }
    .fact span { display: block; margin-top: 2px; font-weight: 850; overflow-wrap: anywhere; }
    .assignment { display: grid; grid-template-columns: minmax(180px, 1fr) auto auto; gap: 8px; align-items: end; }
    .history-list { display: grid; gap: 1px; background: var(--line); }
    .history-row { padding: 9px; background: #fff; }
    .history-row strong { display: block; }
    @media (max-width: 980px) {
      .page-head { align-items: stretch; flex-direction: column; }
      .page-head > div:first-child, .filters { width: 100%; flex: none; }
      .filters { grid-template-columns: 1fr 1fr 1fr; }
      .filters .search { grid-column: 1 / 3; }
      .layout { grid-template-columns: 1fr; }
      aside { border-right: 0; border-bottom: 1px solid var(--line); }
      .form-stack { grid-template-columns: 1fr 1fr; }
      .form-stack h2, .form-stack .wide, .form-stack button { grid-column: 1 / -1; }
      .detail.visible { grid-template-columns: 1fr; }
      .history { border-top: 1px solid var(--line); border-left: 0; }
    }
    @media (max-width: 640px) {
      main { padding: 10px; }
      h1 { font-size: 22px; }
      .filters { grid-template-columns: 1fr 1fr; }
      .filters .search { grid-column: 1 / -1; }
      .summary { grid-template-columns: 1fr 1fr; }
      .summary-item:nth-child(2) { border-right: 0; }
      .summary-item:nth-child(-n+2) { border-bottom: 1px solid var(--line); }
      .form-stack { grid-template-columns: 1fr; }
      .form-stack > * { grid-column: 1 !important; }
      .task-row { grid-template-columns: 7px minmax(0, 1fr) auto; padding-inline: 11px; }
      .task-row .assignee { grid-column: 2; }
      .task-row button { grid-column: 3; grid-row: 1 / 3; }
      .detail-facts { grid-template-columns: 1fr 1fr; }
      .fact:nth-child(2) { border-right: 0; }
      .fact:nth-child(-n+2) { border-bottom: 1px solid var(--line); }
      .assignment { grid-template-columns: 1fr; }
      .assignment > * { width: 100%; }
    }
  </style>
</head>
<body>
  <header><h1>WMS</h1></header>
  <main>
    <div class="page-head">
      <div>
        <h1>Диспетчер заданий</h1>
        <p class="lead">Формирование очереди, назначение исполнителей и контроль выполнения.</p>
      </div>
      <div class="filters">
        <div><label for="warehouseFilter">Склад</label><select id="warehouseFilter"></select></div>
        <div>
          <label for="statusFilter">Статус</label>
          <select id="statusFilter">
            <option value="active">Активные</option>
            <option value="all">Все</option>
            <option value="new">Новые</option>
            <option value="in_progress">В работе</option>
            <option value="completed">Выполненные</option>
            <option value="cancelled">Отменённые</option>
          </select>
        </div>
        <div>
          <label for="priorityFilter">Приоритет</label>
          <select id="priorityFilter">
            <option value="">Все</option>
            <option value="urgent">Срочный</option>
            <option value="high">Высокий</option>
            <option value="normal">Обычный</option>
            <option value="low">Низкий</option>
          </select>
        </div>
        <div class="search"><label for="taskSearch">Поиск</label><input id="taskSearch" placeholder="Код, объект или исполнитель"></div>
        <button id="refreshBtn" class="secondary" type="button">Обновить</button>
      </div>
    </div>

    <section class="summary" aria-label="Сводка заданий">
      <div class="summary-item"><b>Активные</b><span id="activeCount">0</span></div>
      <div class="summary-item"><b>В работе</b><span id="progressCount">0</span></div>
      <div class="summary-item"><b>Срочные</b><span id="urgentCount">0</span></div>
      <div class="summary-item"><b>Выполнено</b><span id="completedCount">0</span></div>
    </section>

    <section class="layout">
      <aside>
        <form id="createForm" class="form-stack">
          <h2>Новое задание</h2>
          <div class="two wide">
            <div>
              <label for="taskType">Операция</label>
              <select id="taskType">
                <option value="build">Формирование палеты</option>
                <option value="place">Размещение палеты</option>
                <option value="move">Перемещение палеты</option>
                <option value="ship">Отгрузка</option>
                <option value="inventory">Инвентаризация</option>
                <option value="transfer">Между складами</option>
              </select>
            </div>
            <div>
              <label for="taskPriority">Приоритет</label>
              <select id="taskPriority">
                <option value="normal">Обычный</option>
                <option value="high">Высокий</option>
                <option value="urgent">Срочный</option>
                <option value="low">Низкий</option>
              </select>
            </div>
          </div>
          <div class="wide"><label for="taskTitle">Название</label><input id="taskTitle" placeholder="Заполнится автоматически"></div>
          <div class="wide"><label for="taskObject">Код объекта</label><input id="taskObject" placeholder="Палета или документ"></div>
          <div class="wide">
            <label for="taskAssignee">Исполнитель</label>
            <input id="taskAssignee" list="userOptions" placeholder="Можно назначить позже">
          </div>
          <datalist id="userOptions"></datalist>
          <div class="wide"><label for="dispatcher">Диспетчер</label><input id="dispatcher" value="Диспетчер"></div>
          <button class="primary" type="submit">Создать задание</button>
        </form>
      </aside>

      <div class="queue">
        <div class="queue-head">
          <div><h2>Очередь</h2><div id="queueMeta" class="meta">0 заданий</div></div>
          <button id="syncBtn" class="secondary" type="button">Сформировать из операций</button>
        </div>
        <div id="taskList" class="queue-list"></div>
      </div>

      <section id="detailPanel" class="detail">
        <div class="detail-main">
          <div class="detail-head">
            <div><div class="meta">Задание</div><h2 id="detailTitle">-</h2></div>
            <span id="detailStatus" class="badge">-</span>
          </div>
          <div class="detail-facts">
            <div class="fact"><b>Код</b><span id="detailUid">-</span></div>
            <div class="fact"><b>Объект</b><span id="detailObject">-</span></div>
            <div class="fact"><b>Приоритет</b><span id="detailPriority">-</span></div>
            <div class="fact"><b>Создано</b><span id="detailCreated">-</span></div>
          </div>
          <div class="assignment">
            <div><label for="detailAssignee">Исполнитель</label><input id="detailAssignee" list="userOptions" placeholder="Не назначен"></div>
            <button id="assignBtn" class="primary" type="button">Назначить</button>
            <button id="closeTaskBtn" class="danger" type="button">Отменить</button>
          </div>
        </div>
        <div class="history">
          <h3>История</h3>
          <div id="historyList" class="history-list"></div>
        </div>
      </section>
    </section>
  </main>

  <script>
    const state = { warehouses: [], users: [], tasks: [], selectedUid: "" };
    const $ = (id) => document.getElementById(id);
    const typeLabels = {
      build: "Формирование палеты", place: "Размещение палеты", move: "Перемещение палеты",
      ship: "Отгрузка", inventory: "Инвентаризация", transfer: "Между складами",
    };
    const statusLabels = { new: "Новое", in_progress: "В работе", completed: "Выполнено", cancelled: "Отменено" };
    const priorityLabels = { low: "Низкий", normal: "Обычный", high: "Высокий", urgent: "Срочный" };
    const eventLabels = {
      task_created: "Задание создано", task_assigned: "Назначен исполнитель",
      task_unassigned: "Исполнитель снят", task_started: "Задание начато",
      task_completed: "Задание выполнено", task_completed_automatically: "Задание выполнено автоматически",
      task_cancelled: "Задание отменено", task_reopened: "Задание возвращено в очередь",
    };
    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, (char) =>
        ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[char]
      );
    }
    function actor() { return $("dispatcher").value.trim() || "Диспетчер"; }
    function formatDate(value) { return value ? new Date(value).toLocaleString("ru-RU") : "-"; }
    async function api(path, options = {}) {
      const response = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
      const text = await response.text();
      const data = text ? JSON.parse(text) : null;
      if (!response.ok) throw new Error(data?.detail || response.statusText);
      return data;
    }
    function post(path, body = {}) { return api(path, { method: "POST", body: JSON.stringify(body) }); }
    function showError(error) { window.alert(error.message || String(error)); }
    function selectedWarehouse() { return $("warehouseFilter").value; }
    function filteredTasks() {
      const status = $("statusFilter").value;
      const priority = $("priorityFilter").value;
      const search = $("taskSearch").value.trim().toLowerCase();
      return state.tasks.filter((task) => {
        const statusMatch = status === "all"
          || (status === "active" && ["new", "in_progress"].includes(task.status))
          || task.status === status;
        const priorityMatch = !priority || task.priority === priority;
        const haystack = `${task.task_uid} ${task.title} ${task.object_uid || ""} ${task.assigned_to || ""}`.toLowerCase();
        return statusMatch && priorityMatch && (!search || haystack.includes(search));
      });
    }
    function renderSummary() {
      $("activeCount").textContent = state.tasks.filter((task) => ["new", "in_progress"].includes(task.status)).length;
      $("progressCount").textContent = state.tasks.filter((task) => task.status === "in_progress").length;
      $("urgentCount").textContent = state.tasks.filter((task) => task.priority === "urgent" && ["new", "in_progress"].includes(task.status)).length;
      $("completedCount").textContent = state.tasks.filter((task) => task.status === "completed").length;
    }
    function renderTasks() {
      const tasks = filteredTasks();
      $("queueMeta").textContent = `${tasks.length} из ${state.tasks.length}`;
      $("taskList").innerHTML = tasks.map((task) => `
        <div class="task-row ${task.task_uid === state.selectedUid ? "selected" : ""}">
          <span class="priority-mark ${escapeHtml(task.priority)}"></span>
          <div>
            <div class="task-title">${escapeHtml(task.title)}</div>
            <div class="task-code">${escapeHtml(task.object_uid || task.task_uid)}</div>
            <div class="meta">${escapeHtml(typeLabels[task.task_type] || task.task_type)} · ${escapeHtml(priorityLabels[task.priority] || task.priority)}</div>
          </div>
          <div class="assignee">
            <span class="badge ${escapeHtml(task.status)}">${escapeHtml(statusLabels[task.status] || task.status)}</span>
            <div class="meta">${escapeHtml(task.assigned_to || "Не назначено")}</div>
          </div>
          <button type="button" data-task="${escapeHtml(task.task_uid)}">Открыть</button>
        </div>
      `).join("") || '<div class="empty">Заданий по выбранному фильтру нет</div>';
      document.querySelectorAll("[data-task]").forEach((button) => {
        button.addEventListener("click", () => openTask(button.dataset.task).catch(showError));
      });
    }
    async function loadTasks({ sync = false } = {}) {
      if (sync) await post("/api/tasks/sync", { warehouse_code: selectedWarehouse(), actor: actor() });
      state.tasks = await api(`/api/tasks?warehouse_code=${encodeURIComponent(selectedWarehouse())}&limit=500`);
      if (state.selectedUid && !state.tasks.some((task) => task.task_uid === state.selectedUid)) state.selectedUid = "";
      renderSummary();
      renderTasks();
      if (!state.selectedUid) $("detailPanel").classList.remove("visible");
    }
    async function openTask(uid) {
      state.selectedUid = uid;
      const task = state.tasks.find((item) => item.task_uid === uid);
      if (!task) return;
      const events = await api(`/api/tasks/${encodeURIComponent(uid)}/events?limit=50`);
      $("detailTitle").textContent = task.title;
      $("detailStatus").className = `badge ${task.status}`;
      $("detailStatus").textContent = statusLabels[task.status] || task.status;
      $("detailUid").textContent = task.task_uid;
      $("detailObject").textContent = task.object_uid || "-";
      $("detailPriority").textContent = priorityLabels[task.priority] || task.priority;
      $("detailCreated").textContent = formatDate(task.created_at);
      $("detailAssignee").value = task.assigned_to || "";
      const closed = ["completed", "cancelled"].includes(task.status);
      $("assignBtn").disabled = closed;
      $("closeTaskBtn").textContent = closed ? "Вернуть в очередь" : "Отменить";
      $("closeTaskBtn").className = closed ? "secondary" : "danger";
      $("historyList").innerHTML = events.map((event) => `
        <div class="history-row">
          <strong>${escapeHtml(eventLabels[event.operation] || event.operation)}</strong>
          <div class="meta">${escapeHtml(event.actor)} · ${escapeHtml(formatDate(event.created_at))}</div>
        </div>
      `).join("") || '<div class="history-row">История пока пуста</div>';
      $("detailPanel").classList.add("visible");
      renderTasks();
    }
    async function createTask() {
      const task = await post("/api/tasks", {
        warehouse_code: selectedWarehouse(),
        task_type: $("taskType").value,
        priority: $("taskPriority").value,
        title: $("taskTitle").value.trim() || null,
        object_uid: $("taskObject").value.trim().toUpperCase() || null,
        assigned_to: $("taskAssignee").value.trim() || null,
        actor: actor(),
      });
      $("taskTitle").value = "";
      $("taskObject").value = "";
      $("taskAssignee").value = "";
      await loadTasks();
      await openTask(task.task_uid);
    }
    async function assignSelected() {
      if (!state.selectedUid) return;
      await post(`/api/tasks/${encodeURIComponent(state.selectedUid)}/assign`, {
        assigned_to: $("detailAssignee").value.trim() || null,
        actor: actor(),
      });
      await loadTasks();
      await openTask(state.selectedUid);
    }
    async function closeOrReopenSelected() {
      const task = state.tasks.find((item) => item.task_uid === state.selectedUid);
      if (!task) return;
      const endpoint = ["completed", "cancelled"].includes(task.status) ? "reopen" : "cancel";
      await post(`/api/tasks/${encodeURIComponent(task.task_uid)}/${endpoint}`, { actor: actor() });
      await loadTasks();
      await openTask(task.task_uid);
    }
    async function initialize() {
      [state.warehouses, state.users] = await Promise.all([api("/api/warehouses"), api("/api/users")]);
      $("warehouseFilter").innerHTML = state.warehouses.map((warehouse) =>
        `<option value="${escapeHtml(warehouse.code)}">${escapeHtml(warehouse.code)} — ${escapeHtml(warehouse.name)}</option>`
      ).join("");
      $("userOptions").innerHTML = state.users.filter((user) => user.is_active).map((user) =>
        `<option value="${escapeHtml(user.full_name)}">${escapeHtml(user.username)}</option>`
      ).join("");
      $("dispatcher").value = localStorage.getItem("wms.tasks.dispatcher") || "Диспетчер";
      await loadTasks({ sync: true });
    }
    $("createForm").addEventListener("submit", (event) => {
      event.preventDefault();
      createTask().catch(showError);
    });
    $("warehouseFilter").addEventListener("change", () => {
      state.selectedUid = "";
      loadTasks({ sync: true }).catch(showError);
    });
    $("statusFilter").addEventListener("change", renderTasks);
    $("priorityFilter").addEventListener("change", renderTasks);
    $("taskSearch").addEventListener("input", renderTasks);
    $("refreshBtn").addEventListener("click", () => loadTasks().catch(showError));
    $("syncBtn").addEventListener("click", () => loadTasks({ sync: true }).catch(showError));
    $("assignBtn").addEventListener("click", () => assignSelected().catch(showError));
    $("closeTaskBtn").addEventListener("click", () => closeOrReopenSelected().catch(showError));
    $("dispatcher").addEventListener("change", () => localStorage.setItem("wms.tasks.dispatcher", actor()));
    initialize().catch(showError);
  </script>
</body>
</html>"""
