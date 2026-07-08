function updateHeaderClock() {
  const clock = document.getElementById("header-clock");
  if (clock) {
    clock.textContent = new Date().toLocaleString("pt-BR");
  }
}

async function loadCapacity() {
  const days = document.getElementById("capacity-days").value;
  document.getElementById("capacity-pdf").href = `/api/capacity/pdf?days=${days}`;
  document.getElementById("capacity-excel").href = `/api/capacity/excel?days=${days}`;

  const response = await fetch(`/api/capacity/summary?days=${days}`);
  const data = await response.json();
  renderCapacity(data);
}

function renderCapacity(data) {
  const selectedDays = Number(document.getElementById("capacity-days").value);
  document.getElementById("recommendation-status").textContent = data.recommendation.status;
  document.getElementById("recommendation-message").textContent = data.recommendation.message;
  document.getElementById("capacity-recommendation").dataset.status = data.recommendation.status;

  document.getElementById("cap-total-calls").textContent = data.total_calls;
  document.getElementById("cap-direction").textContent = `${data.inbound_calls} recebidas | ${data.outbound_calls} realizadas`;
  document.getElementById("cap-busy-hour-calls").textContent = data.busy_hour_calls;
  document.getElementById("cap-busy-hour-label").textContent = data.busy_hour_label;
  document.getElementById("cap-erlangs").textContent = data.busy_hour_erlangs;
  document.getElementById("cap-peak").textContent = data.peak_concurrent_calls;
  document.getElementById("cap-answered").textContent = data.answered_calls;
  document.getElementById("cap-unanswered").textContent = `${data.unanswered_calls} não atendidas`;
  document.getElementById("cap-average-duration").textContent = data.average_duration;
  document.getElementById("cap-total-duration").textContent = `${data.total_duration} total`;
  document.getElementById("cap-occupancy").textContent = `${data.average_occupancy_percent}%`;
  document.getElementById("cap-all-lines-count").textContent = data.all_lines_busy_count;
  document.getElementById("cap-all-lines-duration").textContent = data.all_lines_busy_duration;

  renderRows("capacity-trunks", data.trunk_usage, (row) => [
    row.trunk,
    row.calls,
    row.duration,
  ]);
  renderRows("capacity-extensions", data.extension_usage, (row) => [
    row.extension,
    row.calls,
    row.duration,
  ]);
  renderRows("capacity-days-table", data.calls_by_day, (row) => [
    row.day,
    row.total,
    row.inbound,
    row.outbound,
    row.answered,
    row.unanswered,
  ]);
  renderErlang(data);

  const volumeRows = selectedDays <= 1
    ? data.calls_by_hour.map((row) => ({ label: row.hour, value: row.calls }))
    : data.calls_by_day.map((row) => ({ label: row.day.slice(0, 5), value: row.total }));
  document.getElementById("capacity-volume-title").textContent = selectedDays <= 1
    ? "Chamadas por hora"
    : "Chamadas por dia";
  document.getElementById("capacity-volume-subtitle").textContent = selectedDays <= 1
    ? "Total de chamadas em cada hora do período"
    : "Total de chamadas em cada dia do período";
  document.getElementById("capacity-concurrency-subtitle").textContent = selectedDays <= 2
    ? "Pico de chamadas ao mesmo tempo em cada hora"
    : "Pico de chamadas ao mesmo tempo em cada dia";

  drawBarChart("capacity-hour-chart", volumeRows);
  drawLineChart(
    "capacity-concurrency-chart",
    data.concurrency_points.map((row) => ({ label: row.label, value: row.active }))
  );
}

function renderRows(tableId, rows, mapper) {
  const table = document.getElementById(tableId);
  if (!rows.length) {
    table.innerHTML = '<tr><td colspan="6" class="text-secondary">Sem dados no período</td></tr>';
    return;
  }

  table.innerHTML = rows.map((row) => `
    <tr>${mapper(row).map((value) => `<td>${value ?? "--"}</td>`).join("")}</tr>
  `).join("");
}

function renderErlang(data) {
  const table = document.getElementById("capacity-erlang");
  const recommendationRows = Object.entries(data.erlang_recommended_lines)
    .map(([target, lines]) => `
      <tr>
        <td>Bloqueio máximo ${target}</td>
        <td><strong>${lines} linhas</strong></td>
      </tr>
    `)
    .join("");

  table.innerHTML = `
    <tr>
      <td>Bloqueio estimado com ${data.line_count} linhas</td>
      <td><strong>${data.erlang_blocking_percent}%</strong></td>
    </tr>
    ${recommendationRows}
  `;
}

function drawBarChart(canvasId, rows) {
  const canvas = document.getElementById(canvasId);
  const { ctx, width, height } = prepareCanvas(canvas);
  const padding = { top: 28, right: 16, bottom: 34, left: 42 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;
  ctx.clearRect(0, 0, width, height);

  if (!rows.length) {
    drawChartGrid(ctx, padding, chartWidth, chartHeight, 1);
    drawEmpty(ctx, width, height);
    return;
  }

  const maxValue = Math.max(...rows.map((row) => row.value), 1);
  drawChartGrid(ctx, padding, chartWidth, chartHeight, maxValue);
  const barWidth = chartWidth / rows.length;
  rows.forEach((row, index) => {
    const value = row.value;
    const barHeight = (value / maxValue) * chartHeight;
    const x = padding.left + index * barWidth + 2;
    const y = padding.top + chartHeight - barHeight;
    const width = Math.max(barWidth - 4, 2);
    ctx.fillStyle = "#0d6efd";
    ctx.fillRect(x, y, width, barHeight);

    if (barWidth >= 18 || value === maxValue) {
      ctx.fillStyle = "#111827";
      ctx.font = "12px system-ui, sans-serif";
      ctx.textAlign = "center";
      ctx.fillText(String(value), x + width / 2, Math.max(y - 6, 12));
    }
  });

  drawXAxisLabels(ctx, rows, padding, chartWidth, height, "bar");
}

function drawLineChart(canvasId, rows) {
  const canvas = document.getElementById(canvasId);
  const { ctx, width, height } = prepareCanvas(canvas);
  const padding = { top: 28, right: 18, bottom: 34, left: 42 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;
  ctx.clearRect(0, 0, width, height);

  if (!rows.length) {
    drawChartGrid(ctx, padding, chartWidth, chartHeight, 1);
    drawEmpty(ctx, width, height);
    return;
  }

  const maxValue = Math.max(...rows.map((row) => row.value), 1);
  drawChartGrid(ctx, padding, chartWidth, chartHeight, maxValue);
  if (rows.length === 1) {
    drawPoint(ctx, padding.left + chartWidth / 2, padding.top + chartHeight - (rows[0].value / maxValue) * chartHeight);
  } else {
    ctx.beginPath();
    rows.forEach((row, index) => {
      const x = padding.left + (index / (rows.length - 1)) * chartWidth;
      const y = padding.top + chartHeight - (row.value / maxValue) * chartHeight;
      if (index === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.lineWidth = 3;
    ctx.strokeStyle = "#dc3545";
    ctx.stroke();
  }

  rows.forEach((row, index) => {
    const x = rows.length === 1
      ? padding.left + chartWidth / 2
      : padding.left + (index / (rows.length - 1)) * chartWidth;
    const y = padding.top + chartHeight - (row.value / maxValue) * chartHeight;
    if (row.value > 0) {
      drawPoint(ctx, x, y);
      if (rows.length <= 31 || row.value === maxValue) {
        ctx.fillStyle = "#111827";
        ctx.font = "12px system-ui, sans-serif";
        ctx.textAlign = "center";
        ctx.fillText(String(row.value), x, Math.max(y - 8, 12));
      }
    }
  });
  drawXAxisLabels(ctx, rows, padding, chartWidth, height, "line");
}

function prepareCanvas(canvas) {
  const parentWidth = Math.max(canvas.parentElement.clientWidth - 8, 320);
  const cssHeight = 260;
  const ratio = window.devicePixelRatio || 1;
  canvas.style.width = "100%";
  canvas.style.height = `${cssHeight}px`;
  canvas.width = Math.floor(parentWidth * ratio);
  canvas.height = Math.floor(cssHeight * ratio);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  return { ctx, width: parentWidth, height: cssHeight };
}

function drawPoint(ctx, x, y) {
  ctx.beginPath();
  ctx.arc(x, y, 3, 0, Math.PI * 2);
  ctx.fillStyle = "#dc3545";
  ctx.fill();
}

function drawChartGrid(ctx, padding, chartWidth, chartHeight, maxValue) {
  ctx.strokeStyle = "#e9eef5";
  ctx.lineWidth = 1;
  ctx.fillStyle = "#6c757d";
  ctx.font = "11px system-ui, sans-serif";
  ctx.textAlign = "right";
  for (let index = 0; index <= 4; index += 1) {
    const y = padding.top + (chartHeight / 4) * index;
    ctx.beginPath();
    ctx.moveTo(padding.left, y);
    ctx.lineTo(padding.left + chartWidth, y);
    ctx.stroke();
    const value = Math.round(maxValue - (maxValue / 4) * index);
    ctx.fillText(String(value), padding.left - 8, y + 4);
  }
}

function drawXAxisLabels(ctx, rows, padding, chartWidth, height, chartType) {
  const labelStep = Math.max(Math.ceil(rows.length / 8), 1);
  const barWidth = chartWidth / Math.max(rows.length, 1);
  ctx.fillStyle = "#6c757d";
  ctx.font = "11px system-ui, sans-serif";
  ctx.textAlign = "center";
  rows.forEach((row, index) => {
    if (index % labelStep !== 0 && index !== rows.length - 1) return;
    const x = chartType === "bar"
      ? padding.left + index * barWidth + barWidth / 2
      : rows.length === 1
        ? padding.left + chartWidth / 2
        : padding.left + (index / (rows.length - 1)) * chartWidth;
    ctx.fillText(row.label, x, height - 10);
  });
  ctx.textAlign = "start";
}

function drawEmpty(ctx, width, height) {
  ctx.fillStyle = "#6c757d";
  ctx.font = "14px system-ui, sans-serif";
  ctx.textAlign = "center";
  ctx.fillText("Sem dados no período", width / 2, height / 2);
  ctx.textAlign = "start";
}

document.getElementById("capacity-days").addEventListener("change", loadCapacity);
updateHeaderClock();
window.setInterval(updateHeaderClock, 1000);
loadCapacity();
