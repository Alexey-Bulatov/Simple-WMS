(() => {
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
