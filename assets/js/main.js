(function () {
  var toggle = document.querySelector(".nav-toggle");
  var nav = document.getElementById("site-nav");
  if (toggle && nav) {
    toggle.addEventListener("click", function () {
      var open = nav.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  document.querySelectorAll("[data-copy-bibtex]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var wrap = btn.closest(".bibtex-wrap");
      var code = wrap ? wrap.querySelector(".bibtex-code") : null;
      if (!code || !navigator.clipboard) return;
      navigator.clipboard.writeText(code.textContent.trim()).then(function () {
        var original = btn.textContent;
        btn.textContent = "Copied";
        window.setTimeout(function () {
          btn.textContent = original;
        }, 1600);
      });
    });
  });

  document.querySelectorAll("[data-copy-email]").forEach(function (btn) {
    btn.classList.add("is-ready");
    btn.addEventListener("click", function () {
      var wrap = btn.closest(".hero-contact");
      var addrEl = wrap ? wrap.querySelector(".contact-address") : null;
      if (!addrEl || !navigator.clipboard) return;
      var eu = addrEl.getAttribute("data-eu") || "";
      var ed = addrEl.getAttribute("data-ed") || "";
      if (!eu || !ed) return;
      navigator.clipboard.writeText(eu + "@" + ed).then(function () {
        var original = btn.textContent;
        btn.textContent = "Copied";
        window.setTimeout(function () {
          btn.textContent = original;
        }, 1600);
      });
    });
  });

  var filterBar = document.querySelector("[data-topic-filter]");
  if (filterBar) {
    filterBar.classList.add("is-ready");
    var buttons = filterBar.querySelectorAll("[data-topic]");
    var entries = document.querySelectorAll(".paper-entry[data-topics]");
    buttons.forEach(function (btn) {
      btn.addEventListener("click", function () {
        var selected = btn.getAttribute("data-topic");
        buttons.forEach(function (b) {
          b.classList.toggle("is-active", b === btn);
          b.setAttribute("aria-pressed", b === btn ? "true" : "false");
        });
        entries.forEach(function (entry) {
          if (selected === "all") {
            entry.classList.remove("is-hidden");
            return;
          }
          var topics = (entry.getAttribute("data-topics") || "").split("|");
          entry.classList.toggle("is-hidden", topics.indexOf(selected) === -1);
        });
      });
    });
  }
})();
