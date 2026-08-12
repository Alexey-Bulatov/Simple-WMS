(() => {
  const originalFetch = window.fetch.bind(window);
  let confirmationDialog = null;

  function requestConfirmationPassword() {
    if (!confirmationDialog) {
      confirmationDialog = document.createElement("dialog");
      confirmationDialog.className = "confirmation-dialog";
      confirmationDialog.innerHTML = `
        <form method="dialog">
          <span class="eyebrow">Подтверждение полномочий</span>
          <h2>Введите текущий пароль</h2>
          <input type="password" autocomplete="current-password" aria-label="Текущий пароль" required>
          <div class="form-actions"><button value="cancel" type="submit" formnovalidate>Отмена</button><button class="primary" value="confirm" type="submit">Подтвердить</button></div>
        </form>`;
      document.body.appendChild(confirmationDialog);
    }
    const input = confirmationDialog.querySelector("input");
    input.value = "";
    confirmationDialog.showModal();
    input.focus();
    return new Promise((resolve) => {
      confirmationDialog.addEventListener("close", () => {
        resolve(confirmationDialog.returnValue === "confirm" ? input.value : null);
      }, { once: true });
    });
  }

  window.fetch = async (input, init = {}) => {
    const response = await originalFetch(input, init);
    const headers = new Headers(init.headers || {});
    if (response.status !== 403 || headers.has("X-WMS-Confirm-Password")) return response;
    const body = await response.clone().json().catch(() => ({}));
    if (body.detail !== "current password confirmation is required") return response;
    const password = await requestConfirmationPassword();
    if (!password) return response;
    headers.set("X-WMS-Confirm-Password", password);
    return originalFetch(input, { ...init, headers });
  };

  async function loadUser() {
    try {
      const response = await fetch("/api/auth/me", { headers: { Accept: "application/json" } });
      const profileLink = document.querySelector('nav a[href="/profile"]');
      if (!response.ok) {
        if (profileLink) {
          profileLink.href = `/login?next=${encodeURIComponent(location.pathname)}`;
          profileLink.textContent = "Вход";
        }
        return;
      }
      const user = await response.json();
      if (profileLink) profileLink.textContent = user.full_name;
      document.querySelectorAll("[data-admin-link]").forEach((link) => {
        link.hidden = user.role !== "admin";
      });
      document.querySelectorAll("#actorInput, #demoActor").forEach((input) => {
        input.value = user.username;
        input.readOnly = true;
      });
    } catch (_) {
      // The warehouse screens keep their existing offline error handling.
    }
  }

  loadUser();
})();
