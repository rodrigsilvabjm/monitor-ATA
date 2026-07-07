const TOTAL_LINES = window.gatewayMonitorInitialSnapshot.lines.length;
const usageHistory = [];
let congestionStartedAt = null;
let congestionTimerInterval = null;
let activeCallTimerInterval = null;

const statusLabels = {
  idle: "Livre",
  busy: "Ocupada",
  ringing: "Chamando",
  unavailable: "Indisponivel",
  unknown: "Desconhecida",
  not_configured: "Sem OID",
  configured: "Configurada",
  disabled: "Desabilitado",
};

const badgeClasses = {
  idle: "text-bg-success",
  busy: "text-bg-danger",
  ringing: "text-bg-warning",
  unavailable: "text-bg-secondary",
  unknown: "text-bg-secondary",
  not_configured: "text-bg-secondary",
  configured: "text-bg-info",
  disabled: "text-bg-dark",
};

const eventLabels = {
  state_change: "Mudanca",
  congestion_start: "Congestionou",
  congestion_end: "Liberou",
};

const eventClasses = {
  state_change: "event-pill event-state",
  congestion_start: "event-pill event-danger",
  congestion_end: "event-pill event-success",
};

function updateHeaderClock() {
  const clock = document.getElementById("header-clock");
  if (!clock) {
    return;
  }

  clock.textContent = new Date().toLocaleString("pt-BR");
}

function startHeaderClock() {
  updateHeaderClock();
  window.setInterval(updateHeaderClock, 1000);
}

function renderSnapshot(snapshot) {
  const counts = calculateCounts(snapshot);
  const occupancy = Math.round((counts.busy / TOTAL_LINES) * 100);

  document.getElementById("updated-at").textContent = new Date(
    snapshot.updated_at
  ).toLocaleString("pt-BR");

  renderMetrics(counts, occupancy, snapshot);
  renderLines(snapshot);
  renderHeatmap(snapshot);
  pushUsagePoint(occupancy);
  drawUsageChart();
}

function calculateCounts(snapshot) {
  return snapshot.lines.reduce(
    (acc, line) => {
      if (line.status === "busy") acc.busy += 1;
      if (line.status === "idle") acc.idle += 1;
      if (line.status === "ringing") acc.ringing += 1;
      if (!["busy", "idle", "ringing"].includes(line.status)) acc.other += 1;
      return acc;
    },
    { busy: 0, idle: 0, ringing: 0, other: 0 }
  );
}

function renderMetrics(counts, occupancy, snapshot) {
  document.getElementById("busy-count").textContent = counts.busy;
  document.getElementById("busy-label").textContent = `${counts.busy} de ${TOTAL_LINES} linhas`;
  document.getElementById("idle-count").textContent = counts.idle;
  document.getElementById("idle-label").textContent = `${counts.idle} disponiveis`;
  document.getElementById("occupancy-percent").textContent = `${occupancy}%`;
  document.getElementById("occupancy-bar").style.width = `${occupancy}%`;

  const summary = document.getElementById("line-summary");
  summary.textContent = `${counts.busy} ocupadas - ${counts.idle} livres`;
  summary.className = `badge ${occupancy >= 100 ? "text-bg-danger" : "text-bg-secondary"}`;

  updateCongestionState(counts.busy === TOTAL_LINES, snapshot.updated_at);
}

function updateCongestionState(isCongested, updatedAt) {
  const card = document.getElementById("congestion-card");
  const label = document.getElementById("congestion-label");

  if (isCongested && !congestionStartedAt) {
    congestionStartedAt = new Date(updatedAt);
    startCongestionTimer();
  }

  if (!isCongested) {
    congestionStartedAt = null;
    stopCongestionTimer();
    document.getElementById("congestion-timer").textContent = "00:00";
  }

  card.classList.toggle("is-congested", isCongested);
  label.textContent = isCongested ? "Todas as linhas ocupadas" : "Sem congestionamento";
}

function startCongestionTimer() {
  if (congestionTimerInterval) {
    return;
  }

  congestionTimerInterval = window.setInterval(() => {
    if (!congestionStartedAt) {
      return;
    }
    const elapsedSeconds = Math.floor((Date.now() - congestionStartedAt.getTime()) / 1000);
    document.getElementById("congestion-timer").textContent = formatClock(elapsedSeconds);
  }, 1000);
}

function stopCongestionTimer() {
  if (congestionTimerInterval) {
    window.clearInterval(congestionTimerInterval);
    congestionTimerInterval = null;
  }
}

function formatClock(totalSeconds) {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function formatDuration(totalSeconds) {
  const safeSeconds = Math.max(totalSeconds || 0, 0);
  const hours = Math.floor(safeSeconds / 3600);
  const minutes = Math.floor((safeSeconds % 3600) / 60);
  const seconds = safeSeconds % 60;
  if (hours > 0) {
    return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function renderLines(snapshot) {
  snapshot.lines.forEach((line) => {
    const card = document.querySelector(`[data-line="${line.line}"]`);
    if (!card) {
      return;
    }

    const status = line.status || "unknown";
    const badge = card.querySelector(".line-status");
    const message = card.querySelector(".line-message");
    const raw = card.querySelector(".line-raw");

    card.dataset.status = status;
    badge.className = `line-status badge ${badgeClasses[status] || "text-bg-secondary"}`;
    badge.textContent = statusLabels[status] || status;
    message.textContent = line.message || "Leitura recebida";
    raw.textContent = `Valor: ${line.raw_value || "--"}`;
  });
}

function renderHeatmap(snapshot) {
  snapshot.lines.forEach((line) => {
    const cell = document.querySelector(`[data-heat-line="${line.line}"]`);
    if (!cell) {
      return;
    }
    cell.dataset.status = line.status || "unknown";
    cell.title = `Linha ${line.line}: ${statusLabels[line.status] || line.status}`;
  });
}

function pushUsagePoint(occupancy) {
  usageHistory.push({
    value: occupancy,
    time: new Date(),
  });

  if (usageHistory.length > 40) {
    usageHistory.shift();
  }
}

function drawUsageChart() {
  const canvas = document.getElementById("usage-chart");
  const context = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  const padding = 28;
  const chartWidth = width - padding * 2;
  const chartHeight = height - padding * 2;

  context.clearRect(0, 0, width, height);
  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, width, height);

  drawGrid(context, padding, chartWidth, chartHeight);

  if (usageHistory.length < 2) {
    drawEmptyChart(context, width, height);
    return;
  }

  context.beginPath();
  usageHistory.forEach((point, index) => {
    const x = padding + (index / (usageHistory.length - 1)) * chartWidth;
    const y = padding + chartHeight - (point.value / 100) * chartHeight;
    if (index === 0) {
      context.moveTo(x, y);
    } else {
      context.lineTo(x, y);
    }
  });
  context.lineWidth = 3;
  context.strokeStyle = "#0d6efd";
  context.stroke();

  const latest = usageHistory[usageHistory.length - 1];
  const x = padding + chartWidth;
  const y = padding + chartHeight - (latest.value / 100) * chartHeight;
  context.fillStyle = latest.value >= 100 ? "#dc3545" : "#0d6efd";
  context.beginPath();
  context.arc(x, y, 5, 0, Math.PI * 2);
  context.fill();
}

function drawGrid(context, padding, chartWidth, chartHeight) {
  context.strokeStyle = "#e9eef5";
  context.lineWidth = 1;
  context.fillStyle = "#6c757d";
  context.font = "12px system-ui, sans-serif";

  [0, 25, 50, 75, 100].forEach((value) => {
    const y = padding + chartHeight - (value / 100) * chartHeight;
    context.beginPath();
    context.moveTo(padding, y);
    context.lineTo(padding + chartWidth, y);
    context.stroke();
    context.fillText(`${value}%`, 4, y + 4);
  });
}

function drawEmptyChart(context, width, height) {
  context.fillStyle = "#6c757d";
  context.font = "14px system-ui, sans-serif";
  context.textAlign = "center";
  context.fillText("Aguardando dados em tempo real", width / 2, height / 2);
  context.textAlign = "start";
}

function setConnectionState(isConnected, label) {
  const indicator = document.getElementById("ws-indicator");
  const text = document.getElementById("ws-label");

  indicator.classList.toggle("is-connected", isConnected);
  indicator.classList.toggle("is-disconnected", !isConnected);
  text.textContent = label;
}

function connectGatewaySocket() {
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${scheme}://${window.location.host}/ws/gateway-lines`);

  socket.addEventListener("open", () => {
    setConnectionState(true, "Tempo real ativo");
  });

  socket.addEventListener("message", (event) => {
    renderSnapshot(JSON.parse(event.data));
    loadEvents();
  });

  socket.addEventListener("close", () => {
    setConnectionState(false, "Reconectando");
    window.setTimeout(connectGatewaySocket, 2000);
  });

  socket.addEventListener("error", () => {
    setConnectionState(false, "Falha no tempo real");
    socket.close();
  });
}

function renderAsteriskSnapshot(snapshot) {
  document.getElementById("simultaneous-calls").textContent = snapshot.simultaneous_calls;
  document.getElementById("average-call-duration").textContent = formatDuration(
    snapshot.average_duration_seconds
  );
  document.getElementById("missed-calls").textContent = snapshot.missed_calls;
  document.getElementById("ami-status").textContent = snapshot.connected ? "Online" : "Offline";
  document.getElementById("asterisk-state").textContent = snapshot.connected
    ? "AMI conectado"
    : "AMI desconectado";
  document.getElementById("ami-updated-at").textContent = new Date(
    snapshot.updated_at
  ).toLocaleString("pt-BR");

  const summary = document.getElementById("calls-summary");
  summary.textContent = `${snapshot.simultaneous_calls} ativas`;
  summary.className = `badge ${snapshot.simultaneous_calls > 0 ? "text-bg-primary" : "text-bg-secondary"}`;

  renderActiveCalls(snapshot.active_calls);
}

function renderActiveCalls(activeCalls) {
  const table = document.getElementById("active-calls-table");
  if (!table) {
    return;
  }

  if (activeCalls.length === 0) {
    table.innerHTML = '<tr><td colspan="6" class="text-secondary">Sem chamadas ativas</td></tr>';
    return;
  }

  table.innerHTML = activeCalls.map((call) => `
    <tr data-started-at="${call.started_at}">
      <td>${call.source_number || "--"}</td>
      <td>${call.destination_number || "--"}</td>
      <td>${call.answered_extension || "--"}</td>
      <td>${call.fxo_line || "--"}</td>
      <td><span class="event-pill">${call.status}</span></td>
      <td class="call-duration">${formatDuration(call.duration_seconds)}</td>
    </tr>
  `).join("");

  startActiveCallTimer();
}

function startActiveCallTimer() {
  if (activeCallTimerInterval) {
    return;
  }

  activeCallTimerInterval = window.setInterval(() => {
    document.querySelectorAll("[data-started-at]").forEach((row) => {
      const startedAt = new Date(row.dataset.startedAt);
      const elapsedSeconds = Math.floor((Date.now() - startedAt.getTime()) / 1000);
      const durationCell = row.querySelector(".call-duration");
      if (durationCell) {
        durationCell.textContent = formatDuration(elapsedSeconds);
      }
    });
  }, 1000);
}

function connectAsteriskSocket() {
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${scheme}://${window.location.host}/ws/asterisk`);

  socket.addEventListener("message", (event) => {
    renderAsteriskSnapshot(JSON.parse(event.data));
  });

  socket.addEventListener("close", () => {
    window.setTimeout(connectAsteriskSocket, 2000);
  });
}

async function loadEvents() {
  const table = document.getElementById("events-table");
  if (!table) {
    return;
  }

  try {
    const response = await fetch("/api/events?limit=8");
    const events = await response.json();
    if (events.length === 0) {
      table.innerHTML = '<tr><td colspan="4" class="text-secondary">Sem eventos gravados</td></tr>';
      return;
    }

    table.innerHTML = events.map((event) => `
      <tr>
        <td>${formatEventTime(event.created_at)}</td>
        <td><span class="${eventClasses[event.event_type] || "event-pill"}">${eventLabels[event.event_type] || event.event_type}</span></td>
        <td><span class="history-lines">${event.busy_lines} ocup. / ${event.idle_lines} livres</span></td>
        <td class="history-message">${formatEventSummary(event)}</td>
      </tr>
    `).join("");
  } catch {
    table.innerHTML = '<tr><td colspan="4" class="text-secondary">Historico indisponivel</td></tr>';
  }
}

function formatEventTime(value) {
  return new Date(value).toLocaleTimeString("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function formatEventSummary(event) {
  if (event.event_type === "congestion_start") {
    return "Todas as linhas ocupadas";
  }
  if (event.event_type === "congestion_end") {
    return `Congestionamento encerrado em ${formatDuration(event.duration)}`;
  }
  return simplifyLineChanges(event.message);
}

function simplifyLineChanges(message) {
  if (!message) {
    return "--";
  }

  return message
    .replaceAll("idle -> busy", "ocupou")
    .replaceAll("busy -> idle", "liberou")
    .replaceAll("busy -> ringing", "chamando")
    .replaceAll("ringing -> busy", "ocupou")
    .split(";")
    .map((item) => item.trim())
    .slice(0, 3)
    .join(" | ");
}

startHeaderClock();
renderSnapshot(window.gatewayMonitorInitialSnapshot);
renderAsteriskSnapshot(window.asteriskInitialSnapshot);
connectGatewaySocket();
connectAsteriskSocket();
loadEvents();
