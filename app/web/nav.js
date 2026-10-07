/* Shared nav helper for operator pages: shows who's signed in and wires Sign out. */
(async function () {
  try {
    const me = await (await fetch("/api/me")).json();
    document.querySelectorAll("[data-operator]").forEach(e => { e.textContent = me.name || ""; });
  } catch (e) { /* not signed in; the server will redirect anyway */ }

  document.querySelectorAll("[data-logout]").forEach(el => {
    el.addEventListener("click", async (e) => {
      e.preventDefault();
      try { await fetch("/api/logout", { method: "POST" }); } catch (_) {}
      location.href = "/login";
    });
  });
})();
