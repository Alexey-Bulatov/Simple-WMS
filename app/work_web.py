from fastapi import APIRouter
from fastapi.responses import HTMLResponse


router = APIRouter()


@router.get("/work", response_class=HTMLResponse, include_in_schema=False)
def work_page() -> str:
    return """<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Рабочее место WMS</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #eef2f3;
      --surface: #fff;
      --surface-soft: #f7f9fa;
      --line: #d5dde1;
      --line-strong: #aebbc2;
      --text: #142129;
      --muted: #65727a;
      --accent: #087a70;
      --accent-dark: #075f58;
      --accent-soft: #e7f6f3;
      --ok: #087443;
      --ok-soft: #eaf8ef;
      --warn: #9a5b0a;
      --warn-soft: #fff6e5;
      --danger: #b42318;
      --danger-soft: #fff0ee;
      --header: #111a20;
    }
    * { box-sizing: border-box; }
    html, body { min-height: 100%; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 15px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    button, input, select { font: inherit; }
    button, a { -webkit-tap-highlight-color: transparent; }
    button:focus-visible, input:focus-visible, select:focus-visible, a:focus-visible {
      outline: 3px solid #f4b740;
      outline-offset: 2px;
    }
    .work-header {
      min-height: 62px;
      padding: 9px 20px;
      display: grid;
      grid-template-columns: auto minmax(420px, 760px) auto;
      align-items: center;
      gap: 22px;
      color: #fff;
      background: var(--header);
    }
    .brand {
      color: #fff;
      font-size: 18px;
      font-weight: 850;
      text-decoration: none;
      white-space: nowrap;
    }
    .context {
      display: grid;
      grid-template-columns: minmax(230px, 1fr) minmax(180px, .7fr);
      gap: 10px;
    }
    .context-field { min-width: 0; }
    .context label {
      display: block;
      margin-bottom: 2px;
      color: #aebcc4;
      font-size: 10px;
      font-weight: 850;
      text-transform: uppercase;
    }
    .context select, .context input {
      width: 100%;
      height: 36px;
      min-width: 0;
      padding: 5px 9px;
      border: 1px solid #40505a;
      border-radius: 5px;
      background: #202c34;
      color: #fff;
    }
    .tech-link {
      min-height: 38px;
      padding: 8px 11px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border: 1px solid #52616a;
      border-radius: 5px;
      color: #d9e4e8;
      font-size: 13px;
      font-weight: 750;
      text-decoration: none;
      white-space: nowrap;
    }
    .work-layout {
      width: min(1180px, 100%);
      margin: 0 auto;
      padding: 18px;
      display: grid;
      grid-template-columns: 240px minmax(0, 1fr);
      gap: 18px;
      align-items: start;
    }
    .operation-nav {
      position: sticky;
      top: 18px;
      display: grid;
      gap: 6px;
    }
    .nav-title {
      margin: 0 0 6px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 850;
      text-transform: uppercase;
    }
    .operation-button {
      width: 100%;
      min-height: 56px;
      padding: 9px 11px;
      display: grid;
      grid-template-columns: 28px 1fr auto;
      align-items: center;
      gap: 9px;
      border: 1px solid transparent;
      border-radius: 6px;
      background: transparent;
      color: var(--text);
      text-align: left;
      cursor: pointer;
    }
    .operation-button:hover { background: #e2e8ea; }
    .operation-button.active {
      border-color: #a9d9d2;
      background: var(--accent-soft);
      color: var(--accent-dark);
    }
    .operation-number {
      width: 28px;
      height: 28px;
      display: grid;
      place-items: center;
      border: 1px solid var(--line-strong);
      border-radius: 50%;
      background: var(--surface);
      font-size: 12px;
      font-weight: 900;
    }
    .operation-button strong { font-size: 14px; }
    .queue-count {
      min-width: 26px;
      padding: 2px 6px;
      border-radius: 10px;
      background: #dde5e8;
      color: #3b4a52;
      font-size: 11px;
      font-weight: 850;
      text-align: center;
    }
    .operation-button.active .queue-count { background: #c8eae5; color: var(--accent-dark); }
    .nav-separator { height: 1px; margin: 10px 0; background: var(--line); }
    .quiet-link {
      padding: 8px 11px;
      color: #41515a;
      font-size: 13px;
      font-weight: 700;
      text-decoration: none;
    }
    .workspace {
      min-width: 0;
      overflow: hidden;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: var(--surface);
    }
    .workflow-head {
      padding: 20px 22px 16px;
      border-bottom: 1px solid var(--line);
    }
    .eyebrow {
      margin-bottom: 3px;
      color: var(--accent-dark);
      font-size: 11px;
      font-weight: 900;
      text-transform: uppercase;
    }
    h1, h2, p { margin-top: 0; }
    h1 { margin-bottom: 5px; font-size: 24px; letter-spacing: 0; }
    h2 { margin-bottom: 0; font-size: 16px; letter-spacing: 0; }
    .workflow-description { margin-bottom: 0; color: var(--muted); }
    .steps {
      margin: 17px 0 0;
      padding: 0;
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      list-style: none;
    }
    .steps.four { grid-template-columns: repeat(4, 1fr); }
    .step[hidden] { display: none; }
    .step {
      min-width: 0;
      display: grid;
      grid-template-columns: 28px 1fr;
      align-items: center;
      gap: 8px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 750;
    }
    .step::after {
      content: "";
      height: 2px;
      margin-inline: 8px;
      grid-column: 3;
      background: var(--line);
    }
    .step:last-child::after { display: none; }
    .step-mark {
      width: 28px;
      height: 28px;
      display: grid;
      place-items: center;
      border: 2px solid var(--line-strong);
      border-radius: 50%;
      background: var(--surface);
      font-size: 11px;
      font-weight: 900;
    }
    .step.active { color: var(--text); }
    .step.active .step-mark { border-color: var(--accent); color: #fff; background: var(--accent); }
    .step.done .step-mark { border-color: var(--ok); color: var(--ok); background: var(--ok-soft); }
    .step.done::after { background: #7fc7a1; }
    .workflow-body { padding: 20px 22px; display: grid; gap: 16px; }
    .notice {
      min-height: 46px;
      padding: 11px 13px;
      border-left: 4px solid #4d93c4;
      border-radius: 4px;
      background: #eef7fc;
      font-weight: 750;
    }
    .notice.ok { border-color: var(--ok); color: var(--ok); background: var(--ok-soft); }
    .notice.warn { border-color: #d89725; color: var(--warn); background: var(--warn-soft); }
    .notice.err { border-color: var(--danger); color: var(--danger); background: var(--danger-soft); }
    .operation-context {
      padding: 12px 0 15px;
      display: grid;
      grid-template-columns: minmax(220px, 300px) minmax(0, 1fr);
      align-items: end;
      gap: 16px;
      border-bottom: 1px solid var(--line);
    }
    .operation-context[hidden] { display: none; }
    .operation-context label {
      display: block;
      margin-bottom: 4px;
      color: var(--muted);
      font-size: 11px;
      font-weight: 850;
      text-transform: uppercase;
    }
    .operation-context select {
      width: 100%;
      min-height: 44px;
      padding: 8px 10px;
      border: 1px solid var(--line-strong);
      border-radius: 5px;
      background: #fff;
      color: var(--text);
      font-weight: 800;
    }
    .operation-context-help { padding-bottom: 5px; color: var(--muted); font-size: 12px; }
    .scan-area {
      padding: 16px;
      border: 2px solid var(--accent);
      border-radius: 7px;
      background: #fbfefd;
    }
    .next-action {
      margin-bottom: 9px;
      display: block;
      color: var(--accent-dark);
      font-size: 16px;
      font-weight: 850;
    }
    .scan-input {
      width: 100%;
      height: 64px;
      padding: 10px 12px;
      border: 1px solid var(--line-strong);
      border-radius: 5px;
      background: #fff;
      color: var(--text);
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 24px;
      font-weight: 800;
      letter-spacing: 0;
    }
    .scan-input:disabled { background: #edf1f2; color: var(--muted); }
    .scan-hint { margin-top: 7px; color: var(--muted); font-size: 12px; }
    .current-object {
      display: none;
      border-top: 1px solid var(--line);
      border-bottom: 1px solid var(--line);
    }
    .current-object.visible { display: block; }
    .object-head {
      padding: 12px 0;
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 12px;
    }
    .object-kicker { color: var(--muted); font-size: 11px; font-weight: 850; text-transform: uppercase; }
    .object-code {
      margin-top: 2px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 18px;
      font-weight: 900;
      overflow-wrap: anywhere;
    }
    .text-button {
      min-height: 34px;
      padding: 6px 9px;
      border: 1px solid var(--line);
      border-radius: 5px;
      background: #fff;
      color: #40515a;
      font-weight: 750;
      cursor: pointer;
    }
    .facts {
      padding: 0 0 14px;
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 1px;
      background: var(--line);
    }
    .fact { min-width: 0; padding: 10px; background: var(--surface-soft); }
    .fact b { display: block; color: var(--muted); font-size: 10px; text-transform: uppercase; }
    .fact span { display: block; margin-top: 3px; font-weight: 850; overflow-wrap: anywhere; }
    .action-row { display: flex; flex-wrap: wrap; gap: 9px; }
    .primary-action, .secondary-action {
      min-height: 46px;
      padding: 9px 16px;
      border-radius: 5px;
      font-weight: 850;
      cursor: pointer;
    }
    .primary-action { border: 1px solid var(--accent); background: var(--accent); color: #fff; }
    .primary-action:hover { background: var(--accent-dark); }
    .secondary-action { border: 1px solid var(--accent); background: #fff; color: var(--accent-dark); }
    button[hidden] { display: none; }
    button:disabled { cursor: not-allowed; border-color: var(--line); background: #e7ecee; color: #89969d; }
    .queue-section { border-top: 1px solid var(--line); }
    .queue-head {
      padding: 14px 22px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      background: var(--surface-soft);
    }
    .queue-subtitle { margin-top: 2px; color: var(--muted); font-size: 12px; }
    .queue-list { max-height: 290px; overflow-y: auto; }
    .queue-row {
      min-height: 62px;
      padding: 10px 22px;
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      align-items: center;
      gap: 12px;
      border-top: 1px solid var(--line);
    }
    .queue-code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-weight: 850; overflow-wrap: anywhere; }
    .queue-meta { margin-top: 2px; color: var(--muted); font-size: 12px; }
    .empty-row { padding: 18px 22px; border-top: 1px solid var(--line); color: var(--muted); }
    .completion {
      display: none;
      padding: 18px;
      border: 1px solid #a7dbbe;
      border-radius: 6px;
      background: var(--ok-soft);
    }
    .completion.visible { display: block; }
    .completion strong { display: block; color: var(--ok); font-size: 17px; }
    .completion-code { margin-top: 6px; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-weight: 850; }
    .shipment-create {
      display: none;
      padding: 16px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--surface-soft);
    }
    .shipment-create.visible { display: grid; gap: 12px; }
    .shipment-fields { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .shipment-fields label { display: block; margin-bottom: 4px; color: var(--muted); font-size: 11px; font-weight: 850; text-transform: uppercase; }
    .shipment-fields input, .shipment-fields select { width: 100%; min-height: 42px; padding: 8px 10px; border: 1px solid var(--line-strong); border-radius: 5px; background: #fff; }
    .shipment-create > div > label { display: block; margin-bottom: 4px; color: var(--muted); font-size: 11px; font-weight: 850; text-transform: uppercase; }
    .shipment-create > div > input { width: 100%; min-height: 42px; padding: 8px 10px; border: 1px solid var(--line-strong); border-radius: 5px; background: #fff; }
    .progress-track { height: 10px; margin: 0 0 14px; overflow: hidden; border-radius: 5px; background: #dde5e8; }
    .progress-fill { width: 0; height: 100%; background: var(--accent); transition: width .2s ease; }
    .problem-box { display: none; padding: 13px 0 0; border-top: 1px solid var(--line); }
    .problem-box.visible { display: block; }
    .problem-head { margin-bottom: 8px; display: flex; align-items: center; justify-content: space-between; gap: 10px; }
    .problem-list { display: grid; gap: 1px; background: var(--line); }
    .problem-row { padding: 10px; display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: center; gap: 10px; background: var(--surface-soft); }
    .problem-status { color: var(--danger); font-size: 12px; font-weight: 850; }
    .queue-divider { padding: 9px 22px; border-top: 1px solid var(--line); background: #eaf0f2; color: #46565e; font-size: 11px; font-weight: 900; text-transform: uppercase; }
    .task-priority { min-width: 74px; padding: 4px 7px; border-radius: 4px; font-size: 11px; font-weight: 900; text-align: center; }
    .task-priority.low { color: #52616a; background: #e8edef; }
    .task-priority.normal { color: #175f59; background: var(--accent-soft); }
    .task-priority.high { color: var(--warn); background: var(--warn-soft); }
    .task-priority.urgent { color: var(--danger); background: var(--danger-soft); }
    .task-actions { display: flex; align-items: center; gap: 7px; }
    @media (max-width: 900px) {
      .work-header { grid-template-columns: 1fr auto; gap: 10px; padding: 9px 12px; }
      .context { grid-column: 1 / -1; grid-row: 2; grid-template-columns: 1fr 1fr; width: 100%; }
      .work-layout { padding: 12px; grid-template-columns: 1fr; }
      .operation-nav { position: static; grid-template-columns: repeat(7, 1fr); }
      .nav-title, .nav-separator, .quiet-link { display: none; }
    }
    @media (max-width: 620px) {
      .work-header { grid-template-columns: 1fr auto; }
      .brand { font-size: 16px; }
      .tech-link { width: 38px; overflow: hidden; color: transparent; position: relative; }
      .tech-link::after { content: "..."; position: absolute; color: #d9e4e8; font-size: 18px; }
      .context { grid-template-columns: 1fr; }
      .work-layout { padding: 8px; gap: 8px; }
      .operation-nav { display: flex; overflow-x: auto; padding-bottom: 3px; }
      .operation-button { flex: 0 0 175px; min-height: 52px; grid-template-columns: 24px 1fr auto; padding: 7px; }
      .operation-number { width: 24px; height: 24px; }
      .workflow-head, .workflow-body { padding: 16px 13px; }
      h1 { font-size: 21px; }
      .steps { gap: 4px; }
      .step { grid-template-columns: 25px 1fr; gap: 5px; }
      .step-mark { width: 25px; height: 25px; }
      .step::after { display: none; }
      .steps.four { grid-template-columns: 1fr 1fr 1.2fr 1.05fr; }
      .steps.four .step { grid-template-columns: 20px minmax(0, 1fr); gap: 3px; font-size: 11px; }
      .steps.four .step-mark { width: 20px; height: 20px; }
      .steps.four .step > span:last-child { min-width: 0; }
      .scan-input { height: 58px; font-size: 19px; }
      .facts { grid-template-columns: 1fr 1fr; }
      .shipment-fields { grid-template-columns: 1fr; }
      .operation-context { grid-template-columns: 1fr; gap: 7px; }
      .action-row > * { width: 100%; }
      .problem-row { grid-template-columns: 1fr; }
      .problem-row .text-button { width: 100%; }
      .task-actions { align-items: stretch; flex-direction: column; }
      .queue-head, .queue-row { padding-inline: 13px; }
      .queue-divider { padding-inline: 13px; }
    }
  </style>
</head>
<body>
  <header class="work-header">
    <a class="brand" href="/work">WMS Pilot</a>
    <div class="context">
      <div class="context-field">
        <label for="workWarehouse">Склад</label>
        <select id="workWarehouse" aria-label="Текущий склад"></select>
      </div>
      <div class="context-field">
        <label for="workActor">Оператор</label>
        <input id="workActor" aria-label="Оператор" autocomplete="off" value="Кладовщик">
      </div>
    </div>
    <a class="tech-link" href="/tech">Технический режим</a>
  </header>

  <main class="work-layout">
    <nav class="operation-nav" aria-label="Складские операции">
      <div class="nav-title">Операции</div>
      <button class="operation-button active" type="button" data-operation="tasks">
        <span class="operation-number">1</span>
        <strong>Задания</strong>
        <span id="taskCount" class="queue-count">0</span>
      </button>
      <button class="operation-button" type="button" data-operation="build">
        <span class="operation-number">2</span>
        <strong>Формирование палеты</strong>
        <span id="openCount" class="queue-count">0</span>
      </button>
      <button class="operation-button" type="button" data-operation="place">
        <span class="operation-number">3</span>
        <strong>Размещение палеты</strong>
        <span id="waitingCount" class="queue-count">0</span>
      </button>
      <button class="operation-button" type="button" data-operation="move">
        <span class="operation-number">4</span>
        <strong>Перемещение палеты</strong>
        <span id="availableCount" class="queue-count">0</span>
      </button>
      <button class="operation-button" type="button" data-operation="ship">
        <span class="operation-number">5</span>
        <strong>Отгрузка</strong>
        <span id="shipmentCount" class="queue-count">0</span>
      </button>
      <button class="operation-button" type="button" data-operation="inventory">
        <span class="operation-number">6</span>
        <strong>Инвентаризация</strong>
        <span id="inventoryCount" class="queue-count">0</span>
      </button>
      <button class="operation-button" type="button" data-operation="transfer">
        <span class="operation-number">7</span>
        <strong>Между складами</strong>
        <span id="transferCount" class="queue-count">0</span>
      </button>
      <div class="nav-separator"></div>
      <a class="quiet-link" href="/cards">Поиск объекта</a>
      <a class="quiet-link" href="/tech">Все функции</a>
    </nav>

    <section class="workspace" aria-live="polite">
      <div class="workflow-head">
        <div class="eyebrow">Текущая операция</div>
        <h1 id="operationTitle">Формирование палеты</h1>
        <p id="operationDescription" class="workflow-description">Соберите коробки на палету и завершите формирование.</p>
        <ol class="steps" aria-label="Этапы операции">
          <li class="step active" data-step="1"><span class="step-mark">1</span><span id="stepOneLabel">Палета</span></li>
          <li class="step" data-step="2"><span class="step-mark">2</span><span id="stepTwoLabel">Коробки</span></li>
          <li class="step" data-step="3"><span class="step-mark">3</span><span id="stepThreeLabel">Завершение</span></li>
          <li class="step" data-step="4" hidden><span class="step-mark">4</span><span id="stepFourLabel">Готово</span></li>
        </ol>
      </div>

      <div class="workflow-body">
        <div id="notice" class="notice">Загрузка рабочего места...</div>

        <div id="moveWarehouseContext" class="operation-context" hidden>
          <div>
            <label for="moveWarehouse">Склад перемещения</label>
            <select id="moveWarehouse" aria-label="Склад перемещения"></select>
          </div>
          <div id="moveWarehouseHint" class="operation-context-help">
            Палеты и целевые ячейки будут отфильтрованы по выбранному складу.
          </div>
        </div>

        <div id="shipmentCreate" class="shipment-create">
          <div class="shipment-fields">
            <div>
              <label for="shipmentCustomer">Получатель</label>
              <input id="shipmentCustomer" autocomplete="off" value="Демо-клиент">
            </div>
            <div>
              <label for="shipmentDestination">Адрес доставки</label>
              <input id="shipmentDestination" autocomplete="off" value="Тестовая точка">
            </div>
          </div>
          <button id="createShipmentBtn" class="primary-action" type="button">Создать заявку на отгрузку</button>
        </div>

        <div id="inventoryStart" class="shipment-create">
          <strong id="inventoryStartTitle">Начать обход склада</strong>
          <button id="startInventoryBtn" class="primary-action" type="button">Начать инвентаризацию</button>
        </div>

        <div id="transferCreate" class="shipment-create">
          <strong>Новое межскладское перемещение</strong>
          <div class="shipment-fields">
            <div>
              <label for="transferDestination">Склад назначения</label>
              <select id="transferDestination"></select>
            </div>
            <div>
              <label for="transferVehicle">Автомобиль</label>
              <input id="transferVehicle" autocomplete="off" placeholder="Например, А000АА 77">
            </div>
          </div>
          <button id="createTransferBtn" class="primary-action" type="button">Создать перемещение</button>
        </div>

        <div id="taskCreate" class="shipment-create">
          <strong>Новое задание</strong>
          <div class="shipment-fields">
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
          <div>
            <label for="taskObjectUid">Код объекта</label>
            <input id="taskObjectUid" autocomplete="off" placeholder="Палета или документ">
          </div>
          <button id="createTaskBtn" class="primary-action" type="button">Добавить в очередь</button>
        </div>

        <div id="taskOverview" class="current-object">
          <div class="object-head">
            <div>
              <div class="object-kicker">Очередь склада</div>
              <div id="taskWarehouse" class="object-code">-</div>
            </div>
            <button id="toggleTaskCreateBtn" class="text-button" type="button">Новое задание</button>
          </div>
          <div class="facts">
            <div class="fact"><b>Всего</b><span id="taskTotal">0</span></div>
            <div class="fact"><b>Новые</b><span id="taskNew">0</span></div>
            <div class="fact"><b>В работе</b><span id="taskInProgress">0</span></div>
            <div class="fact"><b>Срочные</b><span id="taskUrgent">0</span></div>
          </div>
        </div>

        <div id="scanArea" class="scan-area">
          <label id="nextAction" class="next-action" for="workScan">Отсканируйте палету</label>
          <input id="workScan" class="scan-input" autocomplete="off" autofocus placeholder="Код палеты">
          <div id="scanHint" class="scan-hint">После сканирования нажмите Enter</div>
        </div>

        <div id="currentObject" class="current-object">
          <div class="object-head">
            <div>
              <div class="object-kicker">Текущая палета</div>
              <div id="palletCode" class="object-code">-</div>
            </div>
            <button id="clearPalletBtn" class="text-button" type="button">Сменить палету</button>
          </div>
          <div class="facts">
            <div class="fact"><b>Статус</b><span id="palletStatus">-</span></div>
            <div class="fact"><b>Коробок</b><span id="palletBoxCount">0</span></div>
            <div class="fact"><b>Партия</b><span id="palletBatch">-</span></div>
            <div class="fact"><b>Ячейка</b><span id="palletLocation">-</span></div>
          </div>
        </div>

        <div id="shipmentObject" class="current-object">
          <div class="object-head">
            <div>
              <div class="object-kicker">Текущая отгрузка</div>
              <div id="shipmentCode" class="object-code">-</div>
            </div>
            <button id="clearShipmentBtn" class="text-button" type="button">Сменить заявку</button>
          </div>
          <div class="facts">
            <div class="fact"><b>Статус</b><span id="shipmentStatus">-</span></div>
            <div class="fact"><b>Получатель</b><span id="shipmentCustomerFact">-</span></div>
            <div class="fact"><b>Направление</b><span id="shipmentDestinationFact">-</span></div>
            <div class="fact"><b>Погружено</b><span id="shipmentProgress">0 / 0</span></div>
          </div>
        </div>

        <div id="inventoryObject" class="current-object">
          <div class="object-head">
            <div>
              <div class="object-kicker">Текущая инвентаризация</div>
              <div id="inventoryCode" class="object-code">-</div>
            </div>
            <button id="clearInventoryBtn" class="text-button" type="button">Сменить обход</button>
          </div>
          <div class="facts">
            <div class="fact"><b>Статус</b><span id="inventoryStatus">-</span></div>
            <div class="fact"><b>Склад</b><span id="inventoryWarehouse">-</span></div>
            <div class="fact"><b>Проверено</b><span id="inventoryChecked">0 / 0</span></div>
            <div class="fact"><b>Расхождений</b><span id="inventoryProblemsCount">0</span></div>
          </div>
          <div class="progress-track" aria-label="Прогресс инвентаризации">
            <div id="inventoryProgressFill" class="progress-fill"></div>
          </div>
        </div>

        <div id="transferObject" class="current-object">
          <div class="object-head">
            <div>
              <div class="object-kicker">Текущее перемещение</div>
              <div id="transferCode" class="object-code">-</div>
            </div>
            <button id="clearTransferBtn" class="text-button" type="button">Сменить документ</button>
          </div>
          <div class="facts">
            <div class="fact"><b>Маршрут</b><span id="transferRoute">-</span></div>
            <div class="fact"><b>Статус</b><span id="transferStatus">-</span></div>
            <div class="fact"><b>Погружено</b><span id="transferLoaded">0 / 0</span></div>
            <div class="fact"><b>Принято</b><span id="transferReceived">0 / 0</span></div>
          </div>
        </div>

        <div id="inventoryProblems" class="problem-box">
          <div class="problem-head">
            <h2>Расхождения</h2>
            <span id="inventoryProblemBadge" class="queue-count">0</span>
          </div>
          <div id="inventoryProblemList" class="problem-list"></div>
        </div>

        <div id="completion" class="completion">
          <strong id="completionTitle">Операция завершена</strong>
          <div id="completionText"></div>
          <div id="completionCode" class="completion-code"></div>
        </div>

        <div class="action-row">
          <button id="newPalletBtn" class="primary-action" type="button">Открыть новую палету</button>
          <button id="closePalletBtn" class="primary-action" type="button" hidden>Завершить формирование</button>
          <button id="toPlacementBtn" class="primary-action" type="button" hidden>Перейти к размещению</button>
          <button id="nextPalletBtn" class="primary-action" type="button" hidden>Разместить следующую палету</button>
          <button id="toExpeditionBtn" class="primary-action" type="button" hidden>Передать в экспедицию</button>
          <button id="closeShipmentBtn" class="primary-action" type="button" hidden>Завершить отгрузку</button>
          <button id="newShipmentBtn" class="primary-action" type="button" hidden>Следующая отгрузка</button>
          <button id="emptyLocationBtn" class="secondary-action" type="button" hidden>Пусто</button>
          <button id="completeInventoryBtn" class="primary-action" type="button" hidden>Завершить инвентаризацию</button>
          <button id="newInventoryBtn" class="primary-action" type="button" hidden>Следующая инвентаризация</button>
          <button id="transferExpeditionBtn" class="primary-action" type="button" hidden>Передать в экспедицию</button>
          <button id="dispatchTransferBtn" class="primary-action" type="button" hidden>Отправить в путь</button>
          <button id="placeTransferBtn" class="primary-action" type="button" hidden>Разместить принятые палеты</button>
          <button id="newTransferBtn" class="primary-action" type="button" hidden>Следующее перемещение</button>
        </div>
      </div>

      <div class="queue-section">
        <div class="queue-head">
          <div>
            <h2 id="queueTitle">Открытые палеты</h2>
            <div id="queueSubtitle" class="queue-subtitle">Можно продолжить ранее начатую работу</div>
          </div>
          <button id="refreshQueueBtn" class="text-button" type="button">Обновить</button>
        </div>
        <div id="queueList" class="queue-list"></div>
      </div>
    </section>
  </main>

  <script>
    const $ = (id) => document.getElementById(id);
    const requestedOperation = new URLSearchParams(window.location.search).get("operation");
    const state = {
      operation: ["tasks", "build", "place", "move", "ship", "inventory", "transfer"].includes(requestedOperation) ? requestedOperation : "tasks",
      activePalletUid: localStorage.getItem("wms.work.activePalletUid") || "",
      pallet: null,
      boxes: [],
      warehouses: [],
      locations: [],
      batches: [],
      openPallets: [],
      waitingPallets: [],
      availablePallets: [],
      shipments: [],
      activeShipmentUid: localStorage.getItem("wms.work.activeShipmentUid") || "",
      shipment: null,
      shipmentPallets: [],
      inventories: [],
      activeInventoryUid: localStorage.getItem("wms.work.activeInventoryUid") || "",
      inventory: null,
      inventoryProgress: null,
      inventoryLines: [],
      transfers: [],
      activeTransferUid: localStorage.getItem("wms.work.activeTransferUid") || "",
      transfer: null,
      transferPallets: [],
      tasks: [],
      taskCreateVisible: false,
      warehouseCode: localStorage.getItem("wms.work.warehouse") || "",
      completedPlacement: null,
      completedMove: null,
      prefixes: { pallet: "PLT-", box: "BOX-" },
    };

    const statusLabels = {
      open: "Открыта",
      waiting_placement: "Ожидает размещения",
      available: "Размещена",
      reserved: "В резерве",
      expedition: "В экспедиции",
      loaded: "Погружена",
      shipped: "Отгружена",
      blocked: "Заблокирована",
      quarantine: "Карантин",
    };

    const shipmentStatusLabels = {
      draft: "Черновик",
      reserved: "Палеты зарезервированы",
      expedition: "В экспедиции",
      loading: "Идёт погрузка",
      completed: "Завершена",
      cancelled: "Отменена",
    };

    const shipmentPalletStatusLabels = {
      reserved: "В резерве",
      expedition: "Ожидает погрузки",
      loaded: "Погружена",
    };

    const inventoryStatusLabels = {
      open: "Открыта",
      completed: "Завершена",
    };

    const inventoryLineStatusLabels = {
      expected: "Ожидается",
      scanned: "Совпадение",
      missing: "Палета отсутствует",
      extra: "Лишняя палета",
      wrong_location: "Чужая ячейка",
    };

    const transferStatusLabels = {
      draft: "Черновик",
      reserved: "Палеты зарезервированы",
      expedition: "В экспедиции",
      loading: "Идёт погрузка",
      in_transit: "В пути",
      receiving: "Идёт приёмка",
      completed: "Завершено",
      cancelled: "Отменено",
    };

    const transferPalletStatusLabels = {
      reserved: "В резерве",
      expedition: "Ожидает погрузки",
      loaded: "Погружена",
      in_transit: "В пути",
      received: "Принята",
    };

    const taskTypeLabels = {
      build: "Формирование палеты",
      place: "Размещение палеты",
      move: "Перемещение палеты",
      ship: "Отгрузка",
      inventory: "Инвентаризация",
      transfer: "Между складами",
    };

    const taskStatusLabels = {
      new: "Новое",
      in_progress: "В работе",
      completed: "Выполнено",
      cancelled: "Отменено",
    };

    const taskPriorityLabels = {
      low: "Низкий",
      normal: "Обычный",
      high: "Высокий",
      urgent: "Срочный",
    };

    function escapeHtml(value) {
      return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }

    function actor() {
      return $("workActor").value.trim() || "Кладовщик";
    }

    function focusScan() {
      if (!$("workScan").disabled) setTimeout(() => $("workScan").focus(), 30);
    }

    function humanError(message) {
      const text = String(message || "Не удалось выполнить операцию");
      const mappings = [
        ["pallet not found", "Палета не найдена"],
        ["box not found", "Коробка не найдена"],
        ["location not found", "Ячейка не найдена"],
        ["box already belongs to a pallet", "Коробка уже находится на палете"],
        ["different batch", "На палете уже находится другая партия"],
        ["different product", "На палете уже находится другой товар"],
        ["location is occupied", "Ячейка занята"],
        ["location capacity is already reached", "Ячейка занята"],
        ["cannot be accepted", "Коробка уже была принята"],
        ["must be closed", "Сначала завершите формирование палеты"],
        ["already in this location", "Палета уже находится в этой ячейке"],
        ["between warehouses without a transfer", "Для перемещения между складами нужен документ"],
        ["shipment not found", "Заявка на отгрузку не найдена"],
        ["shipment cannot accept pallets", "В эту заявку больше нельзя добавлять палеты"],
        ["only available pallet can be reserved", "Палета недоступна для резервирования"],
        ["pallet already belongs to a shipment", "Палета уже включена в другую отгрузку"],
        ["shipment pallets must belong to one warehouse", "Все палеты заявки должны находиться на одном складе"],
        ["only reserved shipment can be moved to expedition", "Сначала добавьте палеты в заявку"],
        ["shipment has no reserved pallets", "В заявке нет палет"],
        ["shipment must be in expedition or loading status", "Сначала передайте заявку в экспедицию"],
        ["pallet does not belong to this shipment", "Палета не входит в выбранную заявку"],
        ["pallet already loaded", "Палета уже погружена"],
        ["all shipment pallets must be loaded before close", "Сначала погрузите все палеты заявки"],
        ["inventory not found", "Инвентаризация не найдена"],
        ["warehouse already has open inventory", "На складе уже идёт инвентаризация"],
        ["inventory is already completed", "Инвентаризация уже завершена"],
        ["scan location first", "Сначала отсканируйте ячейку"],
        ["location belongs to another warehouse", "Ячейка относится к другому складу"],
        ["only storage locations are included", "В обход входят только ячейки хранения"],
        ["pallet already scanned in this inventory", "Палета уже проверена в этой инвентаризации"],
        ["inventory has unchecked locations", "Сначала проверьте все ячейки склада"],
        ["inventory discrepancy is already resolved", "Расхождение уже обработано"],
        ["inventory discrepancy line not found", "Расхождение не найдено"],
        ["transfer not found", "Перемещение не найдено"],
        ["source and destination warehouses must be different", "Склад назначения должен отличаться от склада отправления"],
        ["transfer cannot accept pallets", "В этот документ больше нельзя добавлять палеты"],
        ["pallet is not located at the source warehouse", "Палета находится не на складе отправления"],
        ["pallet already belongs to an active transfer", "Палета уже включена в другое перемещение"],
        ["pallet already belongs to this transfer", "Палета уже включена в это перемещение"],
        ["only reserved transfer can be moved to expedition", "Сначала добавьте палеты в документ"],
        ["transfer has no reserved pallets", "В перемещении нет палет"],
        ["transfer must be in expedition or loading status", "Сначала передайте палеты в экспедицию"],
        ["pallet does not belong to this transfer", "Палета не входит в выбранное перемещение"],
        ["all transfer pallets must be loaded before dispatch", "Сначала погрузите все палеты"],
        ["transfer must be in transit or receiving status", "Перемещение ещё не отправлено"],
        ["pallet was not sent in this transfer", "Палета не отправлялась по этому документу"],
        ["pallet already received", "Палета уже принята"],
        ["task not found", "Задание не найдено"],
        ["task cannot be started", "Это задание уже закрыто"],
        ["task is assigned to another operator", "Задание назначено другому сотруднику"],
        ["cancelled task cannot be completed", "Отменённое задание нельзя завершить"],
      ];
      const found = mappings.find(([needle]) => text.toLowerCase().includes(needle));
      return found ? found[1] : text;
    }

    async function api(path, options = {}) {
      const response = await fetch(path, {
        headers: { "Content-Type": "application/json" },
        ...options,
      });
      const text = await response.text();
      let data = null;
      try { data = text ? JSON.parse(text) : null; } catch (_) { data = text; }
      if (!response.ok) throw new Error(humanError(data?.detail || response.statusText));
      return data;
    }

    function post(path, body = {}) {
      return api(path, { method: "POST", body: JSON.stringify(body) });
    }

    function setNotice(message, kind = "") {
      $("notice").className = `notice ${kind}`;
      $("notice").textContent = message;
    }

    function setSteps(activeStep, completedSteps = []) {
      document.querySelectorAll(".step").forEach((step) => {
        const number = Number(step.dataset.step);
        step.classList.toggle("active", number === activeStep);
        step.classList.toggle("done", completedSteps.includes(number));
      });
    }

    function setStepCount(count) {
      const steps = document.querySelector(".steps");
      steps.classList.toggle("four", count === 4);
      document.querySelector('[data-step="4"]').hidden = count !== 4;
    }

    function batchLabel(batchId) {
      const batch = state.batches.find((item) => item.id === batchId);
      return batch?.batch_number || "-";
    }

    function locationCode(locationId) {
      const location = state.locations.find((item) => item.id === locationId);
      return location?.code || "-";
    }

    function selectedWarehouse() {
      return state.warehouses.find((item) => item.code === state.warehouseCode);
    }

    function storageLocations() {
      const warehouse = selectedWarehouse();
      if (!warehouse) return [];
      return state.locations.filter(
        (item) => item.warehouse_id === warehouse.id && item.kind === "storage" && item.is_active,
      );
    }

    function palletBelongsToSelectedWarehouse(pallet) {
      const warehouse = selectedWarehouse();
      const location = state.locations.find((item) => item.id === pallet?.current_location_id);
      return Boolean(warehouse && location && location.warehouse_id === warehouse.id);
    }

    function warehouseCodeForPallet(pallet) {
      const location = state.locations.find((item) => item.id === pallet?.current_location_id);
      const warehouse = state.warehouses.find((item) => item.id === location?.warehouse_id);
      return warehouse?.code || "";
    }

    function activeShipmentWarehouseCode() {
      const firstPallet = state.shipmentPallets[0]?.pallet;
      return warehouseCodeForPallet(firstPallet);
    }

    function openInventoriesForSelectedWarehouse() {
      return state.inventories.filter(
        (inventory) => inventory.status === "open" && inventory.warehouse_code === state.warehouseCode,
      );
    }

    function transfersForSelectedWarehouse() {
      return state.transfers.filter((transfer) =>
        transfer.source_warehouse_code === state.warehouseCode
        || transfer.destination_warehouse_code === state.warehouseCode,
      );
    }

    function persistActivePallet(uid) {
      state.activePalletUid = uid || "";
      if (state.activePalletUid) localStorage.setItem("wms.work.activePalletUid", state.activePalletUid);
      else localStorage.removeItem("wms.work.activePalletUid");
    }

    function persistActiveShipment(uid) {
      state.activeShipmentUid = uid || "";
      if (state.activeShipmentUid) localStorage.setItem("wms.work.activeShipmentUid", state.activeShipmentUid);
      else localStorage.removeItem("wms.work.activeShipmentUid");
    }

    function persistActiveInventory(uid) {
      state.activeInventoryUid = uid || "";
      if (state.activeInventoryUid) localStorage.setItem("wms.work.activeInventoryUid", state.activeInventoryUid);
      else localStorage.removeItem("wms.work.activeInventoryUid");
    }

    function persistActiveTransfer(uid) {
      state.activeTransferUid = uid || "";
      if (state.activeTransferUid) localStorage.setItem("wms.work.activeTransferUid", state.activeTransferUid);
      else localStorage.removeItem("wms.work.activeTransferUid");
    }

    function clearCompletion() {
      state.completedPlacement = null;
      state.completedMove = null;
      $("completion").classList.remove("visible");
    }

    async function clearActivePallet(message = "Выбор палеты сброшен") {
      persistActivePallet("");
      state.pallet = null;
      state.boxes = [];
      clearCompletion();
      render();
      setNotice(message, "warn");
      focusScan();
    }

    async function clearActiveShipment(message = "Выбор заявки сброшен") {
      persistActiveShipment("");
      state.shipment = null;
      state.shipmentPallets = [];
      clearCompletion();
      render();
      setNotice(message, "warn");
    }

    async function clearActiveInventory(message = "Выбор инвентаризации сброшен") {
      persistActiveInventory("");
      state.inventory = null;
      state.inventoryProgress = null;
      state.inventoryLines = [];
      clearCompletion();
      render();
      setNotice(message, "warn");
    }

    async function clearActiveTransfer(message = "Выбор перемещения сброшен") {
      persistActiveTransfer("");
      state.transfer = null;
      state.transferPallets = [];
      clearCompletion();
      render();
      setNotice(message, "warn");
    }

    async function loadActivePallet() {
      if (!state.activePalletUid) {
        state.pallet = null;
        state.boxes = [];
        return;
      }
      try {
        const [pallet, boxes] = await Promise.all([
          api(`/api/pallets/${encodeURIComponent(state.activePalletUid)}`),
          api(`/api/pallets/${encodeURIComponent(state.activePalletUid)}/boxes`),
        ]);
        state.pallet = pallet;
        state.boxes = boxes;
      } catch (error) {
        persistActivePallet("");
        state.pallet = null;
        state.boxes = [];
        setNotice(error.message, "err");
      }
    }

    async function loadActiveShipment() {
      if (!state.activeShipmentUid) {
        state.shipment = null;
        state.shipmentPallets = [];
        return;
      }
      try {
        const [shipment, pallets] = await Promise.all([
          api(`/api/shipments/${encodeURIComponent(state.activeShipmentUid)}`),
          api(`/api/shipments/${encodeURIComponent(state.activeShipmentUid)}/pallets`),
        ]);
        state.shipment = shipment;
        state.shipmentPallets = pallets;
      } catch (error) {
        persistActiveShipment("");
        state.shipment = null;
        state.shipmentPallets = [];
        setNotice(error.message, "err");
      }
    }

    async function loadActiveInventory() {
      if (!state.activeInventoryUid) {
        state.inventory = null;
        state.inventoryProgress = null;
        state.inventoryLines = [];
        return;
      }
      try {
        const [inventory, progress, lines] = await Promise.all([
          api(`/api/inventories/${encodeURIComponent(state.activeInventoryUid)}`),
          api(`/api/inventories/${encodeURIComponent(state.activeInventoryUid)}/progress`),
          api(`/api/inventories/${encodeURIComponent(state.activeInventoryUid)}/lines`),
        ]);
        state.inventory = inventory;
        state.inventoryProgress = progress;
        state.inventoryLines = lines;
      } catch (error) {
        persistActiveInventory("");
        state.inventory = null;
        state.inventoryProgress = null;
        state.inventoryLines = [];
        setNotice(error.message, "err");
      }
    }

    async function loadActiveTransfer() {
      if (!state.activeTransferUid) {
        state.transfer = null;
        state.transferPallets = [];
        return;
      }
      try {
        const [transfer, pallets] = await Promise.all([
          api(`/api/transfers/${encodeURIComponent(state.activeTransferUid)}`),
          api(`/api/transfers/${encodeURIComponent(state.activeTransferUid)}/pallets`),
        ]);
        state.transfer = transfer;
        state.transferPallets = pallets;
      } catch (error) {
        persistActiveTransfer("");
        state.transfer = null;
        state.transferPallets = [];
        setNotice(error.message, "err");
      }
    }

    async function refreshQueues() {
      const [rows, availableRows, shipments, inventories, transfers, tasks] = await Promise.all([
        api("/api/pallets?status=open&status=waiting_placement&limit=200"),
        api(`/api/pallets?status=available&warehouse_code=${encodeURIComponent(state.warehouseCode)}&limit=200`),
        api("/api/shipments?status=draft&status=reserved&status=expedition&status=loading&limit=100"),
        api("/api/inventories?limit=100"),
        api("/api/transfers?status=draft&status=reserved&status=expedition&status=loading&status=in_transit&status=receiving&limit=100"),
        post("/api/tasks/sync", { warehouse_code: state.warehouseCode, actor: actor() }),
      ]);
      state.openPallets = rows.filter((item) => item.status === "open");
      state.waitingPallets = rows.filter((item) => item.status === "waiting_placement");
      state.availablePallets = availableRows;
      state.shipments = shipments;
      state.inventories = inventories;
      state.transfers = transfers;
      state.tasks = tasks.filter((task) => !task.assigned_to || task.assigned_to === actor());
      $("openCount").textContent = state.openPallets.length;
      $("waitingCount").textContent = state.waitingPallets.length;
      $("availableCount").textContent = state.availablePallets.length;
      $("shipmentCount").textContent = state.shipments.length;
      $("inventoryCount").textContent = openInventoriesForSelectedWarehouse().length;
      $("transferCount").textContent = transfersForSelectedWarehouse().length;
      $("taskCount").textContent = state.tasks.length;
      renderQueue();
    }

    async function refreshWorkplace() {
      await Promise.all([loadActivePallet(), loadActiveShipment(), loadActiveInventory(), loadActiveTransfer()]);
      await refreshQueues();
      render();
    }

    function renderCurrentPallet() {
      const visible = Boolean(state.pallet) && ["build", "place", "move"].includes(state.operation);
      $("currentObject").classList.toggle("visible", visible);
      if (!visible) return;
      $("palletCode").textContent = state.pallet.pallet_uid;
      $("palletStatus").textContent = statusLabels[state.pallet.status] || state.pallet.status;
      $("palletBoxCount").textContent = state.boxes.length;
      $("palletBatch").textContent = batchLabel(state.pallet.batch_id);
      $("palletLocation").textContent = locationCode(state.pallet.current_location_id);
    }

    function renderCurrentShipment() {
      const visible = state.operation === "ship" && Boolean(state.shipment);
      $("shipmentObject").classList.toggle("visible", visible);
      if (!visible) return;
      $("shipmentCode").textContent = state.shipment.shipment_uid;
      $("shipmentStatus").textContent = shipmentStatusLabels[state.shipment.status] || state.shipment.status;
      $("shipmentCustomerFact").textContent = state.shipment.customer_name;
      $("shipmentDestinationFact").textContent = state.shipment.destination;
      $("shipmentProgress").textContent = `${state.shipment.loaded_count} / ${state.shipment.pallet_count}`;
    }

    function renderCurrentInventory() {
      const visible = state.operation === "inventory" && Boolean(state.inventory);
      $("inventoryObject").classList.toggle("visible", visible);
      if (!visible) return;
      const progress = state.inventoryProgress;
      $("inventoryCode").textContent = state.inventory.inventory_uid;
      $("inventoryStatus").textContent = inventoryStatusLabels[state.inventory.status] || state.inventory.status;
      $("inventoryWarehouse").textContent = state.inventory.warehouse_code || "-";
      $("inventoryChecked").textContent = progress ? `${progress.checked_locations} / ${progress.total_locations}` : "0 / 0";
      $("inventoryProblemsCount").textContent = progress?.problem_lines.length || 0;
      $("inventoryProgressFill").style.width = `${progress?.progress_percent || 0}%`;
    }

    function renderCurrentTransfer() {
      const visible = state.operation === "transfer" && Boolean(state.transfer);
      $("transferObject").classList.toggle("visible", visible);
      if (!visible) return;
      $("transferCode").textContent = state.transfer.transfer_uid;
      $("transferRoute").textContent = `${state.transfer.source_warehouse_code} → ${state.transfer.destination_warehouse_code}`;
      $("transferStatus").textContent = transferStatusLabels[state.transfer.status] || state.transfer.status;
      $("transferLoaded").textContent = `${state.transfer.loaded_count} / ${state.transfer.pallet_count}`;
      $("transferReceived").textContent = `${state.transfer.received_count} / ${state.transfer.pallet_count}`;
    }

    function renderTaskOverview() {
      const visible = state.operation === "tasks";
      $("taskOverview").classList.toggle("visible", visible);
      if (!visible) return;
      $("taskWarehouse").textContent = state.warehouseCode || "-";
      $("taskTotal").textContent = state.tasks.length;
      $("taskNew").textContent = state.tasks.filter((task) => task.status === "new").length;
      $("taskInProgress").textContent = state.tasks.filter((task) => task.status === "in_progress").length;
      $("taskUrgent").textContent = state.tasks.filter((task) => task.priority === "urgent").length;
    }

    function inventoryResolution(status) {
      if (status === "missing") return { endpoint: "confirm-missing", label: "Подтвердить недостачу" };
      if (status === "extra") return { endpoint: "place-found", label: "Разместить по факту" };
      if (status === "wrong_location") return { endpoint: "move-to-actual", label: "Переместить по факту" };
      return null;
    }

    function renderInventoryProblems() {
      const problems = state.operation === "inventory" ? state.inventoryProgress?.problem_lines || [] : [];
      $("inventoryProblems").classList.toggle("visible", problems.length > 0);
      $("inventoryProblemBadge").textContent = problems.length;
      $("inventoryProblemList").innerHTML = problems.map((line) => {
        const action = inventoryResolution(line.status);
        return `
          <div class="problem-row">
            <div>
              <div class="queue-code">${escapeHtml(line.pallet.pallet_uid)}</div>
              <div class="problem-status">${escapeHtml(inventoryLineStatusLabels[line.status] || line.status)}</div>
              <div class="queue-meta">Ожидалась: ${escapeHtml(line.expected_location_code || "-")} · Факт: ${escapeHtml(line.actual_location_code || "-")}</div>
            </div>
            ${action ? `<button class="text-button" type="button" data-resolve-inventory="${escapeHtml(line.pallet.pallet_uid)}" data-inventory-status="${escapeHtml(line.status)}">${escapeHtml(action.label)}</button>` : ""}
          </div>`;
      }).join("");
      document.querySelectorAll("[data-resolve-inventory]").forEach((button) => {
        button.addEventListener("click", () => resolveInventoryProblem(
          button.dataset.resolveInventory,
          button.dataset.inventoryStatus,
        ).catch(showError));
      });
    }

    function renderQueue() {
      if (state.operation === "tasks") {
        return renderTaskQueue();
      }
      if (state.operation === "inventory") {
        return renderInventoryQueue();
      }
      if (state.operation === "transfer") {
        return renderTransferQueue();
      }
      if (state.operation === "ship") {
        return renderShipmentQueue();
      }
      const queueConfig = state.operation === "build"
        ? {
            rows: state.openPallets,
            title: "Открытые палеты",
            subtitle: "Можно продолжить ранее начатую работу",
            empty: "Открытых палет нет",
          }
        : state.operation === "place"
          ? {
              rows: state.waitingPallets,
              title: "Ожидают размещения",
              subtitle: "Выберите палету или отсканируйте её код",
              empty: "Все палеты размещены",
            }
          : {
              rows: state.availablePallets,
              title: `Палеты на складе ${state.warehouseCode}`,
              subtitle: "Выберите палету или отсканируйте её код",
              empty: "На складе нет доступных палет",
            };
      const rows = queueConfig.rows;
      $("queueTitle").textContent = queueConfig.title;
      $("queueSubtitle").textContent = queueConfig.subtitle;
      $("queueList").innerHTML = rows.map((pallet) => `
        <div class="queue-row">
          <div>
            <div class="queue-code">${escapeHtml(pallet.pallet_uid)}</div>
            <div class="queue-meta">${pallet.box_count} кор. · ${escapeHtml(batchLabel(pallet.batch_id))}${state.operation === "move" ? ` · ${escapeHtml(pallet.current_location_code || "-")}` : ""}</div>
          </div>
          <button class="text-button" type="button" data-pallet="${escapeHtml(pallet.pallet_uid)}">Выбрать</button>
        </div>
      `).join("") || `<div class="empty-row">${queueConfig.empty}</div>`;
      document.querySelectorAll("[data-pallet]").forEach((button) => {
        button.addEventListener("click", () => selectPallet(button.dataset.pallet).catch(showError));
      });
    }

    function renderInventoryQueue() {
      if (!state.inventory || state.inventory.status === "completed") {
        const openRows = openInventoriesForSelectedWarehouse();
        $("queueTitle").textContent = `Инвентаризации склада ${state.warehouseCode}`;
        $("queueSubtitle").textContent = "Продолжите открытый обход или начните новый";
        $("queueList").innerHTML = openRows.map((inventory) => `
          <div class="queue-row">
            <div>
              <div class="queue-code">${escapeHtml(inventory.inventory_uid)}</div>
              <div class="queue-meta">Проверено палет: ${inventory.scanned_count} · Расхождений: ${inventory.missing_count + inventory.extra_count + inventory.wrong_location_count}</div>
            </div>
            <button class="text-button" type="button" data-inventory="${escapeHtml(inventory.inventory_uid)}">Продолжить</button>
          </div>
        `).join("") || '<div class="empty-row">Открытых инвентаризаций нет</div>';
        document.querySelectorAll("[data-inventory]").forEach((button) => {
          button.addEventListener("click", () => selectInventory(button.dataset.inventory).catch(showError));
        });
        return;
      }

      const progress = state.inventoryProgress;
      const locations = progress?.unchecked_locations_list || [];
      const pallets = progress?.unchecked_pallets || [];
      $("queueTitle").textContent = "Осталось проверить";
      $("queueSubtitle").textContent = `${locations.length} яч. · ${pallets.length} пал.`;
      const locationRows = locations.map((location) => `
        <div class="queue-row">
          <div>
            <div class="queue-code">${escapeHtml(location.location_code)}</div>
            <div class="queue-meta">Ожидается палет: ${location.expected_count}</div>
          </div>
          <button class="text-button" type="button" data-inventory-location="${escapeHtml(location.location_code)}">Выбрать</button>
        </div>
      `).join("") || '<div class="empty-row">Все ячейки проверены</div>';
      const palletRows = pallets.length
        ? `<div class="queue-divider">Непроверенные палеты</div>${pallets.map((pallet) => `
            <div class="queue-row">
              <div>
                <div class="queue-code">${escapeHtml(pallet.pallet_uid)}</div>
                <div class="queue-meta">${escapeHtml(pallet.current_location_code || "-")} · ${pallet.box_count} кор.</div>
              </div>
            </div>
          `).join("")}`
        : "";
      $("queueList").innerHTML = locationRows + palletRows;
      document.querySelectorAll("[data-inventory-location]").forEach((button) => {
        button.addEventListener("click", () => scanInventoryLocation(button.dataset.inventoryLocation).catch(showError));
      });
    }

    function renderTaskQueue() {
      $("queueTitle").textContent = `Задания склада ${state.warehouseCode}`;
      $("queueSubtitle").textContent = "Сначала задания в работе, затем новые по приоритету";
      $("queueList").innerHTML = state.tasks.map((task) => `
        <div class="queue-row">
          <div>
            <div class="queue-code">${escapeHtml(task.title)}</div>
            <div class="queue-meta">${escapeHtml(taskTypeLabels[task.task_type] || task.task_type)} · ${escapeHtml(task.object_uid || "Без объекта")} · ${escapeHtml(taskStatusLabels[task.status] || task.status)}${task.assigned_to ? ` · ${escapeHtml(task.assigned_to)}` : ""}</div>
          </div>
          <div class="task-actions">
            <span class="task-priority ${escapeHtml(task.priority)}">${escapeHtml(taskPriorityLabels[task.priority] || task.priority)}</span>
            <button class="text-button" type="button" data-start-task="${escapeHtml(task.task_uid)}">${task.status === "in_progress" ? "Продолжить" : "Начать"}</button>
            ${task.status === "in_progress" ? `<button class="text-button" type="button" data-complete-task="${escapeHtml(task.task_uid)}">Выполнено</button>` : ""}
          </div>
        </div>
      `).join("") || '<div class="empty-row">Очередь пуста</div>';
      document.querySelectorAll("[data-start-task]").forEach((button) => {
        button.addEventListener("click", () => beginTask(button.dataset.startTask).catch(showError));
      });
      document.querySelectorAll("[data-complete-task]").forEach((button) => {
        button.addEventListener("click", () => finishTask(button.dataset.completeTask).catch(showError));
      });
    }

    function renderShipmentQueue() {
      if (!state.shipment || state.shipment.status === "completed") {
        $("queueTitle").textContent = "Отгрузки в работе";
        $("queueSubtitle").textContent = "Продолжите существующую заявку или создайте новую";
        $("queueList").innerHTML = state.shipments.map((shipment) => `
          <div class="queue-row">
            <div>
              <div class="queue-code">${escapeHtml(shipment.shipment_uid)}</div>
              <div class="queue-meta">${escapeHtml(shipment.customer_name)} · ${escapeHtml(shipmentStatusLabels[shipment.status] || shipment.status)} · ${shipment.loaded_count}/${shipment.pallet_count}</div>
            </div>
            <button class="text-button" type="button" data-shipment="${escapeHtml(shipment.shipment_uid)}">Продолжить</button>
          </div>
        `).join("") || '<div class="empty-row">Незавершённых отгрузок нет</div>';
        document.querySelectorAll("[data-shipment]").forEach((button) => {
          button.addEventListener("click", () => selectShipment(button.dataset.shipment).catch(showError));
        });
        return;
      }

      if (["draft", "reserved"].includes(state.shipment.status)) {
        $("queueTitle").textContent = `Доступные палеты склада ${state.warehouseCode}`;
        $("queueSubtitle").textContent = "Добавляйте палеты сканером или кнопкой";
        $("queueList").innerHTML = state.availablePallets.map((pallet) => `
          <div class="queue-row">
            <div>
              <div class="queue-code">${escapeHtml(pallet.pallet_uid)}</div>
              <div class="queue-meta">${pallet.box_count} кор. · ${escapeHtml(batchLabel(pallet.batch_id))} · ${escapeHtml(pallet.current_location_code || "-")}</div>
            </div>
            <button class="text-button" type="button" data-reserve-pallet="${escapeHtml(pallet.pallet_uid)}">В заявку</button>
          </div>
        `).join("") || '<div class="empty-row">На складе нет доступных палет</div>';
        document.querySelectorAll("[data-reserve-pallet]").forEach((button) => {
          button.addEventListener("click", () => reserveShipmentPallet(button.dataset.reservePallet).catch(showError));
        });
        return;
      }

      $("queueTitle").textContent = "Палеты заявки";
      $("queueSubtitle").textContent = "Погрузка подтверждается сканированием каждой палеты";
      $("queueList").innerHTML = state.shipmentPallets.map((row) => {
        const pallet = row.pallet;
        const canLoad = row.shipment_pallet_status === "expedition";
        return `
          <div class="queue-row">
            <div>
              <div class="queue-code">${escapeHtml(pallet.pallet_uid)}</div>
              <div class="queue-meta">${pallet.box_count} кор. · ${escapeHtml(shipmentPalletStatusLabels[row.shipment_pallet_status] || row.shipment_pallet_status)}</div>
            </div>
            ${canLoad ? `<button class="text-button" type="button" data-load-pallet="${escapeHtml(pallet.pallet_uid)}">Погрузить</button>` : '<span class="queue-count">Готово</span>'}
          </div>`;
      }).join("") || '<div class="empty-row">В заявке нет палет</div>';
      document.querySelectorAll("[data-load-pallet]").forEach((button) => {
        button.addEventListener("click", () => loadShipmentPallet(button.dataset.loadPallet).catch(showError));
      });
    }

    function renderTransferQueue() {
      if (!state.transfer || state.transfer.status === "completed") {
        const rows = transfersForSelectedWarehouse();
        $("queueTitle").textContent = "Межскладские перемещения в работе";
        $("queueSubtitle").textContent = "Продолжите документ отправления или приёмки";
        $("queueList").innerHTML = rows.map((transfer) => `
          <div class="queue-row">
            <div>
              <div class="queue-code">${escapeHtml(transfer.transfer_uid)}</div>
              <div class="queue-meta">${escapeHtml(transfer.source_warehouse_code)} → ${escapeHtml(transfer.destination_warehouse_code)} · ${escapeHtml(transferStatusLabels[transfer.status] || transfer.status)} · ${transfer.pallet_count} пал.</div>
            </div>
            <button class="text-button" type="button" data-transfer="${escapeHtml(transfer.transfer_uid)}">Продолжить</button>
          </div>
        `).join("") || '<div class="empty-row">Незавершённых перемещений нет</div>';
        document.querySelectorAll("[data-transfer]").forEach((button) => {
          button.addEventListener("click", () => selectTransfer(button.dataset.transfer).catch(showError));
        });
        return;
      }

      if (["draft", "reserved"].includes(state.transfer.status)) {
        $("queueTitle").textContent = `Доступные палеты склада ${state.transfer.source_warehouse_code}`;
        $("queueSubtitle").textContent = "Добавляйте палеты сканером или кнопкой";
        $("queueList").innerHTML = state.availablePallets.map((pallet) => `
          <div class="queue-row">
            <div>
              <div class="queue-code">${escapeHtml(pallet.pallet_uid)}</div>
              <div class="queue-meta">${pallet.box_count} кор. · ${escapeHtml(batchLabel(pallet.batch_id))} · ${escapeHtml(pallet.current_location_code || "-")}</div>
            </div>
            <button class="text-button" type="button" data-reserve-transfer-pallet="${escapeHtml(pallet.pallet_uid)}">В документ</button>
          </div>
        `).join("") || '<div class="empty-row">На складе отправления нет доступных палет</div>';
        document.querySelectorAll("[data-reserve-transfer-pallet]").forEach((button) => {
          button.addEventListener("click", () => reserveTransferPallet(button.dataset.reserveTransferPallet).catch(showError));
        });
        return;
      }

      const receiving = ["in_transit", "receiving"].includes(state.transfer.status);
      $("queueTitle").textContent = receiving ? "Палеты к приёмке" : "Палеты перемещения";
      $("queueSubtitle").textContent = receiving
        ? "Подтвердите приёмку сканированием каждой палеты"
        : "Погрузка подтверждается сканированием каждой палеты";
      $("queueList").innerHTML = state.transferPallets.map((row) => {
        const canLoad = ["expedition", "loading"].includes(state.transfer.status)
          && row.transfer_pallet_status === "expedition";
        const canReceive = receiving && row.transfer_pallet_status === "in_transit";
        return `
          <div class="queue-row">
            <div>
              <div class="queue-code">${escapeHtml(row.pallet.pallet_uid)}</div>
              <div class="queue-meta">${row.pallet.box_count} кор. · ${escapeHtml(transferPalletStatusLabels[row.transfer_pallet_status] || row.transfer_pallet_status)}</div>
            </div>
            ${canLoad ? `<button class="text-button" type="button" data-load-transfer-pallet="${escapeHtml(row.pallet.pallet_uid)}">Погрузить</button>` : ""}
            ${canReceive ? `<button class="text-button" type="button" data-receive-transfer-pallet="${escapeHtml(row.pallet.pallet_uid)}">Принять</button>` : ""}
            ${!canLoad && !canReceive ? '<span class="queue-count">Готово</span>' : ""}
          </div>`;
      }).join("") || '<div class="empty-row">В документе нет палет</div>';
      document.querySelectorAll("[data-load-transfer-pallet]").forEach((button) => {
        button.addEventListener("click", () => loadTransferPallet(button.dataset.loadTransferPallet).catch(showError));
      });
      document.querySelectorAll("[data-receive-transfer-pallet]").forEach((button) => {
        button.addEventListener("click", () => receiveTransferPallet(button.dataset.receiveTransferPallet).catch(showError));
      });
    }

    function showCompletion(title, text, code) {
      $("completionTitle").textContent = title;
      $("completionText").textContent = text;
      $("completionCode").textContent = code;
      $("completion").classList.add("visible");
    }

    function renderBuild() {
      setStepCount(3);
      $("operationTitle").textContent = "Формирование палеты";
      $("operationDescription").textContent = "Соберите коробки на палету и завершите формирование.";
      $("stepOneLabel").textContent = "Палета";
      $("stepTwoLabel").textContent = "Коробки";
      $("stepThreeLabel").textContent = "Завершение";
      $("nextPalletBtn").hidden = true;
      $("toPlacementBtn").hidden = true;
      $("newPalletBtn").hidden = Boolean(state.pallet);
      $("closePalletBtn").hidden = true;
      $("scanArea").hidden = false;
      $("workScan").disabled = false;
      clearCompletion();

      if (!state.pallet) {
        setSteps(1);
        $("nextAction").textContent = "Отсканируйте палету или откройте новую";
        $("workScan").placeholder = "Код палеты";
        $("scanHint").textContent = "Для продолжения можно выбрать палету из списка ниже";
        return;
      }

      if (state.pallet.status === "open") {
        setSteps(2, [1]);
        $("nextAction").textContent = "Сканируйте коробки";
        $("workScan").placeholder = "Код коробки";
        $("scanHint").textContent = state.boxes.length
          ? `На палете ${state.boxes.length} кор. После последней коробки завершите формирование.`
          : "Первая коробка задаст товар и партию палеты";
        $("closePalletBtn").hidden = state.boxes.length === 0;
        return;
      }

      if (state.pallet.status === "waiting_placement") {
        setSteps(3, [1, 2]);
        $("scanArea").hidden = true;
        $("toPlacementBtn").hidden = false;
        showCompletion(
          "Формирование завершено",
          `Палета содержит ${state.boxes.length} кор. и готова к размещению.`,
          state.pallet.pallet_uid,
        );
        return;
      }

      setSteps(1);
      $("newPalletBtn").hidden = false;
      $("scanArea").hidden = true;
      setNotice("Эта палета недоступна для формирования. Выберите открытую палету.", "warn");
    }

    function renderPlace() {
      setStepCount(3);
      $("operationTitle").textContent = "Размещение палеты";
      $("operationDescription").textContent = `Разместите закрытую палету на складе ${state.warehouseCode || "-"}.`;
      $("stepOneLabel").textContent = "Палета";
      $("stepTwoLabel").textContent = "Ячейка";
      $("stepThreeLabel").textContent = "Готово";
      $("newPalletBtn").hidden = true;
      $("closePalletBtn").hidden = true;
      $("toPlacementBtn").hidden = true;
      $("nextPalletBtn").hidden = true;
      $("scanArea").hidden = false;
      $("workScan").disabled = false;

      if (state.completedPlacement) {
        setSteps(3, [1, 2, 3]);
        $("scanArea").hidden = true;
        $("nextPalletBtn").hidden = false;
        $("nextPalletBtn").textContent = "Разместить следующую палету";
        showCompletion(
          "Палета размещена",
          `Ячейка ${state.completedPlacement.locationCode}.`,
          state.completedPlacement.palletUid,
        );
        return;
      }

      clearCompletion();
      if (!state.pallet) {
        setSteps(1);
        $("nextAction").textContent = "Отсканируйте палету";
        $("workScan").placeholder = "Код палеты";
        $("scanHint").textContent = "Нужна палета со статусом «Ожидает размещения»";
        return;
      }

      if (state.pallet.status === "waiting_placement") {
        setSteps(2, [1]);
        $("nextAction").textContent = "Отсканируйте ячейку";
        $("workScan").placeholder = "Код ячейки";
        $("scanHint").textContent = `Будет использован склад ${state.warehouseCode}`;
        return;
      }

      setSteps(1);
      $("scanArea").hidden = true;
      setNotice("Палета уже размещена или недоступна для размещения.", "warn");
    }

    function renderMove() {
      setStepCount(4);
      $("operationTitle").textContent = "Перемещение палеты";
      $("operationDescription").textContent = `Переместите палету в другую ячейку склада ${state.warehouseCode || "-"}.`;
      $("stepOneLabel").textContent = "Склад";
      $("stepTwoLabel").textContent = "Палета";
      $("stepThreeLabel").textContent = "Новая ячейка";
      $("stepFourLabel").textContent = "Готово";
      $("moveWarehouse").value = state.warehouseCode;
      $("moveWarehouseHint").textContent =
        `${state.availablePallets.length} пал. доступно · ${storageLocations().length} яч. хранения`;
      $("newPalletBtn").hidden = true;
      $("closePalletBtn").hidden = true;
      $("toPlacementBtn").hidden = true;
      $("nextPalletBtn").hidden = true;
      $("scanArea").hidden = false;
      $("workScan").disabled = false;

      if (state.completedMove) {
        setSteps(4, [1, 2, 3, 4]);
        $("scanArea").hidden = true;
        $("nextPalletBtn").hidden = false;
        $("nextPalletBtn").textContent = "Переместить следующую палету";
        showCompletion(
          "Палета перемещена",
          `${state.completedMove.fromLocationCode} → ${state.completedMove.locationCode}`,
          state.completedMove.palletUid,
        );
        return;
      }

      clearCompletion();
      if (!state.pallet) {
        setSteps(2, [1]);
        $("nextAction").textContent = "Отсканируйте палету";
        $("workScan").placeholder = "Код палеты";
        $("scanHint").textContent = `Нужна размещённая палета склада ${state.warehouseCode}`;
        return;
      }

      if (state.pallet.status === "available" && palletBelongsToSelectedWarehouse(state.pallet)) {
        setSteps(3, [1, 2]);
        $("nextAction").textContent = "Отсканируйте новую ячейку";
        $("workScan").placeholder = "Код ячейки";
        $("scanHint").textContent = `Текущая ячейка: ${locationCode(state.pallet.current_location_id)}`;
        return;
      }

      setSteps(2, [1]);
      $("scanArea").hidden = true;
      setNotice(`Палета недоступна для перемещения на складе ${state.warehouseCode}.`, "warn");
    }

    function renderShipment() {
      setStepCount(4);
      $("operationTitle").textContent = "Отгрузка";
      $("operationDescription").textContent = "Соберите заявку, передайте палеты в экспедицию и подтвердите погрузку.";
      $("stepOneLabel").textContent = "Заявка";
      $("stepTwoLabel").textContent = "Резерв";
      $("stepThreeLabel").textContent = "Экспедиция";
      $("stepFourLabel").textContent = "Погрузка";
      $("newPalletBtn").hidden = true;
      $("closePalletBtn").hidden = true;
      $("toPlacementBtn").hidden = true;
      $("nextPalletBtn").hidden = true;
      $("toExpeditionBtn").hidden = true;
      $("closeShipmentBtn").hidden = true;
      $("newShipmentBtn").hidden = true;
      $("shipmentCreate").classList.remove("visible");
      $("scanArea").hidden = false;
      $("workScan").disabled = false;
      clearCompletion();

      if (!state.shipment) {
        setSteps(1);
        $("scanArea").hidden = true;
        $("shipmentCreate").classList.add("visible");
        return;
      }

      if (["draft", "reserved"].includes(state.shipment.status)) {
        setSteps(2, [1]);
        $("nextAction").textContent = "Сканируйте палеты в заявку";
        $("workScan").placeholder = "Код палеты";
        $("scanHint").textContent = `Доступны размещённые палеты склада ${state.warehouseCode}`;
        $("toExpeditionBtn").hidden = state.shipment.pallet_count === 0;
        return;
      }

      if (["expedition", "loading"].includes(state.shipment.status)) {
        setSteps(4, [1, 2, 3]);
        $("nextAction").textContent = "Сканируйте палеты при погрузке";
        $("workScan").placeholder = "Код палеты";
        $("scanHint").textContent = `Погружено ${state.shipment.loaded_count} из ${state.shipment.pallet_count}`;
        $("closeShipmentBtn").hidden = !(
          state.shipment.status === "loading"
          && state.shipment.pallet_count > 0
          && state.shipment.loaded_count === state.shipment.pallet_count
        );
        return;
      }

      setSteps(4, [1, 2, 3, 4]);
      $("scanArea").hidden = true;
      $("newShipmentBtn").hidden = false;
      showCompletion(
        "Отгрузка завершена",
        `Погружено ${state.shipment.pallet_count} пал. Ячейки освобождены.`,
        state.shipment.shipment_uid,
      );
    }

    function renderInventory() {
      setStepCount(4);
      $("operationTitle").textContent = "Инвентаризация";
      $("operationDescription").textContent = `Проверьте все ячейки хранения склада ${state.warehouseCode || "-"}.`;
      $("stepOneLabel").textContent = "Начало";
      $("stepTwoLabel").textContent = "Ячейка";
      $("stepThreeLabel").textContent = "Палета";
      $("stepFourLabel").textContent = "Итог";
      $("newPalletBtn").hidden = true;
      $("closePalletBtn").hidden = true;
      $("toPlacementBtn").hidden = true;
      $("nextPalletBtn").hidden = true;
      $("toExpeditionBtn").hidden = true;
      $("closeShipmentBtn").hidden = true;
      $("newShipmentBtn").hidden = true;
      $("emptyLocationBtn").hidden = true;
      $("completeInventoryBtn").hidden = true;
      $("newInventoryBtn").hidden = true;
      $("inventoryStart").classList.remove("visible");
      $("scanArea").hidden = false;
      $("workScan").disabled = false;
      clearCompletion();

      if (!state.inventory) {
        const hasOpenInventory = openInventoriesForSelectedWarehouse().length > 0;
        setSteps(1);
        $("scanArea").hidden = true;
        $("inventoryStart").classList.add("visible");
        $("inventoryStartTitle").textContent = hasOpenInventory
          ? "На складе уже есть открытая инвентаризация"
          : `Склад ${state.warehouseCode} готов к обходу`;
        $("startInventoryBtn").disabled = hasOpenInventory;
        $("startInventoryBtn").textContent = hasOpenInventory
          ? "Продолжите обход из списка ниже"
          : "Начать инвентаризацию";
        return;
      }

      if (state.inventory.status === "completed") {
        setSteps(4, [1, 2, 3, 4]);
        $("scanArea").hidden = true;
        $("newInventoryBtn").hidden = false;
        showCompletion(
          "Инвентаризация завершена",
          `Проверено ${state.inventoryProgress?.checked_locations || 0} яч. Расхождения сохранены.`,
          state.inventory.inventory_uid,
        );
        return;
      }

      if (state.inventory.current_location_code) {
        setSteps(3, [1, 2]);
        $("nextAction").textContent = `Ячейка ${state.inventory.current_location_code}: сканируйте палету`;
        $("workScan").placeholder = "Код палеты";
        $("scanHint").textContent = "Если ячейка пустая, нажмите «Пусто»";
        $("emptyLocationBtn").hidden = false;
        return;
      }

      if ((state.inventoryProgress?.unchecked_locations || 0) > 0) {
        setSteps(2, [1]);
        $("nextAction").textContent = "Отсканируйте следующую ячейку";
        $("workScan").placeholder = "Код ячейки";
        $("scanHint").textContent = `Осталось ${state.inventoryProgress.unchecked_locations} яч.`;
        return;
      }

      setSteps(4, [1, 2, 3]);
      $("scanArea").hidden = true;
      $("completeInventoryBtn").hidden = false;
      $("completeInventoryBtn").textContent = state.inventoryProgress?.problem_lines.length
        ? "Завершить с расхождениями"
        : "Завершить инвентаризацию";
    }

    function renderTransfer() {
      setStepCount(4);
      $("operationTitle").textContent = "Межскладское перемещение";
      $("operationDescription").textContent = "Отправьте палеты с одного склада и примите их на другом.";
      $("stepOneLabel").textContent = "Документ";
      $("stepTwoLabel").textContent = "Подбор";
      $("stepThreeLabel").textContent = "Отправка";
      $("stepFourLabel").textContent = "Приёмка";
      $("newPalletBtn").hidden = true;
      $("closePalletBtn").hidden = true;
      $("toPlacementBtn").hidden = true;
      $("nextPalletBtn").hidden = true;
      $("toExpeditionBtn").hidden = true;
      $("closeShipmentBtn").hidden = true;
      $("newShipmentBtn").hidden = true;
      $("emptyLocationBtn").hidden = true;
      $("completeInventoryBtn").hidden = true;
      $("newInventoryBtn").hidden = true;
      $("transferExpeditionBtn").hidden = true;
      $("dispatchTransferBtn").hidden = true;
      $("placeTransferBtn").hidden = true;
      $("newTransferBtn").hidden = true;
      $("transferCreate").classList.remove("visible");
      $("scanArea").hidden = false;
      $("workScan").disabled = false;
      clearCompletion();

      if (!state.transfer) {
        setSteps(1);
        $("scanArea").hidden = true;
        $("transferCreate").classList.add("visible");
        return;
      }

      if (["draft", "reserved"].includes(state.transfer.status)) {
        setSteps(2, [1]);
        $("nextAction").textContent = "Сканируйте палеты в документ";
        $("workScan").placeholder = "Код палеты";
        $("scanHint").textContent = `Маршрут ${state.transfer.source_warehouse_code} → ${state.transfer.destination_warehouse_code}`;
        $("transferExpeditionBtn").hidden = state.transfer.pallet_count === 0;
        return;
      }

      if (["expedition", "loading"].includes(state.transfer.status)) {
        setSteps(3, [1, 2]);
        $("nextAction").textContent = "Сканируйте палеты при погрузке";
        $("workScan").placeholder = "Код палеты";
        $("scanHint").textContent = `Погружено ${state.transfer.loaded_count} из ${state.transfer.pallet_count}`;
        $("dispatchTransferBtn").hidden = !(
          state.transfer.status === "loading"
          && state.transfer.pallet_count > 0
          && state.transfer.loaded_count === state.transfer.pallet_count
        );
        return;
      }

      if (["in_transit", "receiving"].includes(state.transfer.status)) {
        setSteps(4, [1, 2, 3]);
        $("nextAction").textContent = `Приёмка на складе ${state.transfer.destination_warehouse_code}`;
        $("workScan").placeholder = "Код принятой палеты";
        $("scanHint").textContent = `Принято ${state.transfer.received_count} из ${state.transfer.pallet_count}`;
        return;
      }

      setSteps(4, [1, 2, 3, 4]);
      $("scanArea").hidden = true;
      $("placeTransferBtn").hidden = state.transfer.received_count === 0;
      $("newTransferBtn").hidden = false;
      showCompletion(
        "Перемещение завершено",
        `Принято ${state.transfer.received_count} пал. Они ожидают размещения на складе ${state.transfer.destination_warehouse_code}.`,
        state.transfer.transfer_uid,
      );
    }

    function renderTasks() {
      setStepCount(3);
      $("operationTitle").textContent = "Задания";
      $("operationDescription").textContent = "Работы склада в порядке исполнения и приоритета.";
      $("stepOneLabel").textContent = "Очередь";
      $("stepTwoLabel").textContent = "Выполнение";
      $("stepThreeLabel").textContent = "Готово";
      const hasInProgress = state.tasks.some((task) => task.status === "in_progress");
      setSteps(hasInProgress ? 2 : 1, hasInProgress ? [1] : []);
      $("scanArea").hidden = true;
      $("workScan").disabled = true;
      $("newPalletBtn").hidden = true;
      $("closePalletBtn").hidden = true;
      $("toPlacementBtn").hidden = true;
      $("nextPalletBtn").hidden = true;
      $("toExpeditionBtn").hidden = true;
      $("closeShipmentBtn").hidden = true;
      $("newShipmentBtn").hidden = true;
      $("emptyLocationBtn").hidden = true;
      $("completeInventoryBtn").hidden = true;
      $("newInventoryBtn").hidden = true;
      $("transferExpeditionBtn").hidden = true;
      $("dispatchTransferBtn").hidden = true;
      $("placeTransferBtn").hidden = true;
      $("newTransferBtn").hidden = true;
      $("taskCreate").classList.toggle("visible", state.taskCreateVisible);
      clearCompletion();
    }

    function render() {
      $("moveWarehouseContext").hidden = state.operation !== "move";
      if (state.operation !== "ship") {
        $("shipmentCreate").classList.remove("visible");
        $("toExpeditionBtn").hidden = true;
        $("closeShipmentBtn").hidden = true;
        $("newShipmentBtn").hidden = true;
      }
      if (state.operation !== "inventory") {
        $("inventoryStart").classList.remove("visible");
        $("emptyLocationBtn").hidden = true;
        $("completeInventoryBtn").hidden = true;
        $("newInventoryBtn").hidden = true;
        $("inventoryProblems").classList.remove("visible");
      }
      if (state.operation !== "transfer") {
        $("transferCreate").classList.remove("visible");
        $("transferExpeditionBtn").hidden = true;
        $("dispatchTransferBtn").hidden = true;
        $("placeTransferBtn").hidden = true;
        $("newTransferBtn").hidden = true;
      }
      if (state.operation !== "tasks") {
        state.taskCreateVisible = false;
        $("taskCreate").classList.remove("visible");
      }
      document.querySelectorAll("[data-operation]").forEach((button) => {
        button.classList.toggle("active", button.dataset.operation === state.operation);
      });
      const operationNav = document.querySelector(".operation-nav");
      const activeOperation = document.querySelector(`[data-operation="${state.operation}"]`);
      if (operationNav.scrollWidth > operationNav.clientWidth && activeOperation) {
        operationNav.scrollLeft = activeOperation.offsetLeft - (operationNav.clientWidth - activeOperation.offsetWidth) / 2;
      }
      renderCurrentPallet();
      renderCurrentShipment();
      renderCurrentInventory();
      renderCurrentTransfer();
      renderTaskOverview();
      renderInventoryProblems();
      renderQueue();
      if (state.operation === "tasks") renderTasks();
      else if (state.operation === "build") renderBuild();
      else if (state.operation === "place") renderPlace();
      else if (state.operation === "move") renderMove();
      else if (state.operation === "ship") renderShipment();
      else if (state.operation === "inventory") renderInventory();
      else renderTransfer();
    }

    async function selectPallet(uid) {
      clearCompletion();
      persistActivePallet(uid);
      await loadActivePallet();
      if (!state.pallet) return render();
      const allowed = state.operation === "build"
        ? ["open", "waiting_placement"].includes(state.pallet.status)
        : state.operation === "place"
          ? state.pallet.status === "waiting_placement"
          : state.pallet.status === "available" && palletBelongsToSelectedWarehouse(state.pallet);
      if (!allowed) {
        await clearActivePallet("Палета не подходит для выбранной операции");
        return;
      }
      render();
      setNotice(`Палета выбрана: ${uid}`, "ok");
      focusScan();
    }

    async function selectShipment(uid) {
      clearCompletion();
      persistActiveShipment(uid);
      await loadActiveShipment();
      if (!state.shipment) return render();
      const shipmentWarehouseCode = activeShipmentWarehouseCode();
      if (shipmentWarehouseCode && shipmentWarehouseCode !== state.warehouseCode) {
        state.warehouseCode = shipmentWarehouseCode;
        localStorage.setItem("wms.work.warehouse", state.warehouseCode);
        $("workWarehouse").value = state.warehouseCode;
      }
      await refreshQueues();
      render();
      setNotice(`Выбрана отгрузка ${uid}`, "ok");
      focusScan();
    }

    async function createShipment() {
      const shipment = await post("/api/shipments", {
        actor: actor(),
        customer_name: $("shipmentCustomer").value.trim() || "Демо-клиент",
        destination: $("shipmentDestination").value.trim() || "Тестовая точка",
      });
      persistActiveShipment(shipment.shipment_uid);
      await loadActiveShipment();
      await refreshQueues();
      render();
      setNotice(`Создана заявка ${shipment.shipment_uid}. Добавьте палеты.`, "ok");
      focusScan();
    }

    async function reserveShipmentPallet(palletUid) {
      if (!state.shipment) throw new Error("Сначала создайте или выберите заявку");
      const pallet = await api(`/api/pallets/${encodeURIComponent(palletUid)}`);
      if (pallet.status !== "available") throw new Error("Палета недоступна для резервирования");
      if (!palletBelongsToSelectedWarehouse(pallet)) {
        throw new Error(`Палета находится не на складе ${state.warehouseCode}`);
      }
      const shipmentWarehouseCode = activeShipmentWarehouseCode();
      if (shipmentWarehouseCode && shipmentWarehouseCode !== state.warehouseCode) {
        throw new Error(`Палеты заявки относятся к складу ${shipmentWarehouseCode}`);
      }
      await post(
        `/api/shipments/${encodeURIComponent(state.shipment.shipment_uid)}/pallets/${encodeURIComponent(palletUid)}`,
        { actor: actor() },
      );
      await loadActiveShipment();
      await refreshQueues();
      render();
      setNotice(`Палета добавлена в заявку: ${palletUid}`, "ok");
      focusScan();
    }

    async function moveShipmentToExpedition() {
      if (!state.shipment) throw new Error("Сначала выберите заявку");
      await post(`/api/shipments/${encodeURIComponent(state.shipment.shipment_uid)}/expedition`, { actor: actor() });
      await loadActiveShipment();
      await refreshQueues();
      render();
      setNotice("Палеты переданы в экспедицию. Начинайте контроль погрузки.", "ok");
      focusScan();
    }

    async function loadShipmentPallet(palletUid) {
      if (!state.shipment) throw new Error("Сначала выберите заявку");
      await post(
        `/api/shipments/${encodeURIComponent(state.shipment.shipment_uid)}/load/${encodeURIComponent(palletUid)}`,
        { actor: actor() },
      );
      await loadActiveShipment();
      await refreshQueues();
      render();
      setNotice(`Погрузка подтверждена: ${palletUid}`, "ok");
      focusScan();
    }

    async function closeActiveShipment() {
      if (!state.shipment) throw new Error("Сначала выберите заявку");
      await post(`/api/shipments/${encodeURIComponent(state.shipment.shipment_uid)}/close`, {
        actor: actor(),
        reason: "Погрузка завершена на складе",
      });
      await loadActiveShipment();
      await refreshQueues();
      render();
      setNotice("Отгрузка завершена. Складские ячейки освобождены.", "ok");
    }

    async function createManualTask() {
      const task = await post("/api/tasks", {
        warehouse_code: state.warehouseCode,
        task_type: $("taskType").value,
        priority: $("taskPriority").value,
        object_uid: $("taskObjectUid").value.trim().toUpperCase() || null,
        actor: actor(),
      });
      state.taskCreateVisible = false;
      $("taskObjectUid").value = "";
      await refreshQueues();
      render();
      setNotice(`Задание добавлено: ${task.task_uid}`, "ok");
    }

    async function beginTask(taskUid) {
      let task = state.tasks.find((item) => item.task_uid === taskUid);
      if (!task) throw new Error("Задание не найдено");
      task = await post(`/api/tasks/${encodeURIComponent(taskUid)}/start`, { actor: actor() });
      state.warehouseCode = task.warehouse_code;
      localStorage.setItem("wms.work.warehouse", state.warehouseCode);
      $("workWarehouse").value = state.warehouseCode;
      updateTransferDestinations();

      if (["build", "place", "move"].includes(task.task_type)) {
        persistActivePallet(task.object_uid || "");
        await loadActivePallet();
      } else if (task.task_type === "ship") {
        persistActiveShipment(task.object_uid || "");
        await loadActiveShipment();
      } else if (task.task_type === "inventory") {
        persistActiveInventory(task.object_uid || "");
        await loadActiveInventory();
      } else if (task.task_type === "transfer") {
        persistActiveTransfer(task.object_uid || "");
        await loadActiveTransfer();
      }

      await refreshQueues();
      await switchOperation(task.task_type, ["build", "place", "move"].includes(task.task_type));
      setNotice(`${task.title}. Задание назначено: ${actor()}.`, "ok");
      focusScan();
    }

    async function finishTask(taskUid) {
      await post(`/api/tasks/${encodeURIComponent(taskUid)}/complete`, { actor: actor() });
      await refreshQueues();
      render();
      setNotice("Задание отмечено выполненным.", "ok");
    }

    function transferWorkWarehouse(transfer) {
      return ["in_transit", "receiving", "completed"].includes(transfer.status)
        ? transfer.destination_warehouse_code
        : transfer.source_warehouse_code;
    }

    function updateTransferDestinations() {
      const destinations = state.warehouses.filter((warehouse) => warehouse.code !== state.warehouseCode);
      const previous = $("transferDestination").value;
      $("transferDestination").innerHTML = destinations.map((warehouse) =>
        `<option value="${escapeHtml(warehouse.code)}">${escapeHtml(warehouse.code)} — ${escapeHtml(warehouse.name)}</option>`,
      ).join("");
      if (destinations.some((item) => item.code === previous)) $("transferDestination").value = previous;
    }

    async function selectTransfer(uid) {
      clearCompletion();
      persistActiveTransfer(uid);
      await loadActiveTransfer();
      if (!state.transfer) return render();
      const workWarehouse = transferWorkWarehouse(state.transfer);
      if (workWarehouse && workWarehouse !== state.warehouseCode) {
        state.warehouseCode = workWarehouse;
        localStorage.setItem("wms.work.warehouse", state.warehouseCode);
        $("workWarehouse").value = state.warehouseCode;
        updateTransferDestinations();
      }
      await refreshQueues();
      render();
      setNotice(`Выбрано перемещение ${uid}`, "ok");
      focusScan();
    }

    async function createTransfer() {
      const destination = $("transferDestination").value;
      if (!destination) throw new Error("Добавьте второй склад для межскладского перемещения");
      const transfer = await post("/api/transfers", {
        actor: actor(),
        source_warehouse_code: state.warehouseCode,
        destination_warehouse_code: destination,
        vehicle_number: $("transferVehicle").value.trim() || null,
      });
      persistActiveTransfer(transfer.transfer_uid);
      await loadActiveTransfer();
      await refreshQueues();
      render();
      setNotice(`Создано перемещение ${transfer.transfer_uid}. Добавьте палеты.`, "ok");
      focusScan();
    }

    async function reserveTransferPallet(palletUid) {
      if (!state.transfer) throw new Error("Сначала создайте или выберите перемещение");
      await post(
        `/api/transfers/${encodeURIComponent(state.transfer.transfer_uid)}/pallets/${encodeURIComponent(palletUid)}`,
        { actor: actor() },
      );
      await loadActiveTransfer();
      await refreshQueues();
      render();
      setNotice(`Палета добавлена в перемещение: ${palletUid}`, "ok");
      focusScan();
    }

    async function moveTransferToExpedition() {
      if (!state.transfer) throw new Error("Сначала выберите перемещение");
      await post(`/api/transfers/${encodeURIComponent(state.transfer.transfer_uid)}/expedition`, { actor: actor() });
      await loadActiveTransfer();
      await refreshQueues();
      render();
      setNotice("Палеты переданы в экспедицию, исходные ячейки освобождены.", "ok");
      focusScan();
    }

    async function loadTransferPallet(palletUid) {
      if (!state.transfer) throw new Error("Сначала выберите перемещение");
      await post(
        `/api/transfers/${encodeURIComponent(state.transfer.transfer_uid)}/load/${encodeURIComponent(palletUid)}`,
        { actor: actor() },
      );
      await loadActiveTransfer();
      await refreshQueues();
      render();
      setNotice(`Погрузка подтверждена: ${palletUid}`, "ok");
      focusScan();
    }

    async function dispatchActiveTransfer() {
      if (!state.transfer) throw new Error("Сначала выберите перемещение");
      await post(`/api/transfers/${encodeURIComponent(state.transfer.transfer_uid)}/dispatch`, {
        actor: actor(),
        reason: "Межскладская отправка из рабочего места WMS",
      });
      await loadActiveTransfer();
      const destination = state.transfer.destination_warehouse_code;
      state.warehouseCode = destination;
      localStorage.setItem("wms.work.warehouse", destination);
      $("workWarehouse").value = destination;
      updateTransferDestinations();
      await refreshQueues();
      render();
      setNotice(`Машина отправлена. Продолжите приёмку на складе ${destination}.`, "ok");
      focusScan();
    }

    async function receiveTransferPallet(palletUid) {
      if (!state.transfer) throw new Error("Сначала выберите перемещение");
      await post(
        `/api/transfers/${encodeURIComponent(state.transfer.transfer_uid)}/receive/${encodeURIComponent(palletUid)}`,
        { actor: actor() },
      );
      await loadActiveTransfer();
      await refreshQueues();
      render();
      const complete = state.transfer.status === "completed";
      setNotice(
        complete ? "Все палеты приняты. Перемещение завершено." : `Палета принята: ${palletUid}`,
        "ok",
      );
      focusScan();
    }

    async function placeReceivedTransferPallets() {
      if (!state.transfer || state.transfer.status !== "completed") throw new Error("Сначала завершите приёмку");
      const destination = state.transfer.destination_warehouse_code;
      const firstWaiting = state.transferPallets.find((row) => row.pallet.status === "waiting_placement")?.pallet;
      state.warehouseCode = destination;
      localStorage.setItem("wms.work.warehouse", destination);
      $("workWarehouse").value = destination;
      updateTransferDestinations();
      if (firstWaiting) {
        persistActivePallet(firstWaiting.pallet_uid);
        await loadActivePallet();
      }
      await refreshQueues();
      await switchOperation("place", true);
      setNotice(`Разместите принятые палеты на складе ${destination}.`, "ok");
    }

    async function selectInventory(uid) {
      clearCompletion();
      persistActiveInventory(uid);
      await loadActiveInventory();
      if (!state.inventory) return render();
      if (state.inventory.warehouse_code && state.inventory.warehouse_code !== state.warehouseCode) {
        state.warehouseCode = state.inventory.warehouse_code;
        localStorage.setItem("wms.work.warehouse", state.warehouseCode);
        $("workWarehouse").value = state.warehouseCode;
      }
      await refreshQueues();
      render();
      setNotice(`Выбрана инвентаризация ${uid}`, "ok");
      focusScan();
    }

    async function startInventory() {
      const inventory = await post("/api/inventories", {
        warehouse_code: state.warehouseCode,
        actor: actor(),
      });
      persistActiveInventory(inventory.inventory_uid);
      await loadActiveInventory();
      await refreshQueues();
      render();
      setNotice(`Начат обход склада ${state.warehouseCode}. Сканируйте ячейку.`, "ok");
      focusScan();
    }

    async function scanInventoryLocation(locationCodeValue) {
      if (!state.inventory || state.inventory.status !== "open") {
        throw new Error("Сначала начните или выберите инвентаризацию");
      }
      if (state.inventory.current_location_code) {
        throw new Error("Сначала отсканируйте палету или нажмите «Пусто»");
      }
      const location = storageLocations().find((item) => item.code === locationCodeValue);
      if (!location) throw new Error(`Ячейка ${locationCodeValue} не относится к складу ${state.warehouseCode}`);
      const unchecked = state.inventoryProgress?.unchecked_locations_list.some(
        (item) => item.location_code === locationCodeValue,
      );
      if (!unchecked) throw new Error("Эта ячейка уже проверена");
      await post(`/api/inventories/${encodeURIComponent(state.inventory.inventory_uid)}/scan-location`, {
        location_code: locationCodeValue,
        actor: actor(),
      });
      await loadActiveInventory();
      render();
      setNotice(`Ячейка ${locationCodeValue}: сканируйте палету или нажмите «Пусто».`, "ok");
      focusScan();
    }

    async function scanInventoryPallet(palletUid) {
      if (!state.inventory?.current_location_code) throw new Error("Сначала отсканируйте ячейку");
      const locationCodeValue = state.inventory.current_location_code;
      await post(`/api/inventories/${encodeURIComponent(state.inventory.inventory_uid)}/scan`, {
        pallet_uid: palletUid,
        actor: actor(),
      });
      await loadActiveInventory();
      const line = state.inventoryLines.find((item) => item.pallet.pallet_uid === palletUid);
      render();
      if (line?.status === "scanned") {
        setNotice(`Совпадение: ${palletUid} находится в ${locationCodeValue}.`, "ok");
      } else {
        setNotice(`${inventoryLineStatusLabels[line?.status] || "Зафиксировано расхождение"}: ${palletUid}.`, "warn");
      }
      focusScan();
    }

    async function confirmEmptyInventoryLocation() {
      if (!state.inventory?.current_location_code) throw new Error("Сначала отсканируйте ячейку");
      const locationCodeValue = state.inventory.current_location_code;
      const locationProgress = state.inventoryProgress?.unchecked_locations_list.find(
        (item) => item.location_code === locationCodeValue,
      );
      await post(`/api/inventories/${encodeURIComponent(state.inventory.inventory_uid)}/confirm-location`, {
        location_code: locationCodeValue,
        actor: actor(),
      });
      await loadActiveInventory();
      render();
      if ((locationProgress?.expected_count || 0) > 0) {
        setNotice(`Ячейка ${locationCodeValue} закрыта. Зафиксировано отсутствие ожидаемой палеты.`, "warn");
      } else {
        setNotice(`Пустая ячейка подтверждена: ${locationCodeValue}.`, "ok");
      }
      focusScan();
    }

    async function resolveInventoryProblem(palletUid, status) {
      if (!state.inventory) throw new Error("Сначала выберите инвентаризацию");
      const action = inventoryResolution(status);
      if (!action) throw new Error("Для расхождения нет доступного действия");
      await post(
        `/api/inventories/${encodeURIComponent(state.inventory.inventory_uid)}/discrepancies/${encodeURIComponent(palletUid)}/${action.endpoint}`,
        { actor: actor(), reason: "Обработано в рабочем месте WMS" },
      );
      await loadActiveInventory();
      await refreshQueues();
      render();
      setNotice(`${action.label}: ${palletUid}`, "ok");
      focusScan();
    }

    async function completeActiveInventory() {
      if (!state.inventory) throw new Error("Сначала выберите инвентаризацию");
      await post(`/api/inventories/${encodeURIComponent(state.inventory.inventory_uid)}/complete`, { actor: actor() });
      await loadActiveInventory();
      await refreshQueues();
      render();
      setNotice("Инвентаризация завершена. Расхождения сохранены.", "ok");
    }

    async function createPallet() {
      const pallet = await post("/api/pallets", { actor: actor() });
      persistActivePallet(pallet.pallet_uid);
      await loadActivePallet();
      await refreshQueues();
      render();
      setNotice(`Открыта палета ${pallet.pallet_uid}. Сканируйте коробки.`, "ok");
      focusScan();
    }

    async function addBox(boxUid) {
      if (!state.pallet || state.pallet.status !== "open") {
        throw new Error("Сначала откройте или выберите палету");
      }
      try {
        await post(`/api/boxes/${encodeURIComponent(boxUid)}/accept`, { actor: actor() });
      } catch (error) {
        if (!String(error.message).includes("уже была принята")) throw error;
      }
      await post(
        `/api/pallets/${encodeURIComponent(state.pallet.pallet_uid)}/boxes/${encodeURIComponent(boxUid)}`,
        { actor: actor() },
      );
      await loadActivePallet();
      await refreshQueues();
      render();
      setNotice(`Коробка добавлена: ${boxUid}`, "ok");
    }

    async function closePallet() {
      if (!state.pallet) throw new Error("Сначала выберите палету");
      await post(`/api/pallets/${encodeURIComponent(state.pallet.pallet_uid)}/close`, {
        actor: actor(),
        reason: "Рабочее место WMS",
      });
      await loadActivePallet();
      await refreshQueues();
      render();
      setNotice("Формирование завершено. Палета ожидает размещения.", "ok");
    }

    async function placePallet(locationCodeValue) {
      if (!state.pallet || state.pallet.status !== "waiting_placement") {
        throw new Error("Сначала отсканируйте палету для размещения");
      }
      const location = storageLocations().find((item) => item.code === locationCodeValue);
      if (!location) throw new Error(`Ячейка ${locationCodeValue} не относится к складу ${state.warehouseCode}`);
      const palletUid = state.pallet.pallet_uid;
      await post(`/api/pallets/${encodeURIComponent(palletUid)}/place`, {
        actor: actor(),
        reason: "Рабочее место WMS",
        location_code: locationCodeValue,
      });
      state.completedPlacement = { palletUid, locationCode: locationCodeValue };
      persistActivePallet("");
      state.pallet = null;
      state.boxes = [];
      await refreshQueues();
      render();
      setNotice(`Палета размещена в ячейке ${locationCodeValue}`, "ok");
    }

    async function movePallet(locationCodeValue) {
      if (!state.pallet || state.pallet.status !== "available") {
        throw new Error("Сначала отсканируйте размещённую палету");
      }
      if (!palletBelongsToSelectedWarehouse(state.pallet)) {
        throw new Error(`Палета находится не на складе ${state.warehouseCode}`);
      }
      const location = storageLocations().find((item) => item.code === locationCodeValue);
      if (!location) throw new Error(`Ячейка ${locationCodeValue} не относится к складу ${state.warehouseCode}`);
      const fromLocationCode = locationCode(state.pallet.current_location_id);
      if (fromLocationCode === locationCodeValue) throw new Error("Палета уже находится в этой ячейке");
      const palletUid = state.pallet.pallet_uid;
      await post(`/api/pallets/${encodeURIComponent(palletUid)}/move`, {
        actor: actor(),
        reason: "Рабочее место WMS",
        location_code: locationCodeValue,
      });
      state.completedMove = { palletUid, fromLocationCode, locationCode: locationCodeValue };
      persistActivePallet("");
      state.pallet = null;
      state.boxes = [];
      await refreshQueues();
      render();
      setNotice(`Палета перемещена в ячейку ${locationCodeValue}`, "ok");
    }

    async function handleScan(rawValue) {
      const value = rawValue.trim().toUpperCase();
      if (!value) return;
      const isPallet = value.startsWith(state.prefixes.pallet);
      const isBox = value.startsWith(state.prefixes.box);

      if (state.operation === "inventory") {
        if (!state.inventory) throw new Error("Сначала начните или выберите инвентаризацию");
        if (state.inventory.status !== "open") throw new Error("Инвентаризация уже завершена");
        if (state.inventory.current_location_code) {
          if (!isPallet) throw new Error("Сейчас ожидается код палеты или кнопка «Пусто»");
          return scanInventoryPallet(value);
        }
        if (isPallet) throw new Error("Сначала отсканируйте ячейку");
        if (isBox) throw new Error("Сейчас ожидается код ячейки");
        return scanInventoryLocation(value);
      }

      if (state.operation === "ship") {
        if (!state.shipment) throw new Error("Сначала создайте или выберите заявку");
        if (!isPallet) throw new Error("Сейчас ожидается код палеты");
        if (["draft", "reserved"].includes(state.shipment.status)) return reserveShipmentPallet(value);
        if (["expedition", "loading"].includes(state.shipment.status)) return loadShipmentPallet(value);
        throw new Error("Эта отгрузка уже завершена");
      }

      if (state.operation === "transfer") {
        if (!state.transfer) throw new Error("Сначала создайте или выберите перемещение");
        if (!isPallet) throw new Error("Сейчас ожидается код палеты");
        if (["draft", "reserved"].includes(state.transfer.status)) return reserveTransferPallet(value);
        if (["expedition", "loading"].includes(state.transfer.status)) return loadTransferPallet(value);
        if (["in_transit", "receiving"].includes(state.transfer.status)) return receiveTransferPallet(value);
        throw new Error("Это перемещение уже завершено");
      }

      if (state.operation === "build") {
        if (!state.pallet) {
          if (!isPallet) throw new Error("Сначала отсканируйте палету или откройте новую");
          return selectPallet(value);
        }
        if (isPallet) return selectPallet(value);
        if (!isBox) throw new Error("Сейчас ожидается код коробки");
        return addBox(value);
      }

      if (!state.pallet) {
        if (!isPallet) throw new Error("Сначала отсканируйте палету");
        return selectPallet(value);
      }
      if (isPallet) return selectPallet(value);
      if (isBox) throw new Error("Сейчас ожидается код ячейки");
      return state.operation === "place" ? placePallet(value) : movePallet(value);
    }

    function showError(error) {
      setNotice(humanError(error.message), "err");
      focusScan();
    }

    function defaultOperationNotice() {
      if (state.operation === "tasks") {
        const inProgress = state.tasks.filter((task) => task.status === "in_progress").length;
        if (inProgress) return `Заданий в работе: ${inProgress}`;
        return state.tasks.length ? "Выберите следующее задание" : "Очередь пуста";
      }
      if (state.operation === "build") return "Выберите палету или откройте новую";
      if (state.operation === "place") return "Отсканируйте палету, ожидающую размещения";
      if (state.operation === "move") return "Отсканируйте размещённую палету";
      if (state.operation === "ship") {
        if (!state.shipment) return "Создайте новую заявку или выберите отгрузку в работе";
        return state.shipment.status === "completed"
          ? "Отгрузка завершена. Складские ячейки освобождены"
          : "Продолжайте текущий этап отгрузки";
      }
      if (state.operation === "transfer") {
        if (!state.transfer) return "Создайте новое перемещение или выберите документ в работе";
        if (state.transfer.status === "completed") return "Перемещение завершено. Палеты ожидают размещения";
        if (["in_transit", "receiving"].includes(state.transfer.status)) return "Продолжайте приёмку на складе назначения";
        return "Продолжайте текущий этап межскладского перемещения";
      }
      if (!state.inventory) return "Начните новую инвентаризацию или продолжите открытый обход";
      if (state.inventory.status === "completed") return "Инвентаризация завершена";
      if (state.inventory.current_location_code) return "Сканируйте палету или нажмите «Пусто»";
      if ((state.inventoryProgress?.unchecked_locations || 0) === 0) return "Все ячейки проверены. Завершите инвентаризацию";
      return "Отсканируйте следующую ячейку";
    }

    async function switchOperation(operation, keepPallet = false) {
      state.operation = operation;
      clearCompletion();
      if (operation === "ship") {
        persistActivePallet("");
        state.pallet = null;
        state.boxes = [];
        await loadActiveShipment();
      }
      if (operation === "inventory") {
        persistActivePallet("");
        state.pallet = null;
        state.boxes = [];
        await loadActiveInventory();
      }
      if (operation === "transfer") {
        persistActivePallet("");
        state.pallet = null;
        state.boxes = [];
        await loadActiveTransfer();
        if (state.transfer) {
          const workWarehouse = transferWorkWarehouse(state.transfer);
          if (workWarehouse !== state.warehouseCode) {
            state.warehouseCode = workWarehouse;
            localStorage.setItem("wms.work.warehouse", workWarehouse);
            $("workWarehouse").value = workWarehouse;
            updateTransferDestinations();
            await refreshQueues();
          }
        }
      }
      if (!keepPallet) {
        const compatible = state.pallet && (
          operation === "build"
            ? ["open", "waiting_placement"].includes(state.pallet.status)
            : operation === "place"
              ? state.pallet.status === "waiting_placement"
              : operation === "move" && state.pallet.status === "available" && palletBelongsToSelectedWarehouse(state.pallet)
        );
        if (!compatible) {
          persistActivePallet("");
          state.pallet = null;
          state.boxes = [];
        }
      }
      history.replaceState(null, "", `/work?operation=${operation}`);
      render();
      setNotice(defaultOperationNotice());
      focusScan();
    }

    async function initialize() {
      const [constants, warehouses, locations, batches] = await Promise.all([
        api("/api/meta/constants"),
        api("/api/warehouses"),
        api("/api/locations"),
        api("/api/batches"),
      ]);
      state.prefixes.pallet = `${constants.pallet_code_prefix}-`;
      state.prefixes.box = `${constants.box_code_prefix}-`;
      state.warehouses = warehouses;
      state.locations = locations;
      state.batches = batches;

      const warehouseOptions = warehouses.map((warehouse) =>
        `<option value="${escapeHtml(warehouse.code)}">${escapeHtml(warehouse.code)} — ${escapeHtml(warehouse.name)}</option>`,
      ).join("");
      $("workWarehouse").innerHTML = warehouseOptions;
      $("moveWarehouse").innerHTML = warehouseOptions;
      if (!warehouses.some((item) => item.code === state.warehouseCode)) {
        state.warehouseCode = warehouses.some((item) => item.code === constants.default_warehouse_code)
          ? constants.default_warehouse_code
          : warehouses[0]?.code || "";
      }
      $("workWarehouse").value = state.warehouseCode;
      $("moveWarehouse").value = state.warehouseCode;
      updateTransferDestinations();
      $("workActor").value = localStorage.getItem("wms.work.actor") || "Кладовщик";

      await Promise.all([loadActivePallet(), loadActiveShipment(), loadActiveInventory(), loadActiveTransfer()]);
      const shipmentWarehouseCode = activeShipmentWarehouseCode();
      if (state.operation === "ship" && shipmentWarehouseCode && shipmentWarehouseCode !== state.warehouseCode) {
        state.warehouseCode = shipmentWarehouseCode;
        localStorage.setItem("wms.work.warehouse", state.warehouseCode);
        $("workWarehouse").value = state.warehouseCode;
      }
      if (
        state.operation === "inventory"
        && state.inventory?.warehouse_code
        && state.inventory.warehouse_code !== state.warehouseCode
      ) {
        state.warehouseCode = state.inventory.warehouse_code;
        localStorage.setItem("wms.work.warehouse", state.warehouseCode);
        $("workWarehouse").value = state.warehouseCode;
      }
      if (state.operation === "transfer" && state.transfer) {
        state.warehouseCode = transferWorkWarehouse(state.transfer);
        localStorage.setItem("wms.work.warehouse", state.warehouseCode);
        $("workWarehouse").value = state.warehouseCode;
        updateTransferDestinations();
      }
      const activeIsCompatible = state.pallet && (
        state.operation === "build"
          ? ["open", "waiting_placement"].includes(state.pallet.status)
          : state.operation === "place"
            ? state.pallet.status === "waiting_placement"
            : state.operation === "move" && state.pallet.status === "available" && palletBelongsToSelectedWarehouse(state.pallet)
      );
      if (state.pallet && !activeIsCompatible) {
        persistActivePallet("");
        state.pallet = null;
        state.boxes = [];
      }
      await refreshQueues();
      render();
      setNotice(defaultOperationNotice());
      focusScan();
    }

    document.querySelectorAll("[data-operation]").forEach((button) => {
      button.addEventListener("click", () => switchOperation(button.dataset.operation).catch(showError));
    });
    $("workScan").addEventListener("keydown", async (event) => {
      if (event.key !== "Enter") return;
      event.preventDefault();
      const value = event.currentTarget.value;
      event.currentTarget.value = "";
      try { await handleScan(value); } catch (error) { showError(error); } finally { focusScan(); }
    });
    async function changeWarehouse(warehouseCode) {
        state.warehouseCode = warehouseCode;
        localStorage.setItem("wms.work.warehouse", state.warehouseCode);
        $("workWarehouse").value = state.warehouseCode;
        $("moveWarehouse").value = state.warehouseCode;
        persistActivePallet("");
        state.pallet = null;
        state.boxes = [];
        persistActiveShipment("");
        state.shipment = null;
        state.shipmentPallets = [];
        persistActiveInventory("");
        state.inventory = null;
        state.inventoryProgress = null;
        state.inventoryLines = [];
        persistActiveTransfer("");
        state.transfer = null;
        state.transferPallets = [];
        updateTransferDestinations();
        clearCompletion();
        await refreshQueues();
        render();
        setNotice(`Выбран склад: ${state.warehouseCode}`, "ok");
        focusScan();
    }
    $("workWarehouse").addEventListener("change", (event) => {
      changeWarehouse(event.currentTarget.value).catch(showError);
    });
    $("moveWarehouse").addEventListener("change", (event) => {
      changeWarehouse(event.currentTarget.value).catch(showError);
    });
    $("workActor").addEventListener("change", () => {
      localStorage.setItem("wms.work.actor", actor());
      refreshQueues().then(render).catch(showError);
    });
    $("newPalletBtn").addEventListener("click", () => createPallet().catch(showError));
    $("closePalletBtn").addEventListener("click", () => closePallet().catch(showError));
    $("clearPalletBtn").addEventListener("click", () => clearActivePallet().catch(showError));
    $("refreshQueueBtn").addEventListener("click", () => refreshWorkplace().then(focusScan).catch(showError));
    $("toPlacementBtn").addEventListener("click", () => switchOperation("place", true).catch(showError));
    $("nextPalletBtn").addEventListener("click", () => {
      clearCompletion();
      render();
      setNotice("Отсканируйте следующую палету");
      focusScan();
    });
    $("createShipmentBtn").addEventListener("click", () => createShipment().catch(showError));
    $("clearShipmentBtn").addEventListener("click", () => clearActiveShipment().catch(showError));
    $("toExpeditionBtn").addEventListener("click", () => moveShipmentToExpedition().catch(showError));
    $("closeShipmentBtn").addEventListener("click", () => closeActiveShipment().catch(showError));
    $("newShipmentBtn").addEventListener("click", () => clearActiveShipment("Создайте следующую заявку или выберите отгрузку в работе").catch(showError));
    $("startInventoryBtn").addEventListener("click", () => startInventory().catch(showError));
    $("clearInventoryBtn").addEventListener("click", () => clearActiveInventory().catch(showError));
    $("emptyLocationBtn").addEventListener("click", () => confirmEmptyInventoryLocation().catch(showError));
    $("completeInventoryBtn").addEventListener("click", () => completeActiveInventory().catch(showError));
    $("newInventoryBtn").addEventListener("click", () => clearActiveInventory("Начните следующую инвентаризацию или выберите открытый обход").catch(showError));
    $("createTransferBtn").addEventListener("click", () => createTransfer().catch(showError));
    $("clearTransferBtn").addEventListener("click", () => clearActiveTransfer().catch(showError));
    $("transferExpeditionBtn").addEventListener("click", () => moveTransferToExpedition().catch(showError));
    $("dispatchTransferBtn").addEventListener("click", () => dispatchActiveTransfer().catch(showError));
    $("placeTransferBtn").addEventListener("click", () => placeReceivedTransferPallets().catch(showError));
    $("newTransferBtn").addEventListener("click", () => clearActiveTransfer("Создайте следующее перемещение или выберите документ в работе").catch(showError));
    $("toggleTaskCreateBtn").addEventListener("click", () => {
      state.taskCreateVisible = !state.taskCreateVisible;
      render();
    });
    $("createTaskBtn").addEventListener("click", () => createManualTask().catch(showError));

    initialize().catch(showError);
  </script>
</body>
</html>"""


@router.get("/tech", response_class=HTMLResponse, include_in_schema=False)
def tech_page() -> str:
    return """<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Технический режим WMS</title>
  <style>
    :root { --bg: #eef2f3; --panel: #fff; --line: #d5dde1; --text: #142129; --muted: #65727a; --accent: #087a70; --dark: #111a20; }
    * { box-sizing: border-box; }
    body { margin: 0; background: var(--bg); color: var(--text); font: 15px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    header { min-height: 58px; padding: 10px 20px; display: flex; align-items: center; justify-content: space-between; gap: 16px; color: #fff; background: var(--dark); }
    header strong { font-size: 17px; }
    header a { min-height: 36px; padding: 7px 11px; display: inline-flex; align-items: center; border: 1px solid #52616a; border-radius: 5px; color: #e5edef; font-weight: 750; text-decoration: none; }
    main { width: min(980px, 100%); margin: 0 auto; padding: 26px 18px; }
    h1 { margin: 0; font-size: 26px; letter-spacing: 0; }
    .lead { margin: 7px 0 26px; color: var(--muted); }
    .groups { display: grid; grid-template-columns: repeat(3, 1fr); gap: 24px; }
    section { min-width: 0; }
    h2 { margin: 0 0 10px; padding-bottom: 9px; border-bottom: 2px solid var(--line); font-size: 16px; letter-spacing: 0; }
    .links { display: grid; }
    .links a { padding: 11px 4px; border-bottom: 1px solid var(--line); color: #175f59; font-weight: 750; text-decoration: none; }
    .links a:hover { color: var(--accent); background: #f6faf9; }
    .links span { display: block; margin-top: 2px; color: var(--muted); font-size: 12px; font-weight: 400; }
    @media (max-width: 760px) { .groups { grid-template-columns: 1fr; gap: 26px; } main { padding: 20px 13px; } }
  </style>
</head>
<body>
  <header><strong>WMS · технический режим</strong><a href="/work">Рабочее место</a></header>
  <main>
    <h1>Все функции системы</h1>
    <p class="lead">Полные экраны пилота, справочники и средства проверки.</p>
    <div class="groups">
      <section>
        <h2>Операции</h2>
        <div class="links">
          <a href="/scan">Склад<span>Палеты, коробки, размещение и служебные действия</span></a>
          <a href="/transfers">Перемещения<span>Между складами</span></a>
          <a href="/shipments">Отгрузки<span>Заявки, резерв и погрузка</span></a>
          <a href="/inventory">Инвентаризация<span>Обходы и расхождения</span></a>
          <a href="/terminal">Эмулятор ТСД<span>Компактные рабочие сценарии</span></a>
        </div>
      </section>
      <section>
        <h2>Контроль</h2>
        <div class="links">
          <a href="/cards">Карточки объектов<span>Палеты, коробки и ячейки</span></a>
          <a href="/map">Карта склада<span>Состояние и редактор схемы</span></a>
        </div>
      </section>
      <section>
        <h2>Управление</h2>
        <div class="links">
          <a href="/tasks">Диспетчер заданий<span>Очередь, назначения и контроль выполнения</span></a>
          <a href="/catalog">Справочники<span>Демо-данные, импорт и этикетки</span></a>
          <a href="/docs">Документация API<span>Контракты backend</span></a>
        </div>
      </section>
    </div>
  </main>
</body>
</html>"""
