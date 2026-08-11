(() => {
  const state = {
    tasks: [],
    task: null,
    object: null,
    unitConfirmed: false,
    scanMode: null,
    targetLocation: null,
  };
  const $ = (id) => document.getElementById(id);
  const typeLabels = {
    build: "Формирование",
    place: "Размещение",
    move: "Перемещение",
    ship: "Отгрузка",
    inventory: "Инвентаризация",
    transfer: "Межскладская передача",
  };
  const statusLabels = { new: "Новое", in_progress: "В работе", completed: "Выполнено", cancelled: "Отменено" };
  const priorityLabels = { low: "Низкий", normal: "Обычный", high: "Высокий", urgent: "Срочный" };
  const objectStatusLabels = {
    open: "Открыта", closed: "Закрыта", available: "Доступна", blocked: "Заблокирована",
    quarantine: "Карантин", draft: "Черновик", reserved: "Резерв", expedition: "Экспедиция",
    loading: "Погрузка", in_transit: "В пути", receiving: "Приёмка", completed: "Завершено",
  };

  function esc(value) {
    return String(value ?? "—").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
  }
  function actor() { return $("actorInput").value.trim() || "Кладовщик"; }
  function warehouse() { return $("warehouseSelect").value; }
  async function api(path, options = {}) {
    const response = await fetch(path, options);
    if (response.status === 401) {
      location.href = `/login?next=${encodeURIComponent(location.pathname)}`;
      throw new Error("Требуется вход");
    }
    const text = await response.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch (_) { data = text; }
    if (!response.ok) throw new Error(data?.detail || response.statusText);
    return data;
  }
  function post(path, payload) {
    return api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  }
  function setMessage(text, kind = "") {
    $("message").className = `message ${kind}`;
    $("message").textContent = text;
  }
  function toast(text) {
    const node = $("toast");
    node.textContent = text;
    node.hidden = false;
    setTimeout(() => { node.hidden = true; }, 2600);
  }
  function focusScanner() {
    if (!$("scanBlock").hidden) setTimeout(() => $("scanInput").focus(), 30);
  }
  function fact(label, value) {
    return `<div class="fact"><b>${esc(label)}</b><span>${esc(value)}</span></div>`;
  }
  function button(label, action, className = "primary") {
    return `<button class="${className}" type="button" data-action="${action}">${esc(label)}</button>`;
  }

  async function loadWarehouses() {
    const rows = await api("/api/warehouses");
    $("warehouseSelect").innerHTML = rows.map((row) => `<option value="${esc(row.code)}">${esc(row.code)} · ${esc(row.name)}</option>`).join("");
    const saved = localStorage.getItem("wms-warehouse");
    if (saved && rows.some((row) => row.code === saved)) $("warehouseSelect").value = saved;
  }

  async function loadTasks(sync = true) {
    if (!warehouse()) return;
    if (sync) await post("/api/logistic-tasks/sync", { warehouse_code: warehouse(), actor: actor() });
    const query = new URLSearchParams({ warehouse_code: warehouse(), limit: "500" });
    query.append("status", "new");
    query.append("status", "in_progress");
    const rows = await api(`/api/logistic-tasks?${query.toString()}`);
    state.tasks = rows.filter((task) => !task.assigned_to || task.assigned_to === actor());
    renderQueue();
    if (state.task) {
      const current = state.tasks.find((task) => task.task_uid === state.task.task_uid);
      if (current) state.task = current;
    }
  }

  function renderQueue() {
    $("newCount").textContent = state.tasks.filter((task) => task.status === "new").length;
    $("progressCount").textContent = state.tasks.filter((task) => task.status === "in_progress").length;
    $("highCount").textContent = state.tasks.filter((task) => ["high", "urgent"].includes(task.priority)).length;
    $("taskList").innerHTML = state.tasks.map((task) => `
      <button class="task-row ${state.task?.task_uid === task.task_uid ? "selected" : ""}" type="button" data-task="${esc(task.task_uid)}">
        <span class="priority-mark ${esc(task.priority)}"></span>
        <span><span class="task-row-title">${esc(task.title)}</span><span class="task-row-meta mono">${esc(task.object_uid)}</span></span>
        <span class="badge ${esc(task.status)}">${esc(statusLabels[task.status])}</span>
      </button>
    `).join("") || '<div class="empty-list">Активных заданий нет</div>';
  }

  async function selectTask(uid) {
    state.task = await api(`/api/logistic-tasks/${encodeURIComponent(uid)}`);
    state.object = await api(state.task.object_url);
    state.unitConfirmed = false;
    state.scanMode = null;
    state.targetLocation = null;
    $("emptyOperation").hidden = true;
    $("activeOperation").hidden = false;
    renderQueue();
    renderOperation();
  }

  function renderFacts() {
    const task = state.task;
    const object = state.object || {};
    if (task.object_type === "logistic_unit") {
      return [fact("Тип", object.type_name), fact("Статус", objectStatusLabels[object.status] || object.status), fact("Ячейка", object.current_location_code), fact("Состав", `${object.contents?.length || 0} поз. / ${object.child_units?.length || 0} ед.`)].join("");
    }
    if (task.object_type === "logistic_shipment") {
      return [fact("Статус", objectStatusLabels[object.status] || object.status), fact("Единиц", object.unit_count), fact("Погружено", object.loaded_count), fact("Получатель", object.customer_name)].join("");
    }
    if (task.object_type === "logistic_transfer") {
      return [fact("Статус", objectStatusLabels[object.status] || object.status), fact("Маршрут", `${object.source_warehouse_code} → ${object.destination_warehouse_code}`), fact("Единиц", object.unit_count), fact("Принято", object.received_count)].join("");
    }
    return [fact("Прогресс", `${object.progress_percent || 0}%`), fact("Ячеек", `${object.checked_locations || 0} / ${object.total_locations || 0}`), fact("Расхождений", object.unresolved_problem_count || 0), fact("Текущая", object.current_location_code)].join("");
  }

  function operationPrompt() {
    const task = state.task;
    const object = state.object || {};
    if (task.status === "new") return { text: "Задание готово к выполнению.", hint: "", scan: false };
    if (task.task_type === "build") return { text: `Отсканируйте ${task.object_uid}, чтобы закрыть формирование.`, hint: "Код логистической единицы", scan: true };
    if (["place", "move"].includes(task.task_type)) {
      return state.unitConfirmed
        ? { text: "Единица подтверждена. Отсканируйте целевую ячейку.", hint: task.parameters?.target_location_code ? `Ожидается ${task.parameters.target_location_code}` : "Код ячейки", scan: true }
        : { text: `Отсканируйте ${task.object_uid}.`, hint: "Код логистической единицы", scan: true };
    }
    if (task.task_type === "ship") {
      if (state.scanMode === "stage") return { text: "Отсканируйте ячейку экспедиции.", hint: "Зона экспедиции", scan: true };
      if (["draft", "reserved"].includes(object.status)) return { text: "Сканируйте единицы для резерва.", hint: "Доступная логистическая единица", scan: true };
      return { text: "Сканируйте единицы при погрузке.", hint: "Единица из заявки", scan: true };
    }
    if (task.task_type === "transfer") {
      if (task.parameters?.phase === "receive") return state.targetLocation
        ? { text: `Ячейка ${state.targetLocation} выбрана. Сканируйте принимаемые единицы.`, hint: "Единица в пути", scan: true }
        : { text: "Отсканируйте ячейку приёмки склада назначения.", hint: "Зона приёмки передач", scan: true };
      if (state.scanMode === "stage") return { text: "Отсканируйте ячейку зоны отправки.", hint: "Зона выдачи передач", scan: true };
      if (["draft", "reserved"].includes(object.status)) return { text: "Сканируйте единицы для передачи.", hint: "Доступная единица", scan: true };
      return { text: "Сканируйте единицы при выдаче или погрузке.", hint: "Единица из передачи", scan: true };
    }
    return object.current_location_code
      ? { text: `Проверяется ${object.current_location_code}. Сканируйте единицы или подтвердите ячейку.`, hint: "Логистическая единица", scan: true }
      : { text: "Отсканируйте следующую ячейку.", hint: "Код ячейки", scan: true };
  }

  function renderActions() {
    const task = state.task;
    const object = state.object || {};
    if (task.status === "new") return button("Начать", "start");
    if (task.status === "completed") return button("Следующее задание", "next");
    if (task.task_type === "ship") {
      let html = "";
      if (object.status === "reserved") html += button("Передать в экспедицию", "stage", "secondary");
      if (object.status === "loading" && object.unit_count && object.loaded_count === object.unit_count) html += button("Завершить отгрузку", "close-shipment");
      return html;
    }
    if (task.task_type === "transfer") {
      if (task.parameters?.phase === "receive") return state.targetLocation ? button("Сменить ячейку", "change-location", "secondary") : "";
      let html = "";
      if (object.status === "reserved") html += button("Передать в зону отправки", "stage", "secondary");
      if (object.transfer_kind === "transport" && object.status === "loading" && object.unit_count && object.loaded_count === object.unit_count) html += button("Отправить машину", "dispatch");
      return html;
    }
    if (task.task_type === "inventory") {
      let html = "";
      if (object.current_location_code) html += button("Пусто", "empty", "secondary") + button("Закончить ячейку", "confirm-location");
      if (!object.unchecked_locations) html += button("Завершить инвентаризацию", "complete-inventory");
      return html;
    }
    return "";
  }

  function renderOperation() {
    const task = state.task;
    if (!task) return;
    $("taskTypeLabel").textContent = typeLabels[task.task_type] || task.task_type;
    $("taskTitle").textContent = task.title;
    $("taskCode").textContent = `${task.task_uid} · ${task.object_uid}`;
    $("taskPriority").className = `badge ${task.priority}`;
    $("taskPriority").textContent = priorityLabels[task.priority] || task.priority;
    $("taskStatus").className = `badge ${task.status}`;
    $("taskStatus").textContent = statusLabels[task.status] || task.status;
    $("railWork").className = `rail-step ${task.status === "in_progress" ? "active" : task.status === "completed" ? "done" : ""}`;
    $("railDone").className = `rail-step ${task.status === "completed" ? "done" : ""}`;
    $("objectFacts").innerHTML = renderFacts();
    const prompt = operationPrompt();
    setMessage(prompt.text, task.status === "completed" ? "ok" : "");
    $("scanBlock").hidden = !prompt.scan;
    $("scanHint").textContent = prompt.hint;
    $("actionBar").innerHTML = renderActions();
    const cardLink = $("objectCardLink");
    cardLink.hidden = task.object_type !== "logistic_unit";
    cardLink.href = `/cards?kind=unit&code=${encodeURIComponent(task.object_uid)}`;
    focusScanner();
  }

  async function refreshCurrent(successMessage) {
    const uid = state.task.task_uid;
    state.task = await api(`/api/logistic-tasks/${encodeURIComponent(uid)}`);
    state.object = await api(state.task.object_url);
    await loadTasks(false);
    renderOperation();
    if (successMessage) {
      setMessage(state.task.status === "completed" ? `${successMessage} Задание закрыто автоматически.` : successMessage, "ok");
      toast(successMessage);
    }
  }

  async function handleScan(rawCode) {
    const code = rawCode.trim().toUpperCase();
    if (!code || !state.task || state.task.status !== "in_progress") return;
    const task = state.task;
    const object = state.object || {};
    if (task.task_type === "build") {
      if (code !== task.object_uid.toUpperCase()) throw new Error(`Ожидается ${task.object_uid}`);
      await post(`/api/logistic-units/${encodeURIComponent(task.object_uid)}/close`, { actor: actor(), reason: "Выполнено из задания" });
      return refreshCurrent("Формирование завершено.");
    }
    if (["place", "move"].includes(task.task_type)) {
      if (!state.unitConfirmed) {
        if (code !== task.object_uid.toUpperCase()) throw new Error(`Ожидается ${task.object_uid}`);
        state.unitConfirmed = true;
        renderOperation();
        return;
      }
      if (task.parameters?.target_location_code && code !== task.parameters.target_location_code.toUpperCase()) throw new Error(`Ожидается ячейка ${task.parameters.target_location_code}`);
      await post(`/api/logistic-units/${encodeURIComponent(task.object_uid)}/${task.task_type}`, { location_code: code, actor: actor(), reason: "Выполнено из задания" });
      return refreshCurrent(task.task_type === "place" ? "Единица размещена." : "Единица перемещена.");
    }
    if (task.task_type === "ship") {
      if (state.scanMode === "stage") {
        await post(`/api/logistic-shipments/${encodeURIComponent(task.object_uid)}/expedition`, { location_code: code, actor: actor() });
        state.scanMode = null;
        return refreshCurrent("Заявка передана в экспедицию.");
      }
      const endpoint = ["draft", "reserved"].includes(object.status) ? "units" : "load";
      await post(`/api/logistic-shipments/${encodeURIComponent(task.object_uid)}/${endpoint}`, { unit_uid: code, actor: actor() });
      return refreshCurrent(endpoint === "units" ? "Единица зарезервирована." : "Единица погружена.");
    }
    if (task.task_type === "transfer") {
      if (task.parameters?.phase === "receive") {
        if (!state.targetLocation) { state.targetLocation = code; renderOperation(); return; }
        await post(`/api/logistic-transfers/${encodeURIComponent(task.object_uid)}/receive/${encodeURIComponent(code)}`, { location_code: state.targetLocation, actor: actor() });
        return refreshCurrent("Единица принята на складе назначения.");
      }
      if (state.scanMode === "stage") {
        await post(`/api/logistic-transfers/${encodeURIComponent(task.object_uid)}/expedition`, { location_code: code, actor: actor() });
        state.scanMode = null;
        return refreshCurrent("Передача готова к выдаче.");
      }
      const endpoint = ["draft", "reserved"].includes(object.status) ? "units" : "load";
      await post(`/api/logistic-transfers/${encodeURIComponent(task.object_uid)}/${endpoint}`, { unit_uid: code, actor: actor() });
      return refreshCurrent(endpoint === "units" ? "Единица добавлена в передачу." : "Единица выдана.");
    }
    if (!object.current_location_code) {
      await post(`/api/logistic-inventories/${encodeURIComponent(task.object_uid)}/scan-location`, { location_code: code, actor: actor() });
      return refreshCurrent("Ячейка выбрана.");
    }
    await post(`/api/logistic-inventories/${encodeURIComponent(task.object_uid)}/scan-unit`, { unit_uid: code, actor: actor() });
    return refreshCurrent("Единица отмечена.");
  }

  async function runAction(action) {
    const task = state.task;
    if (action === "start") {
      state.task = await post(`/api/logistic-tasks/${encodeURIComponent(task.task_uid)}/start`, { actor: actor() });
      state.object = await api(state.task.object_url);
      await loadTasks(false);
      renderOperation();
      return;
    }
    if (action === "next") return clearTask();
    if (action === "stage") { state.scanMode = "stage"; renderOperation(); return; }
    if (action === "change-location") { state.targetLocation = null; renderOperation(); return; }
    if (action === "close-shipment") {
      await post(`/api/logistic-shipments/${encodeURIComponent(task.object_uid)}/close`, { actor: actor(), reason: "Погрузка завершена" });
      return refreshCurrent("Отгрузка завершена.");
    }
    if (action === "dispatch") {
      await post(`/api/logistic-transfers/${encodeURIComponent(task.object_uid)}/dispatch`, { actor: actor(), reason: "Погрузка завершена" });
      return refreshCurrent("Передача отправлена.");
    }
    const inventoryBase = `/api/logistic-inventories/${encodeURIComponent(task.object_uid)}`;
    if (action === "empty") await post(`${inventoryBase}/empty`, { actor: actor() });
    if (action === "confirm-location") await post(`${inventoryBase}/confirm-location`, { actor: actor() });
    if (action === "complete-inventory") await post(`${inventoryBase}/complete`, { actor: actor() });
    return refreshCurrent(action === "complete-inventory" ? "Инвентаризация завершена." : "Ячейка проверена.");
  }

  function clearTask() {
    state.task = null;
    state.object = null;
    state.unitConfirmed = false;
    state.scanMode = null;
    state.targetLocation = null;
    $("activeOperation").hidden = true;
    $("emptyOperation").hidden = false;
    renderQueue();
  }

  $("taskList").addEventListener("click", (event) => {
    const row = event.target.closest("[data-task]");
    if (row) selectTask(row.dataset.task).catch((error) => toast(error.message));
  });
  $("actionBar").addEventListener("click", (event) => {
    const control = event.target.closest("[data-action]");
    if (control) runAction(control.dataset.action).catch((error) => setMessage(error.message, "err"));
  });
  $("scanInput").addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    const code = event.currentTarget.value;
    event.currentTarget.value = "";
    handleScan(code).catch((error) => { setMessage(error.message, "err"); focusScanner(); });
  });
  $("refreshTasks").addEventListener("click", () => loadTasks(true).catch((error) => toast(error.message)));
  $("releaseTask").addEventListener("click", clearTask);
  $("warehouseSelect").addEventListener("change", () => { localStorage.setItem("wms-warehouse", warehouse()); clearTask(); loadTasks(true).catch((error) => toast(error.message)); });
  $("actorInput").addEventListener("change", () => { localStorage.setItem("wms-actor", actor()); clearTask(); loadTasks(false).catch((error) => toast(error.message)); });

  const savedActor = localStorage.getItem("wms-actor");
  if (savedActor) $("actorInput").value = savedActor;
  if ($("deviceClock")) {
    const updateClock = () => { $("deviceClock").textContent = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }); };
    updateClock();
    setInterval(updateClock, 30000);
  }
  loadWarehouses().then(() => loadTasks(true)).catch((error) => toast(error.message));
})();
