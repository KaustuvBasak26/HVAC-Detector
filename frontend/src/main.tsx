import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";
import { installSecureShell } from "./secureDeployment";
import { initTheme } from "./theme";

initTheme();
installSecureShell();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
