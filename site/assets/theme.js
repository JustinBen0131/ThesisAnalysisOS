(() => {
  if (!window.CSS || !CSS.supports("color", "light-dark(black, white)")) return;
  const key = "taos-reader-appearance";
  const root = document.documentElement;
  let select;
  function apply(value) {
    const explicit = value === "light" || value === "dark";
    if (explicit) root.dataset.readerTheme = value;
    else delete root.dataset.readerTheme;
    if (select) select.value = explicit ? value : "system";
  }
  try { apply(localStorage.getItem(key)); } catch { /* The current page still works without storage. */ }

  document.addEventListener("DOMContentLoaded", () => {
    const chrome = document.querySelector('meta[name="theme-color"]');
    if (chrome) {
      const syncColor = () => { chrome.content = getComputedStyle(document.body).backgroundColor; };
      new MutationObserver(syncColor).observe(root, {attributes:true, attributeFilter:["data-reader-theme", "data-mood"]});
      root.addEventListener("transitionend", event => {
        if (event.target === root && event.propertyName === "--bg") syncColor();
      });
      syncColor();
    }
    select = document.getElementById("reader-appearance");
    if (!select) return;
    select.value = root.dataset.readerTheme || "system";
    select.addEventListener("change", () => {
      const choice = select.value;
      apply(choice);
      try {
        if (choice === "system") localStorage.removeItem(key);
        else localStorage.setItem(key, choice);
      } catch { /* This choice lasts until the reader leaves the page. */ }
    });
    select.closest("label").hidden = false;
  });
  window.addEventListener("storage", event => {
    if (event.key === key || event.key === null) apply(event.newValue);
  });
})();
