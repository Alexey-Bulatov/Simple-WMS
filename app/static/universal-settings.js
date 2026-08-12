(() => {
  const $ = (id) => document.getElementById(id);
  const state = { user: null, warehouses: [], users: [], workstations: [], equipment: [] };

  const roleLabels = {
    production_operator: "Оператор производства",
    receiving_clerk: "Оператор приёмки",
    warehouse_clerk: "Кладовщик",
    shipping_operator: "Оператор отгрузки",
    senior_clerk: "Старший кладовщик",
    warehouse_manager: "Руководитель склада",
    admin: "Администратор",
    auditor: "Аудитор",
    integration: "Интеграция",
  };
  const kindLabels = { printer: "Принтер", scanner: "Сканер", terminal: "ТСД", scale: "Весы", other: "Другое" };
  const connectionLabels = { pdf: "PDF", system_queue: "Системная очередь", raw_tcp: "RAW TCP", keyboard: "Клавиатура", camera: "Камера", web: "Веб", serial: "COM / Serial", usb: "USB" };

  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);

  function errorText(body) {
    if (Array.isArray(body.detail)) return body.detail.map((item) => item.msg).join("; ");
    return body.detail || "Операция не выполнена";
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {
      ...options,
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    });
    if (response.status === 204) return null;
    const body = await response.json().catch(() => ({}));
    if (response.status === 401) {
      location.href = `/login?next=${encodeURIComponent(location.pathname)}`;
      throw new Error("Требуется вход");
    }
    if (!response.ok) throw new Error(errorText(body));
    return body;
  }

  function message(text, error = false) {
    $("settingsMessage").textContent = text;
    $("settingsMessage").classList.toggle("error", error);
  }

  function row({ kind, id, title, meta, side, active = true }) {
    return `<button class="settings-row" data-edit-kind="${kind}" data-edit-id="${id}" type="button"><span class="settings-row-main"><span class="settings-row-title"><i class="status-dot ${active ? "" : "off"}"></i>${esc(title)}</span><span class="settings-row-meta">${esc(meta)}</span></span><span class="settings-row-side">${side}</span></button>`;
  }

  function empty(text) {
    return `<div class="empty-list">${esc(text)}</div>`;
  }

  function warehouseOptions(selected = "", includeGeneral = false) {
    const prefix = includeGeneral ? '<option value="">Общий профиль</option>' : '<option value="">Выберите склад</option>';
    return prefix + state.warehouses.map((item) => `<option value="${item.id}" ${String(item.id) === String(selected) ? "selected" : ""}>${esc(item.code)} · ${esc(item.name)}</option>`).join("");
  }

  function renderWarehouses() {
    $("warehouseList").innerHTML = state.warehouses.length ? state.warehouses.map((item) => row({
      kind: "warehouse", id: item.id, title: `${item.code} · ${item.name}`,
      meta: `${item.city || "Город не указан"} · ${item.timezone}`,
      side: '<small>Изменить</small>',
    })).join("") : empty("Складов пока нет");
    $("workstationWarehouse").innerHTML = warehouseOptions($("workstationWarehouse").value);
    $("equipmentWarehouse").innerHTML = warehouseOptions($("equipmentWarehouse").value, true);
    renderUserWarehouseControls();
  }

  function renderUserWarehouseControls(selectedIds = null, defaultId = null) {
    const selected = new Set((selectedIds ?? Array.from(document.querySelectorAll('[name="userWarehouse"]:checked')).map((node) => Number(node.value))).map(Number));
    $("userWarehouses").innerHTML = state.warehouses.length ? state.warehouses.map((item) => `<label class="check-row"><input name="userWarehouse" type="checkbox" value="${item.id}" ${selected.has(item.id) ? "checked" : ""}><span>${esc(item.code)} · ${esc(item.name)}</span></label>`).join("") : '<span class="muted">Сначала создайте склад.</span>';
    $("userDefaultWarehouse").innerHTML = '<option value="">Не выбран</option>' + state.warehouses.filter((item) => selected.has(item.id)).map((item) => `<option value="${item.id}" ${String(item.id) === String(defaultId) ? "selected" : ""}>${esc(item.code)}</option>`).join("");
  }

  function selectedWarehouseIds() {
    return Array.from(document.querySelectorAll('[name="userWarehouse"]:checked')).map((node) => Number(node.value));
  }

  function renderUsers() {
    $("userList").innerHTML = state.users.length ? state.users.map((item) => row({
      kind: "user", id: item.id, title: `${item.full_name} · ${item.username}`,
      meta: `${roleLabels[item.role] || item.role} · ${item.warehouse_codes.join(", ") || (item.role === "admin" ? "Все склады" : "Без склада")}`,
      side: `<span class="badge ${item.must_change_password ? "in_progress" : "completed"}">${item.must_change_password ? "Смена пароля" : "Готов"}</span>`,
      active: item.is_active,
    })).join("") : empty("Пользователей пока нет");
  }

  function renderWorkstations() {
    $("workstationList").innerHTML = state.workstations.length ? state.workstations.map((item) => row({
      kind: "workstation", id: item.id, title: `${item.code} · ${item.name}`,
      meta: `${item.warehouse_code} · ${item.pass_login_enabled ? "Вход по коду разрешён" : "Только пароль"}`,
      side: '<small>Изменить</small>', active: item.is_active,
    })).join("") : empty("Рабочих мест пока нет");
  }

  function equipmentAddress(item) {
    if (item.connection_type === "raw_tcp") return `${item.host}:${item.port}`;
    if (item.connection_type === "system_queue") return item.queue_name;
    if (item.connection_type === "serial") return item.serial_device;
    return connectionLabels[item.connection_type] || item.connection_type;
  }

  function renderEquipment() {
    const warehouses = new Map(state.warehouses.map((item) => [item.id, item.code]));
    $("equipmentList").innerHTML = state.equipment.length ? state.equipment.map((item) => row({
      kind: "equipment", id: item.id, title: `${item.code} · ${item.name}`,
      meta: `${kindLabels[item.device_kind] || item.device_kind} · ${equipmentAddress(item) || "Параметры не заданы"} · ${warehouses.get(item.warehouse_id) || "Общий"}`,
      side: item.is_default ? '<span class="badge completed">По умолчанию</span>' : '<small>Изменить</small>', active: item.is_active,
    })).join("") : empty("Профилей оборудования пока нет");
  }

  function resetWarehouse() {
    $("warehouseForm").reset(); $("warehouseId").value = ""; $("warehouseCode").value = "WH01"; $("warehouseName").value = "Основной склад"; $("warehouseTimezone").value = "Europe/Moscow"; $("warehouseCode").readOnly = false; $("warehouseFormTitle").textContent = "Новый склад";
  }

  function resetUser() {
    $("userForm").reset(); $("userId").value = ""; $("userUsername").readOnly = false; $("userPassword").required = true; $("userPasswordLabel").hidden = false; $("userActive").checked = true; $("userActive").disabled = true; $("userFormTitle").textContent = "Новый пользователь"; renderUserWarehouseControls([], null);
  }

  function resetWorkstation() {
    $("workstationForm").reset(); $("workstationId").value = ""; $("workstationCode").readOnly = false; $("workstationActive").checked = true; $("workstationPass").checked = true; $("workstationFormTitle").textContent = "Новое рабочее место"; $("workstationWarehouse").innerHTML = warehouseOptions();
  }

  function resetEquipment() {
    $("equipmentForm").reset(); $("equipmentId").value = ""; $("equipmentCode").readOnly = false; $("equipmentConnection").value = "raw_tcp"; $("equipmentKind").value = "printer"; $("equipmentParameters").value = "{}"; $("equipmentActive").checked = true; $("equipmentFormTitle").textContent = "Новый профиль оборудования"; $("equipmentWarehouse").innerHTML = warehouseOptions("", true); updateConnectionFields();
  }

  function editWarehouse(id) {
    const item = state.warehouses.find((row) => row.id === id); if (!item) return;
    $("warehouseId").value = item.id; $("warehouseCode").value = item.code; $("warehouseCode").readOnly = true; $("warehouseName").value = item.name; $("warehouseCity").value = item.city || ""; $("warehouseTimezone").value = item.timezone; $("warehouseFormTitle").textContent = `Склад ${item.code}`; $("warehouseName").focus();
  }

  function editUser(id) {
    const item = state.users.find((row) => row.id === id); if (!item) return;
    $("userId").value = item.id; $("userUsername").value = item.username; $("userUsername").readOnly = true; $("userFullName").value = item.full_name; $("userRole").value = item.role; $("userPassword").required = false; $("userPasswordLabel").hidden = true; $("userActive").disabled = false; $("userActive").checked = item.is_active; $("userFormTitle").textContent = item.full_name; renderUserWarehouseControls(item.warehouse_ids, item.default_warehouse_id); $("userFullName").focus();
  }

  function editWorkstation(id) {
    const item = state.workstations.find((row) => row.id === id); if (!item) return;
    $("workstationId").value = item.id; $("workstationCode").value = item.code; $("workstationCode").readOnly = true; $("workstationName").value = item.name; $("workstationWarehouse").innerHTML = warehouseOptions(item.warehouse_id); $("workstationPass").checked = item.pass_login_enabled; $("workstationActive").checked = item.is_active; $("workstationFormTitle").textContent = item.name; $("workstationName").focus();
  }

  function editEquipment(id) {
    const item = state.equipment.find((row) => row.id === id); if (!item) return;
    $("equipmentId").value = item.id; $("equipmentCode").value = item.code; $("equipmentCode").readOnly = true; $("equipmentName").value = item.name; $("equipmentKind").value = item.device_kind; $("equipmentConnection").value = item.connection_type; $("equipmentManufacturer").value = item.manufacturer || ""; $("equipmentModel").value = item.model || ""; $("equipmentWarehouse").innerHTML = warehouseOptions(item.warehouse_id || "", true); $("equipmentDriver").value = item.driver_code || ""; $("equipmentHost").value = item.host || ""; $("equipmentPort").value = item.port || ""; $("equipmentQueue").value = item.queue_name || ""; $("equipmentSerial").value = item.serial_device || ""; $("equipmentParameters").value = JSON.stringify(item.parameters || {}, null, 2); $("equipmentDefault").checked = item.is_default; $("equipmentActive").checked = item.is_active; $("equipmentFormTitle").textContent = item.name; updateConnectionFields(); $("equipmentName").focus();
  }

  function updateConnectionFields() {
    const type = $("equipmentConnection").value;
    document.querySelectorAll("[data-connection-field]").forEach((node) => {
      const field = node.dataset.connectionField;
      node.hidden = !((field === "network" && type === "raw_tcp") || (field === "queue" && type === "system_queue") || (field === "serial" && type === "serial"));
    });
  }

  async function reloadAll(successText = "Настройки загружены.") {
    const [warehouses, users, workstations, equipment] = await Promise.all([
      api("/api/warehouses"), api("/api/auth/admin/users"), api("/api/auth/admin/workstations"), api("/api/equipment-profiles"),
    ]);
    state.warehouses = warehouses; state.users = users; state.workstations = workstations; state.equipment = equipment;
    renderWarehouses(); renderUsers(); renderWorkstations(); renderEquipment(); message(successText);
  }

  function bindForms() {
    $("warehouseForm").addEventListener("submit", async (event) => {
      event.preventDefault(); const id = $("warehouseId").value;
      try {
        await api(id ? `/api/warehouses/${id}` : "/api/warehouses", { method: id ? "PUT" : "POST", body: JSON.stringify({ ...(id ? {} : { code: $("warehouseCode").value }), name: $("warehouseName").value, city: $("warehouseCity").value || null, timezone: $("warehouseTimezone").value }) });
        resetWarehouse(); await reloadAll("Склад сохранён.");
      } catch (error) { message(error.message, true); }
    });
    $("userForm").addEventListener("submit", async (event) => {
      event.preventDefault(); const id = $("userId").value; const warehouseIds = selectedWarehouseIds(); const defaultWarehouseId = $("userDefaultWarehouse").value ? Number($("userDefaultWarehouse").value) : null;
      try {
        const common = { full_name: $("userFullName").value, role: $("userRole").value, warehouse_ids: warehouseIds, default_warehouse_id: defaultWarehouseId };
        if (id) await api(`/api/auth/admin/users/${id}`, { method: "PUT", body: JSON.stringify({ ...common, is_active: $("userActive").checked }) });
        else await api("/api/auth/admin/users", { method: "POST", body: JSON.stringify({ ...common, username: $("userUsername").value, password: $("userPassword").value, must_change_password: true }) });
        resetUser(); await reloadAll("Пользователь сохранён.");
      } catch (error) { message(error.message, true); }
    });
    $("workstationForm").addEventListener("submit", async (event) => {
      event.preventDefault(); const id = $("workstationId").value;
      try {
        const common = { name: $("workstationName").value, warehouse_id: Number($("workstationWarehouse").value), pass_login_enabled: $("workstationPass").checked };
        await api(id ? `/api/auth/admin/workstations/${id}` : "/api/auth/admin/workstations", { method: id ? "PUT" : "POST", body: JSON.stringify(id ? { ...common, is_active: $("workstationActive").checked } : { ...common, code: $("workstationCode").value }) });
        resetWorkstation(); await reloadAll("Рабочее место сохранено.");
      } catch (error) { message(error.message, true); }
    });
    $("equipmentForm").addEventListener("submit", async (event) => {
      event.preventDefault(); const id = $("equipmentId").value;
      try {
        let parameters; try { parameters = JSON.parse($("equipmentParameters").value || "{}"); } catch (_) { throw new Error("Дополнительные параметры должны быть корректным JSON."); }
        const connection = $("equipmentConnection").value;
        const payload = { code: $("equipmentCode").value, name: $("equipmentName").value, device_kind: $("equipmentKind").value, manufacturer: $("equipmentManufacturer").value || null, model: $("equipmentModel").value || null, connection_type: connection, host: connection === "raw_tcp" ? $("equipmentHost").value || null : null, port: connection === "raw_tcp" && $("equipmentPort").value ? Number($("equipmentPort").value) : null, queue_name: connection === "system_queue" ? $("equipmentQueue").value || null : null, serial_device: connection === "serial" ? $("equipmentSerial").value || null : null, driver_code: $("equipmentDriver").value || null, warehouse_id: $("equipmentWarehouse").value ? Number($("equipmentWarehouse").value) : null, parameters, is_default: $("equipmentDefault").checked };
        if (id) payload.is_active = $("equipmentActive").checked;
        await api(id ? `/api/equipment-profiles/${id}` : "/api/equipment-profiles", { method: id ? "PUT" : "POST", body: JSON.stringify(payload) });
        resetEquipment(); await reloadAll("Профиль оборудования сохранён.");
      } catch (error) { message(error.message, true); }
    });
  }

  function bindControls() {
    document.querySelectorAll("[data-settings-tab]").forEach((button) => button.addEventListener("click", () => {
      const tab = button.dataset.settingsTab;
      document.querySelectorAll("[data-settings-tab]").forEach((item) => item.classList.toggle("active", item === button));
      document.querySelectorAll("[data-settings-view]").forEach((view) => { view.hidden = view.dataset.settingsView !== tab; });
      history.replaceState(null, "", `#${tab}`);
    }));
    $("warehouseReset").addEventListener("click", resetWarehouse); $("userReset").addEventListener("click", resetUser); $("workstationReset").addEventListener("click", resetWorkstation); $("equipmentReset").addEventListener("click", resetEquipment); $("equipmentConnection").addEventListener("change", updateConnectionFields);
    $("userWarehouses").addEventListener("change", () => renderUserWarehouseControls(selectedWarehouseIds(), $("userDefaultWarehouse").value));
    document.addEventListener("click", (event) => {
      const target = event.target.closest("[data-edit-kind]"); if (!target) return; const id = Number(target.dataset.editId);
      ({ warehouse: editWarehouse, user: editUser, workstation: editWorkstation, equipment: editEquipment })[target.dataset.editKind]?.(id);
    });
  }

  async function start() {
    bindForms(); bindControls(); resetWarehouse(); resetUser(); resetWorkstation(); resetEquipment();
    try {
      state.user = await api("/api/auth/me");
      if (state.user.role !== "admin") { message("Раздел доступен только администратору.", true); document.querySelectorAll("form button").forEach((button) => { button.disabled = true; }); return; }
      await reloadAll();
      const initial = document.querySelector(`[data-settings-tab="${location.hash.slice(1)}"]`); if (initial) initial.click();
    } catch (error) { message(error.message, true); }
  }

  start();
})();
