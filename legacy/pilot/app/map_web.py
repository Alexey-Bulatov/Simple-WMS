from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.page_shell import standard_page

router = APIRouter()


@router.get("/map", response_class=HTMLResponse, include_in_schema=False)
@standard_page("map")
def map_page() -> str:
    return """<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Складской пилот: карта</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #eef1f3;
      --panel: #fff;
      --line: #d5dce1;
      --text: #17212b;
      --muted: #687480;
      --accent: #087a70;
      --accent-soft: #e7f7f4;
      --dark: #101820;
      --danger: #b42318;
      --warning: #a15c07;
      --blue: #175cd3;
    }
    * { box-sizing: border-box; }
    html, body { height: 100%; }
    body { margin: 0; overflow: hidden; background: var(--bg); color: var(--text); font: 14px/1.4 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    header { height: 54px; padding: 8px 16px; display: flex; align-items: center; justify-content: space-between; gap: 16px; color: #fff; background: var(--dark); }
    header h1 { margin: 0; font-size: 18px; letter-spacing: 0; white-space: nowrap; }
    nav { display: flex; align-items: center; gap: 13px; overflow-x: auto; white-space: nowrap; }
    nav a { color: #d8fbf6; text-decoration: none; font-weight: 750; }
    nav a.active { color: #fff; text-decoration: underline; text-underline-offset: 5px; }
    main { height: calc(100vh - 54px); display: grid; grid-template-columns: 250px minmax(0, 1fr) 292px; }
    aside { min-height: 0; overflow-y: auto; padding: 14px; background: var(--panel); }
    aside.left { border-right: 1px solid var(--line); }
    aside.right { border-left: 1px solid var(--line); }
    h2, h3 { margin: 0; letter-spacing: 0; }
    h2 { font-size: 17px; }
    h3 { font-size: 13px; }
    .stack { display: grid; gap: 11px; }
    .row { display: flex; align-items: center; gap: 7px; }
    .row > * { flex: 1; min-width: 0; }
    label { display: block; margin-bottom: 4px; color: var(--muted); font-size: 10px; font-weight: 900; text-transform: uppercase; }
    input, select, button { width: 100%; min-height: 38px; border: 1px solid var(--line); border-radius: 6px; padding: 7px 9px; background: #fff; color: var(--text); font: inherit; }
    button { cursor: pointer; border-color: var(--accent); background: var(--accent); color: #fff; font-weight: 850; }
    button.secondary { background: #effaf8; color: #08645d; }
    button.ghost { border-color: var(--line); background: #fff; color: var(--text); }
    button.danger { border-color: var(--danger); background: var(--danger); }
    button:disabled { cursor: not-allowed; border-color: var(--line); background: #e9edef; color: #929da5; }
    .section { display: grid; gap: 9px; padding-bottom: 13px; border-bottom: 1px solid var(--line); }
    .section:last-child { padding-bottom: 0; border-bottom: 0; }
    .stats { display: grid; grid-template-columns: 1fr 1fr; gap: 7px; }
    .stat { padding: 8px; border-left: 3px solid var(--line); background: #f7f9fa; }
    .stat b { display: block; font-size: 18px; }
    .stat span { color: var(--muted); font-size: 10px; font-weight: 800; text-transform: uppercase; }
    .legend { display: grid; gap: 6px; }
    .legend-row { display: flex; align-items: center; gap: 8px; font-size: 12px; }
    .swatch { width: 18px; height: 18px; flex: 0 0 auto; border: 2px solid var(--line); border-radius: 4px; background: #fff; }
    .swatch.occupied { border-color: #087a70; background: #cceee8; }
    .swatch.reserved { border-color: #c77700; background: #ffedbd; }
    .swatch.problem { border-color: #b42318; background: #ffd7d2; }
    .swatch.expedition { border-color: #175cd3; background: #d8e7ff; }
    .editor { display: none; }
    .editor.active { display: grid; }
    .workspace { min-width: 0; min-height: 0; display: grid; grid-template-rows: 52px minmax(0, 1fr) 34px; background: #e7ebee; }
    .toolbar { padding: 7px 10px; display: flex; align-items: center; justify-content: space-between; gap: 10px; border-bottom: 1px solid var(--line); background: #fff; }
    .toolbar-title { min-width: 0; }
    .toolbar-title strong { display: block; font-size: 15px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .toolbar-title span { color: var(--muted); font-size: 11px; }
    .toolbar-actions { display: flex; align-items: center; gap: 5px; }
    .icon-button { width: 38px; min-width: 38px; padding: 0; font-size: 18px; }
    .zoom-label { min-width: 52px; color: var(--muted); text-align: center; font-size: 11px; font-weight: 800; }
    .mode-badge { padding: 5px 8px; border-radius: 5px; color: #344054; background: #edf1f3; font-size: 11px; font-weight: 850; }
    .mode-badge.edit { color: #08645d; background: var(--accent-soft); }
    .map-viewport { min-width: 0; min-height: 0; overflow: auto; padding: 16px; }
    .canvas-sizer { position: relative; margin: auto; }
    .map-canvas { position: absolute; left: 0; top: 0; width: 1000px; height: 600px; overflow: hidden; border: 1px solid #bac4ca; background: #f9fafb; transform-origin: left top; user-select: none; }
    .grid-line { position: absolute; z-index: 0; pointer-events: none; background: #e4e8eb; }
    .grid-line.vertical { top: 0; bottom: 0; width: 1px; }
    .grid-line.horizontal { left: 0; right: 0; height: 1px; }
    .map-canvas.editing { cursor: crosshair; }
    .map-item { position: absolute; overflow: visible; }
    .map-item.selected { outline: 3px solid #111820; outline-offset: 3px; }
    .map-item.dragging { opacity: .82; z-index: 20 !important; }
    .rack { z-index: 2; border: 2px solid #65737d; border-radius: 5px; background: #dce2e5; }
    .rack-name { position: absolute; left: 0; top: -22px; max-width: 100%; padding: 2px 5px; color: #35434d; background: rgba(249, 250, 251, .92); font-size: 11px; font-weight: 900; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .location { z-index: 4; display: grid; align-content: center; justify-items: center; gap: 2px; border: 2px solid #9aa6ad; border-radius: 5px; background: #fff; box-shadow: 0 1px 2px rgba(16, 24, 32, .08); cursor: pointer; }
    .editing .location, .editing .rack, .editing .map-label, .editing .aisle { cursor: move; }
    .location.occupied { border-color: #087a70; background: #cceee8; }
    .location.reserved { border-color: #c77700; background: #ffedbd; }
    .location.problem { border-color: #b42318; background: #ffd7d2; }
    .location.expedition { border-color: #175cd3; background: #d8e7ff; }
    .location.receiving { border-color: #667085; background: #e8ecef; }
    .location-code { max-width: 100%; padding: 0 4px; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; font-weight: 950; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .location-meta { color: #4e5c66; font-size: 9px; font-weight: 800; }
    .map-label { z-index: 5; display: flex; align-items: center; padding: 4px 7px; border-left: 4px solid var(--accent); background: rgba(255, 255, 255, .88); font-size: 15px; font-weight: 900; }
    .aisle { z-index: 1; display: flex; align-items: center; justify-content: center; border: 2px dashed #aab4ba; color: #7b878f; background: #eef1f3; font-size: 11px; font-weight: 850; text-transform: uppercase; }
    .workspace-footer { padding: 7px 12px; display: flex; align-items: center; justify-content: space-between; gap: 10px; border-top: 1px solid var(--line); color: var(--muted); background: #fff; font-size: 11px; }
    .status { position: fixed; left: 50%; bottom: 16px; z-index: 50; min-width: 280px; max-width: min(620px, calc(100vw - 30px)); padding: 10px 12px; border: 1px solid #b7d8ef; border-radius: 6px; background: #eff8ff; box-shadow: 0 8px 24px rgba(16, 24, 32, .16); font-weight: 800; transform: translateX(-50%); }
    .status.ok { color: #067647; border-color: #a7e1c2; background: #eafaf1; }
    .status.err { color: var(--danger); border-color: #f0b8b2; background: #fff0ee; }
    .status.hidden { display: none; }
    .object-code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 16px; font-weight: 900; overflow-wrap: anywhere; }
    .detail { padding: 8px 0; border-bottom: 1px solid #e5e9eb; }
    .detail:last-child { border-bottom: 0; }
    .detail b { display: block; color: var(--muted); font-size: 10px; text-transform: uppercase; }
    .detail span { display: block; margin-top: 2px; font-weight: 800; overflow-wrap: anywhere; }
    .pallet { padding: 8px; border: 1px solid var(--line); border-radius: 6px; background: #f8fafb; }
    .pallet strong { display: block; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; overflow-wrap: anywhere; }
    .empty-inspector { color: var(--muted); }
    .hidden { display: none !important; }
    @media (max-width: 1050px) {
      main { grid-template-columns: 220px minmax(0, 1fr); }
      aside.right { display: none; }
    }
    @media (max-width: 720px) {
      body { overflow: auto; }
      header { height: auto; min-height: 54px; align-items: flex-start; flex-direction: column; }
      main { height: auto; min-height: calc(100vh - 90px); grid-template-columns: 1fr; }
      aside.left { border-right: 0; border-bottom: 1px solid var(--line); }
      .workspace { min-height: 620px; }
      .map-viewport { padding: 8px; }
    }
  </style>
</head>
<body>
  <header>
    <h1>Складской пилот: карта</h1>
    <nav>
      <a href="/scan">Склад</a>
      <a href="/terminal">ТСД</a>
      <a class="active" href="/map">Карта</a>
      <a href="/shipments">Отгрузки</a>
      <a href="/inventory">Инвентаризация</a>
      <a href="/catalog">Справочники</a>
      <a href="/cards">Карточки</a>
      <a href="/docs">API</a>
    </nav>
  </header>

  <main>
    <aside class="left">
      <div class="stack">
        <div class="section">
          <h2>Склад</h2>
          <select id="warehouseSelect"></select>
          <button id="editModeBtn" class="secondary" type="button">Редактировать схему</button>
        </div>
        <div class="section">
          <h3>Состояние</h3>
          <div class="stats">
            <div class="stat"><b id="statLocations">0</b><span>Ячеек</span></div>
            <div class="stat"><b id="statPallets">0</b><span>Палет</span></div>
            <div class="stat"><b id="statEmpty">0</b><span>Свободно</span></div>
            <div class="stat"><b id="statProblems">0</b><span>Проблем</span></div>
          </div>
        </div>
        <div class="section">
          <h3>Обозначения</h3>
          <div class="legend">
            <div class="legend-row"><span class="swatch"></span>Свободная</div>
            <div class="legend-row"><span class="swatch occupied"></span>Занята</div>
            <div class="legend-row"><span class="swatch reserved"></span>Резерв</div>
            <div class="legend-row"><span class="swatch expedition"></span>Экспедиция</div>
            <div class="legend-row"><span class="swatch problem"></span>Проблема</div>
          </div>
        </div>
        <div id="editorPanel" class="section editor stack">
          <h3>Новый ряд</h3>
          <div class="row">
            <input id="rowCode" class="mono" placeholder="R03" aria-label="Код ряда">
            <input id="rowCount" type="number" min="1" max="8" value="4" aria-label="Количество ячеек">
          </div>
          <input id="rowLabel" placeholder="Название стеллажа" aria-label="Название стеллажа">
          <select id="rowOrientation" aria-label="Ориентация ряда">
            <option value="horizontal">Горизонтально</option>
            <option value="vertical">Вертикально</option>
          </select>
          <button id="addRowBtn" type="button">Добавить ряд</button>
          <h3>Отдельная ячейка</h3>
          <input id="locationCode" class="mono" placeholder="WH02-ST01-X01" aria-label="Код новой ячейки">
          <input id="locationLabel" placeholder="Название ячейки" aria-label="Название новой ячейки">
          <button id="addLocationBtn" class="secondary" type="button">Добавить ячейку</button>
          <h3>Подпись</h3>
          <div class="row">
            <input id="newLabel" placeholder="Название зоны" aria-label="Новая подпись">
            <button id="addLabelBtn" class="secondary" type="button">Добавить</button>
          </div>
          <button id="resetMapBtn" class="danger" type="button">Вернуть демо-схему</button>
        </div>
      </div>
    </aside>

    <section class="workspace">
      <div class="toolbar">
        <div class="toolbar-title"><strong id="warehouseTitle">Карта склада</strong><span id="warehouseSubtitle">Загрузка...</span></div>
        <div class="toolbar-actions">
          <span id="modeBadge" class="mode-badge">Просмотр</span>
          <button id="zoomOutBtn" class="icon-button ghost" type="button" title="Уменьшить">−</button>
          <span id="zoomLabel" class="zoom-label">100%</span>
          <button id="zoomInBtn" class="icon-button ghost" type="button" title="Увеличить">+</button>
          <button id="fitBtn" class="ghost" type="button" title="Вписать карту">Вписать</button>
        </div>
      </div>
      <div id="mapViewport" class="map-viewport">
        <div id="canvasSizer" class="canvas-sizer">
          <div id="mapCanvas" class="map-canvas"></div>
        </div>
      </div>
      <div class="workspace-footer"><span id="footerHint">Выберите ячейку для просмотра</span><span id="unplacedCount"></span></div>
    </section>

    <aside class="right">
      <div id="inspector" class="stack empty-inspector">
        <h2>Объект</h2>
        <div>Выберите ячейку, стеллаж или подпись на карте</div>
      </div>
    </aside>
  </main>

  <div id="status" class="status hidden"></div>

  <script>
    const state = { map: null, warehouses: [], selectedId: null, editMode: false, zoom: 1, drag: null, statusTimer: null };
    const $ = (id) => document.getElementById(id);
    const statusLabels = {
      open: "Открыта", waiting_placement: "Ожидает размещения", available: "Доступна",
      reserved: "В резерве", picking: "Отбор", expedition: "В экспедиции",
      loaded: "Погружена", quarantine: "Карантин", blocked: "Заблокирована",
      shipped: "Отгружена",
    };
    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>\"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'\"':"&quot;","'":"&#039;"}[char]));
    }
    async function api(path, options = {}) {
      const response = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
      const text = await response.text();
      const data = text ? JSON.parse(text) : null;
      if (!response.ok) throw new Error(data?.detail || response.statusText);
      return data;
    }
    function post(path, body = {}) { return api(path, { method: "POST", body: JSON.stringify(body) }); }
    function showStatus(message, kind = "") {
      clearTimeout(state.statusTimer);
      const element = $("status");
      element.textContent = message;
      element.className = `status ${kind}`;
      state.statusTimer = setTimeout(() => element.classList.add("hidden"), 3200);
    }
    function currentItem() { return state.map?.items.find((item) => item.id === state.selectedId) || null; }
    function setZoom(value) {
      state.zoom = Math.max(.45, Math.min(1.6, value));
      $("mapCanvas").style.transform = `scale(${state.zoom})`;
      $("canvasSizer").style.width = `${1000 * state.zoom}px`;
      $("canvasSizer").style.height = `${600 * state.zoom}px`;
      $("zoomLabel").textContent = `${Math.round(state.zoom * 100)}%`;
    }
    function fitMap() {
      const viewport = $("mapViewport");
      const zoom = Math.min((viewport.clientWidth - 32) / 1000, (viewport.clientHeight - 32) / 600, 1);
      setZoom(zoom);
      viewport.scrollTo({ left: 0, top: 0 });
    }
    function shortCode(code) {
      const parts = String(code || "").split("-");
      return parts.length > 3 ? parts.slice(-2).join("-") : code;
    }
    function itemClass(item) {
      if (item.item_type !== "location") return item.item_type === "label" ? "map-label" : item.item_type;
      const receiving = item.location?.kind === "receiving" ? " receiving" : "";
      return `location ${item.location?.state || "empty"}${receiving}`;
    }
    function renderMapItems() {
      const canvas = $("mapCanvas");
      canvas.innerHTML = "";
      for (let x = 40; x < 1000; x += 40) {
        const line = document.createElement("span");
        line.className = "grid-line vertical";
        line.style.left = `${x}px`;
        canvas.appendChild(line);
      }
      for (let y = 40; y < 600; y += 40) {
        const line = document.createElement("span");
        line.className = "grid-line horizontal";
        line.style.top = `${y}px`;
        canvas.appendChild(line);
      }
      const order = { aisle: 1, rack: 2, location: 3, label: 4 };
      const items = [...state.map.items].sort((a, b) => (order[a.item_type] || 9) - (order[b.item_type] || 9));
      items.forEach((item) => {
        const element = document.createElement("div");
        element.className = `map-item ${itemClass(item)}${item.id === state.selectedId ? " selected" : ""}`;
        element.dataset.itemId = item.id;
        element.style.left = `${item.x}px`;
        element.style.top = `${item.y}px`;
        element.style.width = `${item.width}px`;
        element.style.height = `${item.height}px`;
        element.title = item.location?.code || item.label;
        if (item.item_type === "location") {
          const pallets = item.location?.pallets || [];
          const meta = pallets.length ? `${pallets.length} пал. · ${pallets[0].pallet_uid.slice(-6)}` : item.location?.kind === "receiving" ? "приемка" : "свободно";
          element.innerHTML = `<span class="location-code">${escapeHtml(shortCode(item.location?.code))}</span><span class="location-meta">${escapeHtml(meta)}</span>`;
        } else if (item.item_type === "rack") {
          element.innerHTML = `<span class="rack-name">${escapeHtml(item.label)}</span>`;
        } else {
          element.textContent = item.label;
        }
        element.addEventListener("click", (event) => {
          event.stopPropagation();
          selectItem(item.id);
        });
        element.addEventListener("pointerdown", startDrag);
        canvas.appendChild(element);
      });
      canvas.classList.toggle("editing", state.editMode && state.map.editable);
    }
    function renderStats() {
      const stats = state.map.stats;
      $("statLocations").textContent = stats.locations;
      $("statPallets").textContent = stats.pallets;
      $("statEmpty").textContent = stats.empty;
      $("statProblems").textContent = stats.problems;
      $("warehouseTitle").textContent = `${state.map.warehouse.code} · ${state.map.warehouse.name}`;
      $("warehouseSubtitle").textContent = state.map.editable ? "Учебный склад" : "Демонстрационный склад";
      $("unplacedCount").textContent = state.map.unplaced_locations.length ? `Без места на карте: ${state.map.unplaced_locations.length}` : "Все ячейки размещены";
      $("editModeBtn").disabled = !state.map.editable;
      $("editModeBtn").textContent = state.map.editable ? (state.editMode ? "Завершить редактирование" : "Редактировать схему") : "Схема защищена";
      $("editorPanel").classList.toggle("active", state.editMode && state.map.editable);
      $("modeBadge").textContent = state.editMode ? "Редактирование" : "Просмотр";
      $("modeBadge").classList.toggle("edit", state.editMode);
      $("footerHint").textContent = state.editMode ? "Перетаскивайте объекты мышью" : "Выберите ячейку для просмотра";
    }
    function renderInspector() {
      const item = currentItem();
      if (!item) {
        $("inspector").className = "stack empty-inspector";
        $("inspector").innerHTML = `<h2>Объект</h2><div>Выберите ячейку, стеллаж или подпись на карте</div>`;
        return;
      }
      const location = item.location;
      const pallets = location?.pallets || [];
      $("inspector").className = "stack";
      $("inspector").innerHTML = `
        <h2>${escapeHtml(item.item_type === "location" ? "Ячейка" : item.item_type === "rack" ? "Стеллаж" : item.item_type === "aisle" ? "Проход" : "Подпись")}</h2>
        <div class="object-code">${escapeHtml(location?.code || item.label)}</div>
        ${location ? `
          <div class="detail"><b>Состояние</b><span>${escapeHtml(location.state === "empty" ? "Свободна" : location.state === "occupied" ? "Занята" : location.state === "reserved" ? "Резерв" : location.state === "problem" ? "Проблема" : "Экспедиция")}</span></div>
          <div class="detail"><b>Вместимость</b><span>${location.pallets.length} / ${location.capacity_pallets}</span></div>
          <div id="inspectorPallets" class="stack">${pallets.map((pallet) => `<div class="pallet"><strong>${escapeHtml(pallet.pallet_uid)}</strong><span>${escapeHtml(statusLabels[pallet.status] || pallet.status)} · ${pallet.box_count} кор.</span><div class="meta">${escapeHtml(pallet.product_name)} · ${escapeHtml(pallet.batch_number)}</div></div>`).join("") || `<div class="empty-inspector">Ячейка свободна</div>`}</div>
          <div class="row"><a href="/cards?kind=location&code=${encodeURIComponent(location.code)}"><button class="secondary" type="button">Карточка</button></a><a href="/api/locations/${encodeURIComponent(location.code)}/label.pdf" target="_blank"><button class="ghost" type="button">PDF</button></a></div>
        ` : ""}
        ${state.editMode && state.map.editable ? `
          <div class="section">
            <label for="selectedLabel">Подпись</label>
            <input id="selectedLabel" value="${escapeHtml(item.label)}">
            <button id="saveSelectedBtn" class="secondary" type="button">Сохранить подпись</button>
            ${item.item_type === "rack" ? `<button id="rotateSelectedBtn" class="ghost" type="button">Повернуть на 90°</button>` : ""}
            <button id="deleteSelectedBtn" class="danger" type="button">Удалить объект</button>
          </div>
        ` : ""}
      `;
      $("saveSelectedBtn")?.addEventListener("click", saveSelectedLabel);
      $("rotateSelectedBtn")?.addEventListener("click", rotateSelected);
      $("deleteSelectedBtn")?.addEventListener("click", deleteSelected);
    }
    function render() {
      renderStats();
      renderMapItems();
      renderInspector();
      const racks = state.map.items.filter((item) => item.item_type === "rack").length;
      if (!$("rowCode").value) $("rowCode").value = `R${String(racks + 1).padStart(2, "0")}`;
    }
    async function loadMap(code, fit = false) {
      state.map = await api(`/api/maps/${encodeURIComponent(code)}`);
      if (!state.map.editable) state.editMode = false;
      if (!state.map.items.some((item) => item.id === state.selectedId)) state.selectedId = null;
      render();
      if (fit) requestAnimationFrame(fitMap);
    }
    function selectItem(id) {
      state.selectedId = id;
      renderMapItems();
      renderInspector();
    }
    function startDrag(event) {
      if (!state.editMode || !state.map.editable || event.button !== 0) return;
      const element = event.currentTarget;
      const item = state.map.items.find((row) => row.id === Number(element.dataset.itemId));
      if (!item || item.is_locked) return;
      event.preventDefault();
      state.selectedId = item.id;
      document.querySelectorAll(".map-item.selected").forEach((row) => row.classList.remove("selected"));
      element.classList.add("selected");
      renderInspector();
      element.setPointerCapture(event.pointerId);
      const children = state.map.items.filter((row) => row.parent_id === item.id).map((row) => ({ id: row.id, x: row.x, y: row.y }));
      state.drag = { item, element, startX: event.clientX, startY: event.clientY, originalX: item.x, originalY: item.y, children };
      element.classList.add("dragging");
      element.addEventListener("pointermove", moveDrag);
      element.addEventListener("pointerup", endDrag, { once: true });
      element.addEventListener("pointercancel", endDrag, { once: true });
    }
    function moveDrag(event) {
      if (!state.drag) return;
      const dx = Math.round((event.clientX - state.drag.startX) / state.zoom);
      const dy = Math.round((event.clientY - state.drag.startY) / state.zoom);
      const x = Math.max(0, Math.min(1000 - state.drag.item.width, state.drag.originalX + dx));
      const y = Math.max(0, Math.min(600 - state.drag.item.height, state.drag.originalY + dy));
      state.drag.element.style.left = `${x}px`;
      state.drag.element.style.top = `${y}px`;
      state.drag.children.forEach((child) => {
        const childElement = $(`map-item-${child.id}`) || document.querySelector(`[data-item-id="${child.id}"]`);
        if (childElement) {
          childElement.style.left = `${child.x + x - state.drag.originalX}px`;
          childElement.style.top = `${child.y + y - state.drag.originalY}px`;
        }
      });
      state.drag.x = x;
      state.drag.y = y;
    }
    async function endDrag(event) {
      if (!state.drag) return;
      const drag = state.drag;
      state.drag = null;
      drag.element.classList.remove("dragging");
      drag.element.removeEventListener("pointermove", moveDrag);
      try {
        const x = drag.x ?? drag.originalX;
        const y = drag.y ?? drag.originalY;
        if (x !== drag.originalX || y !== drag.originalY) {
          state.map = await post(`/api/maps/${state.map.warehouse.code}/items/${drag.item.id}`, { x, y, actor: "map-editor" });
          render();
          showStatus("Положение сохранено", "ok");
        }
      } catch (error) {
        showStatus(error.message, "err");
        await loadMap(state.map.warehouse.code);
      }
    }
    async function addRow() {
      const code = $("rowCode").value.trim().toUpperCase();
      const label = $("rowLabel").value.trim() || `Стеллаж ${code}`;
      if (!code) throw new Error("Введите код ряда");
      const rackCount = state.map.items.filter((item) => item.item_type === "rack").length;
      const orientation = $("rowOrientation").value;
      const position = orientation === "vertical"
        ? { x: 690 + (rackCount % 2) * 150, y: 40 }
        : { x: 70, y: 90 + (rackCount % 4) * 125 };
      state.map = await post(`/api/maps/${state.map.warehouse.code}/rows`, {
        zone_code: "ST01", row_code: code, label,
        location_count: Number($("rowCount").value), orientation,
        x: position.x, y: position.y, actor: "map-editor",
      });
      $("rowCode").value = "";
      $("rowLabel").value = "";
      render();
      showStatus(`Ряд ${code} и его ячейки созданы в БД`, "ok");
    }
    async function addLocation() {
      const code = $("locationCode").value.trim().toUpperCase();
      const label = $("locationLabel").value.trim() || code;
      if (!code) throw new Error("Введите код ячейки");
      state.map = await post(`/api/maps/${state.map.warehouse.code}/locations`, {
        zone_code: "ST01", code, label, x: 760, y: 500, width: 110, height: 58, actor: "map-editor",
      });
      $("locationCode").value = "";
      $("locationLabel").value = "";
      render();
      showStatus(`Ячейка ${code} создана в справочнике`, "ok");
    }
    async function addLabel() {
      const label = $("newLabel").value.trim();
      if (!label) throw new Error("Введите подпись");
      state.map = await post(`/api/maps/${state.map.warehouse.code}/labels`, { label, x: 680, y: 40, width: 240, height: 40, actor: "map-editor" });
      $("newLabel").value = "";
      render();
      showStatus("Подпись добавлена", "ok");
    }
    async function saveSelectedLabel() {
      const item = currentItem();
      const label = $("selectedLabel").value.trim();
      if (!item || !label) return;
      state.map = await post(`/api/maps/${state.map.warehouse.code}/items/${item.id}`, { label, actor: "map-editor" });
      render();
      showStatus("Подпись сохранена", "ok");
    }
    async function rotateSelected() {
      const item = currentItem();
      if (!item || item.item_type !== "rack") return;
      state.map = await post(`/api/maps/${state.map.warehouse.code}/items/${item.id}`, { rotation: item.rotation === 90 ? 0 : 90, actor: "map-editor" });
      render();
      showStatus("Стеллаж повёрнут", "ok");
    }
    async function deleteSelected() {
      const item = currentItem();
      if (!item) return;
      const subject = item.location?.code || item.label;
      if (!window.confirm(`Удалить «${subject}»? Связанные пустые ячейки будут удалены из БД.`)) return;
      state.map = await post(`/api/maps/${state.map.warehouse.code}/items/${item.id}/delete`, { actor: "map-editor" });
      state.selectedId = null;
      render();
      showStatus("Объект и связанные пустые ячейки удалены", "ok");
    }
    async function resetMap() {
      if (!window.confirm("Вернуть исходную схему WH02? Все созданные пустые ячейки будут удалены из БД.")) return;
      state.map = await post(`/api/maps/${state.map.warehouse.code}/reset`, { actor: "map-editor" });
      state.selectedId = null;
      $("rowCode").value = "";
      render();
      showStatus("Учебная схема и справочник ячеек восстановлены", "ok");
    }
    function run(action) { action().catch((error) => showStatus(error.message, "err")); }
    $("warehouseSelect").addEventListener("change", (event) => loadMap(event.currentTarget.value, true).catch((error) => showStatus(error.message, "err")));
    $("editModeBtn").addEventListener("click", () => {
      if (!state.map?.editable) return;
      state.editMode = !state.editMode;
      render();
    });
    $("zoomOutBtn").addEventListener("click", () => setZoom(state.zoom - .1));
    $("zoomInBtn").addEventListener("click", () => setZoom(state.zoom + .1));
    $("fitBtn").addEventListener("click", fitMap);
    $("addRowBtn").addEventListener("click", () => run(addRow));
    $("addLocationBtn").addEventListener("click", () => run(addLocation));
    $("addLabelBtn").addEventListener("click", () => run(addLabel));
    $("resetMapBtn").addEventListener("click", () => run(resetMap));
    $("mapCanvas").addEventListener("click", () => selectItem(null));
    window.addEventListener("resize", () => requestAnimationFrame(fitMap));
    post("/api/maps/setup", { actor: "map-ui" })
      .then((warehouses) => {
        state.warehouses = warehouses;
        $("warehouseSelect").innerHTML = warehouses.map((warehouse) => `<option value="${escapeHtml(warehouse.code)}">${escapeHtml(warehouse.code)} · ${escapeHtml(warehouse.name)}</option>`).join("");
        const requestedWarehouse = new URLSearchParams(window.location.search).get("warehouse");
        const initialWarehouse = warehouses.some((warehouse) => warehouse.code === requestedWarehouse)
          ? requestedWarehouse
          : warehouses[0].code;
        $("warehouseSelect").value = initialWarehouse;
        return loadMap(initialWarehouse, true);
      })
      .catch((error) => showStatus(error.message, "err"));
  </script>
</body>
</html>"""
