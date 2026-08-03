from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.page_shell import standard_page


router = APIRouter()


@router.get("/settings", response_class=HTMLResponse, include_in_schema=False)
@standard_page("settings")
def settings_page() -> str:
    return """<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Настройки Simple WMS</title>
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
      --danger: #a9362a;
      --dark: #111820;
    }
    * { box-sizing: border-box; }
    body { margin: 0; background: var(--bg); color: var(--text); font: 14px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    button, input, select { font: inherit; }
    button:focus-visible, input:focus-visible, select:focus-visible, a:focus-visible { outline: 3px solid #f4b740; outline-offset: 2px; }
    main { width: min(1360px, 100%); margin: 0 auto; padding: 20px; }
    h1, h2, h3, p { margin-top: 0; }
    h1 { margin-bottom: 4px; font-size: 26px; letter-spacing: 0; }
    h2 { margin-bottom: 0; font-size: 18px; letter-spacing: 0; }
    h3 { margin-bottom: 10px; font-size: 15px; letter-spacing: 0; }
    .page-head { margin-bottom: 14px; display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; }
    .muted, .status { color: var(--muted); }
    .tabs { display: flex; gap: 0; border-bottom: 1px solid var(--line); background: var(--panel); }
    .tab { min-height: 44px; padding: 9px 15px; border: 0; border-right: 1px solid var(--line); border-radius: 0; background: #fff; color: var(--text); cursor: pointer; font-weight: 800; }
    .tab.active { color: var(--accent-dark); background: var(--accent-soft); box-shadow: inset 0 -3px 0 var(--accent); }
    .view { display: none; }
    .view.active { display: block; }
    .layout { display: grid; grid-template-columns: 370px minmax(0, 1fr); border: 1px solid var(--line); border-top: 0; background: var(--panel); }
    aside { min-width: 0; padding: 16px; border-right: 1px solid var(--line); background: var(--soft); }
    .content { min-width: 0; }
    .content-head { min-height: 58px; padding: 13px 15px; display: flex; align-items: center; justify-content: space-between; gap: 12px; border-bottom: 1px solid var(--line); }
    .form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .wide { grid-column: 1 / -1; }
    label { display: block; margin-bottom: 4px; color: var(--muted); font-size: 10px; font-weight: 900; text-transform: uppercase; }
    input, select, button { min-height: 40px; border: 1px solid var(--line); border-radius: 5px; padding: 8px 10px; background: #fff; color: var(--text); }
    input, select { width: 100%; }
    select[multiple] { min-height: 112px; }
    button { cursor: pointer; font-weight: 800; }
    button.primary { border-color: var(--accent); background: var(--accent); color: #fff; }
    button.primary:hover { background: var(--accent-dark); }
    button.secondary { border-color: #9bcfc8; background: var(--accent-soft); color: var(--accent-dark); }
    button.compact { min-height: 32px; padding: 5px 9px; }
    .checks { display: flex; flex-wrap: wrap; gap: 10px 14px; }
    .checks label { display: inline-flex; align-items: center; gap: 6px; margin: 0; color: var(--text); font-size: 12px; text-transform: none; }
    .checks input { width: 17px; min-height: 17px; margin: 0; }
    .actions { display: flex; gap: 8px; }
    .status { min-height: 20px; margin: 10px 0 0; font-size: 12px; }
    .status.error { color: var(--danger); }
    .table-wrap { overflow-x: auto; }
    table { width: 100%; border-collapse: collapse; }
    th, td { padding: 10px 11px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: middle; }
    th { color: var(--muted); background: var(--soft); font-size: 10px; text-transform: uppercase; }
    tr.selected td { background: #f0faf8; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-weight: 800; }
    .badge { display: inline-flex; padding: 3px 7px; border-radius: 4px; color: #40515a; background: #e8edef; font-size: 10px; font-weight: 900; }
    .badge.default { color: var(--accent-dark); background: var(--accent-soft); }
    .empty { padding: 28px 16px; color: var(--muted); text-align: center; }
    @media (max-width: 900px) {
      main { padding: 12px; }
      .layout { grid-template-columns: 1fr; }
      aside { border-right: 0; border-bottom: 1px solid var(--line); }
      .tabs { overflow-x: auto; }
    }
    @media (max-width: 560px) {
      main { padding: 8px; }
      h1 { font-size: 22px; }
      .page-head { align-items: flex-start; flex-direction: column; }
      .form-grid { grid-template-columns: 1fr; }
      .wide { grid-column: auto; }
      .content-head { align-items: flex-start; flex-direction: column; }
    }
  </style>
</head>
<body>
  <header><h1>WMS</h1></header>
  <main>
    <div class="page-head">
      <div>
        <h1>Настройки</h1>
        <p class="muted">Справочники продукта и подключаемое оборудование.</p>
      </div>
      <button id="refreshBtn" class="secondary" type="button">Обновить</button>
    </div>

    <nav class="tabs" aria-label="Разделы настроек">
      <button class="tab active" type="button" data-tab="equipment">Оборудование</button>
      <button class="tab" type="button" data-tab="uom">Единицы измерения</button>
      <button class="tab" type="button" data-tab="types">Типы тары</button>
    </nav>

    <section id="equipmentView" class="view active">
      <div class="layout">
        <aside>
          <form id="equipmentForm" class="form-grid">
            <input id="equipmentId" type="hidden">
            <h2 class="wide" id="equipmentFormTitle">Новое устройство</h2>
            <div><label for="equipmentCode">Код</label><input id="equipmentCode" required maxlength="48" placeholder="ATOL_TT42"></div>
            <div><label for="equipmentName">Название</label><input id="equipmentName" required maxlength="160" placeholder="Термопринтер 47x25"></div>
            <div>
              <label for="equipmentKind">Тип</label>
              <select id="equipmentKind">
                <option value="printer">Принтер</option>
                <option value="scanner">Сканер</option>
                <option value="terminal">ТСД</option>
                <option value="scale">Весы</option>
                <option value="other">Другое</option>
              </select>
            </div>
            <div>
              <label for="equipmentConnection">Подключение</label>
              <select id="equipmentConnection">
                <option value="raw_tcp">RAW TCP</option>
                <option value="system_queue">Системная очередь</option>
                <option value="pdf">PDF</option>
                <option value="keyboard">Клавиатура</option>
                <option value="web">Web</option>
                <option value="camera">Камера</option>
                <option value="serial">COM / Serial</option>
                <option value="usb">USB</option>
              </select>
            </div>
            <div><label for="equipmentManufacturer">Производитель</label><input id="equipmentManufacturer" maxlength="120"></div>
            <div><label for="equipmentModel">Модель</label><input id="equipmentModel" maxlength="120"></div>
            <div class="network-field"><label for="equipmentHost">IP / имя узла</label><input id="equipmentHost" maxlength="255" placeholder="192.168.10.204"></div>
            <div class="network-field"><label for="equipmentPort">Порт</label><input id="equipmentPort" type="number" min="1" max="65535" value="9100"></div>
            <div class="queue-field wide"><label for="equipmentQueue">Системная очередь</label><input id="equipmentQueue" maxlength="120"></div>
            <div class="serial-field wide"><label for="equipmentSerial">COM / устройство</label><input id="equipmentSerial" maxlength="160" placeholder="/dev/ttyUSB0"></div>
            <div><label for="equipmentDriver">Драйвер</label><input id="equipmentDriver" maxlength="80" placeholder="tspl_bitmap_47x25"></div>
            <div><label for="equipmentWarehouse">Склад</label><select id="equipmentWarehouse"></select></div>
            <div class="wide checks">
              <label><input id="equipmentDefault" type="checkbox"> По умолчанию</label>
              <label><input id="equipmentActive" type="checkbox" checked> Активно</label>
            </div>
            <div class="wide actions">
              <button class="primary" type="submit">Сохранить</button>
              <button id="equipmentResetBtn" class="secondary" type="button">Очистить</button>
            </div>
          </form>
          <p id="equipmentStatus" class="status"></p>
        </aside>
        <div class="content">
          <div class="content-head"><h2>Подключённые устройства</h2><span id="equipmentCount" class="muted"></span></div>
          <div class="table-wrap">
            <table>
              <thead><tr><th>Код</th><th>Тип</th><th>Устройство</th><th>Подключение</th><th>Склад</th><th></th></tr></thead>
              <tbody id="equipmentRows"></tbody>
            </table>
          </div>
        </div>
      </div>
    </section>

    <section id="uomView" class="view">
      <div class="layout">
        <aside>
          <form id="uomForm" class="form-grid">
            <h2 class="wide">Новая единица</h2>
            <div><label for="uomCode">Код</label><input id="uomCode" required maxlength="32" placeholder="KG"></div>
            <div><label for="uomSymbol">Обозначение</label><input id="uomSymbol" required maxlength="24" placeholder="кг"></div>
            <div class="wide"><label for="uomName">Название</label><input id="uomName" required maxlength="120" placeholder="Килограмм"></div>
            <div>
              <label for="uomDimension">Группа</label>
              <select id="uomDimension">
                <option value="quantity">Количество</option>
                <option value="mass">Масса</option>
                <option value="volume">Объём</option>
                <option value="length">Длина</option>
                <option value="area">Площадь</option>
              </select>
            </div>
            <div><label for="uomPrecision">Знаков после запятой</label><input id="uomPrecision" type="number" min="0" max="6" value="0"></div>
            <div class="wide"><label for="uomFactor">Коэффициент к базовой</label><input id="uomFactor" type="number" min="0.00000001" step="0.00000001" value="1"></div>
            <div class="wide checks"><label><input id="uomBase" type="checkbox"> Базовая единица группы</label></div>
            <button class="primary wide" type="submit">Добавить</button>
          </form>
          <p id="uomStatus" class="status"></p>
        </aside>
        <div class="content">
          <div class="content-head"><h2>Единицы измерения</h2><span id="uomCount" class="muted"></span></div>
          <div class="table-wrap">
            <table>
              <thead><tr><th>Код</th><th>Название</th><th>Группа</th><th>Точность</th><th>Коэффициент</th></tr></thead>
              <tbody id="uomRows"></tbody>
            </table>
          </div>
        </div>
      </div>
    </section>

    <section id="typesView" class="view">
      <div class="layout">
        <aside>
          <form id="typeForm" class="form-grid">
            <h2 class="wide">Новый тип тары</h2>
            <div><label for="typeCode">Код</label><input id="typeCode" required maxlength="32" placeholder="DRUM"></div>
            <div><label for="typePrefix">Префикс</label><input id="typePrefix" required maxlength="16" placeholder="DRM"></div>
            <div class="wide"><label for="typeName">Название</label><input id="typeName" required maxlength="120" placeholder="Бочка"></div>
            <div><label for="typeTare">Масса тары</label><input id="typeTare" type="number" min="0" step="0.001"></div>
            <div><label for="typeWeightUom">Единица массы</label><select id="typeWeightUom"></select></div>
            <div><label for="typeLength">Длина, мм</label><input id="typeLength" type="number" min="1"></div>
            <div><label for="typeWidth">Ширина, мм</label><input id="typeWidth" type="number" min="1"></div>
            <div><label for="typeHeight">Высота, мм</label><input id="typeHeight" type="number" min="1"></div>
            <div><label for="typeLabelProfile">Профиль этикетки</label><input id="typeLabelProfile" maxlength="80"></div>
            <div class="wide checks">
              <label><input id="typeGoods" type="checkbox" checked> Содержит товар</label>
              <label><input id="typeUnits" type="checkbox"> Содержит другие единицы</label>
              <label><input id="typeReturnable" type="checkbox"> Оборотная тара</label>
            </div>
            <div class="wide"><label for="typeChildren">Допустимые вложенные типы</label><select id="typeChildren" multiple></select></div>
            <button class="primary wide" type="submit">Добавить</button>
          </form>
          <p id="typeStatus" class="status"></p>
        </aside>
        <div class="content">
          <div class="content-head"><h2>Типы логистических единиц</h2><span id="typeCount" class="muted"></span></div>
          <div class="table-wrap">
            <table>
              <thead><tr><th>Код</th><th>Название</th><th>Префикс</th><th>Назначение</th><th>Вложенность</th></tr></thead>
              <tbody id="typeRows"></tbody>
            </table>
          </div>
        </div>
      </div>
    </section>
  </main>
  <script>
    const state = { warehouses: [], equipment: [], units: [], types: [] };
    const $ = (id) => document.getElementById(id);
    const valueOrNull = (value) => value === "" ? null : value;
    const numberOrNull = (value) => value === "" ? null : Number(value);

    async function api(path, options = {}) {
      const response = await fetch(path, {
        ...options,
        headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      });
      if (!response.ok) {
        let detail = `Ошибка ${response.status}`;
        try {
          const data = await response.json();
          detail = Array.isArray(data.detail) ? data.detail.map((row) => row.msg).join("; ") : (data.detail || detail);
        } catch (_) {}
        throw new Error(detail);
      }
      return response.json();
    }

    function setStatus(id, text, error = false) {
      const node = $(id);
      node.textContent = text;
      node.classList.toggle("error", error);
    }

    const kindLabels = { printer: "Принтер", scanner: "Сканер", terminal: "ТСД", scale: "Весы", other: "Другое" };
    const connectionLabels = {
      pdf: "PDF", system_queue: "Системная очередь", raw_tcp: "RAW TCP", keyboard: "Клавиатура",
      camera: "Камера", web: "Web", serial: "COM / Serial", usb: "USB",
    };
    const dimensionLabels = { quantity: "Количество", mass: "Масса", volume: "Объём", length: "Длина", area: "Площадь" };

    function warehouseName(id) {
      if (id === null) return "Общее";
      return state.warehouses.find((row) => row.id === id)?.code || `склад ${id}`;
    }

    function renderEquipment() {
      $("equipmentCount").textContent = `${state.equipment.length} шт.`;
      $("equipmentRows").innerHTML = state.equipment.length ? state.equipment.map((item) => {
        const destination = item.connection_type === "raw_tcp"
          ? `${item.host}:${item.port}`
          : item.connection_type === "system_queue" ? item.queue_name : connectionLabels[item.connection_type];
        const device = [item.manufacturer, item.model].filter(Boolean).join(" ") || item.name;
        return `<tr class="${Number($("equipmentId").value) === item.id ? "selected" : ""}">
          <td><span class="mono">${item.code}</span>${item.is_default ? ' <span class="badge default">по умолчанию</span>' : ""}</td>
          <td>${kindLabels[item.device_kind] || item.device_kind}</td>
          <td>${device}</td>
          <td>${destination || "-"}</td>
          <td>${warehouseName(item.warehouse_id)}</td>
          <td><button class="compact secondary" type="button" data-edit-equipment="${item.id}">Изменить</button></td>
        </tr>`;
      }).join("") : '<tr><td colspan="6" class="empty">Устройства не настроены</td></tr>';
    }

    function renderUnits() {
      $("uomCount").textContent = `${state.units.length} шт.`;
      $("uomRows").innerHTML = state.units.map((item) => `<tr>
        <td class="mono">${item.code}</td><td>${item.name} (${item.symbol})</td>
        <td>${dimensionLabels[item.dimension] || item.dimension}${item.is_base ? ' <span class="badge default">базовая</span>' : ""}</td>
        <td>${item.decimal_precision}</td><td>${item.factor_to_base}</td>
      </tr>`).join("");
      const massUnits = state.units.filter((item) => item.dimension === "mass" && item.is_active);
      $("typeWeightUom").innerHTML = '<option value="">Не выбрана</option>' + massUnits.map((item) => `<option value="${item.id}">${item.code} — ${item.symbol}</option>`).join("");
    }

    function renderTypes() {
      $("typeCount").textContent = `${state.types.length} шт.`;
      const names = Object.fromEntries(state.types.map((item) => [item.id, item.name]));
      $("typeRows").innerHTML = state.types.map((item) => {
        const purpose = [item.can_contain_goods ? "товар" : "", item.can_contain_units ? "единицы" : "", item.is_returnable ? "оборотная" : ""].filter(Boolean).join(", ");
        const children = item.allowed_child_type_ids.map((id) => names[id] || id).join(", ") || "без ограничения";
        return `<tr><td class="mono">${item.code}</td><td>${item.name}</td><td class="mono">${item.identifier_prefix}</td><td>${purpose || "-"}</td><td>${children}</td></tr>`;
      }).join("");
      $("typeChildren").innerHTML = state.types.map((item) => `<option value="${item.id}">${item.code} — ${item.name}</option>`).join("");
    }

    function fillWarehouseOptions() {
      $("equipmentWarehouse").innerHTML = '<option value="">Общее устройство</option>' + state.warehouses.map((item) => `<option value="${item.id}">${item.code} — ${item.name}</option>`).join("");
    }

    function syncConnectionFields() {
      const connection = $("equipmentConnection").value;
      document.querySelectorAll(".network-field").forEach((node) => node.hidden = connection !== "raw_tcp");
      document.querySelectorAll(".queue-field").forEach((node) => node.hidden = connection !== "system_queue");
      document.querySelectorAll(".serial-field").forEach((node) => node.hidden = connection !== "serial");
    }

    function resetEquipmentForm() {
      $("equipmentForm").reset();
      $("equipmentId").value = "";
      $("equipmentPort").value = "9100";
      $("equipmentConnection").value = "raw_tcp";
      $("equipmentActive").checked = true;
      $("equipmentFormTitle").textContent = "Новое устройство";
      syncConnectionFields();
      renderEquipment();
      setStatus("equipmentStatus", "");
    }

    function editEquipment(id) {
      const item = state.equipment.find((row) => row.id === id);
      if (!item) return;
      $("equipmentId").value = item.id;
      $("equipmentCode").value = item.code;
      $("equipmentName").value = item.name;
      $("equipmentKind").value = item.device_kind;
      $("equipmentConnection").value = item.connection_type;
      $("equipmentManufacturer").value = item.manufacturer || "";
      $("equipmentModel").value = item.model || "";
      $("equipmentHost").value = item.host || "";
      $("equipmentPort").value = item.port || "";
      $("equipmentQueue").value = item.queue_name || "";
      $("equipmentSerial").value = item.serial_device || "";
      $("equipmentDriver").value = item.driver_code || "";
      $("equipmentWarehouse").value = item.warehouse_id || "";
      $("equipmentDefault").checked = item.is_default;
      $("equipmentActive").checked = item.is_active;
      $("equipmentFormTitle").textContent = `Устройство ${item.code}`;
      syncConnectionFields();
      renderEquipment();
      window.scrollTo({ top: 0, behavior: "smooth" });
    }

    async function loadAll() {
      try {
        [state.warehouses, state.equipment, state.units, state.types] = await Promise.all([
          api("/api/warehouses"), api("/api/equipment-profiles"), api("/api/units-of-measure"), api("/api/logistic-unit-types"),
        ]);
        fillWarehouseOptions();
        renderEquipment();
        renderUnits();
        renderTypes();
      } catch (error) {
        setStatus("equipmentStatus", error.message, true);
      }
    }

    document.querySelectorAll(".tab").forEach((button) => button.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((item) => item.classList.toggle("active", item === button));
      document.querySelectorAll(".view").forEach((view) => view.classList.remove("active"));
      $(`${button.dataset.tab}View`).classList.add("active");
    }));
    $("equipmentConnection").addEventListener("change", syncConnectionFields);
    $("equipmentResetBtn").addEventListener("click", resetEquipmentForm);
    $("refreshBtn").addEventListener("click", loadAll);
    $("equipmentRows").addEventListener("click", (event) => {
      const button = event.target.closest("[data-edit-equipment]");
      if (button) editEquipment(Number(button.dataset.editEquipment));
    });

    $("equipmentForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      const id = Number($("equipmentId").value) || null;
      const payload = {
        code: $("equipmentCode").value,
        name: $("equipmentName").value,
        device_kind: $("equipmentKind").value,
        manufacturer: valueOrNull($("equipmentManufacturer").value),
        model: valueOrNull($("equipmentModel").value),
        connection_type: $("equipmentConnection").value,
        host: valueOrNull($("equipmentHost").value),
        port: numberOrNull($("equipmentPort").value),
        queue_name: valueOrNull($("equipmentQueue").value),
        serial_device: valueOrNull($("equipmentSerial").value),
        driver_code: valueOrNull($("equipmentDriver").value),
        warehouse_id: numberOrNull($("equipmentWarehouse").value),
        parameters: {},
        is_default: $("equipmentDefault").checked,
      };
      if (id) payload.is_active = $("equipmentActive").checked;
      try {
        await api(id ? `/api/equipment-profiles/${id}` : "/api/equipment-profiles", {
          method: id ? "PUT" : "POST",
          body: JSON.stringify(payload),
        });
        resetEquipmentForm();
        await loadAll();
        setStatus("equipmentStatus", "Профиль сохранён");
      } catch (error) {
        setStatus("equipmentStatus", error.message, true);
      }
    });

    $("uomForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        await api("/api/units-of-measure", {
          method: "POST",
          body: JSON.stringify({
            code: $("uomCode").value,
            name: $("uomName").value,
            symbol: $("uomSymbol").value,
            dimension: $("uomDimension").value,
            decimal_precision: Number($("uomPrecision").value),
            factor_to_base: $("uomFactor").value,
            is_base: $("uomBase").checked,
          }),
        });
        $("uomForm").reset();
        $("uomFactor").value = "1";
        await loadAll();
        setStatus("uomStatus", "Единица добавлена");
      } catch (error) {
        setStatus("uomStatus", error.message, true);
      }
    });

    $("typeForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      const childIds = Array.from($("typeChildren").selectedOptions).map((option) => Number(option.value));
      try {
        await api("/api/logistic-unit-types", {
          method: "POST",
          body: JSON.stringify({
            code: $("typeCode").value,
            name: $("typeName").value,
            identifier_prefix: $("typePrefix").value,
            tare_weight: valueOrNull($("typeTare").value),
            tare_weight_uom_id: numberOrNull($("typeWeightUom").value),
            length_mm: numberOrNull($("typeLength").value),
            width_mm: numberOrNull($("typeWidth").value),
            height_mm: numberOrNull($("typeHeight").value),
            can_contain_goods: $("typeGoods").checked,
            can_contain_units: $("typeUnits").checked,
            is_returnable: $("typeReturnable").checked,
            label_profile: valueOrNull($("typeLabelProfile").value),
            allowed_child_type_ids: childIds,
          }),
        });
        $("typeForm").reset();
        $("typeGoods").checked = true;
        await loadAll();
        setStatus("typeStatus", "Тип добавлен");
      } catch (error) {
        setStatus("typeStatus", error.message, true);
      }
    });

    syncConnectionFields();
    loadAll();
  </script>
</body>
</html>"""
