(() => {
  const $ = (id) => document.getElementById(id);
  const state = { user: null, warehouses: [], recipients: [], uoms: [], issues: [], result: null, item: null, position: null, returnIssue: null, canManageCatalog: false };
  const recipientLabels = { employee: "Сотрудник", department: "Подразделение", workplace: "Рабочее место" };
  const statusLabels = { posted: "Проведена", reversed: "Исправлена", released: "Годен", quarantine: "Карантин" };
  const dimensionLabels = { quantity: "Количество", mass: "Масса", volume: "Объём", length: "Длина", area: "Площадь" };
  const accountabilityLabels = { not_applicable: "Без возврата", open: "На ответственности", partial: "Возвращено частично", returned: "Возвращено", written_off: "Списано по нормативу", closed_mixed: "Закрыто возвратом и списанием" };
  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
  const number = (value) => Number(value || 0).toLocaleString("ru-RU", { maximumFractionDigits: 6 });

  function errorText(body) {
    if (Array.isArray(body.detail)) return body.detail.map((item) => item.msg).join("; ");
    return body.detail || "Операция не выполнена";
  }
  async function api(path, options = {}) {
    const response = await fetch(path, { ...options, headers: { "Content-Type": "application/json", ...(options.headers || {}) } });
    const body = await response.json().catch(() => ({}));
    if (response.status === 401) {
      location.href = `/login?next=${encodeURIComponent(location.pathname)}`;
      throw new Error("Требуется вход");
    }
    if (!response.ok) throw new Error(errorText(body));
    return body;
  }
  function message(id, text, kind = "") {
    $(id).className = `message ${kind}`;
    $(id).textContent = text;
  }
  function fact(label, value) { return `<div class="fact"><b>${esc(label)}</b><span>${esc(value)}</span></div>`; }
  function sourceLabel(position) { return position.logistic_unit_uid || position.location_code || "Без держателя"; }
  function itemCodeForScan(item) {
    const matched = item.packagings.find((packaging) => packaging.matched);
    return matched?.barcode || matched?.code || item.product_code;
  }
  function uomOptions(items) {
    return items.map((uom) => `<option value="${uom.id}">${esc(uom.name)} (${esc(uom.symbol)}) · ${esc(dimensionLabels[uom.dimension] || uom.dimension)}</option>`).join("");
  }
  function compatibleUoms(item) {
    return state.uoms.filter((uom) => uom.dimension === item.base_uom_dimension);
  }
  function dateAfterDays(days) {
    const result = new Date();
    result.setDate(result.getDate() + Number(days));
    return result.toISOString().slice(0, 10);
  }
  function selectedIssueMode() {
    const [issueKind, accountabilityPolicy] = $("issueKind").value.split(":");
    return { issueKind, accountabilityPolicy: accountabilityPolicy || null };
  }

  function renderSearchResults() {
    const items = state.result?.items || [];
    if (!items.length) {
      $("stockSearchResults").innerHTML = '<div class="empty-list">Номенклатура не найдена</div>';
      return;
    }
    $("stockSearchResults").innerHTML = items.map((item) => `<button class="stock-result-row ${state.item?.product_id === item.product_id ? "selected" : ""}" data-product-id="${item.product_id}" type="button"><span><strong>${esc(item.product_name)}</strong><small class="mono">${esc(item.product_code)}</small></span><span class="stock-result-quantity"><b>${number(item.available_quantity)}</b><small>${esc(item.base_uom_symbol || item.base_uom_code || "")}</small></span></button>`).join("");
  }

  function renderDetail(item) {
    state.item = item;
    renderSearchResults();
    const uom = item.base_uom_symbol || item.base_uom_code || "";
    const packages = item.packagings.length ? item.packagings.map((packaging) => `<span class="package-chip"><b>${esc(packaging.name)}</b> · ${number(packaging.quantity)} ${esc(packaging.uom_symbol)}${packaging.barcode ? ` · <span class="mono">${esc(packaging.barcode)}</span>` : ""}</span>`).join("") : '<span class="muted">Упаковки не заведены</span>';
    const positions = item.positions.length ? item.positions.map((position) => {
      const available = Number(position.available_quantity) > 0;
      const details = [position.warehouse_code, position.location_code, position.root_logistic_unit_uid && position.root_logistic_unit_uid !== position.logistic_unit_uid ? `в ${position.root_logistic_unit_uid}` : null, position.batch_number ? `партия ${position.batch_number}` : null, position.serial_number ? `серия ${position.serial_number}` : null].filter(Boolean).join(" · ");
      return `<div class="stock-position-row"><div><strong>${esc(sourceLabel(position))}</strong><small>${esc(details)}</small></div><div class="position-quantity"><b>${number(position.available_quantity)} ${esc(uom)}</b><small>из ${number(position.quantity)}</small></div><button class="secondary" data-issue-position="${position.id}" type="button" ${available ? "" : "disabled"}>Выдать</button></div>`;
    }).join("") : '<div class="empty-list">Фактического остатка пока нет</div>';
    const addPackaging = state.canManageCatalog ? '<button class="secondary compact" data-add-packaging type="button">Добавить упаковку</button>' : "";
    $("stockDetail").innerHTML = `<div class="card-hero"><span class="eyebrow">Номенклатура</span><div class="card-code">${esc(item.product_name)} <small class="mono">${esc(item.product_code)}</small></div><div class="facts stock-facts">${fact("Всего", `${number(item.total_quantity)} ${uom}`)}${fact("Доступно", `${number(item.available_quantity)} ${uom}`)}${fact("В резерве", `${number(item.reserved_quantity)} ${uom}`)}${fact("Карантин", `${number(item.quarantine_quantity)} ${uom}`)}${fact("Заблокировано", `${number(item.blocked_quantity)} ${uom}`)}${fact("В пути", `${number(item.in_transit_quantity)} ${uom}`)}</div></div><div class="stock-detail-body"><section><div class="stock-section-head"><h3>Упаковки и коды</h3>${addPackaging}</div><div class="package-list">${packages}</div></section><section><h3>Где находится</h3><div class="stock-position-list">${positions}</div></section></div>`;
  }

  function issueOptions(item) {
    const units = compatibleUoms(item).map((uom) => `<option value="uom:${uom.id}">${esc(uom.name)} (${esc(uom.symbol)})</option>`);
    const packages = item.packagings.map((packaging) => `<option value="packaging:${packaging.id}">${esc(packaging.name)} (${number(packaging.base_quantity)} ${esc(item.base_uom_symbol || item.base_uom_code)})</option>`);
    return [...units, ...packages].join("");
  }

  function openIssue(positionId) {
    const position = state.item.positions.find((item) => item.id === positionId);
    if (!position) return;
    state.position = position;
    $("issuePanel").hidden = false;
    $("issueFacts").innerHTML = `${fact("Товар", state.item.product_name)}${fact("Источник", sourceLabel(position))}${fact("Доступно", `${number(position.available_quantity)} ${state.item.base_uom_symbol || state.item.base_uom_code}`)}${fact("Партия / серия", position.batch_number || position.serial_number || "Без партии")}`;
    $("issueUom").innerHTML = issueOptions(state.item);
    $("issueKind").value = "permanent";
    $("issueQuantity").value = "1";
    $("issueReason").value = "";
    $("issueRequestReference").value = "";
    $("issueSourceScan").value = "";
    $("issueItemScan").value = "";
    updateIssueTerms();
    updateExistingIssueWarning();
    message("issueMessage", "Отсканируйте источник, затем товар или упаковку.");
    $("issuePanel").scrollIntoView({ behavior: "smooth", block: "start" });
    setTimeout(() => $("issueSourceScan").focus(), 250);
  }

  function updateIssueTerms() {
    const { issueKind, accountabilityPolicy } = selectedIssueMode();
    const accountable = issueKind === "accountable";
    $("plannedCloseField").hidden = !accountable;
    $("autoWriteoffField").hidden = accountabilityPolicy !== "normative_writeoff";
    $("plannedCloseLabel").textContent = accountabilityPolicy === "normative_writeoff" ? "Дата списания по нормативу" : "Ожидаемая дата возврата";
    $("issuePlannedCloseDate").required = accountabilityPolicy === "normative_writeoff";
    if (accountabilityPolicy === "normative_writeoff" && !$("issuePlannedCloseDate").value && state.item?.accountability_period_days) {
      $("issuePlannedCloseDate").value = dateAfterDays(state.item.accountability_period_days);
    }
    if (!accountable) $("issuePlannedCloseDate").value = "";
    updateExistingIssueWarning();
  }

  function updateExistingIssueWarning() {
    if (!state.item || !$("issueRecipient").value) return;
    const recipientId = Number($("issueRecipient").value);
    const openLines = state.issues.flatMap((issue) => issue.recipient_id === recipientId && issue.issue_kind === "accountable" ? issue.movements.filter((movement) => movement.product_id === state.item.product_id && Number(movement.remaining_quantity) > 0).map((movement) => ({ issue, movement })) : []);
    if (!openLines.length) {
      $("existingIssueWarning").hidden = true;
      return;
    }
    const total = openLines.reduce((sum, item) => sum + Number(item.movement.remaining_quantity), 0);
    const dates = openLines.map((item) => item.issue.planned_close_date).filter(Boolean).sort();
    $("existingIssueWarning").textContent = `У получателя уже числится ${number(total)} ${state.item.base_uom_symbol || state.item.base_uom_code}${dates.length ? `, ближайшая плановая дата ${new Date(`${dates[0]}T00:00:00`).toLocaleDateString("ru-RU")}` : ""}. Новая выдача разрешена.`;
    $("existingIssueWarning").hidden = false;
  }

  async function search() {
    const query = $("stockQuery").value.trim();
    if (!query) throw new Error("Введите название, код или штрихкод");
    const warehouse = $("stockWarehouse").value;
    state.result = await api(`/api/stock-search?query=${encodeURIComponent(query)}${warehouse ? `&warehouse_id=${encodeURIComponent(warehouse)}` : ""}`);
    state.item = null;
    renderSearchResults();
    if (state.result.items.length === 1) renderDetail(state.result.items[0]);
    message("stockSearchMessage", state.result.items.length ? `Найдено: ${state.result.items.length}` : "Совпадений нет.", state.result.items.length ? "ok" : "warn");
  }

  function openProductDialog() {
    $("productForm").reset();
    $("productUom").innerHTML = uomOptions(state.uoms);
    const pieces = state.uoms.find((uom) => uom.code === "PCS");
    if (pieces) $("productUom").value = String(pieces.id);
    message("productMessage", "Код будет приведён к верхнему регистру.");
    $("productDialog").showModal();
    setTimeout(() => $("productCode").focus(), 50);
  }

  function openPackagingDialog() {
    if (!state.item) return;
    $("packagingForm").reset();
    $("packagingTitle").textContent = `Упаковка для ${state.item.product_code}`;
    $("packagingFacts").innerHTML = `${fact("Номенклатура", state.item.product_name)}${fact("Базовая единица", `${state.item.base_uom_symbol || state.item.base_uom_code}`)}`;
    $("packagingUom").innerHTML = uomOptions(compatibleUoms(state.item));
    $("packagingQuantity").value = "1";
    message("packagingMessage", "Количество будет пересчитано в базовую единицу товара.");
    $("packagingDialog").showModal();
    setTimeout(() => $("packagingCode").focus(), 50);
  }

  async function submitProduct() {
    const shelfLife = $("productShelfLife").value.trim();
    const accountabilityPeriod = $("productAccountabilityPeriod").value.trim();
    const created = await api("/api/products", {
      method: "POST",
      body: JSON.stringify({
        code: $("productCode").value,
        name: $("productName").value,
        base_uom_id: Number($("productUom").value),
        shelf_life_days: shelfLife ? Number(shelfLife) : null,
        accountability_period_days: accountabilityPeriod ? Number(accountabilityPeriod) : null,
      }),
    });
    $("productDialog").close();
    $("stockQuery").value = created.code;
    await search();
    message("stockSearchMessage", `Позиция ${created.code} создана. Теперь можно добавить упаковку и штрихкод.`, "ok");
  }

  async function submitPackaging() {
    if (!state.item) throw new Error("Номенклатура не выбрана");
    const productCode = state.item.product_code;
    await api("/api/product-packagings", {
      method: "POST",
      body: JSON.stringify({
        product_id: state.item.product_id,
        code: $("packagingCode").value,
        name: $("packagingName").value,
        quantity: $("packagingQuantity").value,
        uom_id: Number($("packagingUom").value),
        barcode: $("packagingBarcode").value.trim() || null,
      }),
    });
    $("packagingDialog").close();
    $("stockQuery").value = productCode;
    await search();
    message("stockSearchMessage", `Упаковка добавлена к позиции ${productCode}.`, "ok");
  }

  async function submitIssue() {
    if (!state.position || !state.item) throw new Error("Источник выдачи не выбран");
    const unit = $("issueUom").value.split(":");
    const line = {
      stock_position_id: state.position.id,
      input_quantity: $("issueQuantity").value,
      input_uom_id: unit[0] === "uom" ? Number(unit[1]) : null,
      packaging_id: unit[0] === "packaging" ? Number(unit[1]) : null,
      source_scan: $("issueSourceScan").value,
      item_scan: $("issueItemScan").value,
    };
    const { issueKind, accountabilityPolicy } = selectedIssueMode();
    const result = await api("/api/internal-issues", {
      method: "POST",
      body: JSON.stringify({
        recipient_id: Number($("issueRecipient").value),
        issue_kind: issueKind,
        accountability_policy: accountabilityPolicy,
        planned_close_date: $("issuePlannedCloseDate").value || null,
        auto_writeoff: accountabilityPolicy === "normative_writeoff" && $("issueAutoWriteoff").checked,
        reason: $("issueReason").value,
        request_reference: $("issueRequestReference").value || null,
        idempotency_key: `web-issue:${crypto.randomUUID()}`,
        actor: state.user?.username || "web-operator",
        lines: [line],
      }),
    });
    message("issueMessage", `Выдача ${result.uid} проведена. ${issueKind === "accountable" ? "Ответственность получателя открыта." : "Запас списан без возврата."}`, "ok");
    document.querySelectorAll("#issuePanel .rail-step").forEach((step, index) => { step.classList.toggle("done", index < 3); step.classList.remove("active"); });
    await Promise.all([search(), loadIssues()]);
  }

  async function loadIssues() {
    state.issues = await api("/api/internal-issues?limit=50");
    $("recentIssues").innerHTML = state.issues.length ? state.issues.map((issue) => {
      const quantity = issue.movements.reduce((total, movement) => total + Number(movement.quantity), 0);
      const remaining = issue.movements.reduce((total, movement) => total + Number(movement.remaining_quantity), 0);
      const product = issue.movements[0]?.product_code || "Без строк";
      const accountable = issue.issue_kind === "accountable";
      const canReturn = issue.status === "posted" && accountable && remaining > 0;
      const terms = accountable ? `${accountabilityLabels[issue.accountability_status] || issue.accountability_status}${issue.planned_close_date ? ` · до ${new Date(`${issue.planned_close_date}T00:00:00`).toLocaleDateString("ru-RU")}` : ""}` : "Без возврата";
      return `<div class="data-row issue-row"><div class="data-row-head"><strong>${esc(issue.recipient_name)}</strong><span class="badge ${accountable && remaining > 0 ? "in_progress" : "completed"}">${esc(terms)}</span></div><small><span class="mono">${esc(issue.uid)}</span> · ${esc(product)} · выдано ${number(quantity)}${accountable ? ` · осталось ${number(remaining)}` : ""} · ${new Date(issue.posted_at || issue.created_at).toLocaleString("ru-RU")}</small>${canReturn ? `<button class="secondary" data-return-issue="${esc(issue.uid)}" type="button">Оформить возврат</button>` : ""}</div>`;
    }).join("") : '<div class="empty-list">Выдач пока нет</div>';
    updateExistingIssueWarning();
  }

  function returnMovementOptions(issue) {
    return issue.movements.filter((movement) => Number(movement.remaining_quantity) > 0).map((movement) => `<option value="${movement.id}">${esc(movement.product_code)} · осталось ${number(movement.remaining_quantity)} ${esc(movement.base_uom_code)}</option>`).join("");
  }

  function updateReturnMovement() {
    if (!state.returnIssue) return;
    const movement = state.returnIssue.movements.find((item) => item.id === Number($("returnMovement").value));
    if (!movement) return;
    $("returnQuantity").value = movement.remaining_quantity;
    $("returnQuantity").max = movement.remaining_quantity;
    $("returnUom").innerHTML = `<option value="${movement.base_uom_id}">${esc(movement.base_uom_code)}</option>`;
    $("returnDestinationScan").value = movement.source_logistic_unit_uid || movement.source_location_code || "";
    $("returnItemScan").value = movement.serial_number || movement.product_code;
  }

  function openReturn(issueUid) {
    const issue = state.issues.find((item) => item.uid === issueUid);
    if (!issue) return;
    state.returnIssue = issue;
    $("returnForm").reset();
    $("returnTitle").textContent = `Возврат по ${issue.uid}`;
    $("returnFacts").innerHTML = `${fact("Получатель", issue.recipient_name)}${fact("Статус", accountabilityLabels[issue.accountability_status] || issue.accountability_status)}`;
    $("returnMovement").innerHTML = returnMovementOptions(issue);
    message("returnMessage", "Количество сверяется с невозвращённым остатком исходной выдачи.");
    updateReturnMovement();
    $("returnDialog").showModal();
    setTimeout(() => $("returnQuantity").focus(), 50);
  }

  async function submitReturn() {
    if (!state.returnIssue) throw new Error("Исходная выдача не выбрана");
    const result = await api(`/api/internal-issues/${encodeURIComponent(state.returnIssue.uid)}/returns`, {
      method: "POST",
      body: JSON.stringify({
        reason: $("returnReason").value,
        idempotency_key: `web-return:${crypto.randomUUID()}`,
        actor: state.user?.username || "web-operator",
        lines: [{
          issue_movement_id: Number($("returnMovement").value),
          input_quantity: $("returnQuantity").value,
          input_uom_id: Number($("returnUom").value),
          packaging_id: null,
          quality_status: $("returnQuality").value,
          destination_scan: $("returnDestinationScan").value,
          item_scan: $("returnItemScan").value,
        }],
      }),
    });
    $("returnDialog").close();
    state.returnIssue = null;
    await Promise.all([loadIssues(), state.item ? search() : Promise.resolve()]);
    message("stockSearchMessage", `Возврат ${result.uid} проведён. Остаток восстановлен.`, "ok");
  }

  async function start() {
    try {
      [state.user, state.warehouses, state.recipients, state.uoms] = await Promise.all([
        api("/api/auth/me").catch(() => null), api("/api/warehouses"), api("/api/stock-recipients"), api("/api/units-of-measure"),
      ]);
      state.canManageCatalog = Boolean(state.user?.permissions?.includes("catalog.manage"));
      $("newProduct").hidden = !state.canManageCatalog;
      $("stockWarehouse").innerHTML += state.warehouses.map((item) => `<option value="${item.id}">${esc(item.code)} · ${esc(item.name)}</option>`).join("");
      $("issueRecipient").innerHTML = state.recipients.map((item) => `<option value="${item.id}">${esc(item.name)} · ${esc(recipientLabels[item.kind] || item.kind)}</option>`).join("");
      if (!state.recipients.length) message("issueMessage", "Получателей пока нет. Администратор добавляет их в настройках.", "warn");
      await loadIssues();
    } catch (error) { message("stockSearchMessage", error.message, "err"); }
  }

  $("stockSearchForm").addEventListener("submit", (event) => { event.preventDefault(); search().catch((error) => message("stockSearchMessage", error.message, "err")); });
  $("stockSearchResults").addEventListener("click", (event) => { const row = event.target.closest("[data-product-id]"); if (!row) return; const item = state.result.items.find((candidate) => candidate.product_id === Number(row.dataset.productId)); if (item) renderDetail(item); });
  $("stockDetail").addEventListener("click", (event) => {
    const issueButton = event.target.closest("[data-issue-position]");
    if (issueButton) openIssue(Number(issueButton.dataset.issuePosition));
    if (event.target.closest("[data-add-packaging]")) openPackagingDialog();
  });
  $("newProduct").addEventListener("click", openProductDialog);
  $("productForm").addEventListener("submit", (event) => { event.preventDefault(); submitProduct().catch((error) => message("productMessage", error.message, "err")); });
  $("packagingForm").addEventListener("submit", (event) => { event.preventDefault(); submitPackaging().catch((error) => message("packagingMessage", error.message, "err")); });
  document.addEventListener("click", (event) => { const button = event.target.closest("[data-close-dialog]"); if (button) $(button.dataset.closeDialog).close(); });
  $("issueForm").addEventListener("submit", (event) => { event.preventDefault(); submitIssue().catch((error) => message("issueMessage", error.message, "err")); });
  $("issueKind").addEventListener("change", updateIssueTerms);
  $("issueRecipient").addEventListener("change", updateExistingIssueWarning);
  $("closeIssue").addEventListener("click", () => { $("issuePanel").hidden = true; state.position = null; });
  $("issueSourceScan").addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); $("issueItemScan").focus(); } });
  $("issueItemScan").addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); $("issueReason").focus(); } });
  $("refreshIssues").addEventListener("click", () => loadIssues().catch((error) => message("stockSearchMessage", error.message, "err")));
  $("recentIssues").addEventListener("click", (event) => { const button = event.target.closest("[data-return-issue]"); if (button) openReturn(button.dataset.returnIssue); });
  $("returnMovement").addEventListener("change", updateReturnMovement);
  $("returnForm").addEventListener("submit", (event) => { event.preventDefault(); submitReturn().catch((error) => message("returnMessage", error.message, "err")); });
  start();
})();
