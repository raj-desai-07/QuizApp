/* UI only: validation hints, restart confirmation, double-submit guard. Scoring lives on the server. */
(function () {
  "use strict";

  function showError(form, id, input, message) {
    var box = form.querySelector("#" + id);
    if (box) { box.textContent = message; }
    if (input) { input.classList.add("is-invalid"); input.setAttribute("aria-invalid", "true"); }
  }

  function clearError(form, id, input) {
    var box = form.querySelector("#" + id);
    if (box) { box.textContent = ""; }
    if (input) { input.classList.remove("is-invalid"); input.removeAttribute("aria-invalid"); }
  }

  // Confirmation dialog (native <dialog>, falls back to window.confirm).
  function confirmAction(message, onYes) {
    if (typeof HTMLDialogElement !== "function") { if (window.confirm(message)) { onYes(); } return; }
    var dlg = document.createElement("dialog");
    dlg.className = "dialog";
    dlg.setAttribute("aria-label", "Confirm");
    dlg.innerHTML = '<p></p><div class="dialog-actions"><button type="button" class="button button-ghost" data-no>Cancel</button><button type="button" class="button" data-yes>Yes, continue</button></div>';
    dlg.querySelector("p").textContent = message;
    document.body.appendChild(dlg);
    var close = function () { dlg.close(); dlg.remove(); };
    dlg.querySelector("[data-no]").addEventListener("click", close);
    dlg.querySelector("[data-yes]").addEventListener("click", function () { close(); onYes(); });
    dlg.addEventListener("cancel", function () { dlg.remove(); });
    dlg.showModal();
    dlg.querySelector("[data-no]").focus();
  }

  document.querySelectorAll("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      if (form.dataset.confirmed) { return; }
      if (form.dataset.validate === "name" && !form.player_name.value.trim()) { return; } // let validation handle it
      e.preventDefault();
      confirmAction(form.dataset.confirm, function () { form.dataset.confirmed = "1"; form.submit(); });
    });
  });

  document.querySelectorAll('form[data-validate="name"]').forEach(function (form) {
    var input = form.player_name;
    input.addEventListener("input", function () { clearError(form, "name-error", input); });
    form.addEventListener("submit", function (e) {
      if (!input.value.trim()) {
        e.preventDefault(); e.stopImmediatePropagation();
        showError(form, "name-error", input, "Please enter your name to start the quiz.");
        input.focus();
      }
    }, true);
  });

  document.querySelectorAll('form[data-validate="choice"]').forEach(function (form) {
    var radios = form.querySelectorAll('input[name="choice"]');
    radios.forEach(function (r) { r.addEventListener("change", function () { clearError(form, "choice-error", null); }); });
    form.addEventListener("submit", function (e) {
      if (!form.querySelector('input[name="choice"]:checked')) {
        e.preventDefault();
        showError(form, "choice-error", null, "Please select an answer.");
        radios[0].focus();
      }
    });
  });

  document.querySelectorAll("form[data-once]").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      if (e.defaultPrevented) { return; }
      var btn = form.querySelector('button[type="submit"]');
      if (btn) { setTimeout(function () { btn.disabled = true; }, 0); }
    });
  });

  var focus = document.querySelector("[data-autofocus]");
  if (focus) { focus.focus({ preventScroll: true }); }

  // Restore button state when returning via the back/forward cache.
  window.addEventListener("pageshow", function (e) {
    if (e.persisted) { document.querySelectorAll("form[data-once] button").forEach(function (b) { b.disabled = false; }); }
  });
})();
