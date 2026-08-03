(() => {
  const $ = (id) => document.getElementById(id);
  let selectedKind = "auto";
  const statusLabels = {
    open: "Открыта", closed: "Закрыта", available: "Доступна", blocked: "Заблокирована",
    quarantine: "Карантин", reserved: "Резерв", expedition: "Экспедиция", loaded: "Погружена",
    in_transit: "В пути", shipped: "Отгружена", disassembled: "Разукомплектована",
    new: "Новое", in_progress: "В работе", completed: "Выполнено", cancelled: "Отменено",
  };
  const operationLabels = {
    logistic_unit_created: "Единица создана", logistic_unit_accepted: "Единица принята", logistic_unit_content_added: "Добавлено содержимое",
    logistic_unit_child_added: "Добавлена вложенная единица", logistic_unit_closed: "Формирование завершено", logistic_unit_reopened: "Единица переоткрыта",
    logistic_unit_placed: "Единица размещена", logistic_unit_moved: "Единица перемещена", logistic_unit_blocked: "Единица заблокирована",
    logistic_unit_quarantine: "Единица в карантине", logistic_unit_released: "Единица возвращена в работу",
  };
  function esc(value) { return String(value ?? "—").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]); }
  async function api(path) {
    const response = await fetch(path);
    const text = await response.text();
    const data = text ? JSON.parse(text) : null;
    if (!response.ok) throw new Error(data?.detail || response.statusText);
    return data;
  }
  function message(text, kind = "") { $("cardMessage").className = `message ${kind}`; $("cardMessage").textContent = text; }
  function fact(label, value) { return `<div class="fact"><b>${esc(label)}</b><span>${esc(value)}</span></div>`; }
  function row(title, meta = "", badge = "") { return `<div class="data-row"><div class="data-row-head"><strong>${title}</strong>${badge ? `<span class="badge">${esc(badge)}</span>` : ""}</div>${meta ? `<small>${meta}</small>` : ""}</div>`; }
  function link(kind, code) { return `<a class="mono" href="/cards?kind=${kind}&code=${encodeURIComponent(code)}">${esc(code)}</a>`; }
  function eventsHtml(events) {
    return (events || []).map((event) => row(esc(operationLabels[event.operation] || event.operation), `${new Date(event.created_at).toLocaleString()} · ${esc(event.actor)}`, event.reason || "")).join("") || row("Истории пока нет");
  }
  function unitCard(unit, events, tasks) {
    const contents = (unit.contents || []).map((item) => row(`${esc(item.product_code)} · ${esc(item.quantity)} ${esc(item.uom_symbol || item.uom_code)}`, item.batch_number ? `Партия ${esc(item.batch_number)}` : "Без партии")).join("") || row("Товарного содержимого нет");
    const children = (unit.child_units || []).map((child) => row(link("unit", child.uid), child.type_name, statusLabels[child.status] || child.status)).join("") || row("Вложенных единиц нет");
    const taskRows = (tasks || []).map((task) => row(esc(task.title), `${esc(task.task_uid)} · ${new Date(task.created_at).toLocaleString()}`, statusLabels[task.status] || task.status)).join("") || row("Связанных заданий нет");
    $("cardView").innerHTML = `<div class="card-hero"><span class="eyebrow">Логистическая единица</span><div class="card-code mono">${esc(unit.uid)}</div><div class="facts">${fact("Тип", unit.type_name)}${fact("Статус", statusLabels[unit.status] || unit.status)}${fact("Ячейка", unit.current_location_code)}${fact("Родитель", unit.parent_uid)}</div></div><div class="card-sections"><section class="card-section"><h3>Товарное содержимое</h3><div class="data-list">${contents}</div></section><section class="card-section"><h3>Вложенные единицы</h3><div class="data-list">${children}</div></section><section class="card-section wide"><h3>Задания</h3><div class="data-list">${taskRows}</div></section><section class="card-section wide"><h3>История</h3><div class="data-list">${eventsHtml(events)}</div></section></div>`;
  }
  function locationCard(card) {
    const location = card.location;
    const units = (card.logistic_units || []).map((unit) => row(link("unit", unit.uid), unit.type_name, statusLabels[unit.status] || unit.status)).join("") || row("Ячейка пуста");
    const address = [location.address?.aisle, location.address?.rack, location.address?.section, location.address?.level, location.address?.position].filter(Boolean).join(" / ") || "На уровне зоны";
    $("cardView").innerHTML = `<div class="card-hero"><span class="eyebrow">Ячейка</span><div class="card-code mono">${esc(location.code)}</div><div class="facts">${fact("Тип", location.kind_label)}${fact("Склад", location.warehouse?.code)}${fact("Зона", location.zone?.code)}${fact("Адрес", address)}${fact("Вместимость", location.capacity_units)}</div></div><div class="card-sections"><section class="card-section wide"><h3>Логистические единицы</h3><div class="data-list">${units}</div></section><section class="card-section wide"><h3>История движений</h3><div class="data-list">${eventsHtml(card.events)}</div></section></div>`;
  }
  async function openCard() {
    const raw = $("cardCode").value.trim();
    if (!raw) throw new Error("Введите код объекта");
    let kind = selectedKind;
    let code = raw.toUpperCase();
    if (kind === "auto") {
      const resolved = await api(`/api/cards/resolve/${encodeURIComponent(code)}`);
      kind = resolved.kind;
      code = resolved.code;
    }
    if (kind === "unit") {
      const [unit, events, tasks] = await Promise.all([api(`/api/logistic-units/${encodeURIComponent(code)}`), api(`/api/logistic-units/${encodeURIComponent(code)}/events?limit=100`), api(`/api/logistic-tasks?object_uid=${encodeURIComponent(code)}&limit=100`)]);
      unitCard(unit, events, tasks);
    } else {
      locationCard(await api(`/api/cards/locations/${encodeURIComponent(code)}`));
      kind = "location";
    }
    message("Карточка открыта.", "ok");
    history.replaceState(null, "", `/cards?kind=${kind}&code=${encodeURIComponent(code)}`);
    setTimeout(() => $("cardCode").focus(), 30);
  }
  async function loadWarehouses() {
    const rows = await api("/api/warehouses");
    $("cardWarehouse").innerHTML = rows.map((row) => `<option value="${esc(row.code)}">${esc(row.code)}</option>`).join("");
  }
  async function quickList(kind) {
    document.querySelectorAll("#listUnits,#listLocations").forEach((button) => button.classList.toggle("active", button.id === (kind === "unit" ? "listUnits" : "listLocations")));
    if (kind === "unit") {
      const rows = await api(`/api/logistic-units?warehouse_code=${encodeURIComponent($("cardWarehouse").value)}`);
      $("quickList").innerHTML = rows.slice(0, 80).map((unit) => `<button class="quick-item" data-kind="unit" data-code="${esc(unit.uid)}" type="button"><strong class="mono">${esc(unit.uid)}</strong><small>${esc(unit.type_name)} · ${esc(statusLabels[unit.status] || unit.status)} · ${esc(unit.current_location_code)}</small></button>`).join("") || '<div class="empty-list">Единиц нет</div>';
    } else {
      const warehouses = await api("/api/warehouses");
      const selected = warehouses.find((item) => item.code === $("cardWarehouse").value);
      const rows = await api("/api/locations");
      $("quickList").innerHTML = rows.filter((location) => location.warehouse_id === selected?.id).slice(0, 100).map((location) => `<button class="quick-item" data-kind="location" data-code="${esc(location.code)}" type="button"><strong class="mono">${esc(location.code)}</strong><small>${esc(location.kind)} · ${esc(location.name || "без названия")}</small></button>`).join("") || '<div class="empty-list">Ячеек нет</div>';
    }
  }
  document.querySelectorAll("[data-card-kind]").forEach((button) => button.addEventListener("click", () => { selectedKind = button.dataset.cardKind; document.querySelectorAll("[data-card-kind]").forEach((item) => item.classList.toggle("active", item === button)); }));
  $("openCard").addEventListener("click", () => openCard().catch((error) => message(error.message, "err")));
  $("cardCode").addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); openCard().catch((error) => message(error.message, "err")); } });
  $("listUnits").addEventListener("click", () => quickList("unit").catch((error) => message(error.message, "err")));
  $("listLocations").addEventListener("click", () => quickList("location").catch((error) => message(error.message, "err")));
  $("cardWarehouse").addEventListener("change", () => quickList(document.querySelector("#listLocations.active") ? "location" : "unit").catch((error) => message(error.message, "err")));
  $("quickList").addEventListener("click", (event) => { const item = event.target.closest("[data-code]"); if (!item) return; selectedKind = item.dataset.kind; $("cardCode").value = item.dataset.code; openCard().catch((error) => message(error.message, "err")); });
  const params = new URLSearchParams(location.search);
  if (params.get("code")) { $("cardCode").value = params.get("code"); selectedKind = params.get("kind") || "auto"; }
  loadWarehouses().then(() => quickList("unit")).then(() => { if (params.get("code")) return openCard(); }).catch((error) => message(error.message, "err"));
})();
