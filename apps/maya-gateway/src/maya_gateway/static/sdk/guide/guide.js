/* Maya Handbook — light docs interactivity (vanilla, no framework).
 * Responsibilities: theme toggle, copy-to-clipboard, and global polyglot
 * code-tab sync (Readwise/Mintlify style) persisted to localStorage. */
(function () {
  "use strict";

  var THEME_KEY = "maya.docs.theme";
  var LANG_KEY = "maya.docs.lang";

  var MayaDocs = {
    toggleTheme: function () {
      var next = document.documentElement.dataset.theme === "light" ? "dark" : "light";
      document.documentElement.dataset.theme = next;
      try { localStorage.setItem(THEME_KEY, next); } catch (e) {}
    },
  };
  window.MayaDocs = MayaDocs;

  function addCopyButtons() {
    document.querySelectorAll(".dx-article pre > code").forEach(function (code) {
      var pre = code.parentElement;
      if (pre.querySelector(".dx-copy")) return;
      var btn = document.createElement("button");
      btn.className = "dx-copy";
      btn.type = "button";
      btn.textContent = "Copy";
      btn.addEventListener("click", function () {
        navigator.clipboard.writeText(code.innerText).then(function () {
          btn.textContent = "Copied";
          btn.classList.add("copied");
          setTimeout(function () {
            btn.textContent = "Copy";
            btn.classList.remove("copied");
          }, 1400);
        });
      });
      pre.appendChild(btn);
    });
  }

  // ---- Global polyglot tab sync -------------------------------------------
  // pymdownx tabbed (alternate_style) renders, per set:
  //   <input ...><input ...> <div.tabbed-labels><label/>...</div> <div.tabbed-content>
  // We sync the chosen label *text* across every set on the page + persist it.
  function tabSets() {
    return Array.prototype.slice.call(document.querySelectorAll(".tabbed-set"));
  }

  function applyLang(lang) {
    if (!lang) return;
    var target = lang.toLowerCase();
    tabSets().forEach(function (set) {
      var labels = set.querySelectorAll(".tabbed-labels > label");
      var inputs = set.querySelectorAll(":scope > input[type=radio]");
      for (var i = 0; i < labels.length; i++) {
        if (labels[i].textContent.trim().toLowerCase() === target && inputs[i]) {
          inputs[i].checked = true;
          break;
        }
      }
    });
  }

  function rememberLang(lang) {
    try { localStorage.setItem(LANG_KEY, lang); } catch (e) {}
  }

  function wireTabSync() {
    tabSets().forEach(function (set) {
      set.querySelectorAll(".tabbed-labels > label").forEach(function (label) {
        label.addEventListener("click", function () {
          var lang = label.textContent.trim();
          // Defer so the native radio toggle settles first, then sync the rest.
          setTimeout(function () {
            rememberLang(lang);
            applyLang(lang);
          }, 0);
        });
      });
    });
    var stored;
    try { stored = localStorage.getItem(LANG_KEY); } catch (e) {}
    if (stored) applyLang(stored);
  }

  document.addEventListener("DOMContentLoaded", function () {
    addCopyButtons();
    wireTabSync();
  });
})();
