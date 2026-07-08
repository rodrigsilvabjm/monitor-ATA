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
  drawBarChart("capacity-hour-chart", data.calls_by_hour, "hour", "calls");
  drawLineChart("capacity-concurrency-chart", data.concurrency_points, "time", "active");
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

function drawBarChart(canvasId, rows, labelKey, valueKey) {
  const canvas = document.getElementById(canvasId);
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  const padding = 32;
  const chartWidth = width - padding * 2;
  const chartHeight = height - padding * 2;
  ctx.clearRect(0, 0, width, height);
  drawChartGrid(ctx, padding, chartWidth, chartHeight);

  if (!rows.length) {
    drawEmpty(ctx, width, height);
    return;
  }

  const maxValue = Math.max(...rows.map((row) => row[valueKey]), 1);
  const barWidth = chartWidth / rows.length;
  rows.forEach((row, index) => {
    const value = row[valueKey];
    const barHeight = (value / maxValue) * chartHeight;
    ctx.fillStyle = "#0d6efd";
    ctx.fillRect(
      padding + index * barWidth + 2,
      padding + chartHeight - barHeight,
      Math.max(barWidth - 4, 2),
      barHeight
    );
  });

  ctx.fillStyle = "#6c757d";
  ctx.font = "11px system-ui, sans-serif";
  rows.filter((_, index) => index % Math.ceil(rows.length / 8 || 1) === 0).forEach((row, index) => {
    ctx.fillText(row[labelKey], padding + index * (chartWidth / 8), height - 8);
  });
}

function drawLineChart(canvasId, rows, labelKey, valueKey) {
  const canvas = document.getElementById(canvasId);
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  const padding = 32;
  const chartWidth = width - padding * 2;
  const chartHeight = height - padding * 2;
  ctx.clearRect(0, 0, width, height);
  drawChartGrid(ctx, padding, chartWidth, chartHeight);

  if (rows.length < 2) {
    drawEmpty(ctx, width, height);
    return;
  }

  const maxValue = Math.max(...rows.map((row) => row[valueKey]), 1);
  ctx.beginPath();
  rows.forEach((row, index) => {
    const x = padding + (index / (rows.length - 1)) * chartWidth;
    const y = padding + chartHeight - (row[valueKey] / maxValue) * chartHeight;
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.lineWidth = 3;
  ctx.strokeStyle = "#dc3545";
  ctx.stroke();
}

function drawChartGrid(ctx, padding, chartWidth, chartHeight) {
  ctx.strokeStyle = "#e9eef5";
  ctx.lineWidth = 1;
  for (let index = 0; index <= 4; index += 1) {
    const y = padding + (chartHeight / 4) * index;
    ctx.beginPath();
    ctx.moveTo(padding, y);
    ctx.lineTo(padding + chartWidth, y);
    ctx.stroke();
  }
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
