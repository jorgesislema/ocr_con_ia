/* ══════════════════════════════════════════════════════════════════
   OCR Con IA — SaaS · lógica del frontend (TAREA 2 + flujo de 4 pasos)

   Autenticación JWT:
     * Login → POST /auth/login → token guardado en localStorage.
     * TODA petición fetch pasa por api(), que inyecta
       'Authorization: Bearer <token>'.
     * 401 → token limpiado y vuelta al login.
     * GET /auth/me alimenta la navbar (Hola, email | Plan | Uso X/Y).
     * Cerrar Sesión → borra el token y recarga.

   Flujo de negocio (igual que antes):
     1 Carga → POST /api/v1/documents → task_id
     2 Progreso → GET /api/v1/tasks/{id} (polling)
     3 Revisión → PATCH /api/v1/tasks/{id}
     4 Exportación → POST /api/v1/tasks/{id}/export
   ══════════════════════════════════════════════════════════════════ */

"use strict";

// ── Helpers (antes de cualquier uso) ──
const $ = (sel) => document.querySelector(sel);

// ══════════════════════════════════════════════════════════════════
//  AUTENTICACIÓN (TAREA 2)
// ══════════════════════════════════════════════════════════════════

const TOKEN_KEY = "ocr_token";

const getToken = () => localStorage.getItem(TOKEN_KEY);
const setToken = (t) => localStorage.setItem(TOKEN_KEY, t);
const clearToken = () => localStorage.removeItem(TOKEN_KEY);

/** Wrapper de fetch: inyecta el JWT en TODA petición al backend.
 *  Si el token expiró/ es inválido (401), cierra sesión automáticamente. */
async function api(url, options = {}) {
  const headers = { ...(options.headers || {}) };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(url, { ...options, headers });
  if (res.status === 401) {
    clearToken();
    showLogin("Tu sesión expiró. Inicia sesión de nuevo.");
    throw new Error("No autenticado");
  }
  return res;
}

function showLogin(message = "") {
  document.body.classList.remove("authenticated");
  $("#loginScreen").style.display = "flex";
  $("#userInfo").hidden = true;
  $("#logoutBtn").hidden = true;
  $("#loginError").textContent = message;
}

async function initAuthenticated() {
  const res = await api("/auth/me");
  if (!res.ok) {
    if (res.status !== 401) showLogin("No se pudo validar tu sesión.");
    return;
  }
  const me = await res.json();
  const limit = me.max_documents > 0 ? me.max_documents : "Ilimitado";
  $("#userInfo").textContent =
    `Hola, ${me.email} | Plan: ${me.plan === "pro" ? "Pro" : "Free"} | ` +
    `Uso: ${me.documents_used}/${limit} documentos`;
  $("#userInfo").hidden = false;
  $("#logoutBtn").hidden = false;
  $("#loginError").textContent = "";
  $("#loginScreen").style.display = "none";
  document.body.classList.add("authenticated");
}

$("#loginForm")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const email = $("#loginEmail").value.trim();
  const password = $("#loginPassword").value;
  $("#loginError").textContent = "";
  try {
    const res = await fetch("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Error ${res.status}`);
    }
    const data = await res.json();
    setToken(data.access_token);
    await initAuthenticated();
  } catch (exc) {
    $("#loginError").textContent = exc.message === "No autenticado"
      ? "Credenciales inválidas." : exc.message;
  }
});

$("#logoutBtn")?.addEventListener("click", () => {
  clearToken();          // borra el JWT
  location.reload();     // recarga → vuelve al login
});

// ── Estado global mínimo ──
const state = {
  taskId: null,
  invoice: null,       // InvoiceSchema actual (editable)
  pollTimer: null,
};

function goToStep(n) {
  document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
  $("#step-" + n).classList.add("active");
  document.querySelectorAll(".step").forEach((s) => {
    const stepNum = parseInt(s.dataset.step, 10);
    s.classList.toggle("active", stepNum === n);
    s.classList.toggle("done", stepNum < n);
  });
}

function log(msg) {
  const box = $("#progressLog");
  box.textContent += `[${new Date().toLocaleTimeString()}] ${msg}\n`;
  box.scrollTop = box.scrollHeight;
}

function setProgress(pct, text) {
  $("#progressBar").style.width = pct + "%";
  if (text) $("#progressText").textContent = text;
}

// ══════════════════════════════════════════════════════════════════
//  PASO 1 — Carga
// ══════════════════════════════════════════════════════════════════

const dropzone = $("#dropzone");
const fileInput = $("#fileInput");

$("#browseBtn").addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", () => {
  if (fileInput.files.length) uploadFile(fileInput.files[0]);
});

["dragenter", "dragover"].forEach((ev) =>
  dropzone.addEventListener(ev, (e) => {
    e.preventDefault();
    dropzone.classList.add("dragover");
  })
);
["dragleave", "drop"].forEach((ev) =>
  dropzone.addEventListener(ev, (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
  })
);
dropzone.addEventListener("drop", (e) => {
  const file = e.dataTransfer.files[0];
  if (file) uploadFile(file);
});

async function uploadFile(file) {
  $("#fileInfo").textContent = `📎 ${file.name} (${(file.size / 1024 / 1024).toFixed(2)} MB)`;
  goToStep(2);
  setProgress(15, "Subiendo documento…");
  log(`Subiendo "${file.name}"…`);

  const form = new FormData();
  form.append("file", file);
  try {
    // api() inyecta 'Authorization: Bearer <token>' (TAREA 2.3).
    // FormData: NO fijar Content-Type manualmente (el navegador pone el boundary).
    const res = await api("/api/v1/documents", { method: "POST", body: form });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      if (res.status === 403) {
        log("🚫 " + err.detail);
        setProgress(0, err.detail);
        setTimeout(() => goToStep(1), 4000);
        return;
      }
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const data = await res.json();
    state.taskId = data.task_id;
    log(`Tarea ${data.task_id} encolada (${data.page_count} página(s)).`);
    setProgress(35, "En cola del motor de extracción…");
    startPolling();
  } catch (exc) {
    if (exc.message === "No autenticado") return;
    log("ERROR: " + exc.message);
    setProgress(0, "Falló la subida: " + exc.message);
    setTimeout(() => goToStep(1), 2500);
  }
}

// ══════════════════════════════════════════════════════════════════
//  PASO 2 — Progreso (polling del estado)
// ══════════════════════════════════════════════════════════════════

function startPolling() {
  let tick = 0;
  state.pollTimer = setInterval(async () => {
    tick++;
    setProgress(Math.min(35 + tick * 6, 90), "La IA está extrayendo los datos…");
    try {
      const res = await api(`/api/v1/tasks/${state.taskId}`);
      const task = await res.json();
      if (task.status === "processing") log("Motor de IA procesando…");
      if (["completed", "needs_review"].includes(task.status)) {
        clearInterval(state.pollTimer);
        setProgress(100, "Extracción terminada.");
        state.invoice = task.extracted_data;
        state.validation = { is_valid: task.is_valid, issues: task.issues };
        log(`Estado final: ${task.status} · válido: ${task.is_valid}`);
        setTimeout(() => renderReview(task), 500);
      }
      if (task.status === "failed") {
        clearInterval(state.pollTimer);
        log("ERROR del worker: " + (task.error_message || "desconocido"));
        setProgress(0, "La extracción falló. Inténtalo de nuevo.");
        setTimeout(() => goToStep(1), 3000);
      }
    } catch (exc) {
      if (exc.message === "No autenticado") return;
      log("Error consultando estado: " + exc.message);
    }
  }, 1500);
}

// ══════════════════════════════════════════════════════════════════
//  PASO 3 — Revisión humana (tablas editables)
// ══════════════════════════════════════════════════════════════════

const META_FIELDS = [
  ["invoice_number", "Número"], ["issue_date", "Fecha emisión"],
  ["due_date", "Vencimiento"], ["currency", "Moneda"],
  ["region", "Región"], ["document_type", "Tipo"],
];

function renderReview(task) {
  const inv = state.invoice;
  const banner = $("#validationBanner");
  if (task.is_valid) {
    banner.className = "banner ok";
    banner.textContent = "✔ El motor de validación verificó la aritmética (total = subtotal + impuestos − descuentos).";
  } else {
    banner.className = "banner error";
    banner.innerHTML = "<strong>⚠ Revisión necesaria.</strong> " +
      (task.issues || []).map((i) => `• [${i.code}] ${i.message}`).join("<br>");
  }

  const metaBox = $("#metaFields");
  metaBox.innerHTML = "";
  META_FIELDS.forEach(([key, label]) => {
    const raw = key === "document_type" ? inv.document_type : inv[key];
    metaBox.appendChild(mkField(key, label, raw === null || raw === undefined ? "" : String(raw)));
  });
  metaBox.appendChild(mkField("supplier.name", "Emisor", inv.supplier?.name || ""));
  metaBox.appendChild(mkField("supplier.tax_id", "NIF/RUC emisor", inv.supplier?.tax_id || ""));
  metaBox.appendChild(mkField("customer.name", "Receptor", inv.customer?.name || ""));
  metaBox.appendChild(mkField("customer.tax_id", "NIF/RUC receptor", inv.customer?.tax_id || ""));

  renderTaxesTable();
  renderDiscountsTable();
  renderLinesTable();
  updateTotals();
  goToStep(3);
}

function mkField(path, label, value) {
  const wrap = document.createElement("div");
  wrap.className = "field";
  wrap.innerHTML = `<label>${label}</label>`;
  const input = document.createElement("input");
  input.value = value;
  input.addEventListener("change", () => {
    setByPath(state.invoice, path, input.value || null);
    updateTotals();
  });
  wrap.appendChild(input);
  return wrap;
}

function setByPath(obj, path, value) {
  const parts = path.split(".");
  let cur = obj;
  for (let i = 0; i < parts.length - 1; i++) {
    if (!cur[parts[i]] || typeof cur[parts[i]] !== "object") cur[parts[i]] = {};
    cur = cur[parts[i]];
  }
  cur[parts[parts.length - 1]] = value;
}

function num(v) {
  const n = parseFloat(String(v).replace(",", "."));
  return isNaN(n) ? 0 : n;
}

// ── Tabla de impuestos (array multi-impuesto) ──
function renderTaxesTable() {
  const tbody = $("#taxesTable tbody");
  tbody.innerHTML = "";
  state.invoice.taxes.forEach((t, idx) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td><input value="${t.type || ""}" data-k="type"></td>
      <td><input value="${t.rate ?? ""}" data-k="rate"></td>
      <td><input value="${t.base_amount ?? ""}" data-k="base_amount"></td>
      <td><input value="${t.amount ?? ""}" data-k="amount"></td>
      <td><button title="Eliminar">✕</button></td>`;
    row.querySelectorAll("input").forEach((inp) =>
      inp.addEventListener("change", () => {
        state.invoice.taxes[idx][inp.dataset.k] =
          inp.dataset.k === "type" ? inp.value : num(inp.value);
        updateTotals();
      })
    );
    row.querySelector("button").addEventListener("click", () => {
      state.invoice.taxes.splice(idx, 1);
      renderTaxesTable(); updateTotals();
    });
    tbody.appendChild(row);
  });
}

$("#addTaxBtn").addEventListener("click", () => {
  state.invoice.taxes.push({ type: "IVA", rate: 0, base_amount: 0, amount: 0 });
  renderTaxesTable();
});

// ── Tabla de descuentos ──
function renderDiscountsTable() {
  const tbody = $("#discountsTable tbody");
  tbody.innerHTML = "";
  state.invoice.discounts.forEach((d, idx) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td><input value="${d.concept || ""}" data-k="concept"></td>
      <td><input value="${d.amount ?? ""}" data-k="amount"></td>
      <td><button title="Eliminar">✕</button></td>`;
    row.querySelectorAll("input").forEach((inp) =>
      inp.addEventListener("change", () => {
        state.invoice.discounts[idx][inp.dataset.k] =
          inp.dataset.k === "concept" ? inp.value : num(inp.value);
        updateTotals();
      })
    );
    row.querySelector("button").addEventListener("click", () => {
      state.invoice.discounts.splice(idx, 1);
      renderDiscountsTable(); updateTotals();
    });
    tbody.appendChild(row);
  });
}

$("#addDiscountBtn").addEventListener("click", () => {
  state.invoice.discounts.push({ concept: "Descuento", amount: 0 });
  renderDiscountsTable();
});

// ── Tabla de líneas ──
function renderLinesTable() {
  const tbody = $("#linesTable tbody");
  tbody.innerHTML = "";
  state.invoice.line_items.forEach((li, idx) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td><input value="${li.description || ""}" data-k="description"></td>
      <td><input value="${li.quantity ?? ""}" data-k="quantity"></td>
      <td><input value="${li.unit_price ?? ""}" data-k="unit_price"></td>
      <td><input value="${li.subtotal ?? ""}" data-k="subtotal"></td>
      <td><button title="Eliminar">✕</button></td>`;
    row.querySelectorAll("input").forEach((inp) =>
      inp.addEventListener("change", () => {
        state.invoice.line_items[idx][inp.dataset.k] =
          inp.dataset.k === "description" ? inp.value : num(inp.value);
        updateTotals();
      })
    );
    row.querySelector("button").addEventListener("click", () => {
      state.invoice.line_items.splice(idx, 1);
      renderLinesTable(); updateTotals();
    });
    tbody.appendChild(row);
  });
}

// ── Recalculo en vivo (misma identidad que el backend, para feedback inmediato) ──
function updateTotals() {
  const inv = state.invoice;
  const linesSum = inv.line_items.reduce(
    (acc, li) => acc + num(li.subtotal ?? num(li.quantity) * num(li.unit_price)), 0);
  const taxesSum = inv.taxes.reduce((acc, t) => acc + num(t.amount), 0);
  const discSum = inv.discounts.reduce((acc, d) => acc + num(d.amount), 0);
  const computed = linesSum + taxesSum - discSum;

  inv.subtotal = linesSum;
  const box = $("#totalsBox");
  box.innerHTML = `
    <span>Subtotal: <strong>${linesSum.toFixed(2)}</strong></span>
    <span>Impuestos: <strong>${taxesSum.toFixed(2)}</strong></span>
    <span>Descuentos: <strong>-${discSum.toFixed(2)}</strong></span>
    <span class="total">TOTAL: ${computed.toFixed(2)} ${inv.currency || ""}</span>
    <span class="muted">declarado: ${num(inv.total).toFixed(2)}</span>`;
  box.querySelector(".total").style.color =
    Math.abs(computed - num(inv.total)) <= 0.02 ? "var(--success)" : "var(--error)";
}

// ── Acciones del paso 3 ──
$("#revalidateBtn").addEventListener("click", async () => {
  // Envía tal cual para que el BACKEND valide (regla: Python valida, no el navegador)
  await saveReview(false);
});

$("#approveBtn").addEventListener("click", async () => {
  await saveReview(true);
});

async function saveReview(approve) {
  try {
    const res = await api(`/api/v1/tasks/${state.taskId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ extracted_data: state.invoice, approve }),
    });
    const task = await res.json();
    if (!res.ok) throw new Error(task.detail || `HTTP ${res.status}`);
    state.invoice = task.extracted_data;
    if (task.status === "completed") {
      goToStep(4);
    } else {
      const banner = $("#validationBanner");
      banner.className = "banner error";
      banner.innerHTML = "<strong>⚠ Aún descuadrado.</strong> " +
        (task.issues || []).map((i) => `• [${i.code}] ${i.message}`).join("<br>");
    }
  } catch (exc) {
    if (exc.message === "No autenticado") return;
    alert("Error guardando la revisión: " + exc.message);
  }
}

$("#backToUpload").addEventListener("click", () => goToStep(1));

// ══════════════════════════════════════════════════════════════════
//  PASO 4 — Exportación
// ══════════════════════════════════════════════════════════════════

document.querySelectorAll(".btn.export").forEach((btn) =>
  btn.addEventListener("click", async () => {
    const fmt = btn.dataset.fmt;
    const res = await api(`/api/v1/tasks/${state.taskId}/export`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ formato: fmt }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      alert("Error exportando: " + (err.detail || res.status));
      return;
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = res.headers.get("content-disposition")?.match(/filename="?([^"]+)"?/)?.[1]
      || `documento.${fmt}`;
    a.click();
    URL.revokeObjectURL(url);
  })
);

$("#startOverBtn").addEventListener("click", () => {
  state.taskId = null;
  state.invoice = null;
  $("#progressLog").textContent = "";
  $("#fileInfo").textContent = "";
  fileInput.value = "";
  setProgress(0);
  goToStep(1);
});

// ══════════════════════════════════════════════════════════════════
//  ARRANQUE: sin token → login; con token → validar y abrir la app
// ══════════════════════════════════════════════════════════════════

(async function bootstrap() {
  if (!getToken()) {
    showLogin();
    return;
  }
  try {
    await initAuthenticated();
  } catch {
    showLogin();
  }
})();
