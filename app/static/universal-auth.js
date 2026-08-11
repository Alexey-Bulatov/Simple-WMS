(() => {
  const $ = (id) => document.getElementById(id);

  async function request(path, options = {}) {
    const response = await fetch(path, {
      ...options,
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    });
    if (response.status === 204) return null;
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || "Операция не выполнена");
    return body;
  }

  function safeNext() {
    const value = new URLSearchParams(location.search).get("next") || "/work";
    return value.startsWith("/") && !value.startsWith("//") ? value : "/work";
  }

  function message(id, text, error = false) {
    const node = $(id);
    if (!node) return;
    node.textContent = text;
    node.classList.toggle("error", error);
  }

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

  function setupLogin() {
    const passwordForm = $("passwordLogin");
    if (!passwordForm) return;
    const passForm = $("passLogin");
    document.querySelectorAll("[data-auth-tab]").forEach((button) => {
      button.addEventListener("click", () => {
        const passMode = button.dataset.authTab === "pass";
        document.querySelectorAll("[data-auth-tab]").forEach((item) => item.classList.toggle("active", item === button));
        passwordForm.hidden = passMode;
        passForm.hidden = !passMode;
        (passMode ? $("loginAccessCode") : $("loginUsername")).focus();
      });
    });
    passwordForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      message("authMessage", "Проверяем данные...");
      try {
        await request("/api/auth/login/password", {
          method: "POST",
          body: JSON.stringify({
            username: $("loginUsername").value,
            password: $("loginPassword").value,
            workstation_code: $("loginWorkstation").value || null,
          }),
        });
        location.href = safeNext();
      } catch (error) {
        message("authMessage", error.message, true);
        $("loginPassword").select();
      }
    });
    passForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      message("authMessage", "Проверяем пропуск...");
      try {
        await request("/api/auth/login/pass", {
          method: "POST",
          body: JSON.stringify({
            access_code: $("loginAccessCode").value,
            workstation_code: $("passWorkstation").value,
          }),
        });
        location.href = safeNext();
      } catch (error) {
        message("authMessage", error.message, true);
        $("loginAccessCode").select();
      }
    });
  }

  async function setupProfile() {
    if (!$("profileName")) return;
    try {
      const [user, workstations] = await Promise.all([
        request("/api/auth/me"),
        request("/api/auth/workstations"),
      ]);
      $("profileName").textContent = user.full_name;
      $("profileLogin").textContent = user.username;
      $("profileFacts").innerHTML = [
        ["Роль", roleLabels[user.role] || user.role],
        ["Склады", user.warehouse_codes.join(", ") || "Все для администратора"],
        ["Пароль", user.must_change_password ? "Требуется смена" : "Действует"],
      ].map(([label, value]) => `<div class="fact"><b>${label}</b><span>${value}</span></div>`).join("");
      $("profileWorkstation").innerHTML = workstations.length
        ? workstations.map((item) => `<option value="${item.code}">${item.name} · ${item.code}</option>`).join("")
        : '<option value="">Нет доступных рабочих мест</option>';
      $("issuePassForm").querySelector("button").disabled = !workstations.length;
      if (user.must_change_password) {
        $("issuePassForm").querySelector("button").disabled = true;
        message("profileMessage", "Сначала смените временный пароль.", true);
      }
    } catch (_) {
      location.href = `/login?next=${encodeURIComponent(location.pathname)}`;
      return;
    }

    $("logoutButton").addEventListener("click", async () => {
      await request("/api/auth/logout", { method: "POST", body: "{}" }).catch(() => null);
      location.href = "/login";
    });
    $("issuePassForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      message("profileMessage", "Выпускаем новый код...");
      try {
        const result = await request("/api/auth/passes/issue", {
          method: "POST",
          body: JSON.stringify({
            workstation_code: $("profileWorkstation").value,
            current_password: $("profilePassword").value,
            expires_days: 30,
          }),
        });
        $("issuedPassCode").textContent = result.login_code;
        $("issuedPass").hidden = false;
        $("profilePassword").value = "";
        message("profileMessage", "Предыдущий код отозван. Новый показывается только сейчас.");
      } catch (error) {
        message("profileMessage", error.message, true);
      }
    });
    $("passwordChangeForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      if ($("newPassword").value !== $("repeatPassword").value) {
        message("passwordMessage", "Новые пароли не совпадают.", true);
        $("repeatPassword").select();
        return;
      }
      message("passwordMessage", "Меняем пароль...");
      try {
        await request("/api/auth/password/change", {
          method: "POST",
          body: JSON.stringify({
            current_password: $("currentPassword").value,
            new_password: $("newPassword").value,
          }),
        });
        location.reload();
      } catch (error) {
        message("passwordMessage", error.message, true);
      }
    });
  }

  setupLogin();
  setupProfile();
})();
