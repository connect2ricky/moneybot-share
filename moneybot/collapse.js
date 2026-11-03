// Lets any card be closed and opened by its heading. Closed cards are remembered in this browser.
(() => {
  const STORE = "shutCards";
  const CHEVRON = "▾";
  let shut = new Set();
  try { shut = new Set(JSON.parse(localStorage.getItem(STORE)) || []); } catch (e) {}

  const style = document.createElement("style");
  style.textContent = `
    .card > h2, .card :not(.card) h2 { cursor: pointer; }
    .fold { border: 0; background: none; padding: 0 6px 0 0; color: var(--text-3); font-size: 13px; line-height: 1; cursor: pointer; display: inline-block; transition: transform .15s; }
    .card.shut .fold { transform: rotate(-90deg); padding: 0 0 0 6px; }
    .card.shut { padding-bottom: 14px; }
    .card.shut h2 { margin: 0; }
    .foldhid { display: none !important; }`;
  document.head.append(style);

  const heading = card => card.querySelector("h2");
  // Only the heading's own text: a button inside it, like Hide on balances, is not part of the name.
  const title = h2 => [...h2.childNodes].filter(n => n.nodeType === Node.TEXT_NODE).map(n => n.textContent).join("").trim();
  // Headings that name a month stay one card from month to month.
  const keyOf = h2 => location.pathname + "|" + title(h2).replace(/ (in|for) [A-Z][a-z]+ \d{4}$/, "");

  function apply(card) {
    const h2 = heading(card);
    if (!h2) return;
    if (!h2.querySelector(".fold")) {
      const button = document.createElement("button");
      button.className = "fold";
      button.textContent = CHEVRON;
      h2.prepend(button);
    }
    const closed = shut.has(keyOf(h2));
    h2.querySelector(".fold").setAttribute("aria-label", `${closed ? "Open" : "Close"} ${title(h2)}`);
    h2.querySelector(".fold").setAttribute("aria-expanded", String(!closed));
    card.classList.toggle("shut", closed);
    card.querySelectorAll(".foldhid").forEach(el => el.classList.remove("foldhid"));
    if (!closed) return;
    for (let el = h2; el !== card; el = el.parentElement) {
      for (const sibling of el.parentElement.children) if (sibling !== el) sibling.classList.add("foldhid");
    }
  }
  const applyAll = () => document.querySelectorAll(".card").forEach(apply);

  document.addEventListener("click", e => {
    const h2 = e.target.closest(".card h2");
    if (!h2 || e.target.closest("button:not(.fold), a, input, select")) return;
    const key = keyOf(h2);
    shut.has(key) ? shut.delete(key) : shut.add(key);
    try { localStorage.setItem(STORE, JSON.stringify([...shut])); } catch (e) {}
    applyAll();
  });

  // Pages redraw their cards, so closed ones are closed again after each redraw.
  new MutationObserver(applyAll).observe(document.body, { childList: true, subtree: true });
  applyAll();
})();
