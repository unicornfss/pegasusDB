/**
 * Auto-dismiss Django flash banners after 10s.
 * Alerts should use class "js-flash-message" and Bootstrap dismissible markup.
 */
(function () {
  var AUTO_DISMISS_MS = 10000;

  function dismiss(el) {
    if (!el || !el.isConnected) return;
    if (typeof bootstrap !== "undefined" && bootstrap.Alert) {
      bootstrap.Alert.getOrCreateInstance(el).close();
      return;
    }
    el.remove();
  }

  function init() {
    document.querySelectorAll(".js-flash-message").forEach(function (el) {
      window.setTimeout(function () {
        dismiss(el);
      }, AUTO_DISMISS_MS);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
