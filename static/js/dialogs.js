import { $, $$ } from "./utils.js";

let lastFocus = null;

export function openModal(id, forced = false) {
  const modal = $("#" + id);
  lastFocus = document.activeElement;
  const title = modal.querySelector("h2");
  if (title) {
    if (!title.id) title.id = `${id}-title`;
    modal.setAttribute("aria-labelledby", title.id);
  }
  modal.classList.add("open");
  modal.dataset.forced = forced ? "1" : "0";
  setTimeout(() => modal.querySelector("button,input,select,textarea")?.focus(), 0);
}

export function closeModal(modal) {
  if (typeof modal === "string") modal = $("#" + modal);
  if (!modal || modal.dataset.forced === "1") return;
  modal.classList.remove("open");
  lastFocus?.focus?.();
}

export function initDialogs() {
  $$("[data-close]").forEach((button) => button.addEventListener("click", () => closeModal(button.closest(".modal"))));
  $$(".modal").forEach((modal) => modal.addEventListener("click", (event) => {
    if (event.target === modal) closeModal(modal);
  }));
  document.addEventListener("keydown", (event) => {
    const modal = $(".modal.open");
    if (!modal) return;
    if (event.key === "Escape") closeModal(modal);
    if (event.key !== "Tab") return;
    const focusable = $$("button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex='-1'])", modal);
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable.at(-1);
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  });
}
