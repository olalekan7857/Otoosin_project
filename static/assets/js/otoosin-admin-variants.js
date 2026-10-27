(function () {
  "use strict";

  function initVariantSection(list) {
    var prefix = list.getAttribute("data-variant-prefix") || "variants";
    var totalInput = document.querySelector(
      'input[name="' + prefix + '-TOTAL_FORMS"]'
    );
    var template = document.getElementById("fd-variant-template");
    var addButton = document.querySelector("[data-variant-add]");

    if (!totalInput || !template || !addButton) {
      return;
    }

    function visibleCards() {
      return Array.prototype.filter.call(
        list.querySelectorAll("[data-variant-card]"),
        function (card) {
          return !card.hidden;
        }
      );
    }

    function renumber() {
      visibleCards().forEach(function (card, index) {
        var number = card.querySelector("[data-variant-number]");
        if (number) {
          number.textContent = "Selling option " + (index + 1);
        }
      });
    }

    function defaultInputs() {
      return list.querySelectorAll('input[name$="-is_default"]');
    }

    function syncDefault(source) {
      if (!source.checked) {
        return;
      }
      Array.prototype.forEach.call(defaultInputs(), function (input) {
        if (input !== source) {
          input.checked = false;
        }
      });
    }

    function wireCard(card) {
      var remove = card.querySelector("[data-variant-remove]");
      var deleteInput = card.querySelector('input[name$="-DELETE"]');
      var defaultInput = card.querySelector('input[name$="-is_default"]');
      var isExisting = card.getAttribute("data-variant-existing") === "1";

      if (defaultInput) {
        defaultInput.addEventListener("change", function () {
          syncDefault(defaultInput);
        });
      }

      if (!remove) {
        return;
      }

      remove.addEventListener("click", function () {
        if (isExisting && deleteInput) {
          deleteInput.checked = true;
        } else {
          Array.prototype.forEach.call(
            card.querySelectorAll("input, select, textarea"),
            function (field) {
              if (field.type === "checkbox" || field.type === "radio") {
                field.checked = false;
              } else if (field.type !== "hidden") {
                field.value = "";
              }
            }
          );
          if (deleteInput) {
            deleteInput.checked = false;
          }
        }
        if (defaultInput) {
          defaultInput.checked = false;
        }
        card.hidden = true;
        renumber();
      });
    }

    Array.prototype.forEach.call(
      list.querySelectorAll("[data-variant-card]"),
      wireCard
    );

    addButton.addEventListener("click", function () {
      var index = parseInt(totalInput.value, 10) || 0;
      var wrapper = document.createElement("div");
      wrapper.innerHTML = template.innerHTML.replace(/__prefix__/g, index);
      var card = wrapper.firstElementChild;
      if (!card) {
        return;
      }
      list.appendChild(card);
      totalInput.value = index + 1;
      wireCard(card);
      renumber();
      var firstField = card.querySelector("input.form-control, select");
      if (firstField) {
        firstField.focus();
      }
    });

    renumber();
  }

  function init() {
    Array.prototype.forEach.call(
      document.querySelectorAll("[data-variant-list]"),
      initVariantSection
    );
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
