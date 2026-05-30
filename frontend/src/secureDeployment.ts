export const secureDeployment = import.meta.env.VITE_SECURE_DEPLOYMENT === "true";

function isEditableTarget(target: EventTarget | null): boolean {
  return target instanceof HTMLElement && Boolean(target.closest("input, textarea, select, label, button"));
}

export function installSecureShell(): void {
  if (!secureDeployment) return;

  const meta = document.createElement("meta");
  meta.name = "robots";
  meta.content = "noindex, nofollow, noarchive";
  document.head.appendChild(meta);

  document.addEventListener(
    "contextmenu",
    (event) => {
      if (isEditableTarget(event.target)) return;
      event.preventDefault();
    },
    { capture: true },
  );

  document.addEventListener(
    "keydown",
    (event) => {
      const key = event.key.toLowerCase();
      if (key === "f12") {
        event.preventDefault();
        return;
      }
      if (event.metaKey && event.altKey && ["i", "j", "c", "u"].includes(key)) {
        event.preventDefault();
        return;
      }
      if (event.ctrlKey && event.shiftKey && ["i", "j", "c", "k"].includes(key)) {
        event.preventDefault();
        return;
      }
      if ((event.metaKey || event.ctrlKey) && !event.shiftKey && key === "u") {
        event.preventDefault();
        return;
      }
      if ((event.metaKey || event.ctrlKey) && key === "s") {
        event.preventDefault();
      }
    },
    { capture: true },
  );

  document.addEventListener(
    "copy",
    (event) => {
      if (isEditableTarget(event.target)) return;
      if (document.querySelector(".preview-image--protected:hover, .preview-image--protected:focus-within")) {
        event.preventDefault();
      }
    },
    { capture: true },
  );

  document.addEventListener(
    "dragstart",
    (event) => {
      const target = event.target;
      if (target instanceof HTMLElement && target.closest(".preview-image--protected")) {
        event.preventDefault();
      }
    },
    { capture: true },
  );
}
