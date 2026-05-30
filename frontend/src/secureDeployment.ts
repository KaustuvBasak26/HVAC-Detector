export const secureDeployment = import.meta.env.VITE_SECURE_DEPLOYMENT === "true";

export function installSecureShell(): void {
  if (!secureDeployment) return;

  const meta = document.createElement("meta");
  meta.name = "robots";
  meta.content = "noindex, nofollow";
  document.head.appendChild(meta);

  document.addEventListener(
    "contextmenu",
    (event) => {
      const target = event.target;
      if (target instanceof HTMLElement && target.closest("input, textarea, select, label")) {
        return;
      }
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
      if (event.ctrlKey && event.shiftKey && ["i", "j", "c", "k"].includes(key)) {
        event.preventDefault();
        return;
      }
      if (event.ctrlKey && !event.shiftKey && key === "u") {
        event.preventDefault();
      }
    },
    { capture: true },
  );
}
