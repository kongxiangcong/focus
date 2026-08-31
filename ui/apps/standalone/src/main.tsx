import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import "./standalone.css";

const root = document.getElementById("root");
if (root === null) {
  throw new Error("Focus Reader root element is missing");
}

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
