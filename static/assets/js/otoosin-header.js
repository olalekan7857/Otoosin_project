(function () {
  "use strict";

  window.OtoosinHeader = window.OtoosinHeader || {};

  if (window.OtoosinHeader.initialized) {
    return;
  }

  function initDropdowns() {
    var dropdowns = document.querySelectorAll(".main-menu li.oto-has-dropdown");
    if (!dropdowns.length) {
      return;
    }

    function setOpen(item, toggle, isOpen) {
      if (isOpen) {
        item.classList.add("oto-dropdown-open");
      } else {
        item.classList.remove("oto-dropdown-open");
      }
      toggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
    }

    function closeAll(except) {
      dropdowns.forEach(function (item) {
        if (item === except) {
          return;
        }
        var toggle = item.querySelector(".oto-dropdown-toggle");
        if (toggle) {
          setOpen(item, toggle, false);
        }
      });
    }

    function isInside(item, node) {
      return node && item.contains(node);
    }

    dropdowns.forEach(function (item) {
      var toggle = item.querySelector(".oto-dropdown-toggle");
      var submenu = item.querySelector(".sub-menu");
      if (!toggle || !submenu) {
        return;
      }

      var links = submenu.querySelectorAll("a");

      toggle.addEventListener("click", function (event) {
        event.preventDefault();
        var willOpen = !item.classList.contains("oto-dropdown-open");
        closeAll(item);
        setOpen(item, toggle, willOpen);
      });

      item.addEventListener("mouseenter", function () {
        setOpen(item, toggle, true);
      });

      item.addEventListener("mouseleave", function (event) {
        if (isInside(item, event.relatedTarget)) {
          return;
        }
        if (document.activeElement && isInside(item, document.activeElement)) {
          return;
        }
        setOpen(item, toggle, false);
      });

      item.addEventListener("focusout", function (event) {
        if (isInside(item, event.relatedTarget)) {
          return;
        }
        setOpen(item, toggle, false);
      });

      toggle.addEventListener("keydown", function (event) {
        if (event.key === "ArrowDown") {
          event.preventDefault();
          setOpen(item, toggle, true);
          if (links.length) {
            links[0].focus();
          }
        } else if (event.key === "ArrowUp") {
          event.preventDefault();
          setOpen(item, toggle, true);
          if (links.length) {
            links[links.length - 1].focus();
          }
        }
      });

      submenu.addEventListener("keydown", function (event) {
        if (event.key !== "ArrowDown" && event.key !== "ArrowUp") {
          return;
        }
        var index = Array.prototype.indexOf.call(links, document.activeElement);
        if (index === -1) {
          return;
        }
        event.preventDefault();
        var next = event.key === "ArrowDown" ? index + 1 : index - 1;
        if (next < 0 || next >= links.length) {
          toggle.focus();
          return;
        }
        links[next].focus();
      });
    });

    document.addEventListener("click", function (event) {
      if (!event.target.closest(".main-menu li.oto-has-dropdown")) {
        closeAll(null);
      }
    });

    document.addEventListener("keydown", function (event) {
      if (event.key !== "Escape") {
        return;
      }
      dropdowns.forEach(function (item) {
        if (item.classList.contains("oto-dropdown-open")) {
          var toggle = item.querySelector(".oto-dropdown-toggle");
          if (toggle) {
            setOpen(item, toggle, false);
            toggle.focus();
          }
        }
      });
    });

    window.OtoosinHeader.initialized = true;
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initDropdowns);
  } else {
    initDropdowns();
  }
})();
