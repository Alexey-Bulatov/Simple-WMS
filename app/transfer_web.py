from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.page_shell import standard_page


router = APIRouter()


@router.get("/transfers", response_class=HTMLResponse, include_in_schema=False)
@standard_page("transfers")
def transfers_page() -> str:
    return """<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Складской пилот: межскладские перемещения</title>
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
      --blue: #175cd3;
      --dark: #111820;
    }
    * { box-sizing: border-box; }
    body { margin: 0; background: var(--bg); color: var(--text); font: 15px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    header { min-height: 54px; padding: 10px 18px; display: flex; align-items: center; justify-content: space-between; gap: 12px; color: #fff; background: var(--dark); }
    main { max-width: 1380px; margin: 0 auto; padding: 14px; display: grid; grid-template-columns: 330px minmax(0, 1fr) 370px; gap: 14px; }
    section, aside { min-width: 0; padding: 14px; border: 1px solid var(--line); border-radius: 8px; background: var(--panel); }
    h2, h3 { margin: 0; letter-spacing: 0; }
    h2 { font-size: 17px; }
    h3 { font-size: 14px; }
    a { color: #0b5e58; font-weight: 800; text-decoration: none; }
    .stack { display: grid; gap: 11px; }
    .grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 9px; }
    .facts { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
    .fact { min-width: 0; padding: 8px; border: 1px solid var(--line); border-radius: 6px; background: #fbfcfd; }
    .fact b { display: block; color: var(--muted); font-size: 10px; text-transform: uppercase; }
    .fact span { display: block; margin-top: 2px; font-weight: 850; overflow-wrap: anywhere; }
    label { display: block; margin-bottom: 5px; color: var(--muted); font-size: 11px; font-weight: 850; text-transform: uppercase; }
    input, button, select { width: 100%; min-height: 40px; border: 1px solid var(--line); border-radius: 6px; padding: 8px 10px; background: #fff; color: var(--text); font: inherit; }
    button { cursor: pointer; border-color: var(--accent); background: var(--accent); color: #fff; font-weight: 850; }
    button.secondary { background: #f2fbf9; color: #0b5e58; }
    button.danger { border-color: var(--danger); background: var(--danger); }
    button:disabled { cursor: not-allowed; border-color: var(--line); background: #e9edef; color: #929da5; }
    .status { min-height: 48px; padding: 10px 12px; border: 1px solid #c7dcf3; border-radius: 6px; background: #eff8ff; font-weight: 800; }
    .status.ok { color: var(--ok); border-color: #abefc6; background: #ecfdf3; }
    .status.err { color: var(--danger); border-color: #fecdca; background: #fff1f0; }
    .status.warn { color: var(--warn); border-color: #fedf89; background: #fff8eb; }
    .scan-input { min-height: 66px; border: 2px solid var(--accent); font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 24px; font-weight: 900; letter-spacing: 0; }
    .list { display: grid; gap: 8px; max-height: 510px; overflow: auto; }
    .item { display: grid; gap: 6px; padding: 10px; border: 1px solid var(--line); border-radius: 7px; background: #fff; }
    .item.active { border-color: var(--accent); background: #ecfdf3; }
    .item-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
    .meta { color: var(--muted); font-size: 12px; }
    .badge { flex: 0 0 auto; padding: 3px 7px; border-radius: 5px; color: #344054; background: #eef2f6; font-size: 11px; font-weight: 850; white-space: nowrap; }
    .badge.reserved { color: var(--warn); background: #fff8eb; }
    .badge.expedition, .badge.loading { color: var(--blue); background: #eff8ff; }
    .badge.in_transit { color: #5925dc; background: #f4f3ff; }
    .badge.receiving { color: #026aa2; background: #f0f9ff; }
    .badge.completed, .badge.received { color: var(--ok); background: #ecfdf3; }
    .route { padding: 12px; display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 10px; border: 1px solid var(--line); border-radius: 7px; background: #fbfcfd; }
    .route strong { display: block; font-size: 18px; }
    .route span { color: var(--muted); font-size: 12px; }
    .arrow { color: var(--accent); font-size: 22px; font-weight: 900; }
    .wide { grid-column: 1 / -1; }
    @media (max-width: 1080px) {
      main { grid-template-columns: 1fr; padding: 10px; }
      .wide { grid-column: auto; }
    }
    @media (max-width: 640px) {
      .grid2, .facts { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <header><h1>Складской пилот: перемещения</h1></header>

  <main>
    <aside class="stack">
      <h2>Новое перемещение</h2>
      <div>
        <label for="actor">Оператор</label>
        <input id="actor" value="transfer-demo" autocomplete="off">
      </div>
      <div class="grid2">
        <div><label for="sourceWarehouse">Откуда</label><select id="sourceWarehouse"></select></div>
        <div><label for="destinationWarehouse">Куда</label><select id="destinationWarehouse"></select></div>
      </div>
      <div>
        <label for="vehicleNumber">Автомобиль</label>
        <input id="vehicleNumber" value="А000АА 77" autocomplete="off">
      </div>
      <button id="createBtn">Создать перемещение</button>
      <button id="refreshBtn" class="secondary">Обновить список</button>
      <h2>Документы</h2>
      <div id="transferList" class="list"></div>
    </aside>

    <section class="stack">
      <h2>Активное перемещение</h2>
      <div id="status" class="status">Создайте или выберите документ</div>
      <div class="route">
        <div><span>Склад-источник</span><strong id="sourceCode">-</strong></div>
        <div class="arrow">→</div>
        <div><span>Склад назначения</span><strong id="destinationCode">-</strong></div>
      </div>
      <div class="facts">
        <div class="fact"><b>Документ</b><span id="activeTransfer" class="mono">-</span></div>
        <div class="fact"><b>Статус</b><span id="activeStatus">-</span></div>
        <div class="fact"><b>Погружено</b><span id="loadedCount">0 / 0</span></div>
        <div class="fact"><b>Принято</b><span id="receivedCount">0 / 0</span></div>
      </div>
      <div class="grid2">
        <button id="expeditionBtn" class="secondary">В зону отправки</button>
        <button id="dispatchBtn" class="danger">Отправить в путь</button>
      </div>
      <div>
        <label id="scanLabel" for="scanInput">Скан погрузки</label>
        <input id="scanInput" class="scan-input" placeholder="Код палеты и Enter" autocomplete="off">
      </div>
      <a id="destinationWarehouseLink" href="/scan" hidden>Перейти к размещению на складе назначения</a>
      <h3>Палеты документа</h3>
      <div id="transferPallets" class="list"></div>
    </section>

    <aside class="stack">
      <h2>Доступные палеты источника</h2>
      <div class="meta">В документ можно добавить только доступные палеты, физически размещённые на выбранном складе.</div>
      <button id="refreshAvailableBtn" class="secondary">Обновить</button>
      <div id="availablePallets" class="list"></div>
    </aside>

    <section class="wide stack">
      <h2>История перемещения</h2>
      <div id="transferEvents" class="list"></div>
    </section>
  </main>

  <script>
    const state = { activeTransferUid: "", warehouses: [], active: null };
    const $ = (id) => document.getElementById(id);
    const transferStatusLabels = {
      draft: "Черновик", reserved: "Зарезервировано", expedition: "В зоне отправки",
      loading: "Погрузка", in_transit: "В пути", receiving: "Приёмка",
      completed: "Завершено", cancelled: "Отменено",
    };
    const palletStatusLabels = {
      reserved: "В резерве", expedition: "В зоне отправки", loaded: "Погружена",
      in_transit: "В пути", received: "Принята",
    };
    const operationLabels = {
      transfer_created: "Документ создан",
      transfer_pallet_reserved: "Палета добавлена",
      transfer_moved_to_expedition: "Палеты переданы в зону отправки",
      transfer_pallet_loaded: "Палета погружена",
      transfer_dispatched: "Машина отправлена",
      transfer_pallet_received: "Палета принята складом назначения",
      transfer_completed: "Перемещение завершено",
    };
    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[char]);
    }
    function label(map, value) { return map[value] || value || "-"; }
    function actor() { return $("actor").value.trim() || "transfer-demo"; }
    function setStatus(message, kind = "") {
      $("status").className = `status ${kind}`;
      $("status").textContent = message;
    }
    function focusScan() { setTimeout(() => $("scanInput").focus(), 30); }
    async function api(path, options = {}) {
      const response = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
      const text = await response.text();
      const data = text ? JSON.parse(text) : null;
      if (!response.ok) throw new Error(data?.detail || response.statusText);
      return data;
    }
    function post(path, body = {}) { return api(path, { method: "POST", body: JSON.stringify(body) }); }
    async function loadWarehouses() {
      state.warehouses = await api("/api/warehouses");
      const options = state.warehouses.map((warehouse) =>
        `<option value="${escapeHtml(warehouse.code)}">${escapeHtml(warehouse.code)} - ${escapeHtml(warehouse.name)}</option>`
      ).join("");
      $("sourceWarehouse").innerHTML = options;
      $("destinationWarehouse").innerHTML = options;
      if (state.warehouses.some((item) => item.code === "WH01")) $("sourceWarehouse").value = "WH01";
      if (state.warehouses.some((item) => item.code === "WH02")) $("destinationWarehouse").value = "WH02";
      else if (state.warehouses.length > 1) $("destinationWarehouse").selectedIndex = 1;
    }
    async function refreshTransfers() {
      const transfers = await api("/api/transfers?limit=50");
      $("transferList").innerHTML = transfers.map((transfer) => `
        <div class="item ${transfer.transfer_uid === state.activeTransferUid ? "active" : ""}">
          <div class="item-head">
            <strong class="mono">${escapeHtml(transfer.transfer_uid)}</strong>
            <span class="badge ${escapeHtml(transfer.status)}">${escapeHtml(label(transferStatusLabels, transfer.status))}</span>
          </div>
          <div class="meta">${escapeHtml(transfer.source_warehouse_code)} → ${escapeHtml(transfer.destination_warehouse_code)} · ${transfer.pallet_count} пал.</div>
          <button class="secondary" data-select-transfer="${escapeHtml(transfer.transfer_uid)}">Выбрать</button>
        </div>
      `).join("") || `<div class="item">Перемещений пока нет</div>`;
      document.querySelectorAll("[data-select-transfer]").forEach((button) => {
        button.addEventListener("click", () => selectTransfer(button.dataset.selectTransfer).catch(showError));
      });
    }
    async function refreshAvailable() {
      const sourceCode = state.active?.source_warehouse_code || $("sourceWarehouse").value;
      if (!sourceCode) return;
      const pallets = await api(`/api/pallets?status=available&warehouse_code=${encodeURIComponent(sourceCode)}&limit=200`);
      const canAdd = !state.active || ["draft", "reserved"].includes(state.active.status);
      $("availablePallets").innerHTML = pallets.map((pallet) => `
        <div class="item">
          <div class="item-head">
            <a class="mono" href="/cards?kind=pallet&code=${encodeURIComponent(pallet.pallet_uid)}">${escapeHtml(pallet.pallet_uid)}</a>
            <span class="badge">${pallet.box_count} кор.</span>
          </div>
          <div class="meta">${escapeHtml(pallet.current_location_code || "-")}</div>
          <button data-add-pallet="${escapeHtml(pallet.pallet_uid)}" ${canAdd && state.active ? "" : "disabled"}>В перемещение</button>
        </div>
      `).join("") || `<div class="item">Доступных палет на ${escapeHtml(sourceCode)} нет</div>`;
      document.querySelectorAll("[data-add-pallet]").forEach((button) => {
        button.addEventListener("click", () => addPallet(button.dataset.addPallet).catch(showError));
      });
    }
    function updateControls() {
      const status = state.active?.status || "";
      $("expeditionBtn").disabled = status !== "reserved";
      $("dispatchBtn").disabled = status !== "loading";
      const loading = ["expedition", "loading"].includes(status);
      const receiving = ["in_transit", "receiving"].includes(status);
      $("scanInput").disabled = !loading && !receiving;
      $("scanLabel").textContent = receiving ? "Скан приёмки на складе назначения" : "Скан погрузки";
      $("scanInput").placeholder = receiving ? "Принятая палета и Enter" : "Погружаемая палета и Enter";
      $("destinationWarehouseLink").hidden = status !== "completed";
    }
    async function refreshActive() {
      if (!state.activeTransferUid) {
        state.active = null;
        $("activeTransfer").textContent = "-";
        $("activeStatus").textContent = "-";
        $("sourceCode").textContent = "-";
        $("destinationCode").textContent = "-";
        $("transferPallets").innerHTML = `<div class="item">Документ не выбран</div>`;
        $("transferEvents").innerHTML = `<div class="item">Истории пока нет</div>`;
        updateControls();
        return;
      }
      const [transfer, pallets, events] = await Promise.all([
        api(`/api/transfers/${state.activeTransferUid}`),
        api(`/api/transfers/${state.activeTransferUid}/pallets`),
        api(`/api/transfers/${state.activeTransferUid}/events?limit=50`),
      ]);
      state.active = transfer;
      $("activeTransfer").textContent = transfer.transfer_uid;
      $("activeStatus").textContent = label(transferStatusLabels, transfer.status);
      $("sourceCode").textContent = transfer.source_warehouse_code;
      $("destinationCode").textContent = transfer.destination_warehouse_code;
      $("loadedCount").textContent = `${transfer.loaded_count} / ${transfer.pallet_count}`;
      $("receivedCount").textContent = `${transfer.received_count} / ${transfer.pallet_count}`;
      $("destinationWarehouseLink").href = `/scan?warehouse=${encodeURIComponent(transfer.destination_warehouse_code)}`;
      $("transferPallets").innerHTML = pallets.map((row) => {
        const canLoad = ["expedition", "loading"].includes(transfer.status) && row.transfer_pallet_status === "expedition";
        const canReceive = ["in_transit", "receiving"].includes(transfer.status) && row.transfer_pallet_status === "in_transit";
        return `
          <div class="item">
            <div class="item-head">
              <a class="mono" href="/cards?kind=pallet&code=${encodeURIComponent(row.pallet.pallet_uid)}">${escapeHtml(row.pallet.pallet_uid)}</a>
              <span class="badge ${escapeHtml(row.transfer_pallet_status)}">${escapeHtml(label(palletStatusLabels, row.transfer_pallet_status))}</span>
            </div>
            <div class="meta">Исходная ячейка: ${escapeHtml(row.source_location_code || "-")} · ${row.pallet.box_count} кор.</div>
            ${canLoad ? `<button data-load-pallet="${escapeHtml(row.pallet.pallet_uid)}">Погрузить</button>` : ""}
            ${canReceive ? `<button data-receive-pallet="${escapeHtml(row.pallet.pallet_uid)}">Принять</button>` : ""}
          </div>`;
      }).join("") || `<div class="item">Палеты пока не выбраны</div>`;
      document.querySelectorAll("[data-load-pallet]").forEach((button) => {
        button.addEventListener("click", () => loadPallet(button.dataset.loadPallet).catch(showError));
      });
      document.querySelectorAll("[data-receive-pallet]").forEach((button) => {
        button.addEventListener("click", () => receivePallet(button.dataset.receivePallet).catch(showError));
      });
      $("transferEvents").innerHTML = events.map((event) => `
        <div class="item">
          <strong>${escapeHtml(label(operationLabels, event.operation))}</strong>
          <div class="meta">${escapeHtml(event.actor)} · ${new Date(event.created_at).toLocaleString()}</div>
          ${event.reason ? `<div class="meta">Причина: ${escapeHtml(event.reason)}</div>` : ""}
        </div>
      `).join("") || `<div class="item">Истории пока нет</div>`;
      updateControls();
    }
    async function refreshAll() {
      await refreshTransfers();
      await refreshActive();
      await refreshAvailable();
    }
    function showError(error) { setStatus(error.message, "err"); focusScan(); }
    async function selectTransfer(uid) {
      state.activeTransferUid = uid;
      await refreshAll();
      setStatus(`Выбрано перемещение ${uid}`, "ok");
      focusScan();
    }
    async function createTransfer() {
      const source = $("sourceWarehouse").value;
      const destination = $("destinationWarehouse").value;
      if (!source || !destination || source === destination) throw new Error("Выберите два разных склада");
      const transfer = await post("/api/transfers", {
        actor: actor(), source_warehouse_code: source, destination_warehouse_code: destination,
        vehicle_number: $("vehicleNumber").value.trim() || null,
      });
      state.activeTransferUid = transfer.transfer_uid;
      await refreshAll();
      setStatus(`Создано перемещение ${transfer.transfer_uid}`, "ok");
    }
    async function addPallet(uid) {
      if (!state.activeTransferUid) throw new Error("Сначала создайте или выберите перемещение");
      await post(`/api/transfers/${state.activeTransferUid}/pallets/${encodeURIComponent(uid)}`, { actor: actor() });
      await refreshAll();
      setStatus(`Палета зарезервирована: ${uid}`, "ok");
    }
    async function toExpedition() {
      await post(`/api/transfers/${state.activeTransferUid}/expedition`, { actor: actor() });
      await refreshAll();
      setStatus("Исходные ячейки освобождены, палеты в зоне отправки", "ok");
    }
    async function loadPallet(uid) {
      await post(`/api/transfers/${state.activeTransferUid}/load/${encodeURIComponent(uid)}`, { actor: actor() });
      await refreshAll();
      setStatus(`Палета погружена: ${uid}`, "ok");
    }
    async function dispatchTransfer() {
      await post(`/api/transfers/${state.activeTransferUid}/dispatch`, { actor: actor(), reason: "межскладская отправка" });
      await refreshAll();
      setStatus("Машина отправлена, палеты имеют статус «В пути»", "ok");
    }
    async function receivePallet(uid) {
      await post(`/api/transfers/${state.activeTransferUid}/receive/${encodeURIComponent(uid)}`, { actor: actor() });
      await refreshAll();
      setStatus(`Палета принята: ${uid}`, "ok");
    }
    $("createBtn").addEventListener("click", () => createTransfer().catch(showError));
    $("refreshBtn").addEventListener("click", () => refreshAll().catch(showError));
    $("refreshAvailableBtn").addEventListener("click", () => refreshAvailable().catch(showError));
    $("sourceWarehouse").addEventListener("change", () => refreshAvailable().catch(showError));
    $("expeditionBtn").addEventListener("click", () => toExpedition().catch(showError));
    $("dispatchBtn").addEventListener("click", () => dispatchTransfer().catch(showError));
    $("scanInput").addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      event.preventDefault();
      const uid = event.currentTarget.value.trim();
      event.currentTarget.value = "";
      if (!uid) return;
      const receiving = ["in_transit", "receiving"].includes(state.active?.status);
      (receiving ? receivePallet(uid) : loadPallet(uid)).catch(showError);
    });
    loadWarehouses().then(refreshAll).then(focusScan).catch(showError);
  </script>
</body>
</html>"""
