/* ==========================================================================
   O’TOOSIN Farms — Contact form
   Frontend validation and honest submission feedback. No message delivery
   endpoint is configured, so the form never claims a message was sent and
   never persists the enquiry.
   ========================================================================== */
(function () {
  "use strict";

  var form = document.getElementById("oto-contact-form");
  if (!form) {
    return;
  }

  var statusBox = document.getElementById("oto-contact-status");
  var fields = {
    name: document.getElementById("oto-contact-name"),
    email: document.getElementById("oto-contact-email"),
    phone: document.getElementById("oto-contact-phone"),
    subject: document.getElementById("oto-contact-subject"),
    message: document.getElementById("oto-contact-message")
  };

  var emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
  var subjectValues = fields.subject
    ? Array.prototype.map.call(fields.subject.options, function (option) {
        return option.value;
      })
    : [];
  var triedSubmit = false;

  function errorBox(input) {
    return document.getElementById(input.id + "-error");
  }

  function setError(input, message) {
    if (!input) {
      return;
    }
    var box = errorBox(input);
    if (message) {
      input.setAttribute("aria-invalid", "true");
    } else {
      input.removeAttribute("aria-invalid");
    }
    if (box) {
      box.textContent = message || "";
      box.hidden = !message;
    }
  }

  function validateField(input) {
    var value = (input.value || "").trim();

    if (input === fields.name) {
      if (!value) {
        return "Enter your full name.";
      }
      if (value.length < 2) {
        return "Enter at least 2 characters for your name.";
      }
      return "";
    }

    if (input === fields.email) {
      if (!value) {
        return "Enter your email address.";
      }
      if (!emailPattern.test(value)) {
        return "Enter a valid email address, such as name@example.com.";
      }
      return "";
    }

    if (input === fields.phone) {
      if (!value) {
        return "";
      }
      var digits = value.replace(/\D/g, "");
      if (digits.length < 7 || digits.length > 15) {
        return "Enter a valid phone number, or leave this field blank.";
      }
      return "";
    }

    if (input === fields.subject) {
      if (!value) {
        return "Choose an enquiry type.";
      }
      if (subjectValues.indexOf(value) === -1) {
        return "Choose a valid enquiry type.";
      }
      return "";
    }

    if (input === fields.message) {
      if (!value) {
        return "Enter your message.";
      }
      if (value.length < 10) {
        return "Add a little more detail so we can help (at least 10 characters).";
      }
      return "";
    }

    return "";
  }

  function hideStatus() {
    if (!statusBox) {
      return;
    }
    statusBox.textContent = "";
    statusBox.classList.remove("is-error");
    statusBox.setAttribute("hidden", "");
  }

  function showStatus(message, isError) {
    if (!statusBox) {
      return;
    }
    statusBox.textContent = message;
    statusBox.classList.toggle("is-error", !!isError);
    statusBox.removeAttribute("hidden");
  }

  var orderedFields = [fields.name, fields.email, fields.phone, fields.subject, fields.message];

  orderedFields.forEach(function (input) {
    if (!input) {
      return;
    }

    input.addEventListener("blur", function () {
      if (triedSubmit) {
        setError(input, validateField(input));
      }
    });

    input.addEventListener("input", function () {
      setError(input, "");
      hideStatus();
    });

    input.addEventListener("change", function () {
      setError(input, "");
      hideStatus();
    });
  });

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    triedSubmit = true;

    var firstInvalid = null;
    orderedFields.forEach(function (input) {
      if (!input) {
        return;
      }
      var message = validateField(input);
      setError(input, message);
      if (message && !firstInvalid) {
        firstInvalid = input;
      }
    });

    if (firstInvalid) {
      showStatus("Please check the highlighted fields and try again.", true);
      firstInvalid.focus();
      return;
    }

    showStatus(
      "Message delivery is not connected on this page, so your enquiry has not been sent. Your details remain in the form.",
      false
    );

    if (statusBox) {
      statusBox.focus();
    }
  });
})();
