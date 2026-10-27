(function () {
  "use strict";

  function submitForm(form) {
    if (typeof form.requestSubmit === "function") {
      form.requestSubmit();
    } else {
      form.submit();
    }
  }

  function wireFilter(form) {
    var search = form.querySelector('input[type="search"]');
    var selects = form.querySelectorAll("select");
    var timer = null;

    for (var i = 0; i < selects.length; i++) {
      selects[i].addEventListener("change", function () {
        submitForm(form);
      });
    }

    if (search) {
      search.addEventListener("input", function () {
        window.clearTimeout(timer);
        timer = window.setTimeout(function () {
          submitForm(form);
        }, 500);
      });
    }
  }

  function init() {
    var forms = document.querySelectorAll("[data-catalog-filter]");
    for (var i = 0; i < forms.length; i++) {
      wireFilter(forms[i]);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
