/**
 * Chart.js helper builders for Trading Journal dashboard.
 * Each function creates (or recreates) a chart on the given canvas ID.
 */

function buildLineChart(canvasId, existing, labels, values, label, color) {
  if (existing) existing.destroy();
  const ctx = document.getElementById(canvasId);
  if (!ctx) return null;
  return new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label,
        data: values,
        borderColor: color,
        backgroundColor: color + '22',
        tension: 0.3,
        pointRadius: values.length > 50 ? 0 : 3,
        fill: true,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { maxTicksLimit: 8, maxRotation: 0 } },
        y: { ticks: { callback: v => '$' + v.toLocaleString() } },
      },
    },
  });
}

function buildDoughnutChart(canvasId, existing, labels, values, colors) {
  if (existing) existing.destroy();
  const ctx = document.getElementById(canvasId);
  if (!ctx) return null;
  return new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{ data: values, backgroundColor: colors, borderWidth: 2 }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: 'bottom' },
        tooltip: {
          callbacks: {
            label: ctx => ` ${ctx.label}: ${ctx.parsed}`,
          },
        },
      },
    },
  });
}

function buildBarChart(canvasId, existing, labels, values, label, colors, horizontal) {
  if (existing) existing.destroy();
  const ctx = document.getElementById(canvasId);
  if (!ctx) return null;
  return new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label,
        data: values,
        backgroundColor: colors,
        borderWidth: 0,
      }],
    },
    options: {
      indexAxis: horizontal ? 'y' : 'x',
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { callback: v => typeof v === 'number' ? '$' + v.toLocaleString() : v } },
        y: {},
      },
    },
  });
}
