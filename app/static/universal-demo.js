(() => {
  const $ = (id) => document.getElementById(id);
  let unitTypes = [];
  const esc = (value) => String(value ?? "—").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);

  async function api(path, options = {}) {
    const response = await fetch(path, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    const text = await response.text();
    const data = text ? JSON.parse(text) : null;
    if (!response.ok) throw new Error(data?.detail || response.statusText);
    return data;
  }

  function fact(label, value) {
    return `<div class="fact"><b>${esc(label)}</b><span>${esc(value)}</span></div>`;
  }

  function setMessage(text, kind = "") {
    $("demoMessage").className = `message ${kind}`;
    $("demoMessage").textContent = text;
  }

  function render(result) {
    $("demoFacts").innerHTML = [
      fact("Товаров создано", result.created_products),
      fact("Партий создано", result.created_batches),
      fact("Адресных уровней", (result.created_aisles || 0) + (result.created_racks || 0) + (result.created_sections || 0) + (result.created_levels || 0)),
      fact("Ячеек создано", result.created_locations),
      fact("Единиц создано", result.created_logistic_units),
      fact("Размещено", result.placed_logistic_units),
      fact("Ожидает", result.waiting_logistic_units),
    ].join("");
    $("demoUnits").innerHTML = (result.logistic_unit_uids || []).map((uid) => `<div class="data-row"><div class="data-row-head"><a class="mono" href="/cards?kind=unit&code=${encodeURIComponent(uid)}">${esc(uid)}</a><span class="badge">${esc(result.parent_type_code)}</span></div><small>${result.child_type_code ? `${esc(result.child_type_code)} → ` : ""}${esc(result.content_quantity || "")} ${esc(result.content_uom_code)}</small></div>`).join("") || '<div class="data-row">Новые единицы не создавались.</div>';
  }

  function refreshChildTypes(preferred = "") {
    const parent = unitTypes.find((item) => item.code === $("demoParentType").value);
    const allowed = unitTypes.filter((item) => (parent?.allowed_child_type_ids || []).includes(item.id));
    $("demoChildType").innerHTML = [
      ...(parent?.can_contain_goods ? ['<option value="">Без вложенной тары</option>'] : []),
      ...allowed.map((item) => `<option value="${esc(item.code)}">${esc(item.name)} (${esc(item.code)})</option>`),
    ].join("");
    if ([...$("demoChildType").options].some((option) => option.value === preferred)) {
      $("demoChildType").value = preferred;
    }
    const direct = !$("demoChildType").value;
    $("demoChildren").disabled = direct;
  }

  async function generate() {
    const button = $("generateDemo");
    button.disabled = true;
    setMessage("Формирование данных…");
    try {
      const result = await api("/api/demo/logistic-units", {
        method: "POST",
        body: JSON.stringify({
          warehouse_code: $("demoWarehouseCode").value.trim().toUpperCase(),
          warehouse_name: $("demoWarehouseName").value.trim(),
          storage_locations: Number($("demoStorageLocations").value),
          quantity: Number($("demoQuantity").value),
          parent_type_code: $("demoParentType").value,
          child_type_code: $("demoChildType").value || null,
          child_units_per_parent: Number($("demoChildren").value),
          content_uom_code: $("demoContentUom").value,
          content_quantity: $("demoContentQuantity").value,
          place_to_empty_locations: $("demoPlace").checked,
          actor: $("demoActor").value.trim(),
        }),
      });
      render(result);
      setMessage(`Генерация завершена. Логистических единиц: ${result.created_logistic_units}.`, "ok");
    } catch (error) {
      setMessage(error.message, "err");
    } finally {
      button.disabled = false;
    }
  }

  $("demoForm").addEventListener("submit", (event) => {
    event.preventDefault();
    generate();
  });
  $("demoParentType").addEventListener("change", () => refreshChildTypes());
  $("demoChildType").addEventListener("change", () => {
    $("demoChildren").disabled = !$("demoChildType").value;
  });

  Promise.all([
    api("/api/warehouses"),
    api("/api/logistic-unit-types"),
    api("/api/units-of-measure"),
  ]).then(([warehouses, types, units]) => {
    unitTypes = types.filter((item) => item.is_active);
    $("demoParentType").innerHTML = unitTypes.map((item) => `<option value="${esc(item.code)}">${esc(item.name)} (${esc(item.code)})</option>`).join("");
    $("demoParentType").value = "PALLET";
    refreshChildTypes("BOX");
    $("demoContentUom").innerHTML = units.filter((item) => item.is_active).map((item) => `<option value="${esc(item.code)}">${esc(item.name)} (${esc(item.symbol)})</option>`).join("");
    $("demoContentUom").value = "PCS";
    const preferred = warehouses.find((item) => item.code === "WH01") || warehouses[0];
    if (!preferred) return;
    $("demoWarehouseCode").value = preferred.code;
    $("demoWarehouseName").value = preferred.name;
  }).catch(() => {});
})();
