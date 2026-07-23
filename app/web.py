from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse

from app.page_shell import standard_page

router = APIRouter()


@router.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/work")


@router.get("/terminal", response_class=HTMLResponse, include_in_schema=False)
@standard_page("terminal", desktop_only=True)
def terminal_page() -> str:
    return """<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
  <title>Складской пилот: ТСД</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #e7ebee;
      --screen: #f5f7f8;
      --panel: #fff;
      --line: #d5dce1;
      --text: #17212b;
      --muted: #687480;
      --accent: #087a70;
      --accent-soft: #e8f7f4;
      --danger: #b42318;
      --danger-soft: #fff0ee;
      --warn: #9a5b0a;
      --warn-soft: #fff7e8;
      --ok: #087443;
      --ok-soft: #eafaf1;
      --dark: #101820;
    }
    * { box-sizing: border-box; }
    html, body { min-height: 100%; }
    body { margin: 0; background: var(--bg); color: var(--text); font: 14px/1.35 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    .desktop-header { min-height: 54px; padding: 10px 18px; display: flex; align-items: center; justify-content: space-between; gap: 16px; color: #fff; background: var(--dark); }
    .desktop-header h1 { margin: 0; font-size: 18px; letter-spacing: 0; }
    .desktop-nav { display: flex; align-items: center; gap: 14px; white-space: nowrap; overflow-x: auto; }
    .desktop-nav a { color: #d8fbf6; text-decoration: none; font-weight: 750; }
    .desktop-nav a.active { color: #fff; text-decoration: underline; text-underline-offset: 5px; }
    .stage { min-height: calc(100vh - 54px); padding: 12px; display: grid; place-items: center; }
    .device { width: 390px; height: min(780px, calc(100vh - 78px)); min-height: 560px; overflow: hidden; border: 10px solid #202a33; border-radius: 24px; background: var(--screen); box-shadow: 0 18px 46px rgba(16, 24, 32, .22); }
    .device-bar { height: 28px; padding: 0 12px; display: flex; align-items: center; justify-content: space-between; color: #dce7ec; background: #202a33; font-size: 11px; font-weight: 800; }
    .app { height: calc(100% - 28px); display: grid; grid-template-rows: auto auto minmax(0, 1fr); background: var(--screen); }
    .app-head { min-height: 50px; padding: 9px 12px; display: flex; align-items: center; justify-content: space-between; gap: 8px; color: #fff; background: var(--accent); }
    .app-head strong { display: block; font-size: 17px; }
    .app-head span { display: block; margin-top: 1px; color: #d4fff9; font-size: 11px; }
    .operator { max-width: 130px; overflow: hidden; text-align: right; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; font-weight: 800; }
    .mode-tabs { display: grid; grid-template-columns: repeat(5, 1fr); border-bottom: 1px solid var(--line); background: #fff; }
    .mode-tabs button { min-height: 46px; border: 0; border-right: 1px solid var(--line); border-radius: 0; background: #fff; color: #43515c; font-size: 12px; font-weight: 850; }
    .mode-tabs button:last-child { border-right: 0; }
    .mode-tabs button.active { color: var(--accent); background: var(--accent-soft); box-shadow: inset 0 -3px 0 var(--accent); }
    .view { min-height: 0; overflow-y: auto; padding: 10px; display: none; }
    .view.active { display: block; }
    .stack { display: grid; gap: 9px; }
    .row { display: flex; gap: 8px; align-items: center; }
    .row > * { flex: 1; min-width: 0; }
    .segmented { display: grid; grid-template-columns: 1fr 1fr; padding: 3px; border: 1px solid var(--line); border-radius: 7px; background: #e9edef; }
    .segmented button { min-height: 38px; border: 0; border-radius: 5px; background: transparent; color: #53616c; }
    .segmented button.active { background: #fff; color: var(--accent); box-shadow: 0 1px 3px rgba(16, 24, 32, .14); }
    label { display: block; margin-bottom: 4px; color: var(--muted); font-size: 10px; font-weight: 900; text-transform: uppercase; }
    input, select, button { width: 100%; min-height: 42px; border: 1px solid var(--line); border-radius: 6px; padding: 8px 10px; background: #fff; color: var(--text); font: inherit; }
    button { cursor: pointer; border-color: var(--accent); background: var(--accent); color: #fff; font-weight: 850; }
    button.secondary { background: #f2fbf9; color: #08655e; }
    button.ghost { border-color: var(--line); background: #fff; color: var(--text); }
    button.danger { border-color: var(--danger); background: var(--danger); }
    button:disabled { cursor: not-allowed; border-color: var(--line); background: #e9edef; color: #929da5; }
    .scan { min-height: 58px; border: 2px solid var(--accent); font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 19px; font-weight: 900; letter-spacing: 0; }
    .status { min-height: 52px; padding: 9px 10px; border: 1px solid #b9d7ef; border-radius: 6px; background: #edf7ff; font-weight: 800; overflow-wrap: anywhere; }
    .status.ok { color: var(--ok); border-color: #a7e1c2; background: var(--ok-soft); }
    .status.err { color: var(--danger); border-color: #f3b9b3; background: var(--danger-soft); }
    .status.warn { color: var(--warn); border-color: #efd28d; background: var(--warn-soft); }
    .object { padding: 10px; border: 1px solid var(--line); border-radius: 7px; background: #fff; }
    .object-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }
    .object-code { min-width: 0; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 16px; font-weight: 900; overflow-wrap: anywhere; }
    .badge { flex: 0 0 auto; padding: 3px 7px; border-radius: 5px; color: #41505a; background: #edf1f3; font-size: 10px; font-weight: 900; }
    .facts { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; margin-top: 8px; }
    .fact { min-width: 0; padding: 6px; border: 1px solid #e1e6e9; border-radius: 5px; background: #fafbfc; }
    .fact b { display: block; color: var(--muted); font-size: 9px; text-transform: uppercase; }
    .fact span { display: block; margin-top: 2px; font-weight: 900; overflow-wrap: anywhere; }
    .progress { height: 10px; overflow: hidden; border-radius: 5px; background: #e1e7e9; }
    .progress span { display: block; height: 100%; width: 0; background: var(--accent); transition: width .2s ease; }
    .list { display: grid; gap: 6px; }
    .list-item { padding: 8px; border: 1px solid var(--line); border-radius: 6px; background: #fff; }
    .list-item strong { display: block; overflow-wrap: anywhere; }
    .task-item { border-left: 5px solid #96a2aa; }
    .task-item.normal { border-left-color: var(--accent); }
    .task-item.high { border-left-color: #d89725; }
    .task-item.urgent { border-left-color: var(--danger); }
    .task-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }
    .task-title { margin: 4px 0 2px; font-weight: 900; overflow-wrap: anywhere; }
    .task-code { font: 800 11px/1.3 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; overflow-wrap: anywhere; }
    .task-item button { margin-top: 7px; }
    .meta { color: var(--muted); font-size: 11px; }
    .hidden { display: none !important; }
    .footer-note { padding: 4px 0 2px; color: var(--muted); text-align: center; font-size: 10px; }
    @media (max-width: 620px) {
      .desktop-header { display: none; }
      .stage { min-height: 100dvh; padding: 0; display: block; }
      .device { width: 100%; height: 100dvh; min-height: 0; border: 0; border-radius: 0; box-shadow: none; }
      .device-bar { height: 24px; }
      .app { height: calc(100% - 24px); }
    }
  </style>
</head>
<body>
  <header class="desktop-header">
    <h1>Складской пилот: эмулятор ТСД</h1>
    <nav class="desktop-nav">
      <a href="/scan">Склад</a>
      <a class="active" href="/terminal">ТСД</a>
      <a href="/map">Карта</a>
      <a href="/shipments">Отгрузки</a>
      <a href="/inventory">Инвентаризация</a>
      <a href="/catalog">Справочники</a>
      <a href="/cards">Карточки</a>
      <a href="/docs">API</a>
    </nav>
  </header>

  <main class="stage">
    <section class="device" aria-label="Эмулятор экрана ТСД">
      <div class="device-bar"><span id="clock">--:--</span><span>WMS · Wi-Fi · 87%</span></div>
      <div class="app">
        <div class="app-head">
          <div><strong id="screenTitle">Задания</strong><span id="screenSubtitle">Моя очередь</span></div>
          <div id="operatorLabel" class="operator">tsd-demo</div>
        </div>
        <div class="mode-tabs">
          <button id="modeTasks" class="active" type="button">Задания</button>
          <button id="modeWarehouse" type="button">Склад</button>
          <button id="modeInventory" type="button">Инвент.</button>
          <button id="modeTransfer" type="button">Перем.</button>
          <button id="modeShipping" type="button">Погрузка</button>
        </div>

        <div id="tasksView" class="view active">
          <div class="stack">
            <div class="row">
              <div>
                <label for="taskActor">Оператор</label>
                <input id="taskActor" list="taskUserOptions" autocomplete="off" value="tsd-demo">
                <datalist id="taskUserOptions"></datalist>
              </div>
              <div>
                <label for="taskWarehouse">Склад</label>
                <select id="taskWarehouse"><option value="">Склад</option></select>
              </div>
            </div>
            <div class="facts">
              <div class="fact"><b>Мои</b><span id="taskMineCount">0</span></div>
              <div class="fact"><b>Свободные</b><span id="taskFreeCount">0</span></div>
              <div class="fact"><b>В работе</b><span id="taskProgressCount">0</span></div>
            </div>
            <div id="taskStatus" class="status">Загрузка очереди</div>
            <button id="refreshTasks" class="secondary" type="button">Обновить очередь</button>
            <div id="taskList" class="list"></div>
          </div>
        </div>

        <div id="warehouseView" class="view">
          <div class="stack">
            <div class="segmented">
              <button id="buildMode" class="active" type="button">Формирование</button>
              <button id="placeMode" type="button">Размещение</button>
            </div>
            <div>
              <label for="warehouseScan">Сканер</label>
              <input id="warehouseScan" class="scan" autocomplete="off" autofocus placeholder="Коробка / палета / ячейка">
            </div>
            <div id="warehouseStatus" class="status">Выберите палету или откройте новую</div>
            <div class="object">
              <div class="object-head">
                <div><div class="meta">Активная палета</div><div id="palletUid" class="object-code">Не выбрана</div></div>
                <span id="palletStatus" class="badge">-</span>
              </div>
              <div class="facts">
                <div class="fact"><b>Коробок</b><span id="palletBoxes">0</span></div>
                <div class="fact"><b>Ячейка</b><span id="palletLocation">-</span></div>
                <div class="fact"><b>Партия</b><span id="palletBatch">-</span></div>
              </div>
            </div>
            <div>
              <label for="palletSelect">Палеты в работе</label>
              <select id="palletSelect"><option value="">Не выбрана</option></select>
            </div>
            <div class="row">
              <button id="newPallet" type="button">Новая</button>
              <button id="closePallet" class="danger" type="button">Закрыть</button>
              <button id="clearPallet" class="ghost" type="button">Сброс</button>
            </div>
            <div class="footer-note">Сканер работает как клавиатура с Enter</div>
          </div>
        </div>

        <div id="inventoryView" class="view">
          <div class="stack">
            <div>
              <label for="inventorySelect">Открытая инвентаризация</label>
              <select id="inventorySelect"><option value="">Не выбрана</option></select>
            </div>
            <div id="newInventoryRow" class="row">
              <select id="warehouseSelect"><option value="">Склад</option></select>
              <button id="startInventory" class="secondary" type="button">Начать</button>
            </div>
            <div>
              <label for="inventoryScan">Скан ячейки или палеты</label>
              <input id="inventoryScan" class="scan" autocomplete="off" placeholder="Ячейка / палета">
            </div>
            <div id="inventoryStatus" class="status">Выберите открытую инвентаризацию</div>
            <div class="object">
              <div class="object-head">
                <div><div class="meta">Текущая ячейка</div><div id="inventoryLocation" class="object-code">-</div></div>
                <span id="inventoryPercent" class="badge">0%</span>
              </div>
              <div class="progress"><span id="inventoryProgress"></span></div>
              <div class="facts">
                <div class="fact"><b>Ячейки</b><span id="inventoryLocations">0/0</span></div>
                <div class="fact"><b>Палеты</b><span id="inventoryPallets">0/0</span></div>
                <div class="fact"><b>Проблемы</b><span id="inventoryProblems">0</span></div>
              </div>
            </div>
            <div class="row">
              <button id="emptyLocation" class="secondary" type="button">Пусто</button>
              <button id="refreshInventory" class="ghost" type="button">Обновить</button>
            </div>
            <button id="completeInventory" class="danger" type="button" disabled>Завершить пересчёт</button>
            <div id="inventoryProblemsList" class="list"></div>
          </div>
        </div>

        <div id="shippingView" class="view">
          <div class="stack">
            <div>
              <label for="shipmentSelect">Активная отгрузка</label>
              <select id="shipmentSelect"><option value="">Не выбрана</option></select>
            </div>
            <div>
              <label for="shippingScan">Скан погрузки</label>
              <input id="shippingScan" class="scan" autocomplete="off" placeholder="Код палеты">
            </div>
            <div id="shippingStatus" class="status">Выберите подготовленную отгрузку</div>
            <div class="object">
              <div class="object-head">
                <div><div class="meta">Заявка</div><div id="shipmentUid" class="object-code">-</div></div>
                <span id="shipmentStatus" class="badge">-</span>
              </div>
              <div class="facts">
                <div class="fact"><b>Погружено</b><span id="shipmentLoaded">0/0</span></div>
                <div class="fact"><b>Клиент</b><span id="shipmentCustomer">-</span></div>
                <div class="fact"><b>Точка</b><span id="shipmentDestination">-</span></div>
              </div>
            </div>
            <div class="row">
              <button id="toExpedition" class="secondary" type="button">В экспедицию</button>
              <button id="refreshShipment" class="ghost" type="button">Обновить</button>
            </div>
            <button id="closeShipment" class="danger" type="button">Завершить погрузку</button>
            <div id="shipmentPallets" class="list"></div>
          </div>
        </div>

        <div id="transferView" class="view">
          <div class="stack">
            <div>
              <label for="transferSelect">Межскладское перемещение</label>
              <select id="transferSelect"><option value="">Не выбрано</option></select>
            </div>
            <div>
              <label id="transferScanLabel" for="transferScan">Скан палеты</label>
              <input id="transferScan" class="scan" autocomplete="off" placeholder="Код палеты">
            </div>
            <div id="transferStatus" class="status">Выберите перемещение</div>
            <div class="object">
              <div class="object-head">
                <div><div class="meta">Документ</div><div id="transferUid" class="object-code">-</div></div>
                <span id="transferState" class="badge">-</span>
              </div>
              <div class="facts">
                <div class="fact"><b>Маршрут</b><span id="transferRoute">-</span></div>
                <div class="fact"><b>Погружено</b><span id="transferLoaded">0/0</span></div>
                <div class="fact"><b>Принято</b><span id="transferReceived">0/0</span></div>
              </div>
            </div>
            <div class="row">
              <button id="transferExpedition" class="secondary" type="button">В отправку</button>
              <button id="refreshTransfer" class="ghost" type="button">Обновить</button>
            </div>
            <button id="dispatchTransfer" class="danger" type="button">Отправить в путь</button>
            <div id="transferPallets" class="list"></div>
          </div>
        </div>
      </div>
    </section>
  </main>

  <script>
    const state = {
      mode: "tasks",
      warehouseMode: "build",
      actor: localStorage.getItem("wms.terminal.actor") || "tsd-demo",
      taskWarehouseCode: localStorage.getItem("wms.terminal.warehouse") || "",
      tasks: [],
      activePalletUid: "",
      activeInventoryUid: "",
      activeShipmentUid: "",
      activeTransferUid: "",
      locations: [],
      batches: [],
      prefixes: { box: "BOX-", pallet: "PLT-" },
      currentInventoryLocation: "",
    };
    let taskActorRefreshTimer;
    const $ = (id) => document.getElementById(id);
    const palletLabels = {
      open: "Открыта", waiting_placement: "Ждёт размещения", available: "Доступна",
      reserved: "В резерве", expedition: "В экспедиции", loaded: "Погружена",
      in_transit: "В пути", received: "Принята", blocked: "Заблокирована",
      quarantine: "Карантин", shipped: "Отгружена",
    };
    const shipmentLabels = {
      draft: "Черновик", reserved: "В резерве", expedition: "Экспедиция",
      loading: "Погрузка", completed: "Завершена", cancelled: "Отменена",
    };
    const transferLabels = {
      draft: "Черновик", reserved: "В резерве", expedition: "Зона отправки",
      loading: "Погрузка", in_transit: "В пути", receiving: "Приёмка",
      completed: "Завершено", cancelled: "Отменено",
    };
    const taskTypeLabels = {
      build: "Формирование", place: "Размещение", move: "Перемещение",
      ship: "Отгрузка", inventory: "Инвентаризация", transfer: "Между складами",
    };
    const taskPriorityLabels = { low: "Низкий", normal: "Обычный", high: "Высокий", urgent: "Срочный" };
    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, (char) =>
        ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[char]
      );
    }
    function label(map, value) { return map[value] || value || "-"; }
    function setStatus(id, message, kind = "") {
      const element = $(id);
      element.className = `status ${kind}`;
      element.textContent = message;
    }
    async function api(path, options = {}) {
      const response = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
      const text = await response.text();
      const data = text ? JSON.parse(text) : null;
      if (!response.ok) throw new Error(data?.detail || response.statusText);
      return data;
    }
    function post(path, body = {}) {
      return api(path, { method: "POST", body: JSON.stringify(body) });
    }
    function focusCurrent() {
      if (state.mode === "tasks") return;
      const id = state.mode === "warehouse" ? "warehouseScan"
        : state.mode === "inventory" ? "inventoryScan"
        : state.mode === "transfer" ? "transferScan"
        : "shippingScan";
      setTimeout(() => $(id).focus(), 30);
    }
    function showError(statusId, error) {
      setStatus(statusId, error.message || String(error), "err");
      focusCurrent();
    }
    function updateClock() {
      $("clock").textContent = new Date().toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
    }
    function setMode(mode) {
      state.mode = mode;
      ["tasks", "warehouse", "inventory", "transfer", "shipping"].forEach((name) => {
        $(`${name}View`).classList.toggle("active", name === mode);
      });
      $("modeTasks").classList.toggle("active", mode === "tasks");
      $("modeWarehouse").classList.toggle("active", mode === "warehouse");
      $("modeInventory").classList.toggle("active", mode === "inventory");
      $("modeTransfer").classList.toggle("active", mode === "transfer");
      $("modeShipping").classList.toggle("active", mode === "shipping");
      const titles = {
        tasks: ["Задания", "Моя очередь"],
        warehouse: ["Склад", state.warehouseMode === "build" ? "Формирование палеты" : "Размещение палеты"],
        inventory: ["Инвентаризация", "Обход склада"],
        transfer: ["Перемещение", "Погрузка и приёмка"],
        shipping: ["Погрузка", "Контроль отгрузки"],
      };
      $("screenTitle").textContent = titles[mode][0];
      $("screenSubtitle").textContent = titles[mode][1];
      focusCurrent();
    }
    function setWarehouseMode(mode) {
      state.warehouseMode = mode;
      $("buildMode").classList.toggle("active", mode === "build");
      $("placeMode").classList.toggle("active", mode === "place");
      $("screenSubtitle").textContent = mode === "build" ? "Формирование палеты" : "Размещение палеты";
      setStatus("warehouseStatus", mode === "build" ? "Сканируйте коробки" : "Сканируйте палету, затем ячейку", "warn");
      focusCurrent();
    }
    function batchNumber(batchId) {
      return state.batches.find((batch) => batch.id === batchId)?.batch_number || "-";
    }
    async function loadBaseData() {
      const [constants, locations, batches, warehouses, users] = await Promise.all([
        api("/api/meta/constants"), api("/api/locations"), api("/api/batches"), api("/api/warehouses"), api("/api/users"),
      ]);
      state.prefixes.box = `${constants.box_code_prefix}-`;
      state.prefixes.pallet = `${constants.pallet_code_prefix}-`;
      state.locations = locations;
      state.batches = batches;
      $("warehouseSelect").innerHTML = warehouses.map((warehouse) =>
        `<option value="${warehouse.code}">${warehouse.code}</option>`
      ).join("") || `<option value="">Нет складов</option>`;
      $("taskWarehouse").innerHTML = warehouses.map((warehouse) =>
        `<option value="${escapeHtml(warehouse.code)}">${escapeHtml(warehouse.code)}</option>`
      ).join("") || `<option value="">Нет складов</option>`;
      if (!warehouses.some((warehouse) => warehouse.code === state.taskWarehouseCode)) {
        state.taskWarehouseCode = warehouses[0]?.code || "";
      }
      $("taskWarehouse").value = state.taskWarehouseCode;
      $("taskActor").value = state.actor;
      $("operatorLabel").textContent = state.actor;
      $("taskUserOptions").innerHTML = users.filter((user) => user.is_active).map((user) =>
        `<option value="${escapeHtml(user.full_name)}">${escapeHtml(user.username)}</option>`
      ).join("");
    }

    function showTaskError(error) {
      setStatus("taskStatus", error.message || String(error), "err");
    }
    function renderTasks() {
      const mine = state.tasks.filter((task) => task.assigned_to === state.actor);
      const free = state.tasks.filter((task) => !task.assigned_to);
      $("taskMineCount").textContent = mine.length;
      $("taskFreeCount").textContent = free.length;
      $("taskProgressCount").textContent = state.tasks.filter((task) => task.status === "in_progress").length;
      $("taskList").innerHTML = state.tasks.map((task) => {
        const ownership = task.assigned_to ? task.assigned_to : "Свободно";
        const action = task.status === "in_progress" ? "Продолжить" : task.assigned_to ? "Начать" : "Взять";
        return `<div class="list-item task-item ${escapeHtml(task.priority)}">
          <div class="task-head">
            <span class="task-code">${escapeHtml(task.object_uid || task.task_uid)}</span>
            <span class="badge">${escapeHtml(taskPriorityLabels[task.priority] || task.priority)}</span>
          </div>
          <div class="task-title">${escapeHtml(task.title)}</div>
          <div class="meta">${escapeHtml(taskTypeLabels[task.task_type] || task.task_type)} · ${escapeHtml(ownership)}</div>
          <button type="button" data-start-task="${escapeHtml(task.task_uid)}">${action}</button>
        </div>`;
      }).join("") || `<div class="list-item">Активных заданий нет</div>`;
      document.querySelectorAll("[data-start-task]").forEach((button) => {
        button.addEventListener("click", () => beginTask(button.dataset.startTask).catch(showTaskError));
      });
    }
    async function refreshTasks(sync = true) {
      if (!state.taskWarehouseCode) {
        state.tasks = [];
        renderTasks();
        setStatus("taskStatus", "Выберите склад", "warn");
        return;
      }
      if (sync) {
        await post("/api/tasks/sync", { warehouse_code: state.taskWarehouseCode, actor: state.actor });
      }
      const query = new URLSearchParams();
      query.set("warehouse_code", state.taskWarehouseCode);
      query.append("status", "new");
      query.append("status", "in_progress");
      query.set("assigned_to", state.actor);
      query.set("include_unassigned", "true");
      query.set("limit", "200");
      state.tasks = await api(`/api/tasks?${query.toString()}`);
      renderTasks();
      setStatus("taskStatus", `В очереди: ${state.tasks.length}`, state.tasks.length ? "ok" : "");
    }
    async function routeTask(task) {
      if (["build", "place", "move"].includes(task.task_type)) {
        state.activePalletUid = task.object_uid || "";
        await Promise.all([refreshPalletChoices(), refreshActivePallet()]);
        setWarehouseMode(task.task_type === "build" ? "build" : "place");
        setMode("warehouse");
      } else if (task.task_type === "ship") {
        state.activeShipmentUid = task.object_uid || "";
        await refreshShipments();
        setMode("shipping");
      } else if (task.task_type === "inventory") {
        state.activeInventoryUid = task.object_uid || "";
        await refreshInventories();
        setMode("inventory");
      } else if (task.task_type === "transfer") {
        state.activeTransferUid = task.object_uid || "";
        await refreshTransfers();
        setMode("transfer");
      }
    }
    async function beginTask(taskUid) {
      let task = state.tasks.find((item) => item.task_uid === taskUid);
      if (!task) throw new Error("Задание не найдено");
      if (task.status === "new") {
        task = await post(`/api/tasks/${encodeURIComponent(taskUid)}/start`, { actor: state.actor });
      }
      await routeTask(task);
    }

    async function refreshPalletChoices() {
      const pallets = await api("/api/pallets?status=open&status=waiting_placement&status=available&limit=200");
      $("palletSelect").innerHTML = `<option value="">Не выбрана</option>` + pallets.map((pallet) =>
        `<option value="${pallet.pallet_uid}">${pallet.pallet_uid} · ${label(palletLabels, pallet.status)} · ${pallet.box_count} кор.</option>`
      ).join("");
      $("palletSelect").value = state.activePalletUid;
    }
    async function refreshActivePallet() {
      if (!state.activePalletUid) {
        $("palletUid").textContent = "Не выбрана";
        $("palletStatus").textContent = "-";
        $("palletBoxes").textContent = "0";
        $("palletLocation").textContent = "-";
        $("palletBatch").textContent = "-";
        $("palletSelect").value = "";
        return;
      }
      const [pallet, boxes] = await Promise.all([
        api(`/api/pallets/${encodeURIComponent(state.activePalletUid)}`),
        api(`/api/pallets/${encodeURIComponent(state.activePalletUid)}/boxes`),
      ]);
      const location = state.locations.find((item) => item.id === pallet.current_location_id);
      $("palletUid").textContent = pallet.pallet_uid;
      $("palletStatus").textContent = label(palletLabels, pallet.status);
      $("palletBoxes").textContent = boxes.length;
      $("palletLocation").textContent = location?.code || "-";
      $("palletBatch").textContent = batchNumber(pallet.batch_id);
      $("palletSelect").value = state.activePalletUid;
    }
    async function selectPallet(uid) {
      state.activePalletUid = uid;
      await refreshActivePallet();
      setStatus("warehouseStatus", uid ? `Палета выбрана: ${uid}` : "Палета сброшена", uid ? "ok" : "warn");
      focusCurrent();
    }
    async function createPallet() {
      const pallet = await post("/api/pallets", { actor: state.actor });
      state.activePalletUid = pallet.pallet_uid;
      setWarehouseMode("build");
      await Promise.all([refreshPalletChoices(), refreshActivePallet()]);
      setStatus("warehouseStatus", `Открыта палета ${pallet.pallet_uid}`, "ok");
    }
    async function addBox(code) {
      if (!state.activePalletUid) await createPallet();
      setWarehouseMode("build");
      try {
        await post(`/api/boxes/${encodeURIComponent(code)}/accept`, { actor: state.actor });
      } catch (error) {
        if (!String(error.message).includes("cannot be accepted")) throw error;
      }
      await post(`/api/pallets/${encodeURIComponent(state.activePalletUid)}/boxes/${encodeURIComponent(code)}`, { actor: state.actor });
      await refreshActivePallet();
      setStatus("warehouseStatus", `Коробка добавлена: ${code}`, "ok");
    }
    async function closePallet() {
      if (!state.activePalletUid) throw new Error("Сначала выберите палету");
      await post(`/api/pallets/${encodeURIComponent(state.activePalletUid)}/close`, { actor: state.actor, reason: "ТСД" });
      setWarehouseMode("place");
      await Promise.all([refreshPalletChoices(), refreshActivePallet()]);
      setStatus("warehouseStatus", "Палета закрыта. Сканируйте ячейку", "ok");
    }
    async function placePallet(locationCode) {
      if (!state.activePalletUid) throw new Error("Сначала отсканируйте палету");
      const pallet = await api(`/api/pallets/${encodeURIComponent(state.activePalletUid)}`);
      const action = pallet.status === "available" ? "move" : "place";
      await post(`/api/pallets/${encodeURIComponent(state.activePalletUid)}/${action}`, {
        actor: state.actor, reason: "ТСД", location_code: locationCode,
      });
      await Promise.all([refreshPalletChoices(), refreshActivePallet()]);
      setStatus("warehouseStatus", `Размещено: ${locationCode}`, "ok");
    }
    async function handleWarehouseScan(code) {
      if (code.startsWith(state.prefixes.box)) return addBox(code);
      if (code.startsWith(state.prefixes.pallet)) {
        setWarehouseMode("place");
        return selectPallet(code);
      }
      return placePallet(code);
    }

    async function refreshInventories(selectLatest = false) {
      const inventories = await api("/api/inventories?limit=50");
      const open = inventories.filter((item) => item.status === "open");
      $("inventorySelect").innerHTML = `<option value="">Не выбрана</option>` + open.map((item) =>
        `<option value="${item.inventory_uid}">${item.inventory_uid} · ${item.warehouse_code}</option>`
      ).join("");
      if (selectLatest && !state.activeInventoryUid && open.length) state.activeInventoryUid = open[0].inventory_uid;
      if (state.activeInventoryUid && !open.some((item) => item.inventory_uid === state.activeInventoryUid)) state.activeInventoryUid = "";
      $("inventorySelect").value = state.activeInventoryUid;
      await refreshActiveInventory();
    }
    async function refreshActiveInventory() {
      if (!state.activeInventoryUid) {
        state.currentInventoryLocation = "";
        $("inventoryLocation").textContent = "-";
        $("inventoryPercent").textContent = "0%";
        $("inventoryProgress").style.width = "0%";
        $("inventoryLocations").textContent = "0/0";
        $("inventoryPallets").textContent = "0/0";
        $("inventoryProblems").textContent = "0";
        $("emptyLocation").disabled = true;
        $("completeInventory").disabled = true;
        $("inventoryProblemsList").innerHTML = "";
        setStatus("inventoryStatus", "Выберите открытую инвентаризацию", "warn");
        return;
      }
      const [inventory, progress] = await Promise.all([
        api(`/api/inventories/${state.activeInventoryUid}`),
        api(`/api/inventories/${state.activeInventoryUid}/progress`),
      ]);
      state.currentInventoryLocation = inventory.current_location_code || "";
      $("inventoryLocation").textContent = state.currentInventoryLocation || "-";
      $("inventoryPercent").textContent = `${progress.progress_percent}%`;
      $("inventoryProgress").style.width = `${progress.progress_percent}%`;
      $("inventoryLocations").textContent = `${progress.checked_locations}/${progress.total_locations}`;
      $("inventoryPallets").textContent = `${inventory.scanned_count}/${inventory.expected_count}`;
      $("inventoryProblems").textContent = progress.problem_lines.length;
      $("emptyLocation").disabled = !state.currentInventoryLocation;
      $("completeInventory").disabled = progress.unchecked_locations !== 0;
      $("inventoryProblemsList").innerHTML = progress.problem_lines.slice(0, 3).map((line) =>
        `<div class="list-item"><strong>${line.pallet.pallet_uid}</strong><span class="meta">${line.status} · ожидалась ${line.expected_location_code || "-"} · факт ${line.actual_location_code || "-"}</span></div>`
      ).join("");
      setStatus("inventoryStatus", state.currentInventoryLocation ? "Сканируйте палету или нажмите «Пусто»" : "Сканируйте следующую ячейку", "ok");
    }
    async function startInventory() {
      const warehouseCode = $("warehouseSelect").value;
      if (!warehouseCode) throw new Error("Выберите склад");
      const inventory = await post("/api/inventories", { warehouse_code: warehouseCode, actor: state.actor });
      state.activeInventoryUid = inventory.inventory_uid;
      await refreshInventories();
      setStatus("inventoryStatus", `Начат обход ${warehouseCode}`, "ok");
    }
    async function scanInventoryLocation(code) {
      if (!state.activeInventoryUid) throw new Error("Выберите или начните инвентаризацию");
      await post(`/api/inventories/${state.activeInventoryUid}/scan-location`, { location_code: code, actor: state.actor });
      await refreshActiveInventory();
      setStatus("inventoryStatus", `Ячейка ${code}: сканируйте палету или нажмите «Пусто»`, "ok");
    }
    async function scanInventoryPallet(code) {
      if (!state.activeInventoryUid) throw new Error("Выберите инвентаризацию");
      if (!state.currentInventoryLocation) throw new Error("Сначала отсканируйте ячейку");
      await post(`/api/inventories/${state.activeInventoryUid}/scan`, { pallet_uid: code, actor: state.actor });
      await refreshActiveInventory();
      setStatus("inventoryStatus", `Палета ${code} проверена. Следующая ячейка`, "ok");
    }
    async function confirmEmptyLocation() {
      if (!state.currentInventoryLocation) throw new Error("Сначала отсканируйте ячейку");
      const code = state.currentInventoryLocation;
      await post(`/api/inventories/${state.activeInventoryUid}/confirm-location`, { location_code: code, actor: state.actor });
      await refreshActiveInventory();
      setStatus("inventoryStatus", `Пустая ячейка подтверждена: ${code}`, "ok");
    }
    async function finishInventory() {
      await post(`/api/inventories/${state.activeInventoryUid}/complete`, { actor: state.actor });
      state.activeInventoryUid = "";
      await refreshInventories(true);
      setStatus("inventoryStatus", "Инвентаризация завершена", "ok");
    }
    async function handleInventoryScan(code) {
      if (code.startsWith(state.prefixes.pallet)) return scanInventoryPallet(code);
      if (!state.locations.some((item) => item.code === code)) throw new Error(`Ячейка не найдена: ${code}`);
      return scanInventoryLocation(code);
    }

    async function refreshShipments(selectLatest = false) {
      const shipments = await api("/api/shipments?limit=50");
      const active = shipments.filter((item) => !["completed", "cancelled"].includes(item.status));
      $("shipmentSelect").innerHTML = `<option value="">Не выбрана</option>` + active.map((item) =>
        `<option value="${item.shipment_uid}">${item.shipment_uid} · ${label(shipmentLabels, item.status)}</option>`
      ).join("");
      if (selectLatest && !state.activeShipmentUid && active.length) state.activeShipmentUid = active[0].shipment_uid;
      if (state.activeShipmentUid && !active.some((item) => item.shipment_uid === state.activeShipmentUid)) state.activeShipmentUid = "";
      $("shipmentSelect").value = state.activeShipmentUid;
      await refreshActiveShipment();
    }
    async function refreshActiveShipment() {
      if (!state.activeShipmentUid) {
        $("shipmentUid").textContent = "-";
        $("shipmentStatus").textContent = "-";
        $("shipmentLoaded").textContent = "0/0";
        $("shipmentCustomer").textContent = "-";
        $("shipmentDestination").textContent = "-";
        $("shipmentPallets").innerHTML = "";
        $("toExpedition").disabled = true;
        $("closeShipment").disabled = true;
        setStatus("shippingStatus", "Выберите подготовленную отгрузку", "warn");
        return;
      }
      const [shipment, pallets] = await Promise.all([
        api(`/api/shipments/${state.activeShipmentUid}`),
        api(`/api/shipments/${state.activeShipmentUid}/pallets`),
      ]);
      $("shipmentUid").textContent = shipment.shipment_uid;
      $("shipmentStatus").textContent = label(shipmentLabels, shipment.status);
      $("shipmentLoaded").textContent = `${shipment.loaded_count}/${shipment.pallet_count}`;
      $("shipmentCustomer").textContent = shipment.customer_name;
      $("shipmentDestination").textContent = shipment.destination;
      $("toExpedition").disabled = !["reserved"].includes(shipment.status);
      $("closeShipment").disabled = !shipment.pallet_count || shipment.loaded_count !== shipment.pallet_count;
      $("shipmentPallets").innerHTML = pallets.map((row) =>
        `<div class="list-item"><strong>${row.pallet.pallet_uid}</strong><span class="meta">${label(palletLabels, row.shipment_pallet_status)} · ${row.pallet.box_count} кор.</span></div>`
      ).join("") || `<div class="list-item">Палеты не назначены</div>`;
      setStatus("shippingStatus", shipment.status === "reserved" ? "Передайте палеты в экспедицию" : "Сканируйте палеты при погрузке", "ok");
    }
    async function moveToExpedition() {
      if (!state.activeShipmentUid) throw new Error("Выберите отгрузку");
      await post(`/api/shipments/${state.activeShipmentUid}/expedition`, { actor: state.actor });
      await refreshShipments();
      setStatus("shippingStatus", "Палеты переданы в экспедицию", "ok");
    }
    async function loadShipmentPallet(code) {
      if (!state.activeShipmentUid) throw new Error("Выберите отгрузку");
      await post(`/api/shipments/${state.activeShipmentUid}/load/${encodeURIComponent(code)}`, { actor: state.actor });
      await refreshActiveShipment();
      setStatus("shippingStatus", `Палета погружена: ${code}`, "ok");
    }
    async function finishShipment() {
      await post(`/api/shipments/${state.activeShipmentUid}/close`, { actor: state.actor, reason: "погрузка завершена с ТСД" });
      state.activeShipmentUid = "";
      await refreshShipments(true);
      setStatus("shippingStatus", "Погрузка завершена", "ok");
    }

    async function refreshTransfers(selectLatest = false) {
      const transfers = await api("/api/transfers?limit=50");
      const active = transfers.filter((item) => !["completed", "cancelled"].includes(item.status));
      $("transferSelect").innerHTML = `<option value="">Не выбрано</option>` + active.map((item) =>
        `<option value="${item.transfer_uid}">${item.transfer_uid} · ${item.source_warehouse_code}→${item.destination_warehouse_code} · ${label(transferLabels, item.status)}</option>`
      ).join("");
      if (selectLatest && !state.activeTransferUid && active.length) state.activeTransferUid = active[0].transfer_uid;
      if (state.activeTransferUid && !active.some((item) => item.transfer_uid === state.activeTransferUid)) state.activeTransferUid = "";
      $("transferSelect").value = state.activeTransferUid;
      await refreshActiveTransfer();
    }
    async function refreshActiveTransfer() {
      if (!state.activeTransferUid) {
        $("transferUid").textContent = "-";
        $("transferState").textContent = "-";
        $("transferRoute").textContent = "-";
        $("transferLoaded").textContent = "0/0";
        $("transferReceived").textContent = "0/0";
        $("transferPallets").innerHTML = "";
        $("transferExpedition").disabled = true;
        $("dispatchTransfer").disabled = true;
        $("transferScan").disabled = true;
        setStatus("transferStatus", "Выберите перемещение", "warn");
        return;
      }
      const [transfer, pallets] = await Promise.all([
        api(`/api/transfers/${state.activeTransferUid}`),
        api(`/api/transfers/${state.activeTransferUid}/pallets`),
      ]);
      $("transferUid").textContent = transfer.transfer_uid;
      $("transferState").textContent = label(transferLabels, transfer.status);
      $("transferRoute").textContent = `${transfer.source_warehouse_code}→${transfer.destination_warehouse_code}`;
      $("transferLoaded").textContent = `${transfer.loaded_count}/${transfer.pallet_count}`;
      $("transferReceived").textContent = `${transfer.received_count}/${transfer.pallet_count}`;
      $("transferExpedition").disabled = transfer.status !== "reserved";
      $("dispatchTransfer").disabled = transfer.status !== "loading" || transfer.loaded_count !== transfer.pallet_count;
      const receiving = ["in_transit", "receiving"].includes(transfer.status);
      $("transferScan").disabled = !receiving && !["expedition", "loading"].includes(transfer.status);
      $("transferScanLabel").textContent = receiving ? "Скан приёмки" : "Скан погрузки";
      $("transferPallets").innerHTML = pallets.map((row) =>
        `<div class="list-item"><strong>${row.pallet.pallet_uid}</strong><span class="meta">${label(palletLabels, row.transfer_pallet_status)} · ${row.source_location_code || "-"}</span></div>`
      ).join("") || `<div class="list-item">Палеты не назначены</div>`;
      setStatus(
        "transferStatus",
        receiving ? `Приёмка на ${transfer.destination_warehouse_code}` : transfer.status === "reserved" ? "Передайте палеты в зону отправки" : "Сканируйте палеты",
        "ok",
      );
    }
    async function moveTransferToExpedition() {
      if (!state.activeTransferUid) throw new Error("Выберите перемещение");
      await post(`/api/transfers/${state.activeTransferUid}/expedition`, { actor: state.actor });
      await refreshActiveTransfer();
      setStatus("transferStatus", "Палеты в зоне отправки", "ok");
    }
    async function handleTransferScan(code) {
      if (!state.activeTransferUid) throw new Error("Выберите перемещение");
      const transfer = await api(`/api/transfers/${state.activeTransferUid}`);
      const receiving = ["in_transit", "receiving"].includes(transfer.status);
      const action = receiving ? "receive" : "load";
      await post(`/api/transfers/${state.activeTransferUid}/${action}/${encodeURIComponent(code)}`, { actor: state.actor });
      await refreshActiveTransfer();
      setStatus("transferStatus", receiving ? `Палета принята: ${code}` : `Палета погружена: ${code}`, "ok");
    }
    async function dispatchActiveTransfer() {
      if (!state.activeTransferUid) throw new Error("Выберите перемещение");
      await post(`/api/transfers/${state.activeTransferUid}/dispatch`, { actor: state.actor, reason: "отправлено с ТСД" });
      await refreshActiveTransfer();
      setStatus("transferStatus", "Палеты отправлены в путь", "ok");
    }

    function bindScan(inputId, handler, statusId) {
      $(inputId).addEventListener("keydown", (event) => {
        if (event.key !== "Enter") return;
        event.preventDefault();
        const code = event.currentTarget.value.trim().toUpperCase();
        event.currentTarget.value = "";
        if (!code) return;
        handler(code).catch((error) => showError(statusId, error)).finally(focusCurrent);
      });
    }
    $("modeTasks").addEventListener("click", () => {
      setMode("tasks");
      refreshTasks(true).catch(showTaskError);
    });
    $("modeWarehouse").addEventListener("click", () => setMode("warehouse"));
    $("modeInventory").addEventListener("click", () => setMode("inventory"));
    $("modeTransfer").addEventListener("click", () => setMode("transfer"));
    $("modeShipping").addEventListener("click", () => setMode("shipping"));
    $("buildMode").addEventListener("click", () => setWarehouseMode("build"));
    $("placeMode").addEventListener("click", () => setWarehouseMode("place"));
    $("palletSelect").addEventListener("change", (event) => selectPallet(event.currentTarget.value).catch((error) => showError("warehouseStatus", error)));
    $("newPallet").addEventListener("click", () => createPallet().catch((error) => showError("warehouseStatus", error)));
    $("closePallet").addEventListener("click", () => closePallet().catch((error) => showError("warehouseStatus", error)));
    $("clearPallet").addEventListener("click", () => selectPallet("").catch((error) => showError("warehouseStatus", error)));
    $("inventorySelect").addEventListener("change", (event) => {
      state.activeInventoryUid = event.currentTarget.value;
      refreshActiveInventory().catch((error) => showError("inventoryStatus", error));
    });
    $("startInventory").addEventListener("click", () => startInventory().catch((error) => showError("inventoryStatus", error)));
    $("emptyLocation").addEventListener("click", () => confirmEmptyLocation().catch((error) => showError("inventoryStatus", error)));
    $("refreshInventory").addEventListener("click", () => refreshInventories().catch((error) => showError("inventoryStatus", error)));
    $("completeInventory").addEventListener("click", () => finishInventory().catch((error) => showError("inventoryStatus", error)));
    $("shipmentSelect").addEventListener("change", (event) => {
      state.activeShipmentUid = event.currentTarget.value;
      refreshActiveShipment().catch((error) => showError("shippingStatus", error));
    });
    $("toExpedition").addEventListener("click", () => moveToExpedition().catch((error) => showError("shippingStatus", error)));
    $("refreshShipment").addEventListener("click", () => refreshShipments().catch((error) => showError("shippingStatus", error)));
    $("closeShipment").addEventListener("click", () => finishShipment().catch((error) => showError("shippingStatus", error)));
    $("transferSelect").addEventListener("change", (event) => {
      state.activeTransferUid = event.currentTarget.value;
      refreshActiveTransfer().catch((error) => showError("transferStatus", error));
    });
    $("transferExpedition").addEventListener("click", () => moveTransferToExpedition().catch((error) => showError("transferStatus", error)));
    $("refreshTransfer").addEventListener("click", () => refreshTransfers().catch((error) => showError("transferStatus", error)));
    $("dispatchTransfer").addEventListener("click", () => dispatchActiveTransfer().catch((error) => showError("transferStatus", error)));
    function applyTaskActor(input) {
      state.actor = input.value.trim() || "tsd-demo";
      $("operatorLabel").textContent = state.actor;
      localStorage.setItem("wms.terminal.actor", state.actor);
      refreshTasks(true).catch(showTaskError);
    }
    $("taskActor").addEventListener("input", (event) => {
      const input = event.currentTarget;
      clearTimeout(taskActorRefreshTimer);
      taskActorRefreshTimer = setTimeout(() => applyTaskActor(input), 300);
    });
    $("taskActor").addEventListener("change", (event) => {
      clearTimeout(taskActorRefreshTimer);
      applyTaskActor(event.currentTarget);
    });
    $("taskWarehouse").addEventListener("change", (event) => {
      state.taskWarehouseCode = event.currentTarget.value;
      localStorage.setItem("wms.terminal.warehouse", state.taskWarehouseCode);
      refreshTasks(true).catch(showTaskError);
    });
    $("refreshTasks").addEventListener("click", () => refreshTasks(true).catch(showTaskError));
    bindScan("warehouseScan", handleWarehouseScan, "warehouseStatus");
    bindScan("inventoryScan", handleInventoryScan, "inventoryStatus");
    bindScan("transferScan", handleTransferScan, "transferStatus");
    bindScan("shippingScan", loadShipmentPallet, "shippingStatus");
    updateClock();
    setInterval(updateClock, 30000);
    loadBaseData()
      .then(() => Promise.all([refreshTasks(true), refreshPalletChoices(), refreshInventories(true), refreshTransfers(true), refreshShipments(true)]))
      .then(refreshActivePallet)
      .catch(showTaskError);
  </script>
</body>
</html>"""


@router.get("/cards", response_class=HTMLResponse, include_in_schema=False)
@standard_page("cards")
def cards_page() -> str:
    return """<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Складской пилот: карточки</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f4f6f7;
      --panel: #fff;
      --line: #d7dde2;
      --text: #101828;
      --muted: #667085;
      --accent: #0f766e;
      --danger: #b42318;
      --ok: #067647;
      --warn: #a15c07;
      --dark: #111820;
    }
    * { box-sizing: border-box; }
    body { margin: 0; background: var(--bg); color: var(--text); font: 15px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    header { min-height: 54px; padding: 10px 18px; display: flex; align-items: center; justify-content: space-between; gap: 12px; color: #fff; background: var(--dark); }
    header h1 { margin: 0; font-size: 18px; letter-spacing: 0; }
    header a { color: #d8fbf6; text-decoration: none; font-weight: 700; }
    main { max-width: 1280px; margin: 0 auto; padding: 14px; display: grid; grid-template-columns: 360px minmax(0, 1fr); gap: 14px; }
    section, aside { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 14px; }
    h2, h3 { margin: 0; letter-spacing: 0; }
    h2 { font-size: 17px; }
    h3 { font-size: 14px; }
    a { color: #0b5e58; font-weight: 800; text-decoration: none; }
    .stack { display: grid; gap: 12px; }
    .row { display: flex; gap: 8px; align-items: center; }
    .row > * { flex: 1; }
    .grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .grid3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
    label { display: block; margin-bottom: 5px; color: var(--muted); font-size: 12px; font-weight: 800; text-transform: uppercase; }
    input, select, button, textarea { width: 100%; min-height: 40px; border: 1px solid var(--line); border-radius: 6px; padding: 8px 10px; background: #fff; color: var(--text); font: inherit; }
    textarea { min-height: 76px; resize: vertical; }
    button { cursor: pointer; border-color: var(--accent); background: var(--accent); color: #fff; font-weight: 800; }
    button.secondary { background: #f2fbf9; color: #0b5e58; }
    button.ghost { border-color: var(--line); background: #fff; color: var(--text); }
    .status { min-height: 46px; padding: 10px 12px; border: 1px solid #c7dcf3; border-radius: 6px; background: #eff8ff; font-weight: 800; }
    .status.ok { color: var(--ok); border-color: #abefc6; background: #ecfdf3; }
    .status.err { color: var(--danger); border-color: #fecdca; background: #fff1f0; }
    .status.warn { color: var(--warn); border-color: #fedf89; background: #fff8eb; }
    .scan-input { min-height: 62px; border: 2px solid var(--accent); font-size: 24px; font-weight: 900; letter-spacing: 0; }
    .hero-card { display: grid; gap: 10px; padding: 14px; border: 1px solid var(--line); border-radius: 8px; background: #fbfcfd; }
    .uid { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 24px; font-weight: 900; overflow-wrap: anywhere; }
    .facts { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
    .fact { padding: 8px; border: 1px solid var(--line); border-radius: 6px; background: #fff; }
    .fact b { display: block; color: var(--muted); font-size: 11px; text-transform: uppercase; }
    .fact span { display: block; margin-top: 2px; font-weight: 800; overflow-wrap: anywhere; }
    .cards { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
    .panel { display: grid; gap: 8px; padding: 12px; border: 1px solid var(--line); border-radius: 8px; background: #fbfcfd; }
    .list { display: grid; gap: 8px; max-height: 430px; overflow: auto; }
    .item { display: grid; gap: 5px; padding: 10px; border: 1px solid var(--line); border-radius: 8px; background: #fff; }
    .item-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
    .meta { color: var(--muted); font-size: 13px; }
    .badge { display: inline-flex; align-items: center; min-height: 24px; padding: 2px 7px; border-radius: 999px; background: #eef2f6; color: #344054; font-size: 12px; font-weight: 800; white-space: nowrap; }
    .wide { grid-column: 1 / -1; }
    @media (max-width: 980px) {
      main { grid-template-columns: 1fr; padding: 10px; }
      .grid2, .grid3, .cards, .facts { grid-template-columns: 1fr; }
      header { align-items: flex-start; flex-direction: column; }
      .uid { font-size: 20px; }
    }
  </style>
</head>
<body>
  <header>
    <h1>Складской пилот: карточки</h1>
    <div class="row" style="max-width: 700px;">
      <a href="/scan">Склад</a>
      <a href="/terminal">ТСД</a>
      <a href="/map">Карта</a>
      <a href="/shipments">Отгрузки</a>
      <a href="/inventory">Инвентаризация</a>
      <a href="/catalog">Справочники</a>
      <a href="/cards">Карточки</a>
      <a href="/docs">Документация API</a>
    </div>
  </header>

  <main>
    <aside class="stack">
      <h2>Поиск объекта</h2>
      <div id="status" class="status">Отсканируйте или введите код объекта</div>
      <div>
        <label for="codeInput">Код</label>
        <input id="codeInput" class="scan-input mono" autofocus autocomplete="off" placeholder="Палета / коробка / ячейка">
      </div>
      <div>
        <label for="kindSelect">Тип</label>
        <select id="kindSelect">
          <option value="auto">Определить автоматически</option>
          <option value="pallet">Палета</option>
          <option value="box">Коробка</option>
          <option value="location">Ячейка</option>
        </select>
      </div>
      <button id="loadBtn">Открыть карточку</button>
      <button id="pdfBtn" class="secondary">PDF этикетки</button>
      <div class="grid3">
        <button id="samplePalletBtn" class="ghost">Палеты</button>
        <button id="sampleBoxBtn" class="ghost">Коробки</button>
        <button id="sampleLocationBtn" class="ghost">Ячейки</button>
      </div>
      <div id="samples" class="list">
        <div class="item">Выберите быстрый список</div>
      </div>
    </aside>

    <section class="stack">
      <div id="summary" class="hero-card">
        <h2>Карточка объекта</h2>
        <div class="uid">Не выбрана</div>
        <div class="facts">
          <div class="fact"><b>Тип</b><span>-</span></div>
          <div class="fact"><b>Статус</b><span>-</span></div>
          <div class="fact"><b>Ячейка</b><span>-</span></div>
          <div class="fact"><b>Состав</b><span>-</span></div>
        </div>
      </div>
      <div class="cards">
        <div class="panel">
          <h3>Что внутри</h3>
          <div id="contents" class="list"></div>
        </div>
        <div class="panel">
          <h3>Связанные данные</h3>
          <div id="details" class="list"></div>
        </div>
      </div>
      <div class="panel wide">
        <h3>История</h3>
        <div id="history" class="list"></div>
      </div>
    </section>
  </main>

  <script>
    const state = { card: null };
    const $ = (id) => document.getElementById(id);
    const kindLabels = { pallet: "Палета", box: "Коробка", location: "Ячейка" };
    const operationLabels = {
      box_accepted: "Коробка принята",
      box_added_to_pallet: "Коробка добавлена в палету",
      pallet_opened: "Палета открыта",
      pallet_closed: "Палета закрыта",
      pallet_reopened: "Палета переоткрыта",
      pallet_placed: "Палета размещена",
      pallet_moved: "Палета перемещена",
      pallet_released: "Палета возвращена в работу",
      pallet_blocked: "Палета заблокирована",
      pallet_quarantine: "Палета отправлена в карантин",
      pallet_reserved_for_shipment: "Палета зарезервирована",
      pallet_moved_to_expedition: "Палета передана в экспедицию",
      pallet_loaded: "Палета погружена",
      pallet_shipped: "Палета отгружена",
      pallet_reserved_for_transfer: "Палета зарезервирована для перемещения",
      pallet_moved_to_transfer_expedition: "Палета передана в зону отправки",
      pallet_loaded_for_transfer: "Палета погружена для перемещения",
      pallet_dispatched_between_warehouses: "Палета отправлена на другой склад",
      pallet_received_between_warehouses: "Палета принята другим складом",
      inventory_location_scanned: "Ячейка выбрана в инвентаризации",
      inventory_location_confirmed: "Ячейка подтверждена в инвентаризации",
    };
    function label(map, value) { return map[value] || value || "-"; }
    function setStatus(message, kind = "") {
      const el = $("status");
      el.className = `status ${kind}`;
      el.textContent = message;
    }
    function focusCode() { setTimeout(() => $("codeInput").focus(), 30); }
    async function api(path) {
      const response = await fetch(path);
      const text = await response.text();
      const data = text ? JSON.parse(text) : null;
      if (!response.ok) throw new Error(data?.detail || response.statusText);
      return data;
    }
    function item(html) {
      return `<div class="item">${html}</div>`;
    }
    function fact(labelText, value) {
      return `<div class="fact"><b>${labelText}</b><span>${value || "-"}</span></div>`;
    }
    function link(kind, code, text = code) {
      return `<a class="mono" href="/cards?kind=${kind}&code=${encodeURIComponent(code)}">${text}</a>`;
    }
    function renderEvents(events) {
      $("history").innerHTML = (events || []).map((event) => item(`
        <div class="item-head">
          <strong>${label(operationLabels, event.operation)}</strong>
          <span class="badge">${event.actor || "-"}</span>
        </div>
        <div class="meta">${new Date(event.created_at).toLocaleString()}</div>
        ${event.reason ? `<div class="meta">Причина: ${event.reason}</div>` : ""}
      `)).join("") || item("Истории пока нет");
    }
    function renderPallet(card) {
      const pallet = card.pallet;
      $("summary").innerHTML = `
        <h2>Палета</h2>
        <div class="uid">${pallet.pallet_uid}</div>
        <div class="facts">
          ${fact("Статус", pallet.status_label)}
          ${fact("Ячейка", card.location?.code)}
          ${fact("Коробок", card.boxes.length)}
          ${fact("Партия", pallet.batch_number)}
        </div>
      `;
      $("contents").innerHTML = card.boxes.map((box) => item(`
        <div class="item-head">
          ${link("box", box.box_uid)}
          <span class="badge">${box.status_label}</span>
        </div>
        <div class="meta">Добавлена: ${box.added_at ? new Date(box.added_at).toLocaleString() : "-"}</div>
      `)).join("") || item("Коробок пока нет");
      $("details").innerHTML = [
        item(`<strong>Товар</strong><div>${card.product ? `${card.product.code} - ${card.product.name}` : "-"}</div>`),
        item(`<strong>Партия</strong><div>${card.batch ? `${card.batch.batch_number} | годен до ${card.batch.expiry_date}` : "-"}</div>`),
        item(`<strong>Ячейка</strong><div>${card.location ? link("location", card.location.code) : "-"}</div>`),
        item(`<strong>Отгрузка</strong><div>${card.shipment ? card.shipment.shipment_uid : "-"}</div>`),
      ].join("");
      renderEvents(card.events);
    }
    function renderBox(card) {
      const box = card.box;
      $("summary").innerHTML = `
        <h2>Коробка</h2>
        <div class="uid">${box.box_uid}</div>
        <div class="facts">
          ${fact("Статус", box.status_label)}
          ${fact("Палета", card.pallet ? card.pallet.pallet_uid : "-")}
          ${fact("Ячейка", card.location?.code)}
          ${fact("Партия", card.batch?.batch_number)}
        </div>
      `;
      $("contents").innerHTML = item(`
        <strong>Содержимое коробки</strong>
        <div>${card.product ? card.product.name : "-"}</div>
        <div class="meta">${card.product ? `${card.product.quantity_per_box} ${card.product.unit}` : ""}</div>
      `);
      $("details").innerHTML = [
        item(`<strong>Товар</strong><div>${card.product ? `${card.product.code} - ${card.product.name}` : "-"}</div>`),
        item(`<strong>Партия</strong><div>${card.batch ? `${card.batch.batch_number} | годен до ${card.batch.expiry_date}` : "-"}</div>`),
        item(`<strong>Палета</strong><div>${card.pallet ? link("pallet", card.pallet.pallet_uid) : "-"}</div>`),
        item(`<strong>Ячейка</strong><div>${card.location ? link("location", card.location.code) : "-"}</div>`),
      ].join("");
      renderEvents(card.events);
    }
    function renderLocation(card) {
      const location = card.location;
      $("summary").innerHTML = `
        <h2>Ячейка</h2>
        <div class="uid">${location.code}</div>
        <div class="facts">
          ${fact("Тип", location.kind_label)}
          ${fact("Склад", location.warehouse?.code)}
          ${fact("Зона", location.zone?.code)}
          ${fact("Заполнено", `${location.occupied_pallets} / ${location.capacity_pallets}`)}
        </div>
      `;
      $("contents").innerHTML = card.pallets.map((pallet) => item(`
        <div class="item-head">
          ${link("pallet", pallet.pallet_uid)}
          <span class="badge">${pallet.status_label}</span>
        </div>
        <div class="meta">${pallet.box_count} коробок | ${pallet.product_name} | ${pallet.batch_number}</div>
      `)).join("") || item("Ячейка пустая");
      $("details").innerHTML = [
        item(`<strong>Склад</strong><div>${location.warehouse ? `${location.warehouse.code} - ${location.warehouse.name}` : "-"}</div>`),
        item(`<strong>Зона</strong><div>${location.zone ? `${location.zone.code} - ${location.zone.name}` : "-"}</div>`),
        item(`<strong>Вместимость</strong><div>${location.capacity_pallets} пал.; свободно ${location.free_pallet_slots}</div>`),
        item(`<strong>Активность</strong><div>${location.is_active ? "Активна" : "Отключена"}</div>`),
      ].join("");
      renderEvents(card.events);
    }
    function renderCard(card) {
      state.card = card;
      $("kindSelect").value = card.kind;
      if (card.kind === "pallet") renderPallet(card);
      if (card.kind === "box") renderBox(card);
      if (card.kind === "location") renderLocation(card);
      setStatus(`${label(kindLabels, card.kind)} открыта`, "ok");
      focusCode();
    }
    async function loadCard() {
      const rawCode = $("codeInput").value.trim();
      if (!rawCode) throw new Error("Введите код объекта");
      let kind = $("kindSelect").value;
      let code = rawCode;
      if (kind === "auto") {
        const resolved = await api(`/api/cards/resolve/${encodeURIComponent(rawCode)}`);
        kind = resolved.kind;
        code = resolved.code;
      }
      const path = kind === "pallet"
        ? `/api/cards/pallets/${encodeURIComponent(code)}`
        : kind === "box"
          ? `/api/cards/boxes/${encodeURIComponent(code)}`
          : `/api/cards/locations/${encodeURIComponent(code)}`;
      const card = await api(path);
      renderCard(card);
      const params = new URLSearchParams({ kind, code });
      history.replaceState(null, "", `/cards?${params.toString()}`);
    }
    async function quickList(kind) {
      const path = kind === "pallet" ? "/api/pallets?limit=40" : kind === "box" ? "/api/labels/boxes.pdf" : "/api/locations";
      if (kind === "box") {
        $("samples").innerHTML = item("Для коробок пока удобнее открыть через поиск или список палеты");
        return;
      }
      const rows = await api(path);
      $("samples").innerHTML = rows.slice(0, 40).map((row) => {
        const code = kind === "pallet" ? row.pallet_uid : row.code;
        const meta = kind === "pallet" ? `${row.box_count} коробок | ${row.current_location_code || "-"}` : `${row.kind} | вместимость ${row.capacity_pallets}`;
        return item(`<div class="item-head">${link(kind, code)}<span class="badge">${kindLabels[kind]}</span></div><div class="meta">${meta}</div>`);
      }).join("") || item("Нет объектов");
    }
    $("loadBtn").addEventListener("click", () => loadCard().catch((err) => setStatus(err.message, "err")));
    $("pdfBtn").addEventListener("click", () => {
      if (!state.card?.pdf_url) return setStatus("Сначала откройте карточку", "err");
      window.open(state.card.pdf_url, "_blank");
      focusCode();
    });
    $("samplePalletBtn").addEventListener("click", () => quickList("pallet").catch((err) => setStatus(err.message, "err")));
    $("sampleBoxBtn").addEventListener("click", () => quickList("box").catch((err) => setStatus(err.message, "err")));
    $("sampleLocationBtn").addEventListener("click", () => quickList("location").catch((err) => setStatus(err.message, "err")));
    $("codeInput").addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      event.preventDefault();
      loadCard().catch((err) => setStatus(err.message, "err"));
    });
    const params = new URLSearchParams(window.location.search);
    if (params.get("code")) {
      $("codeInput").value = params.get("code");
      $("kindSelect").value = params.get("kind") || "auto";
      loadCard().catch((err) => setStatus(err.message, "err"));
    } else {
      focusCode();
    }
  </script>
</body>
</html>"""


@router.get("/scan", response_class=HTMLResponse, include_in_schema=False)
@standard_page("scan")
def scan_page() -> str:
    return """<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Складской пилот</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f4f6f7;
      --panel: #fff;
      --line: #d7dde2;
      --text: #101828;
      --muted: #667085;
      --accent: #0f766e;
      --accent-soft: #ecfdf3;
      --danger: #b42318;
      --warn: #a15c07;
      --ok: #067647;
      --dark: #111820;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 15px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    header {
      min-height: 54px;
      padding: 10px 18px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      color: #fff;
      background: var(--dark);
    }
    h1, h2, h3 { margin: 0; letter-spacing: 0; }
    h1 { font-size: 18px; }
    h2 { font-size: 17px; }
    h3 { font-size: 14px; }
    header a { color: #d8fbf6; text-decoration: none; font-weight: 750; }
    .top-nav { display: flex; align-items: center; gap: 13px; white-space: nowrap; }
    .nav-more { position: relative; }
    .nav-more summary { cursor: pointer; color: #d8fbf6; font-weight: 750; list-style: none; }
    .nav-more summary::-webkit-details-marker { display: none; }
    .nav-more-menu { position: absolute; right: 0; top: 30px; z-index: 20; min-width: 190px; padding: 7px; display: grid; gap: 2px; border: 1px solid #34424d; border-radius: 6px; background: #1b2630; box-shadow: 0 10px 26px rgba(0, 0, 0, .24); }
    .nav-more-menu a { padding: 7px 9px; border-radius: 4px; }
    .nav-more-menu a:hover { background: #273641; }
    main {
      max-width: 1260px;
      margin: 0 auto;
      padding: 14px;
      display: grid;
      grid-template-columns: minmax(0, 1fr) 390px;
      gap: 14px;
    }
    section, aside {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
    }
    .stack { display: grid; gap: 12px; }
    .row { display: flex; gap: 8px; align-items: center; }
    .row > * { flex: 1; }
    .grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .grid3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
    label {
      display: block;
      margin-bottom: 5px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 800;
      text-transform: uppercase;
    }
    input, select, button {
      width: 100%;
      min-height: 40px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px 10px;
      background: #fff;
      color: var(--text);
      font: inherit;
    }
    button {
      cursor: pointer;
      border-color: var(--accent);
      background: var(--accent);
      color: #fff;
      font-weight: 800;
    }
    button.secondary {
      background: #f2fbf9;
      color: #0b5e58;
    }
    button.danger {
      border-color: var(--danger);
      background: var(--danger);
    }
    button.ghost {
      border-color: var(--line);
      background: #fff;
      color: var(--text);
    }
    .scenario {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
    }
    .warehouse-strip { display: grid; grid-template-columns: minmax(0, 1fr) 190px; gap: 10px; align-items: end; }
    .map-link { min-height: 40px; padding: 8px 10px; display: flex; align-items: center; justify-content: center; border: 1px solid var(--accent); border-radius: 6px; color: #0b5e58; background: #f2fbf9; font-weight: 850; text-decoration: none; }
    .scenario button {
      min-height: 54px;
      border-color: var(--line);
      background: #fff;
      color: var(--text);
      font-size: 16px;
    }
    .scenario button.active {
      border-color: var(--accent);
      background: var(--accent);
      color: #fff;
    }
    .scan-input {
      min-height: 68px;
      border: 2px solid var(--accent);
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 27px;
      font-weight: 900;
      letter-spacing: 0;
    }
    .status {
      min-height: 46px;
      padding: 10px 12px;
      border: 1px solid #c7dcf3;
      border-radius: 6px;
      background: #eff8ff;
      font-weight: 800;
    }
    .status.ok { color: var(--ok); border-color: #abefc6; background: #ecfdf3; }
    .status.err { color: var(--danger); border-color: #fecdca; background: #fff1f0; }
    .status.warn { color: var(--warn); border-color: #fedf89; background: #fff8eb; }
    .active-card {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 10px;
      align-items: start;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fbfcfd;
    }
    .uid {
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 18px;
      font-weight: 900;
      overflow-wrap: anywhere;
    }
    .facts {
      margin-top: 8px;
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 8px;
    }
    .fact {
      padding: 8px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
    }
    .fact b { display: block; color: var(--muted); font-size: 11px; text-transform: uppercase; }
    .fact span { display: block; margin-top: 2px; font-weight: 800; overflow-wrap: anywhere; }
    .pallet-list {
      display: grid;
      gap: 8px;
      max-height: 510px;
      overflow: auto;
    }
    .pallet-item {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 8px;
      align-items: center;
      padding: 10px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
    }
    .pallet-item.active { border-color: var(--accent); background: var(--accent-soft); }
    .pallet-main { min-width: 0; }
    .pallet-main strong {
      display: block;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      overflow-wrap: anywhere;
    }
    .meta { color: var(--muted); font-size: 13px; }
    .badge {
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      padding: 2px 7px;
      border-radius: 999px;
      background: #eef2f6;
      color: #344054;
      font-size: 12px;
      font-weight: 800;
      white-space: nowrap;
    }
    .badge.open { background: #ecfdf3; color: #067647; }
    .badge.waiting_placement { background: #fff8eb; color: #a15c07; }
    .badge.available { background: #eff8ff; color: #175cd3; }
    .box-list, .log {
      max-height: 260px;
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fbfcfd;
    }
    .line {
      padding: 8px 10px;
      border-bottom: 1px solid var(--line);
      font-size: 13px;
    }
    .line:last-child { border-bottom: 0; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
    .wide { grid-column: 1 / -1; }
    @media (max-width: 940px) {
      main { grid-template-columns: 1fr; padding: 10px; }
      .grid2, .grid3, .facts, .scenario, .warehouse-strip { grid-template-columns: 1fr; }
      .scan-input { font-size: 22px; }
      header { align-items: flex-start; flex-direction: column; }
      .top-nav { width: 100%; overflow-x: auto; padding-bottom: 3px; }
    }
  </style>
</head>
<body>
  <header>
    <h1>Складской пилот</h1>
    <nav class="top-nav">
      <a href="/scan">Склад</a>
      <a href="/terminal">ТСД</a>
      <a href="/map">Карта</a>
      <a href="/shipments">Отгрузки</a>
      <a href="/inventory">Инвентаризация</a>
      <details class="nav-more">
        <summary>Ещё</summary>
        <div class="nav-more-menu">
          <a href="/catalog">Справочники</a>
          <a href="/cards">Карточки</a>
          <a href="/docs">Документация API</a>
        </div>
      </details>
    </nav>
  </header>

  <main>
    <section class="stack">
      <div class="warehouse-strip">
        <div>
          <label for="warehouseSelect">Текущий склад</label>
          <select id="warehouseSelect"></select>
        </div>
        <a id="warehouseMapLink" class="map-link" href="/map">Карта склада</a>
      </div>
      <div class="scenario">
        <button id="scenarioBuild" class="active">Формирование палеты</button>
        <button id="scenarioPlace">Размещение палеты</button>
      </div>

      <div class="grid2">
        <div>
          <label for="actor">Оператор</label>
          <input id="actor" value="scanner-demo" autocomplete="off">
        </div>
        <div>
          <label for="scanInput">Сканер</label>
          <input id="scanInput" class="scan-input" autofocus autocomplete="off" placeholder="Код коробки / палеты / ячейка">
        </div>
      </div>

      <div id="status" class="status">Готово. Выберите палету или создайте новую.</div>

      <div class="active-card">
        <div>
          <h2>Активная палета</h2>
          <div id="activeUid" class="uid">Не выбрана</div>
          <div class="facts">
            <div class="fact"><b>Статус</b><span id="activeStatus">-</span></div>
            <div class="fact"><b>Коробок</b><span id="activeBoxCount">0</span></div>
            <div class="fact"><b>Ячейка</b><span id="activeLocation">-</span></div>
            <div class="fact"><b>Партия</b><span id="activeBatch">-</span></div>
          </div>
        </div>
        <div class="stack">
          <button id="activePalletLabelBtn" class="secondary">PDF палеты</button>
          <button id="activePalletCardBtn" class="secondary">Карточка</button>
          <button id="clearActiveBtn" class="ghost">Сбросить</button>
        </div>
      </div>

      <div class="grid3">
        <button id="newPalletBtn">Новая палета</button>
        <button id="closePalletBtn" class="danger">Закрыть</button>
        <button id="refreshBtn" class="secondary">Обновить</button>
      </div>
      <div class="grid3">
        <button id="reopenPalletBtn" class="secondary">Переоткрыть</button>
        <button id="quarantinePalletBtn" class="secondary">Карантин</button>
        <button id="blockPalletBtn" class="danger">Блок</button>
      </div>
      <button id="releasePalletBtn" class="ghost">Вернуть из блока/карантина</button>

      <div class="box-list" id="activeBoxes">
        <div class="line">Коробок пока нет</div>
      </div>
      <div class="log" id="activeHistory">
        <div class="line">История палеты появится после выбора</div>
      </div>
    </section>

    <aside class="stack">
      <h2>Палеты в работе</h2>
      <div class="row">
        <select id="palletStatusFilter">
          <option value="work">В работе</option>
          <option value="open">Открыта</option>
          <option value="waiting_placement">Ожидает размещения</option>
          <option value="available">Доступна</option>
          <option value="all">Все</option>
        </select>
        <button id="refreshPalletsBtn" class="secondary">Обновить</button>
      </div>
      <div id="palletList" class="pallet-list"></div>
    </aside>

    <section class="stack">
      <h2>Демо-коробки</h2>
      <div class="grid2">
        <div>
          <label for="batchSelect">Партия</label>
          <select id="batchSelect"></select>
        </div>
        <div>
          <label for="boxQty">Количество</label>
          <input id="boxQty" type="number" min="1" max="200" value="5">
        </div>
      </div>
      <button id="generateBtn" class="secondary">Сгенерировать коробки</button>
      <button id="batchBoxLabelsBtn" class="secondary">PDF коробок партии</button>
      <div id="generatedBoxes" class="log"></div>
    </section>

    <section class="stack">
      <h2>Ячейки</h2>
      <div class="row">
        <select id="locationSelect"></select>
        <button id="useLocationBtn" class="secondary">В поле сканера</button>
      </div>
      <button id="locationLabelsBtn" class="secondary">PDF ячеек</button>
      <div class="log" id="locationList"></div>
    </section>

    <section class="wide stack">
      <h2>Поиск коробки</h2>
      <div class="row">
        <input id="boxSearchInput" class="mono" placeholder="Код коробки">
        <button id="boxSearchBtn" class="secondary">Найти</button>
      </div>
      <div id="boxSearchResult" class="log">
        <div class="line">Введите или отсканируйте номер коробки</div>
      </div>
    </section>

    <section class="wide stack">
      <h2>Последние операции</h2>
      <div class="log" id="events"></div>
    </section>
  </main>

  <script>
    const state = {
      scenario: "build",
      activePalletUid: "",
      selectedWarehouseCode: "",
      defaultWarehouseCode: "WH01",
      warehouses: [],
      allLocations: [],
      warehouseLocations: [],
      locations: [],
      batches: [],
    };
    const $ = (id) => document.getElementById(id);
    const codePrefixes = { box: "", pallet: "" };
    const statusLabels = {
      label_created: "Этикетка создана",
      accepted_from_production: "Принята от производства",
      in_open_pallet: "В открытой палете",
      in_closed_pallet: "В закрытой палете",
      open: "Открыта",
      waiting_placement: "Ожидает размещения",
      available: "Доступна",
      reserved: "В резерве",
      expedition: "В экспедиции",
      loaded: "Погружена",
      shipped: "Отгружена",
      blocked: "Заблокирована",
      quarantine: "Карантин",
    };
    const locationKindLabels = {
      storage: "Хранение",
      receiving: "Приемка",
      quarantine: "Карантин",
      discrepancy: "Расхождения",
      expedition: "Экспедиция",
      transfer_out: "Перемещение исходящее",
      transfer_in: "Перемещение входящее",
      scrap: "Списание",
    };
    const operationLabels = {
      box_accepted: "Коробка принята",
      box_added_to_pallet: "Коробка добавлена в палету",
      boxes_generated: "Коробки сгенерированы",
      pallet_opened: "Палета открыта",
      pallet_closed: "Палета закрыта",
      pallet_reopened: "Палета переоткрыта",
      pallet_placed: "Палета размещена",
      pallet_moved: "Палета перемещена",
      pallet_released: "Палета возвращена в работу",
      pallet_blocked: "Палета заблокирована",
      pallet_quarantine: "Палета отправлена в карантин",
      pallet_reserved_for_transfer: "Палета зарезервирована для перемещения",
      pallet_moved_to_transfer_expedition: "Палета передана в зону отправки",
      pallet_loaded_for_transfer: "Палета погружена для перемещения",
      pallet_dispatched_between_warehouses: "Палета отправлена на другой склад",
      pallet_received_between_warehouses: "Палета принята другим складом",
    };
    function label(map, value) { return map[value] || value || "-"; }

    function actor() {
      return $("actor").value.trim() || "scanner-demo";
    }

    function focusScan() {
      setTimeout(() => $("scanInput").focus(), 30);
    }

    function setStatus(message, kind = "") {
      const el = $("status");
      el.className = `status ${kind}`;
      el.textContent = message;
    }

    async function api(path, options = {}) {
      const response = await fetch(path, {
        headers: { "Content-Type": "application/json" },
        ...options,
      });
      const text = await response.text();
      const data = text ? JSON.parse(text) : null;
      if (!response.ok) {
        throw new Error(data?.detail || response.statusText);
      }
      return data;
    }

    function post(path, body = {}) {
      return api(path, { method: "POST", body: JSON.stringify(body) });
    }

    async function loadCodePrefixes() {
      const constants = await api("/api/meta/constants");
      codePrefixes.box = `${constants.box_code_prefix}-`;
      codePrefixes.pallet = `${constants.pallet_code_prefix}-`;
      state.defaultWarehouseCode = constants.default_warehouse_code || "WH01";
    }

    function locationCodeById(id) {
      const location = state.allLocations.find((item) => item.id === id);
      return location ? location.code : "-";
    }

    function batchLabel(id) {
      const batch = state.batches.find((item) => item.id === id);
      return batch ? batch.batch_number : "-";
    }

    function setScenario(scenario) {
      state.scenario = scenario;
      $("scenarioBuild").classList.toggle("active", scenario === "build");
      $("scenarioPlace").classList.toggle("active", scenario === "place");
      setStatus(
        scenario === "build"
          ? "Режим формирования: сканируйте коды коробок."
          : "Режим размещения: выберите закрытую палету и сканируйте ячейку.",
        "warn"
      );
      focusScan();
    }

    async function selectPallet(uid, message = "Палета выбрана") {
      state.activePalletUid = uid;
      await refreshActivePallet();
      await refreshPallets();
      setStatus(`${message}: ${uid}`, "ok");
      focusScan();
    }

    async function refreshActivePallet() {
      if (!state.activePalletUid) {
        $("activeUid").textContent = "Не выбрана";
        $("activeStatus").textContent = "-";
        $("activeBoxCount").textContent = "0";
        $("activeLocation").textContent = "-";
        $("activeBatch").textContent = "-";
        $("activeBoxes").innerHTML = `<div class="line">Коробок пока нет</div>`;
        $("activeHistory").innerHTML = `<div class="line">История палеты появится после выбора</div>`;
        return;
      }
      const [pallet, boxes, history] = await Promise.all([
        api(`/api/pallets/${encodeURIComponent(state.activePalletUid)}`),
        api(`/api/pallets/${encodeURIComponent(state.activePalletUid)}/boxes`),
        api(`/api/pallets/${encodeURIComponent(state.activePalletUid)}/events?limit=20`),
      ]);
      $("activeUid").textContent = pallet.pallet_uid;
      $("activeStatus").textContent = label(statusLabels, pallet.status);
      $("activeBoxCount").textContent = boxes.length;
      $("activeLocation").textContent = pallet.current_location_id ? locationCodeById(pallet.current_location_id) : "-";
      $("activeBatch").textContent = batchLabel(pallet.batch_id);
      $("activeBoxes").innerHTML = boxes.map((box) => `
        <div class="line">
          <a class="mono" href="/cards?kind=box&code=${encodeURIComponent(box.box_uid)}">${box.box_uid}</a>
          <span class="meta">${label(statusLabels, box.status)}</span>
        </div>
      `).join("") || `<div class="line">Коробок пока нет</div>`;
      $("activeHistory").innerHTML = history.map((event) => `
        <div class="line">
          <strong>${label(operationLabels, event.operation)}</strong>
          <span class="meta">${event.actor} | ${new Date(event.created_at).toLocaleString()}</span>
          ${event.reason ? `<div class="meta">Причина: ${event.reason}</div>` : ""}
        </div>
      `).join("") || `<div class="line">Истории пока нет</div>`;
    }

    function statusQuery() {
      const value = $("palletStatusFilter").value;
      if (value === "all") return "";
      if (value === "work") return "?status=open&status=waiting_placement";
      return `?status=${encodeURIComponent(value)}`;
    }

    async function refreshPallets() {
      const rows = await api(`/api/pallets${statusQuery()}`);
      const locationIds = new Set(state.warehouseLocations.map((location) => location.id));
      const pallets = rows.filter((pallet) =>
        pallet.current_location_id
          ? locationIds.has(pallet.current_location_id)
          : ["open", "closed", "waiting_placement"].includes(pallet.status)
      );
      $("palletList").innerHTML = pallets.map((pallet) => {
        const active = pallet.pallet_uid === state.activePalletUid ? " active" : "";
        const location = pallet.current_location_code || "-";
        const batch = batchLabel(pallet.batch_id);
        return `
          <div class="pallet-item${active}">
            <div class="pallet-main">
              <a class="mono" href="/cards?kind=pallet&code=${encodeURIComponent(pallet.pallet_uid)}">${pallet.pallet_uid}</a>
              <div class="meta">${pallet.box_count} коробок | ${batch} | ${location}</div>
            </div>
            <div class="stack">
              <span class="badge ${pallet.status}">${label(statusLabels, pallet.status)}</span>
              <button class="secondary" data-select-pallet="${pallet.pallet_uid}">Выбрать</button>
            </div>
          </div>
        `;
      }).join("") || `<div class="line">Палет по фильтру нет</div>`;
      document.querySelectorAll("[data-select-pallet]").forEach((button) => {
        button.addEventListener("click", () => {
          selectPallet(button.dataset.selectPallet).catch((err) => setStatus(err.message, "err"));
        });
      });
    }

    async function refreshEvents() {
      const events = await api("/api/events?limit=20");
      $("events").innerHTML = events.map((event) => `
        <div class="line">
          <strong>${label(operationLabels, event.operation)}</strong>
          <span class="mono">${event.object_uid}</span>
          <span class="meta">${event.actor} | ${new Date(event.created_at).toLocaleString()}</span>
        </div>
      `).join("") || `<div class="line">Операций пока нет</div>`;
    }

    async function loadDictionaries() {
      const [batches, locations, warehouses] = await Promise.all([
        api("/api/batches"), api("/api/locations"), api("/api/warehouses"),
      ]);
      state.batches = batches;
      state.allLocations = locations;
      state.warehouses = warehouses;
      $("batchSelect").innerHTML = batches.map((batch) =>
        `<option value="${batch.id}">${batch.batch_number} / товар ${batch.product_id}</option>`
      ).join("");
      $("warehouseSelect").innerHTML = warehouses.map((warehouse) =>
        `<option value="${warehouse.code}">${warehouse.code} - ${warehouse.name}</option>`
      ).join("");
      const requestedWarehouse = new URLSearchParams(window.location.search).get("warehouse");
      const initialWarehouse = warehouses.some((warehouse) => warehouse.code === requestedWarehouse)
        ? requestedWarehouse
        : warehouses.some((warehouse) => warehouse.code === state.defaultWarehouseCode)
          ? state.defaultWarehouseCode
          : warehouses[0]?.code || "";
      $("warehouseSelect").value = initialWarehouse;
      applyWarehouse(initialWarehouse);
    }

    function applyWarehouse(warehouseCode) {
      state.selectedWarehouseCode = warehouseCode;
      state.warehouseLocations = state.allLocations.filter((location) => {
        const warehouse = state.warehouses.find((item) => item.code === warehouseCode);
        return warehouse && location.warehouse_id === warehouse.id;
      });
      state.locations = state.warehouseLocations.filter((location) => location.kind === "storage");
      $("locationSelect").innerHTML = state.locations.map((location) =>
        `<option value="${location.code}">${location.code}</option>`
      ).join("");
      $("locationList").innerHTML = state.locations.map((location) => `
        <div class="line"><a class="mono" href="/cards?kind=location&code=${encodeURIComponent(location.code)}">${location.code}</a><span class="meta">${label(locationKindLabels, location.kind)}</span></div>
      `).join("") || `<div class="line">На складе пока нет ячеек</div>`;
      $("warehouseMapLink").href = `/map?warehouse=${encodeURIComponent(warehouseCode)}`;
      history.replaceState(null, "", `/scan?warehouse=${encodeURIComponent(warehouseCode)}`);
    }

    async function switchWarehouse(warehouseCode) {
      applyWarehouse(warehouseCode);
      if (state.activePalletUid) {
        const pallet = await api(`/api/pallets/${encodeURIComponent(state.activePalletUid)}`);
        const belongsHere = !pallet.current_location_id || state.warehouseLocations.some((location) => location.id === pallet.current_location_id);
        if (!belongsHere) state.activePalletUid = "";
      }
      await refreshActivePallet();
      await refreshPallets();
      const warehouse = state.warehouses.find((item) => item.code === warehouseCode);
      setStatus(`Выбран склад: ${warehouse?.name || warehouseCode}`, "ok");
      focusScan();
    }

    async function createPallet() {
      const pallet = await post("/api/pallets", { actor: actor() });
      state.activePalletUid = pallet.pallet_uid;
      setScenario("build");
      await refreshActivePallet();
      await refreshPallets();
      await refreshEvents();
      setStatus(`Открыта новая палета: ${pallet.pallet_uid}`, "ok");
      focusScan();
    }

    async function scanBox(code) {
      if (!state.activePalletUid) {
        await createPallet();
      }
      if (state.scenario !== "build") {
        setScenario("build");
      }
      try {
        await post(`/api/boxes/${encodeURIComponent(code)}/accept`, { actor: actor() });
      } catch (err) {
        if (!String(err.message).includes("cannot be accepted")) throw err;
      }
      await post(
        `/api/pallets/${encodeURIComponent(state.activePalletUid)}/boxes/${encodeURIComponent(code)}`,
        { actor: actor() }
      );
      await refreshActivePallet();
      await refreshPallets();
      await refreshEvents();
      setStatus(`Коробка добавлена: ${code}`, "ok");
    }

    function askReason(defaultReason) {
      const reason = window.prompt("Причина операции", defaultReason);
      if (!reason || !reason.trim()) {
        throw new Error("Нужна причина операции");
      }
      return reason.trim();
    }

    async function palletStatusAction(endpoint, defaultReason, doneMessage) {
      if (!state.activePalletUid) throw new Error("Сначала выберите палету");
      const reason = askReason(defaultReason);
      await post(`/api/pallets/${encodeURIComponent(state.activePalletUid)}/${endpoint}`, {
        actor: actor(),
        reason,
      });
      await refreshActivePallet();
      await refreshPallets();
      await refreshEvents();
      setStatus(doneMessage, "ok");
      focusScan();
    }

    async function searchBox() {
      const code = $("boxSearchInput").value.trim();
      if (!code) return setStatus("Введите номер коробки", "err");
      const trace = await api(`/api/boxes/${encodeURIComponent(code)}/trace`);
      const pallet = trace.pallet;
      $("boxSearchResult").innerHTML = `
        <div class="line"><a class="mono" href="/cards?kind=box&code=${encodeURIComponent(trace.box.box_uid)}">${trace.box.box_uid}</a><span class="meta">${label(statusLabels, trace.box.status)}</span></div>
        <div class="line">Палета: ${pallet ? `<a class="mono" href="/cards?kind=pallet&code=${encodeURIComponent(pallet.pallet_uid)}">${pallet.pallet_uid}</a>` : "-"}</div>
        <div class="line">Статус палеты: <strong>${pallet ? label(statusLabels, pallet.status) : "-"}</strong></div>
        <div class="line">Ячейка: ${trace.location_code ? `<a class="mono" href="/cards?kind=location&code=${encodeURIComponent(trace.location_code)}">${trace.location_code}</a>` : "-"}</div>
        <div class="line">Партия: <strong>${batchLabel(trace.box.batch_id)}</strong></div>
      `;
      if (pallet) {
        state.activePalletUid = pallet.pallet_uid;
        await refreshActivePallet();
        await refreshPallets();
      }
      setStatus(`Коробка найдена: ${code}`, "ok");
      focusScan();
    }

    async function scanPallet(code) {
      await selectPallet(code);
    }

    async function scanLocation(code) {
      if (!state.activePalletUid) throw new Error("Сначала выберите палету из списка");
      if (!state.locations.some((location) => location.code === code)) {
        throw new Error(`Ячейка ${code} не относится к выбранному складу ${state.selectedWarehouseCode}`);
      }
      if (state.scenario !== "place") {
        setScenario("place");
      }
      const pallet = await api(`/api/pallets/${encodeURIComponent(state.activePalletUid)}`);
      const endpoint = pallet.status === "available" ? "move" : "place";
      await post(`/api/pallets/${encodeURIComponent(state.activePalletUid)}/${endpoint}`, {
        actor: actor(),
        reason: "scanner ui",
        location_code: code,
      });
      await refreshActivePallet();
      await refreshPallets();
      await refreshEvents();
      setStatus(`Палета поставлена в ячейку: ${code}`, "ok");
    }

    async function handleScan(value) {
      const code = value.trim();
      if (!code) return;
      if (code.startsWith(codePrefixes.box)) {
        await scanBox(code);
      } else if (code.startsWith(codePrefixes.pallet)) {
        await scanPallet(code);
      } else {
        await scanLocation(code);
      }
    }

    $("scanInput").addEventListener("keydown", async (event) => {
      if (event.key !== "Enter") return;
      event.preventDefault();
      const value = event.currentTarget.value;
      event.currentTarget.value = "";
      try {
        await handleScan(value);
      } catch (err) {
        setStatus(err.message, "err");
      } finally {
        focusScan();
      }
    });

    $("scenarioBuild").addEventListener("click", () => setScenario("build"));
    $("scenarioPlace").addEventListener("click", () => setScenario("place"));
    $("newPalletBtn").addEventListener("click", () => createPallet().catch((err) => setStatus(err.message, "err")));
    $("closePalletBtn").addEventListener("click", async () => {
      if (!state.activePalletUid) return setStatus("Сначала выберите палету", "err");
      try {
        await post(`/api/pallets/${encodeURIComponent(state.activePalletUid)}/close`, {
          actor: actor(),
          reason: "scanner ui",
        });
        setScenario("place");
        await refreshActivePallet();
        await refreshPallets();
        await refreshEvents();
        setStatus(`Палета закрыта. Теперь сканируйте ячейку.`, "ok");
      } catch (err) {
        setStatus(err.message, "err");
      } finally {
        focusScan();
      }
    });
    $("refreshBtn").addEventListener("click", async () => {
      await refreshActivePallet();
      await refreshPallets();
      await refreshEvents();
      focusScan();
    });
    $("reopenPalletBtn").addEventListener("click", () => {
      palletStatusAction("reopen", "дополнение палеты", "Палета переоткрыта для дополнения")
        .catch((err) => setStatus(err.message, "err"));
    });
    $("quarantinePalletBtn").addEventListener("click", () => {
      palletStatusAction("quarantine", "проверка качества", "Палета отправлена в карантин")
        .catch((err) => setStatus(err.message, "err"));
    });
    $("blockPalletBtn").addEventListener("click", () => {
      palletStatusAction("block", "служебная блокировка", "Палета заблокирована")
        .catch((err) => setStatus(err.message, "err"));
    });
    $("releasePalletBtn").addEventListener("click", () => {
      palletStatusAction("release", "решение ответственного", "Палета возвращена в работу")
        .catch((err) => setStatus(err.message, "err"));
    });
    $("refreshPalletsBtn").addEventListener("click", () => refreshPallets().then(focusScan));
    $("palletStatusFilter").addEventListener("change", () => refreshPallets().then(focusScan));
    $("warehouseSelect").addEventListener("change", (event) => {
      switchWarehouse(event.currentTarget.value).catch((err) => setStatus(err.message, "err"));
    });
    $("clearActiveBtn").addEventListener("click", async () => {
      state.activePalletUid = "";
      await refreshActivePallet();
      await refreshPallets();
      setStatus("Активная палета сброшена", "warn");
      focusScan();
    });
    $("activePalletLabelBtn").addEventListener("click", () => {
      if (!state.activePalletUid) return setStatus("Сначала выберите палету", "err");
      window.open(`/api/pallets/${encodeURIComponent(state.activePalletUid)}/label.pdf`, "_blank");
      focusScan();
    });
    $("activePalletCardBtn").addEventListener("click", () => {
      if (!state.activePalletUid) return setStatus("Сначала выберите палету", "err");
      window.open(`/cards?kind=pallet&code=${encodeURIComponent(state.activePalletUid)}`, "_blank");
      focusScan();
    });
    $("generateBtn").addEventListener("click", async () => {
      try {
        const boxes = await post("/api/boxes/generate", {
          batch_id: Number($("batchSelect").value),
          quantity: Number($("boxQty").value),
          actor: actor(),
        });
        $("generatedBoxes").innerHTML = boxes.map((box) =>
          `<div class="line"><a class="mono" href="/cards?kind=box&code=${encodeURIComponent(box.box_uid)}">${box.box_uid}</a><span class="meta">${label(statusLabels, box.status)}</span></div>`
        ).join("");
        await refreshEvents();
        setStatus(`Сгенерировано коробок: ${boxes.length}`, "ok");
      } catch (err) {
        setStatus(err.message, "err");
      } finally {
        focusScan();
      }
    });
    $("useLocationBtn").addEventListener("click", () => {
      $("scanInput").value = $("locationSelect").value;
      focusScan();
    });
    $("batchBoxLabelsBtn").addEventListener("click", () => {
      const batchId = Number($("batchSelect").value);
      if (!batchId) return setStatus("Сначала выберите партию", "err");
      window.open(`/api/labels/boxes.pdf?batch_id=${batchId}`, "_blank");
      focusScan();
    });
    $("locationLabelsBtn").addEventListener("click", () => {
      window.open(`/api/labels/locations.pdf?warehouse_code=${encodeURIComponent(state.selectedWarehouseCode)}`, "_blank");
      focusScan();
    });
    $("boxSearchBtn").addEventListener("click", () => searchBox().catch((err) => setStatus(err.message, "err")));
    $("boxSearchInput").addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      event.preventDefault();
      searchBox().catch((err) => setStatus(err.message, "err"));
    });

    loadCodePrefixes()
      .then(loadDictionaries)
      .then(refreshPallets)
      .then(refreshEvents)
      .then(focusScan)
      .catch((err) => setStatus(err.message, "err"));
  </script>
</body>
</html>"""


@router.get("/catalog", response_class=HTMLResponse, include_in_schema=False)
@standard_page("catalog")
def catalog_page() -> str:
    return """<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Складской пилот: справочники</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f4f6f7;
      --panel: #fff;
      --line: #d7dde2;
      --text: #101828;
      --muted: #667085;
      --accent: #0f766e;
      --danger: #b42318;
      --ok: #067647;
      --warn: #a15c07;
      --dark: #111820;
    }
    * { box-sizing: border-box; }
    body { margin: 0; background: var(--bg); color: var(--text); font: 15px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    header { min-height: 54px; padding: 10px 18px; display: flex; align-items: center; justify-content: space-between; gap: 12px; color: #fff; background: var(--dark); }
    header h1 { margin: 0; font-size: 18px; letter-spacing: 0; }
    header a { color: #d8fbf6; text-decoration: none; font-weight: 700; }
    main { max-width: 1360px; margin: 0 auto; padding: 14px; display: grid; grid-template-columns: 360px minmax(0, 1fr); gap: 14px; }
    section, aside { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 14px; }
    h2 { margin: 0; font-size: 17px; letter-spacing: 0; }
    h3 { margin: 0; font-size: 14px; letter-spacing: 0; }
    .stack { display: grid; gap: 12px; }
    .row { display: flex; gap: 8px; align-items: center; }
    .row > * { flex: 1; }
    .grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .grid3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
    label { display: block; margin-bottom: 5px; color: var(--muted); font-size: 12px; font-weight: 800; text-transform: uppercase; }
    input, select, button { width: 100%; min-height: 40px; border: 1px solid var(--line); border-radius: 6px; padding: 8px 10px; background: #fff; color: var(--text); font: inherit; }
    button { cursor: pointer; border-color: var(--accent); background: var(--accent); color: #fff; font-weight: 800; }
    button.secondary { background: #f2fbf9; color: #0b5e58; }
    .status { min-height: 46px; padding: 10px 12px; border: 1px solid #c7dcf3; border-radius: 6px; background: #eff8ff; font-weight: 800; }
    .status.ok { color: var(--ok); border-color: #abefc6; background: #ecfdf3; }
    .status.err { color: var(--danger); border-color: #fecdca; background: #fff1f0; }
    .cards { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
    .form-card { display: grid; gap: 10px; padding: 12px; border: 1px solid var(--line); border-radius: 8px; background: #fbfcfd; }
    .facts { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
    .fact { padding: 8px; border: 1px solid var(--line); border-radius: 6px; background: #fff; }
    .fact b { display: block; color: var(--muted); font-size: 11px; text-transform: uppercase; }
    .fact span { display: block; margin-top: 2px; font-weight: 800; overflow-wrap: anywhere; }
    .list { display: grid; gap: 8px; max-height: 360px; overflow: auto; }
    .item { display: grid; gap: 5px; padding: 10px; border: 1px solid var(--line); border-radius: 8px; background: #fff; }
    .item-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
    .meta { color: var(--muted); font-size: 13px; }
    .badge { display: inline-flex; align-items: center; min-height: 24px; padding: 2px 7px; border-radius: 999px; background: #eef2f6; color: #344054; font-size: 12px; font-weight: 800; white-space: nowrap; }
    .wide { grid-column: 1 / -1; }
    @media (max-width: 1050px) {
      main { grid-template-columns: 1fr; padding: 10px; }
      .grid2, .grid3, .cards, .facts { grid-template-columns: 1fr; }
      header { align-items: flex-start; flex-direction: column; }
    }
  </style>
</head>
<body>
  <header>
    <h1>Складской пилот: справочники</h1>
    <div class="row" style="max-width: 640px;">
      <a href="/scan">Склад</a>
      <a href="/terminal">ТСД</a>
      <a href="/map">Карта</a>
      <a href="/shipments">Отгрузки</a>
      <a href="/inventory">Инвентаризация</a>
      <a href="/catalog">Справочники</a>
      <a href="/cards">Карточки</a>
      <a href="/docs">Документация API</a>
    </div>
  </header>

  <main>
    <aside class="stack">
      <h2>Демо-генератор</h2>
      <div id="status" class="status">Готово к заполнению справочников</div>
      <div>
        <label for="actor">Оператор</label>
        <input id="actor" value="catalog-demo" autocomplete="off">
      </div>
      <div class="grid2">
        <div>
          <label for="demoWarehouseCode">Склад</label>
          <input id="demoWarehouseCode" class="mono" placeholder="Код склада">
        </div>
        <div>
          <label for="demoLocationQty">Ячеек</label>
          <input id="demoLocationQty" type="number" min="1" max="80" value="10">
        </div>
      </div>
      <button id="demoCatalogBtn">Создать демо-справочники</button>
      <div class="grid2">
        <div>
          <label for="demoBatchSelect">Партия</label>
          <select id="demoBatchSelect"></select>
        </div>
        <div>
          <label for="demoPalletQty">Палет</label>
          <input id="demoPalletQty" type="number" min="1" max="50" value="5">
        </div>
      </div>
      <div class="grid2">
        <div>
          <label for="demoBoxesPerPallet">Коробок/пал.</label>
          <input id="demoBoxesPerPallet" type="number" min="1" max="40" value="4">
        </div>
        <label style="display:flex;align-items:center;gap:8px;margin:22px 0 0;text-transform:none;font-size:14px;color:var(--text);">
          <input id="demoPlace" type="checkbox" checked style="width:auto;min-height:auto;">
          Разместить в свободные
        </label>
      </div>
      <button id="demoPalletsBtn" class="secondary">Создать демо-палеты</button>
      <h2>Печать этикеток</h2>
      <div>
        <label for="labelCodes">Только выбранные коды</label>
        <textarea id="labelCodes" class="mono" placeholder="По одному или через запятую"></textarea>
      </div>
      <div class="grid2">
        <div>
          <label for="labelLimit">Лимит</label>
          <input id="labelLimit" type="number" min="1" max="400" value="40">
        </div>
        <div>
          <label for="labelPalletStatus">Статус палет</label>
          <select id="labelPalletStatus">
            <option value="available,waiting_placement">Доступна + ожид. размещения</option>
            <option value="available">Доступна</option>
            <option value="waiting_placement">Ожидает размещения</option>
            <option value="">Любой</option>
          </select>
        </div>
      </div>
      <div class="grid2">
        <button id="printLocationLabelsBtn" class="secondary">PDF ячеек</button>
        <button id="printPalletLabelsBtn" class="secondary">PDF палет</button>
      </div>
      <button id="printBoxLabelsBtn" class="secondary">PDF коробок</button>
      <h2>Импорт</h2>
      <div>
        <label for="importKind">Что загружаем</label>
        <select id="importKind">
          <option value="products">Товары</option>
          <option value="batches">Партии</option>
          <option value="locations">Ячейки</option>
        </select>
      </div>
      <input id="importFile" type="file" accept=".csv,.tsv,.xlsx,.xlsm">
      <div class="grid2">
        <button id="previewImportBtn" class="secondary">Предпросмотр</button>
        <button id="applyImportBtn">Применить</button>
      </div>
      <div id="importPreview" class="list">
        <div class="item">Файл импорта не выбран</div>
      </div>
      <div class="facts">
        <div class="fact"><b>Товары</b><span id="countProducts">0</span></div>
        <div class="fact"><b>Партии</b><span id="countBatches">0</span></div>
        <div class="fact"><b>Ячейки</b><span id="countLocations">0</span></div>
        <div class="fact"><b>Палеты</b><span id="countPallets">0</span></div>
      </div>
    </aside>

    <section class="stack">
      <h2>Создание справочников</h2>
      <div class="cards">
        <div class="form-card">
          <h3>Товар</h3>
          <div class="grid2">
            <input id="productCode" placeholder="Код">
            <input id="productName" placeholder="Наименование">
          </div>
          <div class="grid3">
          <input id="productUnit" value="шт" placeholder="Ед.">
            <input id="quantityPerBox" type="number" min="1" value="24" placeholder="В коробке">
            <input id="boxesPerPallet" type="number" min="1" value="96" placeholder="Кор./пал.">
          </div>
          <button id="createProductBtn">Создать товар</button>
        </div>

        <div class="form-card">
          <h3>Партия</h3>
          <select id="batchProductSelect"></select>
          <input id="batchNumber" placeholder="Номер партии">
          <div class="grid2">
            <input id="productionDate" type="date">
            <input id="expiryDate" type="date">
          </div>
          <button id="createBatchBtn">Создать партию</button>
        </div>

        <div class="form-card">
          <h3>Склад и зона</h3>
          <div class="grid2">
            <input id="warehouseCode" placeholder="Код склада">
            <input id="warehouseName" placeholder="Название склада">
          </div>
          <button id="createWarehouseBtn">Создать склад</button>
          <select id="zoneWarehouseSelect"></select>
          <div class="grid3">
            <input id="zoneCode" placeholder="Код зоны">
            <input id="zoneName" placeholder="Название зоны">
            <select id="zoneKind"></select>
          </div>
          <button id="createZoneBtn" class="secondary">Создать зону</button>
        </div>

        <div class="form-card">
          <h3>Ячейка</h3>
          <div class="grid2">
            <select id="locationWarehouseSelect"></select>
            <select id="locationZoneSelect"></select>
          </div>
          <input id="locationCode" placeholder="Код ячейки">
          <div class="grid2">
            <select id="locationKind"></select>
            <input id="locationCapacity" type="number" min="1" value="1" placeholder="Вместимость">
          </div>
          <button id="createLocationBtn">Создать ячейку</button>
        </div>
      </div>
    </section>

    <section class="wide stack">
      <h2>Списки</h2>
      <div class="cards">
        <div class="form-card">
          <h3>Товары</h3>
          <div id="productsList" class="list"></div>
        </div>
        <div class="form-card">
          <h3>Партии</h3>
          <div id="batchesList" class="list"></div>
        </div>
        <div class="form-card">
          <h3>Склады и зоны</h3>
          <div id="warehousesList" class="list"></div>
          <div id="zonesList" class="list"></div>
        </div>
        <div class="form-card">
          <h3>Ячейки</h3>
          <div id="locationsList" class="list"></div>
        </div>
      </div>
    </section>
  </main>

  <script>
    const state = { products: [], batches: [], warehouses: [], zones: [], locations: [], pallets: [], constants: {} };
    const kinds = ["storage", "receiving", "quarantine", "discrepancy", "expedition", "transfer_out", "transfer_in", "scrap"];
    const $ = (id) => document.getElementById(id);
    const locationKindLabels = {
      storage: "Хранение",
      receiving: "Приемка",
      quarantine: "Карантин",
      discrepancy: "Расхождения",
      expedition: "Экспедиция",
      transfer_out: "Перемещение исходящее",
      transfer_in: "Перемещение входящее",
      scrap: "Списание",
    };
    const qualityLabels = {
      released: "Разрешена",
      blocked: "Заблокирована",
      quarantine: "Карантин",
    };
    function label(map, value) { return map[value] || value || "-"; }
    function actor() { return $("actor").value.trim() || "catalog-demo"; }
    function setStatus(message, kind = "") {
      const el = $("status");
      el.className = `status ${kind}`;
      el.textContent = message;
    }
    async function api(path, options = {}) {
      const response = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
      const text = await response.text();
      const data = text ? JSON.parse(text) : null;
      if (!response.ok) throw new Error(data?.detail || response.statusText);
      return data;
    }
    function post(path, body = {}) {
      return api(path, { method: "POST", body: JSON.stringify(body) });
    }
    async function upload(path, file) {
      const form = new FormData();
      form.append("file", file);
      const response = await fetch(path, { method: "POST", body: form });
      const text = await response.text();
      const data = text ? JSON.parse(text) : null;
      if (!response.ok) throw new Error(data?.detail?.message || data?.detail || response.statusText);
      return data;
    }
    function selectedLabelCodes() {
      return $("labelCodes").value
        .split(/[,\\s]+/)
        .map((code) => code.trim())
        .filter(Boolean);
    }
    function labelLimitParam() {
      const limit = Math.max(1, Math.min(400, Number($("labelLimit").value) || 40));
      return String(limit);
    }
    function appendRepeated(params, name, values) {
      values.forEach((value) => params.append(name, value));
    }
    async function loadConstants() {
      state.constants = await api("/api/meta/constants");
      $("demoWarehouseCode").value = state.constants.default_warehouse_code || "";
    }
    function optionList(items, labelFn) {
      return items.map((item) => `<option value="${item.id}">${labelFn(item)}</option>`).join("");
    }
    function productName(id) {
      return state.products.find((product) => product.id === id)?.code || `товар ${id}`;
    }
    function warehouseCode(id) {
      return state.warehouses.find((warehouse) => warehouse.id === id)?.code || `склад ${id}`;
    }
    function renderSelects() {
      $("batchProductSelect").innerHTML = optionList(state.products, (p) => `${p.code} - ${p.name}`);
      $("demoBatchSelect").innerHTML = `<option value="">Автовыбор</option>` + optionList(state.batches, (b) => `${b.batch_number} | ${productName(b.product_id)}`);
      $("zoneWarehouseSelect").innerHTML = optionList(state.warehouses, (w) => `${w.code} - ${w.name}`);
      $("locationWarehouseSelect").innerHTML = optionList(state.warehouses, (w) => `${w.code} - ${w.name}`);
      $("locationZoneSelect").innerHTML = optionList(state.zones, (z) => `${warehouseCode(z.warehouse_id)} / ${z.code} - ${z.name}`);
      $("zoneKind").innerHTML = kinds.map((kind) => `<option value="${kind}">${label(locationKindLabels, kind)}</option>`).join("");
      $("locationKind").innerHTML = kinds.map((kind) => `<option value="${kind}">${label(locationKindLabels, kind)}</option>`).join("");
    }
    function renderLists() {
      $("countProducts").textContent = state.products.length;
      $("countBatches").textContent = state.batches.length;
      $("countLocations").textContent = state.locations.length;
      $("countPallets").textContent = state.pallets.length;
      $("productsList").innerHTML = state.products.map((product) => `
        <div class="item">
          <div class="item-head"><strong class="mono">${product.code}</strong><span class="badge">${product.boxes_per_pallet} кор./пал.</span></div>
          <div>${product.name}</div>
          <div class="meta">${product.quantity_per_box} шт. в коробке | срок ${product.shelf_life_days || "-"} дн.</div>
        </div>
      `).join("") || `<div class="item">Товаров пока нет</div>`;
      $("batchesList").innerHTML = state.batches.map((batch) => `
        <div class="item">
          <div class="item-head"><strong class="mono">${batch.batch_number}</strong><span class="badge">${label(qualityLabels, batch.quality_status)}</span></div>
          <div class="meta">${productName(batch.product_id)} | ${batch.production_date} - ${batch.expiry_date}</div>
        </div>
      `).join("") || `<div class="item">Партий пока нет</div>`;
      $("warehousesList").innerHTML = state.warehouses.map((warehouse) => `
        <div class="item">
          <div class="item-head"><strong class="mono">${warehouse.code}</strong><span class="badge">${warehouse.timezone}</span></div>
          <div>${warehouse.name}</div>
          <div class="meta">${warehouse.city || "-"}</div>
        </div>
      `).join("") || `<div class="item">Складов пока нет</div>`;
      $("zonesList").innerHTML = state.zones.map((zone) => `
        <div class="item">
          <div class="item-head"><strong class="mono">${warehouseCode(zone.warehouse_id)} / ${zone.code}</strong><span class="badge">${label(locationKindLabels, zone.kind)}</span></div>
          <div>${zone.name}</div>
        </div>
      `).join("") || `<div class="item">Зон пока нет</div>`;
      $("locationsList").innerHTML = state.locations.map((location) => `
        <div class="item">
          <div class="item-head"><a class="mono" href="/cards?kind=location&code=${encodeURIComponent(location.code)}">${location.code}</a><span class="badge">${label(locationKindLabels, location.kind)}</span></div>
          <div class="meta">${warehouseCode(location.warehouse_id)} | вместимость ${location.capacity_pallets} пал.</div>
        </div>
      `).join("") || `<div class="item">Ячеек пока нет</div>`;
    }
    function renderImportPreview(result) {
      const errors = result.errors || [];
      const rows = result.rows || [];
      const errorHtml = errors.map((error) => `
        <div class="item">
          <div class="item-head"><strong>Строка ${error.row_number}</strong><span class="badge">ошибка</span></div>
          <div class="meta">${error.message}</div>
        </div>
      `).join("");
      const rowsHtml = rows.slice(0, 20).map((row) => `
        <div class="item">
          <div class="item-head"><strong>Строка ${row.row_number}</strong><span class="badge">готова</span></div>
          <div class="meta">${Object.entries(row.data).map(([key, value]) => `${key}: ${value}`).join(" | ")}</div>
        </div>
      `).join("");
      $("importPreview").innerHTML = `
        <div class="item">
          <strong>Всего строк: ${result.total_rows}; готово: ${result.valid_rows}; ошибок: ${errors.length}</strong>
          ${typeof result.created === "number" ? `<div class="meta">Создано: ${result.created}; пропущено: ${result.skipped}</div>` : ""}
        </div>
        ${errorHtml || rowsHtml || `<div class="item">Нет строк для показа</div>`}
      `;
    }
    async function refreshAll() {
      const [products, batches, warehouses, zones, locations, pallets] = await Promise.all([
        api("/api/products"),
        api("/api/batches"),
        api("/api/warehouses"),
        api("/api/zones"),
        api("/api/locations"),
        api("/api/pallets?limit=500"),
      ]);
      Object.assign(state, { products, batches, warehouses, zones, locations, pallets });
      renderSelects();
      renderLists();
    }
    function today(offsetDays = 0) {
      const date = new Date();
      date.setDate(date.getDate() + offsetDays);
      return date.toISOString().slice(0, 10);
    }
    async function createProduct() {
      await post("/api/products", {
        code: $("productCode").value.trim(),
        name: $("productName").value.trim(),
        unit: $("productUnit").value.trim() || "шт",
        quantity_per_box: Number($("quantityPerBox").value),
        boxes_per_pallet: Number($("boxesPerPallet").value),
        shelf_life_days: 365,
      });
      await refreshAll();
      setStatus("Товар создан", "ok");
    }
    async function createBatch() {
      await post("/api/batches", {
        product_id: Number($("batchProductSelect").value),
        batch_number: $("batchNumber").value.trim(),
        production_date: $("productionDate").value,
        expiry_date: $("expiryDate").value,
        quality_status: "released",
        operation_status: "allowed",
      });
      await refreshAll();
      setStatus("Партия создана", "ok");
    }
    async function createWarehouse() {
      await post("/api/warehouses", {
        code: $("warehouseCode").value.trim(),
        name: $("warehouseName").value.trim(),
        city: "Москва",
        timezone: "Europe/Moscow",
      });
      await refreshAll();
      setStatus("Склад создан", "ok");
    }
    async function createZone() {
      await post("/api/zones", {
        warehouse_id: Number($("zoneWarehouseSelect").value),
        code: $("zoneCode").value.trim(),
        name: $("zoneName").value.trim(),
        kind: $("zoneKind").value,
      });
      await refreshAll();
      setStatus("Зона создана", "ok");
    }
    async function createLocation() {
      await post("/api/locations", {
        warehouse_id: Number($("locationWarehouseSelect").value),
        zone_id: Number($("locationZoneSelect").value),
        code: $("locationCode").value.trim(),
        name: $("locationCode").value.trim(),
        kind: $("locationKind").value,
        capacity_pallets: Number($("locationCapacity").value),
      });
      await refreshAll();
      setStatus("Ячейка создана", "ok");
    }
    async function generateCatalog() {
      const result = await post("/api/demo/catalog", {
        warehouse_code: $("demoWarehouseCode").value.trim() || state.constants.default_warehouse_code,
        warehouse_name: "Основной склад 1",
        storage_locations: Number($("demoLocationQty").value),
        actor: actor(),
      });
      await refreshAll();
      setStatus(`Готово: товары +${result.created_products}, партии +${result.created_batches}, ячейки +${result.created_locations}`, "ok");
    }
    async function generatePallets() {
      const batchId = $("demoBatchSelect").value ? Number($("demoBatchSelect").value) : null;
      const result = await post("/api/demo/pallets", {
        batch_id: batchId,
        quantity: Number($("demoPalletQty").value),
        boxes_per_pallet: Number($("demoBoxesPerPallet").value),
        place_to_empty_locations: $("demoPlace").checked,
        actor: actor(),
      });
      await refreshAll();
      setStatus(`Создано палет: ${result.created_pallets}, размещено: ${result.placed_pallets}, ждут размещения: ${result.waiting_pallets}`, "ok");
    }
    function selectedImportFile() {
      const file = $("importFile").files[0];
      if (!file) throw new Error("Выберите CSV или XLSX файл");
      return file;
    }
    async function previewImport() {
      const result = await upload(`/api/import/preview/${$("importKind").value}`, selectedImportFile());
      renderImportPreview(result);
      setStatus(`Предпросмотр: строк ${result.total_rows}, ошибок ${result.errors.length}`, result.errors.length ? "err" : "ok");
    }
    async function applyImportFile() {
      const result = await upload(`/api/import/apply/${$("importKind").value}`, selectedImportFile());
      renderImportPreview(result);
      await refreshAll();
      setStatus(`Импорт применен: создано ${result.created}, пропущено ${result.skipped}`, "ok");
    }
    function showError(err) {
      setStatus(err.message, "err");
    }
    $("productionDate").value = today();
    $("expiryDate").value = today(365);
    $("createProductBtn").addEventListener("click", () => createProduct().catch(showError));
    $("createBatchBtn").addEventListener("click", () => createBatch().catch(showError));
    $("createWarehouseBtn").addEventListener("click", () => createWarehouse().catch(showError));
    $("createZoneBtn").addEventListener("click", () => createZone().catch(showError));
    $("createLocationBtn").addEventListener("click", () => createLocation().catch(showError));
    $("demoCatalogBtn").addEventListener("click", () => generateCatalog().catch(showError));
    $("demoPalletsBtn").addEventListener("click", () => generatePallets().catch(showError));
    $("printLocationLabelsBtn").addEventListener("click", () => {
      const code = $("demoWarehouseCode").value.trim() || state.constants.default_warehouse_code || "";
      const params = new URLSearchParams({ limit: labelLimitParam() });
      const selected = selectedLabelCodes();
      if (selected.length) {
        appendRepeated(params, "location_code", selected);
        params.set("storage_only", "false");
      } else if (code) {
        params.set("warehouse_code", code);
      }
      window.open(`/api/labels/locations.pdf?${params.toString()}`, "_blank");
    });
    $("printPalletLabelsBtn").addEventListener("click", () => {
      const params = new URLSearchParams({ limit: labelLimitParam() });
      const selected = selectedLabelCodes();
      if (selected.length) {
        appendRepeated(params, "pallet_uid", selected);
      } else {
        $("labelPalletStatus").value.split(",").filter(Boolean).forEach((status) => params.append("status", status));
      }
      const batchId = $("demoBatchSelect").value;
      if (batchId) params.set("batch_id", batchId);
      window.open(`/api/labels/pallets.pdf?${params.toString()}`, "_blank");
    });
    $("printBoxLabelsBtn").addEventListener("click", () => {
      const batchId = $("demoBatchSelect").value;
      const params = new URLSearchParams({ limit: labelLimitParam() });
      const selected = selectedLabelCodes();
      if (selected.length) appendRepeated(params, "box_uid", selected);
      if (batchId) params.set("batch_id", batchId);
      window.open(`/api/labels/boxes.pdf?${params.toString()}`, "_blank");
    });
    $("previewImportBtn").addEventListener("click", () => previewImport().catch(showError));
    $("applyImportBtn").addEventListener("click", () => applyImportFile().catch(showError));
    loadConstants().then(refreshAll).catch(showError);
  </script>
</body>
</html>"""


@router.get("/inventory", response_class=HTMLResponse, include_in_schema=False)
@standard_page("inventory")
def inventory_page() -> str:
    return """<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Складской пилот: инвентаризация</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f4f6f7;
      --panel: #fff;
      --line: #d7dde2;
      --text: #101828;
      --muted: #667085;
      --accent: #0f766e;
      --danger: #b42318;
      --ok: #067647;
      --warn: #a15c07;
      --dark: #111820;
    }
    * { box-sizing: border-box; }
    body { margin: 0; background: var(--bg); color: var(--text); font: 15px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    header { min-height: 54px; padding: 10px 18px; display: flex; align-items: center; justify-content: space-between; gap: 12px; color: #fff; background: var(--dark); }
    header h1 { margin: 0; font-size: 18px; letter-spacing: 0; }
    header a { color: #d8fbf6; text-decoration: none; font-weight: 700; }
    main { max-width: 1260px; margin: 0 auto; padding: 14px; display: grid; grid-template-columns: 360px minmax(0, 1fr); gap: 14px; }
    section, aside { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 14px; }
    h2 { margin: 0; font-size: 17px; letter-spacing: 0; }
    .stack { display: grid; gap: 12px; }
    .row { display: flex; gap: 8px; align-items: center; }
    .row > * { flex: 1; }
    .grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .grid4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
    label { display: block; margin-bottom: 5px; color: var(--muted); font-size: 12px; font-weight: 800; text-transform: uppercase; }
    input, button, select { width: 100%; min-height: 40px; border: 1px solid var(--line); border-radius: 6px; padding: 8px 10px; background: #fff; color: var(--text); font: inherit; }
    button { cursor: pointer; border-color: var(--accent); background: var(--accent); color: #fff; font-weight: 800; }
    button.secondary { background: #f2fbf9; color: #0b5e58; }
    button.danger { border-color: var(--danger); background: var(--danger); }
    .status { min-height: 46px; padding: 10px 12px; border: 1px solid #c7dcf3; border-radius: 6px; background: #eff8ff; font-weight: 800; }
    .status.ok { color: var(--ok); border-color: #abefc6; background: #ecfdf3; }
    .status.err { color: var(--danger); border-color: #fecdca; background: #fff1f0; }
    .status.warn { color: var(--warn); border-color: #fedf89; background: #fff8eb; }
    .scan-input { min-height: 66px; border: 2px solid var(--accent); font-size: 25px; font-weight: 900; letter-spacing: 0; }
    .list { display: grid; gap: 8px; max-height: 580px; overflow: auto; }
    .item { display: grid; gap: 6px; padding: 10px; border: 1px solid var(--line); border-radius: 8px; background: #fff; }
    .item.active { border-color: var(--accent); background: #ecfdf3; }
    .item-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
    .meta { color: var(--muted); font-size: 13px; }
    .badge { display: inline-flex; align-items: center; min-height: 24px; padding: 2px 7px; border-radius: 999px; background: #eef2f6; color: #344054; font-size: 12px; font-weight: 800; white-space: nowrap; }
    .badge.scanned { background: #ecfdf3; color: #067647; }
    .badge.expected { background: #eef2f6; color: #344054; }
    .badge.missing { background: #fff1f0; color: #b42318; }
    .badge.extra { background: #fff8eb; color: #a15c07; }
    .badge.wrong_location { background: #f4f3ff; color: #5925dc; }
    .fact { padding: 8px; border: 1px solid var(--line); border-radius: 6px; background: #fbfcfd; }
    .fact b { display: block; color: var(--muted); font-size: 11px; text-transform: uppercase; }
    .fact span { display: block; margin-top: 2px; font-weight: 800; overflow-wrap: anywhere; }
    .wide { grid-column: 1 / -1; }
    @media (max-width: 940px) {
      main { grid-template-columns: 1fr; padding: 10px; }
      .grid2, .grid4 { grid-template-columns: 1fr; }
      header { align-items: flex-start; flex-direction: column; }
    }
  </style>
</head>
<body>
  <header>
    <h1>Складской пилот: инвентаризация</h1>
    <div class="row" style="max-width: 520px;">
      <a href="/scan">Склад</a>
      <a href="/terminal">ТСД</a>
      <a href="/map">Карта</a>
      <a href="/shipments">Отгрузки</a>
      <a href="/inventory">Инвентаризация</a>
      <a href="/catalog">Справочники</a>
      <a href="/cards">Карточки</a>
      <a href="/docs">Документация API</a>
    </div>
  </header>

  <main>
    <aside class="stack">
      <h2>Новый обход склада</h2>
      <div>
        <label for="actor">Оператор</label>
        <input id="actor" value="inventory-demo" autocomplete="off">
      </div>
      <div>
        <label for="warehouseSelect">Склад</label>
        <select id="warehouseSelect"></select>
      </div>
      <button id="startBtn">Начать инвентаризацию склада</button>
      <button id="refreshInventoriesBtn" class="secondary">Обновить список</button>
      <h2>Ячейки</h2>
      <div>
        <select id="locationSelect"></select>
      </div>
      <button id="useLocationBtn" class="secondary">Выбрать ячейку</button>
      <h2>Сессии</h2>
      <div id="inventoryList" class="list"></div>
    </aside>

    <section class="stack">
      <h2>Активная инвентаризация</h2>
      <div id="status" class="status">Выберите ячейку и начните пересчёт</div>
      <div class="grid4">
        <div class="fact"><b>Сессия</b><span id="activeInventory" class="mono">-</span></div>
        <div class="fact"><b>Склад</b><span id="activeWarehouse" class="mono">-</span></div>
        <div class="fact"><b>Текущая ячейка</b><span id="activeLocation" class="mono">-</span></div>
        <div class="fact"><b>Статус</b><span id="activeStatus">-</span></div>
        <div class="fact"><b>Итог</b><span id="activeCounts">0 / 0</span></div>
      </div>
      <div class="grid4">
        <div class="fact"><b>Прогресс</b><span id="progressPercent">0%</span></div>
        <div class="fact"><b>Проверено ячеек</b><span id="checkedLocations">0 / 0</span></div>
        <div class="fact"><b>Непроверенных палет</b><span id="uncheckedPalletsCount">0</span></div>
        <div class="fact"><b>Проблем</b><span id="problemCount">0</span></div>
      </div>
      <div>
        <label for="scanInput">Скан ячейки или палеты</label>
        <input id="scanInput" class="scan-input mono" placeholder="Код ячейки или палеты и Enter" autocomplete="off">
      </div>
      <div class="grid2">
        <button id="confirmLocationBtn" class="secondary">Пусто</button>
        <button id="completeBtn" class="danger">Завершить пересчёт</button>
      </div>
      <h2>Проблемные строки</h2>
      <div id="problemLines" class="list"></div>
      <h2>Непроверенные ячейки</h2>
      <div id="uncheckedLocations" class="list"></div>
      <h2>Непроверенные палеты</h2>
      <div id="uncheckedPallets" class="list"></div>
      <h2>Все строки</h2>
      <div id="lines" class="list"></div>
    </section>

    <section class="wide stack">
      <h2>История инвентаризации</h2>
      <div id="events" class="list"></div>
    </section>
  </main>

  <script>
    const state = { activeInventoryUid: "", locations: [], warehouses: [], currentLocationCode: "" };
    const $ = (id) => document.getElementById(id);
    const codePrefixes = { pallet: "" };
    const inventoryStatusLabels = {
      open: "Открыта",
      completed: "Завершена",
    };
    const lineStatusLabels = {
      expected: "Ожидается",
      scanned: "Найдена",
      missing: "Отсутствует",
      extra: "Лишняя",
      wrong_location: "Чужая ячейка",
    };
    const operationLabels = {
      inventory_started: "Инвентаризация начата",
      inventory_location_scanned: "Ячейка выбрана",
      inventory_location_confirmed: "Ячейка подтверждена",
      inventory_pallet_scanned: "Палета отсканирована",
      inventory_discrepancy_resolved: "Расхождение обработано",
      pallet_inventory_missing_confirmed: "Недостача подтверждена",
      pallet_inventory_found_placed: "Найденная палета размещена",
      pallet_inventory_moved_to_actual: "Палета перемещена по факту",
      inventory_completed: "Инвентаризация завершена",
    };
    const resolutionLabels = {
      missing_confirmed: "Недостача подтверждена",
      found_placed: "Найденная палета размещена",
      moved_to_actual: "Перемещена по факту",
    };
    function label(map, value) { return map[value] || value || "-"; }
    function actor() { return $("actor").value.trim() || "inventory-demo"; }
    function setStatus(message, kind = "") {
      const el = $("status");
      el.className = `status ${kind}`;
      el.textContent = message;
    }
    function focusScan() { setTimeout(() => $("scanInput").focus(), 30); }
    async function api(path, options = {}) {
      const response = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
      const text = await response.text();
      const data = text ? JSON.parse(text) : null;
      if (!response.ok) throw new Error(data?.detail || response.statusText);
      return data;
    }
    function post(path, body = {}) {
      return api(path, { method: "POST", body: JSON.stringify(body) });
    }
    function discrepancyAction(line) {
      if (line.status === "missing") {
        return { endpoint: "confirm-missing", label: "Подтвердить недостачу", reason: "подтверждено по инвентаризации" };
      }
      if (line.status === "extra") {
        return { endpoint: "place-found", label: "Разместить найденную", reason: "размещение по факту инвентаризации" };
      }
      if (line.status === "wrong_location") {
        return { endpoint: "move-to-actual", label: "Переместить по факту", reason: "перемещение по факту инвентаризации" };
      }
      return null;
    }
    async function loadCodePrefixes() {
      const constants = await api("/api/meta/constants");
      codePrefixes.pallet = `${constants.pallet_code_prefix}-`;
    }
    function showError(err) {
      setStatus(err.message, "err");
      focusScan();
    }
    async function loadLocations() {
      const [warehouses, locations] = await Promise.all([api("/api/warehouses"), api("/api/inventory-locations")]);
      state.warehouses = warehouses;
      state.locations = locations;
      $("warehouseSelect").innerHTML = warehouses.map((warehouse) =>
        `<option value="${warehouse.code}">${warehouse.code} - ${warehouse.name}</option>`
      ).join("");
      $("locationSelect").innerHTML = locations.map((location) =>
        `<option value="${location.code}">${location.code}</option>`
      ).join("");
    }
    async function refreshInventories() {
      const inventories = await api("/api/inventories?limit=50");
      $("inventoryList").innerHTML = inventories.map((inv) => `
        <div class="item ${inv.inventory_uid === state.activeInventoryUid ? "active" : ""}">
          <div class="item-head">
            <strong class="mono">${inv.inventory_uid}</strong>
            <span class="badge ${inv.status}">${label(inventoryStatusLabels, inv.status)}</span>
          </div>
          <div class="meta">${inv.warehouse_code || "-"} | текущая: ${inv.current_location_code || "-"}</div>
          <div class="meta">найдено ${inv.scanned_count} / ожидалось ${inv.expected_count}</div>
          <div class="meta">нет ${inv.missing_count} | лишних ${inv.extra_count} | не там ${inv.wrong_location_count}</div>
          <button class="secondary" data-select-inventory="${inv.inventory_uid}">Выбрать</button>
        </div>
      `).join("") || `<div class="item">Инвентаризаций пока нет</div>`;
      document.querySelectorAll("[data-select-inventory]").forEach((button) => {
        button.addEventListener("click", () => selectInventory(button.dataset.selectInventory).catch(showError));
      });
    }
    async function refreshActive() {
      if (!state.activeInventoryUid) {
        $("activeInventory").textContent = "-";
        $("activeWarehouse").textContent = "-";
        $("activeLocation").textContent = "-";
        $("activeStatus").textContent = "-";
        $("activeCounts").textContent = "0 / 0";
        $("progressPercent").textContent = "0%";
        $("checkedLocations").textContent = "0 / 0";
        $("uncheckedPalletsCount").textContent = "0";
        $("problemCount").textContent = "0";
        $("problemLines").innerHTML = `<div class="item">Проблем пока нет</div>`;
        $("uncheckedLocations").innerHTML = `<div class="item">Сессия не выбрана</div>`;
        $("uncheckedPallets").innerHTML = `<div class="item">Сессия не выбрана</div>`;
        $("lines").innerHTML = `<div class="item">Сессия не выбрана</div>`;
        $("events").innerHTML = `<div class="item">Истории пока нет</div>`;
        return;
      }
      const [inv, lines, progress, events] = await Promise.all([
        api(`/api/inventories/${state.activeInventoryUid}`),
        api(`/api/inventories/${state.activeInventoryUid}/lines`),
        api(`/api/inventories/${state.activeInventoryUid}/progress`),
        api(`/api/inventories/${state.activeInventoryUid}/events?limit=50`),
      ]);
      $("activeInventory").textContent = inv.inventory_uid;
      $("activeWarehouse").textContent = inv.warehouse_code || "-";
      $("activeLocation").textContent = inv.current_location_code || "-";
      $("activeStatus").textContent = label(inventoryStatusLabels, inv.status);
      $("activeCounts").textContent = `${inv.scanned_count} / ${inv.expected_count}`;
      $("progressPercent").textContent = `${progress.progress_percent}%`;
      $("checkedLocations").textContent = `${progress.checked_locations} / ${progress.total_locations}`;
      $("uncheckedPalletsCount").textContent = progress.unchecked_pallets.length;
      $("problemCount").textContent = progress.problem_lines.length;
      state.currentLocationCode = inv.current_location_code || "";
      $("problemLines").innerHTML = progress.problem_lines.map((line) => `
        <div class="item">
          <div class="item-head">
            <a class="mono" href="/cards?kind=pallet&code=${encodeURIComponent(line.pallet.pallet_uid)}">${line.pallet.pallet_uid}</a>
            <span class="badge ${line.status}">${label(lineStatusLabels, line.status)}</span>
          </div>
          <div class="meta">Ожидалась: ${line.expected_location_code || "-"} | Факт: ${line.actual_location_code || "-"}</div>
          <button data-resolve-discrepancy="${line.pallet.pallet_uid}" data-discrepancy-status="${line.status}">${discrepancyAction(line)?.label || "Обработать"}</button>
        </div>
      `).join("") || `<div class="item">Проблем пока нет</div>`;
      document.querySelectorAll("[data-resolve-discrepancy]").forEach((button) => {
        button.addEventListener("click", () => resolveDiscrepancy(button.dataset.resolveDiscrepancy, button.dataset.discrepancyStatus).catch(showError));
      });
      $("uncheckedLocations").innerHTML = progress.unchecked_locations_list.map((location) => `
        <div class="item">
          <div class="item-head">
            <a class="mono" href="/cards?kind=location&code=${encodeURIComponent(location.location_code)}">${location.location_code}</a>
            <span class="badge expected">${location.expected_count} пал.</span>
          </div>
          <div class="grid2">
            <button class="secondary" data-use-location="${location.location_code}">Выбрать</button>
            <button data-confirm-location="${location.location_code}">Пусто</button>
          </div>
        </div>
      `).join("") || `<div class="item">Все ячейки проверены или отмечены</div>`;
      document.querySelectorAll("[data-use-location]").forEach((button) => {
        button.addEventListener("click", () => scanLocation(button.dataset.useLocation).catch(showError));
      });
      document.querySelectorAll("[data-confirm-location]").forEach((button) => {
        button.addEventListener("click", () => confirmLocation(button.dataset.confirmLocation).catch(showError));
      });
      $("uncheckedPallets").innerHTML = progress.unchecked_pallets.map((pallet) => `
        <div class="item">
          <a class="mono" href="/cards?kind=pallet&code=${encodeURIComponent(pallet.pallet_uid)}">${pallet.pallet_uid}</a>
          <div class="meta">${pallet.current_location_code || "-"} | ${pallet.box_count} коробок</div>
        </div>
      `).join("") || `<div class="item">Непроверенных палет нет</div>`;
      $("lines").innerHTML = lines.map((line) => `
        <div class="item">
          <div class="item-head">
            <a class="mono" href="/cards?kind=pallet&code=${encodeURIComponent(line.pallet.pallet_uid)}">${line.pallet.pallet_uid}</a>
            <span class="badge ${line.status}">${label(lineStatusLabels, line.status)}</span>
          </div>
          <div class="meta">Ожидалась: ${line.expected_location_code || "-"} | Факт: ${line.actual_location_code || "-"}</div>
          <div class="meta">Текущая ячейка: ${line.pallet.current_location_code || "-"}</div>
          ${line.resolution_action ? `<div class="meta">Решение: ${label(resolutionLabels, line.resolution_action)} | ${line.resolution_actor || "-"} | ${new Date(line.resolved_at).toLocaleString()}</div>` : ""}
        </div>
      `).join("") || `<div class="item">Ожидаемых палет нет</div>`;
      $("events").innerHTML = events.map((event) => `
        <div class="item">
          <strong>${label(operationLabels, event.operation)}</strong>
          <div class="meta">${event.actor} | ${new Date(event.created_at).toLocaleString()}</div>
        </div>
      `).join("") || `<div class="item">Истории пока нет</div>`;
    }
    async function refreshAll() {
      await refreshInventories();
      await refreshActive();
    }
    async function selectInventory(uid) {
      state.activeInventoryUid = uid;
      await refreshAll();
      setStatus(`Выбрана инвентаризация ${uid}`, "ok");
      focusScan();
    }
    async function startInventory() {
      const inv = await post("/api/inventories", {
        warehouse_code: $("warehouseSelect").value,
        actor: actor(),
      });
      state.activeInventoryUid = inv.inventory_uid;
      await refreshAll();
      setStatus(`Начата инвентаризация склада ${inv.warehouse_code}`, "ok");
      focusScan();
    }
    async function scanLocation(locationCode) {
      if (!state.activeInventoryUid) throw new Error("Сначала начните или выберите инвентаризацию");
      await post(`/api/inventories/${state.activeInventoryUid}/scan-location`, {
        location_code: locationCode,
        actor: actor(),
      });
      await refreshAll();
      setStatus(`Ячейка ${locationCode}: сканируйте палету или нажмите "Пусто".`, "ok");
      focusScan();
    }
    async function confirmLocation(locationCode = "") {
      if (!state.activeInventoryUid) throw new Error("Сначала начните или выберите инвентаризацию");
      const targetLocation = locationCode || state.currentLocationCode;
      if (!targetLocation) throw new Error("Сначала отсканируйте или выберите ячейку");
      await post(`/api/inventories/${state.activeInventoryUid}/confirm-location`, {
        location_code: targetLocation,
        actor: actor(),
      });
      await refreshAll();
      setStatus(`Пустая ячейка подтверждена: ${targetLocation}. Сканируйте следующую ячейку.`, "ok");
      focusScan();
    }
    async function scanPallet(palletUid) {
      if (!state.activeInventoryUid) throw new Error("Сначала начните или выберите инвентаризацию");
      if (!state.currentLocationCode) throw new Error("Сначала отсканируйте ячейку");
      await post(`/api/inventories/${state.activeInventoryUid}/scan`, {
        pallet_uid: palletUid,
        actor: actor(),
      });
      await refreshAll();
      setStatus(`Палета отсканирована: ${palletUid}. Ячейка закрыта, сканируйте следующую.`, "ok");
      focusScan();
    }
    async function resolveDiscrepancy(palletUid, status) {
      if (!state.activeInventoryUid) throw new Error("Сначала выберите инвентаризацию");
      const action = discrepancyAction({ status });
      if (!action) throw new Error("Для этой строки нет действия");
      const reason = window.prompt("Причина решения", action.reason);
      if (!reason || !reason.trim()) throw new Error("Нужна причина решения");
      await post(`/api/inventories/${state.activeInventoryUid}/discrepancies/${encodeURIComponent(palletUid)}/${action.endpoint}`, {
        actor: actor(),
        reason: reason.trim(),
      });
      await refreshAll();
      setStatus(`${action.label}: ${palletUid}`, "ok");
      focusScan();
    }
    async function completeInventory() {
      if (!state.activeInventoryUid) throw new Error("Сначала выберите инвентаризацию");
      await post(`/api/inventories/${state.activeInventoryUid}/complete`, { actor: actor() });
      await refreshAll();
      setStatus("Пересчёт завершён, расхождения зафиксированы", "ok");
      focusScan();
    }
    $("startBtn").addEventListener("click", () => startInventory().catch(showError));
    $("refreshInventoriesBtn").addEventListener("click", () => refreshInventories().catch(showError));
    $("confirmLocationBtn").addEventListener("click", () => confirmLocation().catch(showError));
    $("completeBtn").addEventListener("click", () => completeInventory().catch(showError));
    $("useLocationBtn").addEventListener("click", () => scanLocation($("locationSelect").value).catch(showError));
    $("scanInput").addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      event.preventDefault();
      const code = event.currentTarget.value.trim().toUpperCase();
      event.currentTarget.value = "";
      if (!code) return;
      if (code.startsWith(codePrefixes.pallet)) {
        scanPallet(code).catch(showError);
      } else if (state.locations.some((location) => location.code === code)) {
        scanLocation(code).catch(showError);
      } else if (code.startsWith("WH")) {
        showError(new Error(`Складская ячейка не найдена в обходе: ${code}`));
      } else {
        showError(new Error(`Неизвестный код: ${code}`));
      }
    });
    loadCodePrefixes().then(loadLocations).then(refreshAll).then(focusScan).catch(showError);
  </script>
</body>
</html>"""


@router.get("/shipments", response_class=HTMLResponse, include_in_schema=False)
@standard_page("shipments")
def shipments_page() -> str:
    return """<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Складской пилот: отгрузки</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f4f6f7;
      --panel: #fff;
      --line: #d7dde2;
      --text: #101828;
      --muted: #667085;
      --accent: #0f766e;
      --danger: #b42318;
      --ok: #067647;
      --warn: #a15c07;
      --dark: #111820;
    }
    * { box-sizing: border-box; }
    body { margin: 0; background: var(--bg); color: var(--text); font: 15px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    header { min-height: 54px; padding: 10px 18px; display: flex; align-items: center; justify-content: space-between; gap: 12px; color: #fff; background: var(--dark); }
    header h1 { margin: 0; font-size: 18px; letter-spacing: 0; }
    header a { color: #d8fbf6; text-decoration: none; font-weight: 700; }
    main { max-width: 1300px; margin: 0 auto; padding: 14px; display: grid; grid-template-columns: 360px minmax(0, 1fr) 420px; gap: 14px; }
    section, aside { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 14px; }
    h2, h3 { margin: 0; letter-spacing: 0; }
    h2 { font-size: 17px; }
    h3 { font-size: 14px; }
    .stack { display: grid; gap: 12px; }
    .row { display: flex; gap: 8px; align-items: center; }
    .row > * { flex: 1; }
    .grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    label { display: block; margin-bottom: 5px; color: var(--muted); font-size: 12px; font-weight: 800; text-transform: uppercase; }
    input, button, select { width: 100%; min-height: 40px; border: 1px solid var(--line); border-radius: 6px; padding: 8px 10px; background: #fff; color: var(--text); font: inherit; }
    button { cursor: pointer; border-color: var(--accent); background: var(--accent); color: #fff; font-weight: 800; }
    button.secondary { background: #f2fbf9; color: #0b5e58; }
    button.danger { border-color: var(--danger); background: var(--danger); }
    button.ghost { border-color: var(--line); background: #fff; color: var(--text); }
    .status { min-height: 46px; padding: 10px 12px; border: 1px solid #c7dcf3; border-radius: 6px; background: #eff8ff; font-weight: 800; }
    .status.ok { color: var(--ok); border-color: #abefc6; background: #ecfdf3; }
    .status.err { color: var(--danger); border-color: #fecdca; background: #fff1f0; }
    .status.warn { color: var(--warn); border-color: #fedf89; background: #fff8eb; }
    .list { display: grid; gap: 8px; max-height: 540px; overflow: auto; }
    .item { display: grid; gap: 7px; padding: 10px; border: 1px solid var(--line); border-radius: 8px; background: #fff; }
    .item.active { border-color: var(--accent); background: #ecfdf3; }
    .item-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
    .meta { color: var(--muted); font-size: 13px; }
    .badge { display: inline-flex; align-items: center; min-height: 24px; padding: 2px 7px; border-radius: 999px; background: #eef2f6; color: #344054; font-size: 12px; font-weight: 800; white-space: nowrap; }
    .badge.draft { background: #eef2f6; color: #344054; }
    .badge.reserved { background: #fff8eb; color: #a15c07; }
    .badge.expedition { background: #eff8ff; color: #175cd3; }
    .badge.loading { background: #f4f3ff; color: #5925dc; }
    .badge.completed { background: #ecfdf3; color: #067647; }
    .scan-input { min-height: 66px; border: 2px solid var(--accent); font-size: 25px; font-weight: 900; letter-spacing: 0; }
    .facts { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
    .fact { padding: 8px; border: 1px solid var(--line); border-radius: 6px; background: #fbfcfd; }
    .fact b { display: block; color: var(--muted); font-size: 11px; text-transform: uppercase; }
    .fact span { display: block; margin-top: 2px; font-weight: 800; overflow-wrap: anywhere; }
    .wide { grid-column: 1 / -1; }
    @media (max-width: 1050px) {
      main { grid-template-columns: 1fr; padding: 10px; }
      .grid2, .facts { grid-template-columns: 1fr; }
      header { align-items: flex-start; flex-direction: column; }
    }
  </style>
</head>
<body>
  <header>
    <h1>Складской пилот: отгрузки</h1>
    <div class="row" style="max-width: 360px;">
      <a href="/scan">Склад</a>
      <a href="/terminal">ТСД</a>
      <a href="/map">Карта</a>
      <a href="/shipments">Отгрузки</a>
      <a href="/inventory">Инвентаризация</a>
      <a href="/catalog">Справочники</a>
      <a href="/cards">Карточки</a>
      <a href="/docs">Документация API</a>
    </div>
  </header>

  <main>
    <aside class="stack">
      <h2>Отгрузки</h2>
      <div>
        <label for="actor">Оператор</label>
        <input id="actor" value="shipping-demo" autocomplete="off">
      </div>
      <div class="grid2">
        <input id="customerName" value="Демо-клиент" autocomplete="off">
        <input id="destination" value="Тестовая точка" autocomplete="off">
      </div>
      <button id="createShipmentBtn">Создать заявку</button>
      <button id="refreshShipmentsBtn" class="secondary">Обновить</button>
      <div id="shipmentList" class="list"></div>
    </aside>

    <section class="stack">
      <h2>Активная заявка</h2>
      <div id="status" class="status">Создайте или выберите отгрузку</div>
      <div class="facts">
        <div class="fact"><b>Заявка</b><span id="activeShipment" class="mono">-</span></div>
        <div class="fact"><b>Статус</b><span id="activeStatus">-</span></div>
        <div class="fact"><b>Палеты</b><span id="activeCounts">0 / 0</span></div>
      </div>
      <div class="grid2">
        <button id="toExpeditionBtn" class="secondary">В экспедицию</button>
        <button id="closeShipmentBtn" class="danger">Закрыть отгрузку</button>
      </div>
      <div>
        <label for="loadScanInput">Скан погрузки</label>
        <input id="loadScanInput" class="scan-input mono" placeholder="Код палеты и Enter" autocomplete="off">
      </div>
      <div class="list" id="shipmentPallets"></div>
    </section>

    <aside class="stack">
      <h2>Доступные палеты</h2>
      <button id="refreshAvailableBtn" class="secondary">Обновить</button>
      <div id="availablePallets" class="list"></div>
    </aside>

    <section class="wide stack">
      <h2>История отгрузки</h2>
      <div id="shipmentEvents" class="list"></div>
    </section>
  </main>

  <script>
    const state = { activeShipmentUid: "" };
    const $ = (id) => document.getElementById(id);
    const shipmentStatusLabels = {
      draft: "Черновик",
      reserved: "Зарезервирована",
      expedition: "В экспедиции",
      loading: "Погрузка",
      completed: "Завершена",
      cancelled: "Отменена",
    };
    const palletStatusLabels = {
      available: "Доступна",
      reserved: "В резерве",
      expedition: "В экспедиции",
      loaded: "Погружена",
    };
    const operationLabels = {
      shipment_created: "Заявка создана",
      shipment_pallet_reserved: "Палета добавлена в заявку",
      shipment_moved_to_expedition: "Заявка передана в экспедицию",
      shipment_pallet_loaded: "Палета погружена",
      shipment_closed: "Отгрузка закрыта",
    };
    function label(map, value) { return map[value] || value || "-"; }
    function actor() { return $("actor").value.trim() || "shipping-demo"; }
    function setStatus(message, kind = "") {
      const el = $("status");
      el.className = `status ${kind}`;
      el.textContent = message;
    }
    function focusLoad() { setTimeout(() => $("loadScanInput").focus(), 30); }
    async function api(path, options = {}) {
      const response = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
      const text = await response.text();
      const data = text ? JSON.parse(text) : null;
      if (!response.ok) throw new Error(data?.detail || response.statusText);
      return data;
    }
    function post(path, body = {}) {
      return api(path, { method: "POST", body: JSON.stringify(body) });
    }
    async function refreshShipments() {
      const shipments = await api("/api/shipments?limit=50");
      $("shipmentList").innerHTML = shipments.map((shipment) => `
        <div class="item ${shipment.shipment_uid === state.activeShipmentUid ? "active" : ""}">
          <div class="item-head">
            <strong class="mono">${shipment.shipment_uid}</strong>
            <span class="badge ${shipment.status}">${label(shipmentStatusLabels, shipment.status)}</span>
          </div>
          <div class="meta">${shipment.customer_name} | ${shipment.destination}</div>
          <div class="meta">Палеты: ${shipment.loaded_count} / ${shipment.pallet_count}</div>
          <button class="secondary" data-select-shipment="${shipment.shipment_uid}">Выбрать</button>
        </div>
      `).join("") || `<div class="item">Отгрузок пока нет</div>`;
      document.querySelectorAll("[data-select-shipment]").forEach((button) => {
        button.addEventListener("click", () => selectShipment(button.dataset.selectShipment).catch(showError));
      });
    }
    async function refreshAvailable() {
      const pallets = await api("/api/pallets?status=available&limit=200");
      $("availablePallets").innerHTML = pallets.map((pallet) => `
        <div class="item">
          <div class="item-head">
            <a class="mono" href="/cards?kind=pallet&code=${encodeURIComponent(pallet.pallet_uid)}">${pallet.pallet_uid}</a>
            <span class="badge available">${pallet.box_count} кор.</span>
          </div>
          <div class="meta">${pallet.current_location_code || "-"} | партия ${pallet.batch_id || "-"}</div>
          <button data-add-pallet="${pallet.pallet_uid}">В заявку</button>
        </div>
      `).join("") || `<div class="item">Доступных палет нет</div>`;
      document.querySelectorAll("[data-add-pallet]").forEach((button) => {
        button.addEventListener("click", () => addPallet(button.dataset.addPallet).catch(showError));
      });
    }
    async function refreshActive() {
      if (!state.activeShipmentUid) {
        $("activeShipment").textContent = "-";
        $("activeStatus").textContent = "-";
        $("activeCounts").textContent = "0 / 0";
        $("shipmentPallets").innerHTML = `<div class="item">Заявка не выбрана</div>`;
        $("shipmentEvents").innerHTML = `<div class="item">Истории пока нет</div>`;
        return;
      }
      const [shipment, pallets, events] = await Promise.all([
        api(`/api/shipments/${state.activeShipmentUid}`),
        api(`/api/shipments/${state.activeShipmentUid}/pallets`),
        api(`/api/shipments/${state.activeShipmentUid}/events?limit=50`),
      ]);
      $("activeShipment").textContent = shipment.shipment_uid;
      $("activeStatus").textContent = label(shipmentStatusLabels, shipment.status);
      $("activeCounts").textContent = `${shipment.loaded_count} / ${shipment.pallet_count}`;
      $("shipmentPallets").innerHTML = pallets.map((row) => `
        <div class="item">
          <div class="item-head">
            <a class="mono" href="/cards?kind=pallet&code=${encodeURIComponent(row.pallet.pallet_uid)}">${row.pallet.pallet_uid}</a>
            <span class="badge ${row.shipment_pallet_status}">${label(palletStatusLabels, row.shipment_pallet_status)}</span>
          </div>
          <div class="meta">${row.pallet.box_count} коробок | ${row.pallet.current_location_code || "-"}</div>
          <button class="secondary" data-load-pallet="${row.pallet.pallet_uid}">Погрузить</button>
        </div>
      `).join("") || `<div class="item">Палеты не выбраны</div>`;
      document.querySelectorAll("[data-load-pallet]").forEach((button) => {
        button.addEventListener("click", () => loadPallet(button.dataset.loadPallet).catch(showError));
      });
      $("shipmentEvents").innerHTML = events.map((event) => `
        <div class="item">
          <strong>${label(operationLabels, event.operation)}</strong>
          <div class="meta">${event.actor} | ${new Date(event.created_at).toLocaleString()}</div>
          ${event.reason ? `<div class="meta">Причина: ${event.reason}</div>` : ""}
        </div>
      `).join("") || `<div class="item">Истории пока нет</div>`;
    }
    async function refreshAll() {
      await Promise.all([refreshShipments(), refreshAvailable()]);
      await refreshActive();
    }
    function showError(err) {
      setStatus(err.message, "err");
      focusLoad();
    }
    async function selectShipment(uid) {
      state.activeShipmentUid = uid;
      await refreshAll();
      setStatus(`Выбрана заявка ${uid}`, "ok");
      focusLoad();
    }
    async function createShipment() {
      const shipment = await post("/api/shipments", {
        actor: actor(),
        customer_name: $("customerName").value.trim() || "Демо-клиент",
        destination: $("destination").value.trim() || "Тестовая точка",
      });
      state.activeShipmentUid = shipment.shipment_uid;
      await refreshAll();
      setStatus(`Создана заявка ${shipment.shipment_uid}`, "ok");
      focusLoad();
    }
    async function addPallet(palletUid) {
      if (!state.activeShipmentUid) throw new Error("Сначала выберите отгрузку");
      await post(`/api/shipments/${state.activeShipmentUid}/pallets/${palletUid}`, { actor: actor() });
      await refreshAll();
      setStatus(`Палета зарезервирована: ${palletUid}`, "ok");
      focusLoad();
    }
    async function toExpedition() {
      if (!state.activeShipmentUid) throw new Error("Сначала выберите отгрузку");
      await post(`/api/shipments/${state.activeShipmentUid}/expedition`, { actor: actor() });
      await refreshAll();
      setStatus("Палеты переданы в экспедицию", "ok");
      focusLoad();
    }
    async function loadPallet(palletUid) {
      if (!state.activeShipmentUid) throw new Error("Сначала выберите отгрузку");
      await post(`/api/shipments/${state.activeShipmentUid}/load/${palletUid}`, { actor: actor() });
      await refreshAll();
      setStatus(`Палета погружена: ${palletUid}`, "ok");
      focusLoad();
    }
    async function closeShipment() {
      if (!state.activeShipmentUid) throw new Error("Сначала выберите отгрузку");
      await post(`/api/shipments/${state.activeShipmentUid}/close`, { actor: actor(), reason: "погрузка завершена" });
      await refreshAll();
      setStatus("Отгрузка закрыта по факту окончания погрузки", "ok");
      focusLoad();
    }
    $("createShipmentBtn").addEventListener("click", () => createShipment().catch(showError));
    $("refreshShipmentsBtn").addEventListener("click", () => refreshShipments().catch(showError));
    $("refreshAvailableBtn").addEventListener("click", () => refreshAvailable().catch(showError));
    $("toExpeditionBtn").addEventListener("click", () => toExpedition().catch(showError));
    $("closeShipmentBtn").addEventListener("click", () => closeShipment().catch(showError));
    $("loadScanInput").addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      event.preventDefault();
      const palletUid = event.currentTarget.value.trim();
      event.currentTarget.value = "";
      if (!palletUid) return;
      loadPallet(palletUid).catch(showError);
    });
    refreshAll().then(focusLoad).catch(showError);
  </script>
</body>
</html>"""
