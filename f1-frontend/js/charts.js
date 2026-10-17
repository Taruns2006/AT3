/**
 * charts.js — Real-time Chart.js integration for rolling telemetry and G-G scatter.
 */

import { CHART_BUFFER_MAX } from './config.js';
import { RingBuffer } from './utils.js';

let chartSpeed = null;
let chartRpm = null;
let chartBrake = null;
let chartTyre = null;
let chartGForce = null;

const timestamps = new RingBuffer(CHART_BUFFER_MAX);
const speeds = new RingBuffer(CHART_BUFFER_MAX);
const rpms = new RingBuffer(CHART_BUFFER_MAX);
const brakes = new RingBuffer(CHART_BUFFER_MAX);
const tyres = new RingBuffer(CHART_BUFFER_MAX);
const gPoints = new RingBuffer(150);

const chartDefaults = {
  responsive: true,
  maintainAspectRatio: false,
  animation: false,
  scales: {
    x: {
      display: false,
      grid: { display: false },
    },
    y: {
      grid: { color: 'rgba(255, 255, 255, 0.05)' },
      ticks: { color: '#888', font: { size: 10 } },
    },
  },
  plugins: {
    legend: { display: false },
    tooltip: { enabled: false },
  },
};

export function initCharts() {
  if (typeof Chart === 'undefined') {
    console.warn('[Charts] Chart.js library not found.');
    return;
  }

  // 1. Speed Chart
  const elSpeed = document.getElementById('chart-speed');
  if (elSpeed) {
    chartSpeed = new Chart(elSpeed, {
      type: 'line',
      data: {
        labels: [],
        datasets: [{
          data: [],
          borderColor: '#ff1801',
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.2,
          fill: true,
          backgroundColor: 'rgba(255, 24, 1, 0.08)',
        }],
      },
      options: {
        ...chartDefaults,
        scales: {
          ...chartDefaults.scales,
          y: { ...chartDefaults.scales.y, min: 0, max: 360 },
        },
      },
    });
  }

  // 2. RPM Chart
  const elRpm = document.getElementById('chart-rpm');
  if (elRpm) {
    chartRpm = new Chart(elRpm, {
      type: 'line',
      data: {
        labels: [],
        datasets: [{
          data: [],
          borderColor: '#3b82f6',
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.2,
          fill: true,
          backgroundColor: 'rgba(59, 130, 246, 0.08)',
        }],
      },
      options: {
        ...chartDefaults,
        scales: {
          ...chartDefaults.scales,
          y: { ...chartDefaults.scales.y, min: 0, max: 15000 },
        },
      },
    });
  }

  // 3. Brake Temp Chart
  const elBrake = document.getElementById('chart-brake');
  if (elBrake) {
    chartBrake = new Chart(elBrake, {
      type: 'line',
      data: {
        labels: [],
        datasets: [{
          data: [],
          borderColor: '#f59e0b',
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.2,
          fill: true,
          backgroundColor: 'rgba(245, 158, 11, 0.08)',
        }],
      },
      options: {
        ...chartDefaults,
        scales: {
          ...chartDefaults.scales,
          y: { ...chartDefaults.scales.y, min: 100, max: 1100 },
        },
      },
    });
  }

  // 4. Tyre Wear Chart
  const elTyre = document.getElementById('chart-tyre');
  if (elTyre) {
    chartTyre = new Chart(elTyre, {
      type: 'line',
      data: {
        labels: [],
        datasets: [{
          data: [],
          borderColor: '#10b981',
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.2,
          fill: true,
          backgroundColor: 'rgba(16, 185, 129, 0.08)',
        }],
      },
      options: {
        ...chartDefaults,
        scales: {
          ...chartDefaults.scales,
          y: { ...chartDefaults.scales.y, min: 0, max: 100 },
        },
      },
    });
  }

  // 5. G-Force Scatter
  const elGForce = document.getElementById('chart-gforce');
  if (elGForce) {
    chartGForce = new Chart(elGForce, {
      type: 'scatter',
      data: {
        datasets: [{
          data: [],
          backgroundColor: 'rgba(255, 24, 1, 0.65)',
          pointRadius: 3,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        scales: {
          x: {
            min: -5.5,
            max: 5.5,
            grid: { color: 'rgba(255, 255, 255, 0.08)' },
            title: { display: true, text: 'Lateral G', color: '#888' },
            ticks: { color: '#888' },
          },
          y: {
            min: -5.5,
            max: 5.5,
            grid: { color: 'rgba(255, 255, 255, 0.08)' },
            title: { display: true, text: 'Longitudinal G', color: '#888' },
            ticks: { color: '#888' },
          },
        },
        plugins: {
          legend: { display: false },
        },
      },
    });
  }
}

export function pushTelemetry(reading) {
  if (!reading) return;

  const t = reading.sensor_timestamp || new Date().toISOString();
  timestamps.push(t);
  speeds.push(reading.speed_kmh ?? 0);
  rpms.push(reading.rpm ?? 0);
  brakes.push(reading.brake_temp_c ?? 0);
  tyres.push(reading.tire_wear_pct ?? 0);

  const labels = timestamps.toArray();

  if (chartSpeed) {
    chartSpeed.data.labels = labels;
    chartSpeed.data.datasets[0].data = speeds.toArray();
    chartSpeed.update('none');
  }

  if (chartRpm) {
    chartRpm.data.labels = labels;
    chartRpm.data.datasets[0].data = rpms.toArray();
    chartRpm.update('none');
  }

  if (chartBrake) {
    chartBrake.data.labels = labels;
    chartBrake.data.datasets[0].data = brakes.toArray();
    chartBrake.update('none');
  }

  if (chartTyre) {
    chartTyre.data.labels = labels;
    chartTyre.data.datasets[0].data = tyres.toArray();
    chartTyre.update('none');
  }

  if (reading.g_force_lat != null && reading.g_force_long != null) {
    pushGForce(reading.g_force_lat, reading.g_force_long);
  }
}

export function pushGForce(lat, long) {
  if (!chartGForce) return;
  gPoints.push({ x: Number(lat), y: Number(long) });
  chartGForce.data.datasets[0].data = gPoints.toArray();
  chartGForce.update('none');
}
