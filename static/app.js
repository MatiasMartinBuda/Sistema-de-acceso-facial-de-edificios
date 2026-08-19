/* Logic & Interactivity - Sistema Inteligente de Acceso Residencial Web */

let stream = null;
let recogInterval = null;
let doorActive = false;
let audioCtx = null;
let currentUsuario = null;

// Inicialización al cargar la página
document.addEventListener("DOMContentLoaded", () => {
  checkAuthStatus();
  initWebcam();
  iniciarChatBot();
  cargarAdminStats();
  cargarConfiguracion();
  cargarComboUsuariosFotos();
  cargarTablaUsuarios();
});

// --- 0. AUTENTICACIÓN (LOGIN / REGISTRO / SESIÓN) ---

async function checkAuthStatus() {
  const session = localStorage.getItem("acceso_user_session");
  const overlay = document.getElementById("auth-overlay");

  if (session) {
    currentUsuario = JSON.parse(session);
    document.getElementById("lbl-user-name").textContent = `👤 ${currentUsuario.nombre}`;
    overlay.classList.remove("active");
  } else {
    try {
      const res = await fetch("/api/auth/status");
      const data = await res.json();
      if (!data.registrado) {
        toggleAuthForm('register');
      } else {
        toggleAuthForm('login');
      }
    } catch (e) {}
    overlay.classList.add("active");
  }
}

function toggleAuthForm(mode) {
  const fLogin = document.getElementById("form-login");
  const fReg = document.getElementById("form-register");
  if (mode === 'register') {
    fLogin.style.display = "none";
    fReg.style.display = "flex";
  } else {
    fLogin.style.display = "flex";
    fReg.style.display = "none";
  }
}

async function loginApp(e) {
  e.preventDefault();
  const username = document.getElementById("login-username").value.trim();
  const password = document.getElementById("login-password").value.trim();

  try {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password })
    });
    const data = await res.json();

    if (data.exito) {
      currentUsuario = data.usuario;
      localStorage.setItem("acceso_user_session", JSON.stringify(currentUsuario));
      document.getElementById("lbl-user-name").textContent = `👤 ${currentUsuario.nombre}`;
      document.getElementById("auth-overlay").classList.remove("active");
    } else {
      alert(data.mensaje);
    }
  } catch (err) {
    alert("Error al iniciar sesión: " + err);
  }
}

async function registrarApp(e) {
  e.preventDefault();
  const nombre = document.getElementById("reg-nombre").value.trim();
  const username = document.getElementById("reg-username").value.trim();
  const password = document.getElementById("reg-password").value.trim();

  try {
    const res = await fetch("/api/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ nombre, username, password })
    });
    const data = await res.json();

    if (data.exito) {
      alert("Cuenta de administrador creada. Iniciando sesión...");
      document.getElementById("login-username").value = username;
      document.getElementById("login-password").value = password;
      loginApp(e);
    } else {
      alert(data.mensaje);
    }
  } catch (err) {
    alert("Error al registrar cuenta: " + err);
  }
}

function logoutApp() {
  localStorage.removeItem("acceso_user_session");
  currentUsuario = null;
  document.getElementById("auth-overlay").classList.add("active");
}

// --- NAVEGACIÓN ENTRE LAS 8 OPCIONES ---

function switchTab(tabId, btn) {
  document.querySelectorAll(".tab-content").forEach(el => el.classList.remove("active"));
  document.querySelectorAll(".tab-btn").forEach(el => el.classList.remove("active"));
  
  document.getElementById(tabId).classList.add("active");
  if (btn) btn.classList.add("active");

  if (tabId === "tab-config") cargarConfiguracion();
  if (tabId === "tab-agregar-fotos") cargarComboUsuariosFotos();
  if (tabId === "tab-usuarios") cargarTablaUsuarios();
  if (tabId === "tab-admin") cargarAdminStats();
}

let isProcessingFrame = false;
let ultimaBienvenidaMs = 0;

// 1. INICIALIZAR CÁMARA Y RECONOCIMIENTO EN VIVO (INTERVALO DE 900MS CON FRENO)
async function initWebcam() {
  const video = document.getElementById("webcam-video");
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: "user" }
    });
    video.srcObject = stream;
    if (recogInterval) clearInterval(recogInterval);
    recogInterval = setInterval(capturarYReconocer, 900);
  } catch (err) {
    console.error("Error webcam:", err);
  }
}

function capturarFrameBase64() {
  const video = document.getElementById("webcam-video");
  if (!video || !video.videoWidth) return null;

  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(video, 0, 0);
  return canvas.toDataURL("image/jpeg", 0.85);
}

async function capturarYReconocer() {
  if (doorActive || isProcessingFrame) return;

  isProcessingFrame = true;
  try {
    const b64 = capturarFrameBase64();
    if (!b64) return;

    const res = await fetch("/api/reconocer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image: b64 })
    });
    const data = await res.json();

    actualizarBadge(data);

    // Saludar y preguntar si es propietario o visita cuando se detecta un rostro desconocido
    const ahora = Date.now();
    if (data.rostro_detectado && !data.es_residente && (ahora - ultimaBienvenidaMs > 15000)) {
      ultimaBienvenidaMs = ahora;
      const saludo = "¡Hola! Bienvenido al edificio. ¿Sos propietario del departamento o venís de visita?";
      const logs = document.getElementById("chat-logs");
      if (logs) {
        logs.innerHTML += `<div class="chat-msg bot">${saludo}</div>`;
        logs.scrollTop = logs.scrollHeight;
      }
      hablarVozWeb(saludo);
    }

    if (data.estado === "permitido" && !doorActive) {
      abrirPuertaModal(data.nombre, data.depto);
    }
  } catch (err) {
  } finally {
    isProcessingFrame = false;
  }
}


function actualizarBadge(data) {
  const badge = document.getElementById("status-badge");
  const lblScore = document.getElementById("lbl-score");
  const lblLiveness = document.getElementById("lbl-liveness");

  lblScore.textContent = `${data.score || 0}%`;
  
  if (data.parpadeo_ok) {
    lblLiveness.textContent = "OK (Ojos / Parpadeo)";
    lblLiveness.style.color = "#6ee7b7";
  } else {
    lblLiveness.textContent = "Esperando ojos...";
    lblLiveness.style.color = "#f59e0b";
  }

  if (data.estado === "permitido") {
    badge.className = "status-badge granted";
    badge.innerHTML = `● ACCESO PERMITIDO - ${data.nombre.toUpperCase()}`;
  } else if (data.estado === "denegado") {
    badge.className = "status-badge denied";
    badge.innerHTML = `● ACCESO DENEGADO`;
  } else {
    badge.className = "status-badge searching";
    badge.innerHTML = `● BUSCANDO ROSTRO...`;
  }
}

// 2. REGISTRAR NUEVA PERSONA
async function enrolarPersona(e) {
  e.preventDefault();
  const nombre = document.getElementById("enrol-nombre").value.trim();
  const apellido = document.getElementById("enrol-apellido").value.trim();
  const depto = document.getElementById("enrol-depto").value.trim();
  const pin = document.getElementById("enrol-pin").value.trim();
  const categoria = document.getElementById("enrol-categoria").value;
  const telefono = document.getElementById("enrol-telefono").value.trim();
  const email = document.getElementById("enrol-email").value.trim();

  const progress = document.getElementById("enrol-progress");
  const textCount = document.getElementById("enrol-count-text");
  const btn = document.getElementById("btn-enrolar");

  btn.disabled = true;
  btn.textContent = "Capturando fotogramas...";

  const fotos = [];
  const total = 15;

  for (let i = 1; i <= total; i++) {
    const b64 = capturarFrameBase64();
    if (b64) fotos.push(b64);
    
    progress.style.width = `${(i / total) * 100}%`;
    textCount.textContent = `${i} / ${total} fotos capturadas`;
    await new Promise(r => setTimeout(r, 200));
  }

  textCount.textContent = "Enviando datos y entrenando modelo LBPH...";

  try {
    const res = await fetch("/api/enrolar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        nombre, apellido, depto, pin, categoria, telefono, email,
        fotos_base64: fotos
      })
    });
    const data = await res.json();
    alert(data.mensaje);

    // Vaciar los campos para el próximo enrolamiento
    document.getElementById("enrol-nombre").value = "";
    document.getElementById("enrol-apellido").value = "";
    document.getElementById("enrol-depto").value = "";
    document.getElementById("enrol-pin").value = "";
    document.getElementById("enrol-telefono").value = "";
    document.getElementById("enrol-email").value = "";
    document.getElementById("enrol-categoria").value = "propietario";

    cargarAdminStats();
    cargarTablaUsuarios();
  } catch (err) {
    alert("Error al enrolar persona: " + err);
  } finally {
    btn.disabled = false;
    btn.textContent = "Capturar Rostros y Guardar";
    progress.style.width = "0%";
    textCount.textContent = "0 / 15 fotos capturadas";
  }
}


// 3. MÓDULO AGREGAR FOTOS A USUARIO EXISTENTE
async function cargarComboUsuariosFotos() {
  const sel = document.getElementById("select-usuario-fotos");
  if (!sel) return;

  try {
    const res = await fetch("/api/usuarios");
    const usuarios = await res.json();
    if (usuarios.length === 0) {
      sel.innerHTML = '<option value="">No hay usuarios enrolados todavía</option>';
      return;
    }
    sel.innerHTML = usuarios.map(u => `<option value="${u.label_lbph}">${u.nombre} (Depto ${u.depto} - ${u.cant_fotos} fotos)</option>`).join("");
  } catch (e) {}
}

async function agregarFotosUsuario(e) {
  e.preventDefault();
  const label = parseInt(document.getElementById("select-usuario-fotos").value);
  if (!label) {
    alert("Selecciona un usuario válido.");
    return;
  }

  const progress = document.getElementById("add-progress");
  const textCount = document.getElementById("add-count-text");
  const btn = document.getElementById("btn-agregar-fotos");

  btn.disabled = true;
  btn.textContent = "Capturando fotogramas de refuerzo...";

  const fotos = [];
  const total = 10;

  for (let i = 1; i <= total; i++) {
    const b64 = capturarFrameBase64();
    if (b64) fotos.push(b64);
    
    progress.style.width = `${(i / total) * 100}%`;
    textCount.textContent = `${i} / ${total} fotos de refuerzo`;
    await new Promise(r => setTimeout(r, 200));
  }

  textCount.textContent = "Reentrenando modelo LBPH...";

  try {
    const res = await fetch("/api/usuarios/agregar-fotos", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ label, fotos_base64: fotos })
    });
    const data = await res.json();
    alert(data.mensaje);
    cargarComboUsuariosFotos();
    cargarTablaUsuarios();
  } catch (err) {
    alert("Error al agregar fotos: " + err);
  } finally {
    btn.disabled = false;
    btn.textContent = "📸 Capturar Nuevas Fotos y Reentrenar";
    progress.style.width = "0%";
    textCount.textContent = "0 / 10 fotos capturadas";
  }
}

// 4. MÓDULO GESTIÓN DE USUARIOS ENROLADOS (TABLA, LISTA NEGRA, BORRAR)
async function cargarTablaUsuarios() {
  const tbody = document.getElementById("tabla-usuarios-body");
  if (!tbody) return;

  try {
    const res = await fetch("/api/usuarios");
    const usuarios = await res.json();

    if (usuarios.length === 0) {
      tbody.innerHTML = '<tr><td colspan="9" style="padding: 15px; text-align: center; color: var(--text-sub);">No hay usuarios enrolados registrados en el sistema.</td></tr>';
      return;
    }

    tbody.innerHTML = usuarios.map(u => `
      <tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">
        <td style="padding: 10px; font-weight: 700; color: #6ee7b7;">#${u.label_lbph}</td>
        <td style="padding: 10px; font-weight: 600;">${u.nombre}</td>
        <td style="padding: 10px; color: var(--accent-amber);">${u.depto}</td>
        <td style="padding: 10px; color: var(--text-sub);">${u.categoria}</td>
        <td style="padding: 10px;">${u.pin ? '🔑 ' + u.pin : '-'}</td>
        <td style="padding: 10px; color: #93c5fd;">${u.telefono ? '📱 ' + u.telefono : '-'}</td>
        <td style="padding: 10px;">${u.cant_fotos} fotos</td>
        <td style="padding: 10px;">
          ${u.lista_negra ? '<span style="color: var(--accent-red); font-weight:700;">🚫 SÍ</span>' : '<span style="color: var(--text-sub);">No</span>'}
        </td>
        <td style="padding: 10px; text-align: center; display: flex; gap: 6px; justify-content: center;">
          <button onclick="toggleListaNegra(${u.label_lbph}, ${!u.lista_negra})" class="btn" style="font-size: 0.75rem; padding: 4px 8px; background: ${u.lista_negra ? 'var(--accent-green)' : 'var(--accent-red)'}">
            ${u.lista_negra ? 'Quitar Lista Negra' : '🚫 Lista Negra'}
          </button>
          <button onclick="eliminarUsuario(${u.label_lbph}, '${u.nombre}')" class="btn btn-secondary" style="font-size: 0.75rem; padding: 4px 8px; color: #fca5a5;">
            🗑️ Eliminar
          </button>
        </td>
      </tr>
    `).join("");
  } catch (e) {
    console.error("Error al cargar tabla:", e);
  }
}

async function toggleListaNegra(label, nuevoEstado) {
  try {
    const res = await fetch(`/api/usuarios/${label}/lista-negra`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lista_negra: nuevoEstado })
    });
    const data = await res.json();
    alert(data.mensaje);
    cargarTablaUsuarios();
    cargarAdminStats();
  } catch (err) {
    alert("Error al modificar lista negra: " + err);
  }
}

async function eliminarUsuario(label, nombre) {
  if (!confirm(`¿Estás seguro de borrar a ${nombre} (#${label}) del sistema y eliminar sus fotos?`)) return;

  try {
    const res = await fetch(`/api/usuarios/${label}`, { method: "DELETE" });
    const data = await res.json();
    alert(data.mensaje);
    cargarTablaUsuarios();
    cargarAdminStats();
    cargarComboUsuariosFotos();
  } catch (err) {
    alert("Error al eliminar usuario: " + err);
  }
}

// 5. MÓDULO GENERAR Y DESCARGAR REPORTE EXCEL (.XLSX)
function descargarReporteExcel() {
  window.location.href = "/api/reporte/excel";
}

// 6. MÓDULO RESPALDO GOOGLE DRIVE
async function sincronizarDrive() {
  try {
    const res = await fetch("/api/drive/sync", { method: "POST" });
    const data = await res.json();
    alert(data.mensaje);
  } catch (e) {
    alert("Error al respaldar en Drive: " + e);
  }
}

// 7. NOTIFICACIONES WHATSAPP PARA VISITAS (CAMINO C)
async function solicitarWhatsappModal() {
  const depto = prompt("Ingresá el número de Departamento a consultar (ej. 4B):", "4B");
  if (!depto) return;
  const nombreVisita = prompt("Ingresá el nombre de la visita:", "Visita");
  if (!nombreVisita) return;

  try {
    const res = await fetch("/api/visita/whatsapp", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ depto, nombre_visita: nombreVisita })
    });
    const data = await res.json();

    if (!data.exito) {
      alert(data.mensaje);
      return;
    }

    const listDiv = document.getElementById("wa-contactos-list");
    listDiv.innerHTML = data.contactos.map(c => `
      <div style="background: rgba(255,255,255,0.05); padding: 12px; border-radius: 10px; text-align: left;">
        <p style="font-weight: 700; color: #fff;">👤 ${c.nombre} (${c.telefono})</p>
        <p style="font-size: 0.8rem; color: var(--text-sub); margin: 6px 0;">${c.mensaje}</p>
        <a href="${c.url}" target="_blank" class="btn" style="display: block; text-align: center; text-decoration: none; background: #25D366; color: #000; font-weight: 800;">
          📲 Abrir WhatsApp Web / App
        </a>
      </div>
    `).join("");

    document.getElementById("wa-modal").classList.add("active");
  } catch (err) {
    alert("Error al generar consulta de WhatsApp: " + err);
  }
}

function cerrarWaModal() {
  document.getElementById("wa-modal").classList.remove("active");
}

// 8. ASISTENTE IA & AUDIO / PUERTA
function reproducirChimeWeb() {
  try {
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const osc1 = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc1.type = "sine";
    osc1.frequency.setValueAtTime(1200, audioCtx.currentTime);
    osc1.frequency.exponentialRampToValueAtTime(1800, audioCtx.currentTime + 0.2);
    gain.gain.setValueAtTime(0.3, audioCtx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.3);
    osc1.connect(gain);
    gain.connect(audioCtx.destination);
    osc1.start();
    osc1.stop(audioCtx.currentTime + 0.3);
  } catch (e) {}
}

function hablarVozWeb(texto) {
  if ('speechSynthesis' in window) {
    const msg = new SpeechSynthesisUtterance(texto);
    msg.lang = 'es-ES';
    msg.rate = 1.0;
    window.speechSynthesis.speak(msg);
  }
}

function abrirPuertaModal(nombre, depto) {
  doorActive = true;
  reproducirChimeWeb();
  hablarVozWeb(`¡Bienvenido ${nombre}! Acceso concedido.`);

  const modal = document.getElementById("door-modal");
  const timerSec = document.getElementById("modal-timer-sec");
  modal.classList.add("active");

  let seg = 6;
  timerSec.textContent = seg;

  const countTimer = setInterval(() => {
    seg--;
    timerSec.textContent = seg;
    if (seg <= 0) {
      clearInterval(countTimer);
      modal.classList.remove("active");
      doorActive = false;
    }
  }, 1000);

  animarCanvasPuerta(nombre, depto);
}

function animarCanvasPuerta(nombre, depto) {
  const canvas = document.getElementById("door-canvas");
  const ctx = canvas.getContext("2d");
  const W = canvas.width;
  const H = canvas.height;

  let step = 0;
  const maxSteps = 30;
  const maxOffset = 150;

  function renderFrame() {
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = "#030712";
    ctx.fillRect(0, 0, W, H);

    ctx.fillStyle = "#10b981";
    ctx.font = "bold 16px Inter";
    ctx.textAlign = "center";
    ctx.fillText("✨ ACCESO PERMITIDO ✨", W / 2, 70);

    ctx.fillStyle = "#ffffff";
    ctx.font = "bold 20px Inter";
    ctx.fillText((nombre || "RESIDENTE").toUpperCase(), W / 2, 110);

    if (depto) {
      ctx.fillStyle = "#a7f3d0";
      ctx.font = "14px Inter";
      ctx.fillText(`Departamento ${depto}`, W / 2, 140);
    }

    ctx.strokeStyle = "#4b5563";
    ctx.lineWidth = 4;
    ctx.strokeRect(30, 15, W - 60, H - 30);

    const currentOffset = (step / maxSteps) * maxOffset;

    const lx1 = 35 - currentOffset;
    ctx.fillStyle = "#1e3a8a";
    ctx.strokeStyle = "#60a5fa";
    ctx.lineWidth = 2;
    ctx.fillRect(lx1, 20, 210, H - 40);
    ctx.strokeRect(lx1, 20, 210, H - 40);

    const rx1 = 255 + currentOffset;
    ctx.fillRect(rx1, 20, 210, H - 40);
    ctx.strokeRect(rx1, 20, 210, H - 40);

    if (step < maxSteps) {
      step++;
      requestAnimationFrame(renderFrame);
    }
  }

  renderFrame();
}

async function iniciarChatBot() {
  try {
    const res = await fetch("/api/chat/iniciar", { method: "POST" });
    const data = await res.json();
    if (data.respuesta) {
      document.getElementById("chat-logs").innerHTML = `
        <div class="chat-msg bot">${data.respuesta}</div>
      `;
    }
  } catch (e) {}
}

async function enviarMensajeChat(e) {
  e.preventDefault();
  const input = document.getElementById("chat-input");
  const txt = input.value.trim();
  if (!txt) return;

  const logs = document.getElementById("chat-logs");
  logs.innerHTML += `<div class="chat-msg user">${txt}</div>`;
  input.value = "";
  logs.scrollTop = logs.scrollHeight;

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mensaje: txt })
    });
    const data = await res.json();
    
    logs.innerHTML += `<div class="chat-msg bot">${data.respuesta}</div>`;
    logs.scrollTop = logs.scrollHeight;

    if (data.respuesta) hablarVozWeb(data.respuesta);
  } catch (err) {
    console.error("Error chat:", err);
  }
}

async function cargarAdminStats() {
  try {
    const res = await fetch("/api/admin/stats");
    const data = await res.json();

    const listAlertas = document.getElementById("alertas-list");
    listAlertas.innerHTML = data.alertas.map(a => `<li style="padding: 6px; background: rgba(255,255,255,0.04); border-radius: 6px; font-size: 0.85rem;">${a}</li>`).join("");

    const listPersonas = document.getElementById("personas-list");
    listPersonas.innerHTML = data.personas.map(p => `
      <li style="padding: 8px; background: rgba(255,255,255,0.04); border-radius: 8px; font-size: 0.85rem; display: flex; justify-content: space-between;">
        <span><strong>${p.nombre}</strong> (${p.categoria})</span>
        <span style="color: var(--accent-amber);">Depto ${p.depto}</span>
      </li>
    `).join("");
  } catch (e) {}
}

async function preguntarIA(e) {
  e.preventDefault();
  const q = document.getElementById("admin-question").value;
  const box = document.getElementById("admin-ai-answer");
  box.style.display = "block";
  box.innerHTML = "<em>Procesando consulta con la IA...</em>";

  try {
    const res = await fetch("/api/admin/pregunta", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pregunta: q })
    });
    const data = await res.json();
    box.innerHTML = `<strong>Respuesta IA:</strong><br>${data.respuesta}`;
  } catch (err) {
    box.innerHTML = "Error al consultar a la IA: " + err;
  }
}

function descargarBackupZip() {
  window.location.href = "/api/backup/export";
}

async function probarEnvioCorreo() {
  const email = prompt("Ingresá la dirección de correo electrónico donde enviar el email de prueba:", "ejemplo@gmail.com");
  if (!email) return;

  try {
    const res = await fetch("/api/config/test-email", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email })
    });
    const data = await res.json();
    alert(data.mensaje);
  } catch (err) {
    alert("Error al enviar email de prueba: " + err);
  }
}

async function cargarConfiguracion() {
  try {
    const res = await fetch("/api/config");
    const cfg = await res.json();

    if (document.getElementById("cfg-umbral")) {
      document.getElementById("cfg-umbral").value = cfg.UMBRAL_CONFIANZA_RESIDENTE || 60;
      document.getElementById("cfg-duracion-puerta").value = cfg.DURACION_PUERTA_MS || 6000;
      document.getElementById("cfg-fotos-enrolamiento").value = cfg.FOTOS_POR_ENROLAMIENTO || 20;

      document.getElementById("cfg-usar-ia").checked = !!cfg.USAR_IA_GENERATIVA;
      document.getElementById("cfg-ia-provider").value = cfg.IA_PROVIDER || "ollama";
      document.getElementById("cfg-ollama-model").value = cfg.OLLAMA_MODEL || "mistral";
      document.getElementById("cfg-gemini-key").value = cfg.GEMINI_API_KEY || "";

      if (document.getElementById("cfg-notificar-email")) {
        document.getElementById("cfg-notificar-email").checked = cfg.NOTIFICAR_VISITAS_POR_EMAIL !== false;
        document.getElementById("cfg-smtp-host").value = cfg.SMTP_HOST || "smtp.gmail.com";
        document.getElementById("cfg-smtp-port").value = cfg.SMTP_PORT || 587;
        document.getElementById("cfg-smtp-user").value = cfg.SMTP_USER || "";
        document.getElementById("cfg-smtp-pass").value = cfg.SMTP_PASSWORD || "";
      }

      document.getElementById("cfg-sincronizar-drive").checked = !!cfg.SINCRONIZAR_DRIVE;
      document.getElementById("cfg-drive-dir").value = cfg.GOOGLE_DRIVE_DIR || "";
    }
  } catch (err) {}
}

async function guardarConfiguracion(e) {
  e.preventDefault();
  const btn = document.getElementById("btn-guardar-cfg");
  btn.disabled = true;
  btn.textContent = "Guardando...";

  const nuevosDatos = {
    UMBRAL_CONFIANZA_RESIDENTE: parseFloat(document.getElementById("cfg-umbral").value),
    DURACION_PUERTA_MS: parseInt(document.getElementById("cfg-duracion-puerta").value),
    FOTOS_POR_ENROLAMIENTO: parseInt(document.getElementById("cfg-fotos-enrolamiento").value),
    USAR_IA_GENERATIVA: document.getElementById("cfg-usar-ia").checked,
    IA_PROVIDER: document.getElementById("cfg-ia-provider").value,
    OLLAMA_MODEL: document.getElementById("cfg-ollama-model").value.trim(),
    GEMINI_API_KEY: document.getElementById("cfg-gemini-key").value.trim(),
    NOTIFICAR_VISITAS_POR_EMAIL: document.getElementById("cfg-notificar-email") ? document.getElementById("cfg-notificar-email").checked : true,
    SMTP_HOST: document.getElementById("cfg-smtp-host") ? document.getElementById("cfg-smtp-host").value.trim() : "smtp.gmail.com",
    SMTP_PORT: document.getElementById("cfg-smtp-port") ? parseInt(document.getElementById("cfg-smtp-port").value) : 587,
    SMTP_USER: document.getElementById("cfg-smtp-user") ? document.getElementById("cfg-smtp-user").value.trim() : "",
    SMTP_PASSWORD: document.getElementById("cfg-smtp-pass") ? document.getElementById("cfg-smtp-pass").value.trim() : "",
    SINCRONIZAR_DRIVE: document.getElementById("cfg-sincronizar-drive").checked,
    GOOGLE_DRIVE_DIR: document.getElementById("cfg-drive-dir").value.trim()
  };

  try {
    const res = await fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(nuevosDatos)
    });
    const data = await res.json();
    alert(data.mensaje);
  } catch (err) {
    alert("Error al guardar configuración: " + err);
  } finally {
    btn.disabled = false;
    btn.textContent = "💾 Guardar Cambios";
  }
}

