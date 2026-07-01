// Drag-and-drop (plus click-to-pick and auto-submit) for the .ics upload zone.
// Progressive enhancement: the plain file input + button still work without JS.
// Listeners are delegated on document so they keep working after htmx swaps the
// person fragment in. requestSubmit() (not submit()) is used so htmx intercepts.
(function () {
  function zoneOf(e) {
    return e.target.closest("[data-dropzone]");
  }

  document.addEventListener("dragover", function (e) {
    const zone = zoneOf(e);
    if (!zone) return;
    e.preventDefault(); // allow the drop
    zone.classList.add("dragover");
  });

  document.addEventListener("dragleave", function (e) {
    const zone = zoneOf(e);
    if (zone && !zone.contains(e.relatedTarget)) zone.classList.remove("dragover");
  });

  document.addEventListener("drop", function (e) {
    const zone = zoneOf(e);
    if (!zone) return;
    e.preventDefault();
    zone.classList.remove("dragover");
    const input = zone.querySelector('input[type="file"]');
    if (input && e.dataTransfer.files.length) {
      input.files = e.dataTransfer.files;
      input.form.requestSubmit();
    }
  });

  // Click anywhere on the zone (but not the input or the button) opens the picker.
  document.addEventListener("click", function (e) {
    const zone = zoneOf(e);
    if (zone && !e.target.closest("input, button")) {
      zone.querySelector('input[type="file"]').click();
    }
  });

  // A file chosen via the picker submits straight away, matching the drop path.
  document.addEventListener("change", function (e) {
    const input = e.target;
    if (input.matches('[data-dropzone] input[type="file"]') && input.files.length) {
      input.form.requestSubmit();
    }
  });
})();
