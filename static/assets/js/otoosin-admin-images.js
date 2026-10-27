(function () {
  "use strict";

  function wireUploader(root) {
    var input = root.querySelector("[data-image-input]");
    var drop = root.querySelector("[data-image-drop]");
    var preview = root.querySelector("[data-image-preview]");
    var placeholder = root.querySelector("[data-image-placeholder]");
    var name = root.querySelector("[data-image-name]");
    var choose = root.querySelector("[data-image-choose]");
    var remove = root.querySelector("[data-image-remove]");
    var clear = root.querySelector("[data-image-clear-checkbox]");
    var row = root.closest(".fd-edit-image-row") || root;
    var deleteInput = row.querySelector('input[type="checkbox"][name$="-DELETE"]');

    if (!input || !drop || !preview || !placeholder) {
      return;
    }

    var currentUrl = preview.getAttribute("src") || "";
    var objectUrl = null;

    if (name && name.textContent.trim()) {
      name.textContent = name.textContent.trim().split("/").pop();
    }

    function revokeObjectUrl() {
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
        objectUrl = null;
      }
    }

    function showImage(src, label) {
      preview.setAttribute("src", src);
      preview.removeAttribute("hidden");
      placeholder.setAttribute("hidden", "");
      if (remove) {
        remove.removeAttribute("hidden");
      }
      if (name) {
        name.textContent = label || "";
      }
      if (clear) {
        clear.checked = false;
      }
      if (deleteInput) {
        deleteInput.checked = false;
      }
    }

    function showEmpty(label) {
      preview.removeAttribute("src");
      preview.setAttribute("hidden", "");
      placeholder.removeAttribute("hidden");
      if (remove) {
        remove.setAttribute("hidden", "");
      }
      if (name) {
        name.textContent = label || "";
      }
    }

    function selectFile(file) {
      if (!file || !/^image\//i.test(file.type || "")) {
        return;
      }
      revokeObjectUrl();
      objectUrl = URL.createObjectURL(file);
      showImage(objectUrl, file.name);
      drop.classList.remove("is-dragging");
    }

    input.addEventListener("change", function () {
      if (input.files && input.files[0]) {
        selectFile(input.files[0]);
      }
    });

    ["dragenter", "dragover"].forEach(function (eventName) {
      drop.addEventListener(eventName, function (event) {
        event.preventDefault();
        drop.classList.add("is-dragging");
      });
    });

    ["dragleave", "dragend"].forEach(function (eventName) {
      drop.addEventListener(eventName, function (event) {
        drop.classList.remove("is-dragging");
      });
    });

    drop.addEventListener("drop", function (event) {
      event.preventDefault();
      drop.classList.remove("is-dragging");
      var files = event.dataTransfer && event.dataTransfer.files;
      if (!files || !files.length) {
        return;
      }
      try {
        var transfer = new DataTransfer();
        transfer.items.add(files[0]);
        input.files = transfer.files;
      } catch (error) {
        return;
      }
      selectFile(files[0]);
    });

    if (choose) {
      choose.addEventListener("click", function () {
        input.click();
      });
    }

    if (remove) {
      remove.addEventListener("click", function () {
        revokeObjectUrl();
        if (deleteInput) {
          deleteInput.checked = true;
          input.value = "";
          showEmpty("This image will be removed when you save.");
          return;
        }
        if (clear && clear.parentNode) {
          clear.checked = true;
          showEmpty("Current image will be removed when you save.");
          return;
        }
        input.value = "";
        if (currentUrl) {
          showEmpty("Image will be removed when you save.");
        } else {
          showEmpty("");
        }
      });
    }

    if ((deleteInput && deleteInput.checked) || (clear && clear.checked)) {
      showEmpty("Current image will be removed when you save.");
    }
  }

  function init() {
    var uploaders = document.querySelectorAll("[data-image-upload]");
    for (var i = 0; i < uploaders.length; i++) {
      wireUploader(uploaders[i]);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
