/**
 * dashboard.js — Main dashboard controller.
 *
 * Connects REST APIs, WebSocket streaming feed, Chart.js components,
 * KPI indicators, ML predictions, and race leaderboard.
 */

import {
  fetchCars,
  fetchHealth,
  fetchHistory,
  fetchLatest,
  fetchLeaderboard,
  fetchPrediction,
  fetchQuality,
  fetchRaces,
} from './api.js';
import { initCharts, pushTelemetry } from './charts.js';
import {
  BRAKE_DANGER_C,
  BRAKE_WARN_C,
  STALE_THRESHOLD_MS,
  TIRE_DANGER_PCT,
  TIRE_WARN_PCT,
} from './config.js';
import { appState } from './state.js';
import {
  confLabel,
  fmt,
  fmtTime,
  formatPitTime,
  predLevelClass,
  showToast,
} from './utils.js';
import { createSocket, sendCarSelection } from './ws.js';

let lastTelemetryTime = Date.now();
const recentPredictions = [];

// ── DOM ELEMENTS ────────────────────────────────────────────────────────────
const elRaceSelect = document.getElementById('race-select');
const elCarSelect = document.getElementById('car-select');
const elStatusBadge = document.getElementById('status-badge');
const elStatusText = document.getElementById('status-text');
const elStaleWarning = document.getElementById('stale-warning');
const elKpiStrip = document.getElementById('kpi-strip');

// Prediction elements
const elPredBadge = document.getElementById('pred-conf-badge');
const elPredVerdict = document.getElementById('pred-verdict');
const elPredLaps = document.getElementById('pred-laps');
const elProbGaugeFill = document.getElementById('prob-gauge-fill');
const elProbPct = document.getElementById('prob-pct');
const elPitProgress = document.getElementById('pit-progress');
const elPredHistory = document.getElementById('pred-history');

// Leaderboard & Quality
const elLbBody = document.getElementById('lb-body');
const elQRowsIn = document.getElementById('q-rows-in');
const elQRowsOut = document.getElementById('q-rows-out');
const elQQuarantined = document.getElementById('q-quarantined');
const elQReason = document.getElementById('quality-reason');

// ── STATUS BADGE ────────────────────────────────────────────────────────────
function updateStatusBadge(status) {
  appState.connectionStatus = status;
  if (!elStatusBadge || !elStatusText) return;

  elStatusBadge.className = `status-badge status-badge--${status}`;
  elStatusText.textContent = status.charAt(0).toUpperCase() + status.slice(1);
}

// ── KPI STRIP RENDERING ─────────────────────────────────────────────────────
function renderKPIs(t) {
  if (!t || !elKpiStrip) return;

  const tireWear = Number(t.tire_wear_pct ?? 0);
  const brakeTemp = Number(t.brake_temp_c ?? 0);

  let tireColor = 'var(--clr-text-primary)';
  if (tireWear >= TIRE_DANGER_PCT) tireColor = 'var(--clr-red)';
  else if (tireWear >= TIRE_WARN_PCT) tireColor = 'var(--clr-amber)';

  let brakeColor = 'var(--clr-text-primary)';
  if (brakeTemp >= BRAKE_DANGER_C) brakeColor = 'var(--clr-red)';
  else if (brakeTemp >= BRAKE_WARN_C) brakeColor = 'var(--clr-amber)';

  elKpiStrip.innerHTML = `
    <div class="kpi-card">
      <div class="kpi-card__label">Speed</div>
      <div class="kpi-card__value">${fmt(t.speed_kmh, 1)} <span class="kpi-card__unit">km/h</span></div>
    </div>
    <div class="kpi-card">
      <div class="kpi-card__label">RPM</div>
      <div class="kpi-card__value">${t.rpm ?? '—'} <span class="kpi-card__unit">rpm</span></div>
    </div>
    <div class="kpi-card">
      <div class="kpi-card__label">Throttle</div>
      <div class="kpi-card__value">${fmt(t.throttle_pct, 0)} <span class="kpi-card__unit">%</span></div>
    </div>
    <div class="kpi-card">
      <div class="kpi-card__label">Tyre Wear</div>
      <div class="kpi-card__value" style="color:${tireColor}">${fmt(tireWear, 1)} <span class="kpi-card__unit">%</span></div>
    </div>
    <div class="kpi-card">
      <div class="kpi-card__label">Tyre Temp</div>
      <div class="kpi-card__value">${fmt(t.tire_temp_c, 1)} <span class="kpi-card__unit">°C</span></div>
    </div>
    <div class="kpi-card">
      <div class="kpi-card__label">Brake Temp</div>
      <div class="kpi-card__value" style="color:${brakeColor}">${fmt(brakeTemp, 0)} <span class="kpi-card__unit">°C</span></div>
    </div>
    <div class="kpi-card">
      <div class="kpi-card__label">G-Lat</div>
      <div class="kpi-card__value">${fmt(t.g_force_lat, 2)} <span class="kpi-card__unit">g</span></div>
    </div>
    <div class="kpi-card">
      <div class="kpi-card__label">Lap</div>
      <div class="kpi-card__value">${t.lap_number ?? 1}</div>
    </div>
  `;
}

// ── PREDICTION PANEL ────────────────────────────────────────────────────────
function renderPrediction(p) {
  if (!p) return;

  const prob = Number(p.probability ?? 0);
  const pct = Math.round(prob * 100);
  const level = p.level ?? (prob >= 0.7 ? 'red' : prob >= 0.4 ? 'amber' : 'green');
  const levelClass = predLevelClass(level);

  if (elPredBadge) {
    elPredBadge.className = `badge badge${levelClass}`;
    elPredBadge.textContent = confLabel(p.confidence ?? 'high');
  }

  if (elPredVerdict) {
    if (p.pit_needed_within_3_laps) {
      elPredVerdict.innerHTML = `<span style="color:var(--clr-red);font-weight:700;">BOX THIS LAP / NEXT</span>`;
    } else {
      elPredVerdict.innerHTML = `<span style="color:var(--clr-green);font-weight:700;">STAY OUT — TYRES NOMINAL</span>`;
    }
  }

  if (elPredLaps) {
    elPredLaps.textContent = `Estimated pit window: ~${p.estimated_laps_to_pit ?? 5} laps remaining`;
  }

  if (elProbGaugeFill) {
    elProbGaugeFill.style.width = `${pct}%`;
    elProbGaugeFill.style.backgroundColor = level === 'red' ? 'var(--clr-red)' : level === 'amber' ? 'var(--clr-amber)' : 'var(--clr-green)';
  }

  if (elProbPct) {
    elProbPct.textContent = `${pct}%`;
  }

  if (elPitProgress) {
    const est = Number(p.estimated_laps_to_pit ?? 10);
    const progress = Math.min(100, Math.max(0, Math.round(((15 - est) / 15) * 100)));
    elPitProgress.style.width = `${progress}%`;
  }

  // Update recent prediction history
  recentPredictions.unshift({
    time: fmtTime(p.generated_at),
    prob: pct,
    level,
    verdict: p.pit_needed_within_3_laps ? 'PIT' : 'STAY',
  });
  if (recentPredictions.length > 5) recentPredictions.pop();

  if (elPredHistory) {
    elPredHistory.innerHTML = recentPredictions.map(item => `
      <div class="pred-history__item">
        <span class="pred-history__dot" style="background:var(--clr-${item.level})"></span>
        <span>${item.time} — ${item.verdict} (${item.prob}%)</span>
      </div>
    `).join('');
  }
}

// ── LEADERBOARD ─────────────────────────────────────────────────────────────
function renderLeaderboard(rows) {
  if (!elLbBody || !Array.isArray(rows) || rows.length === 0) return;

  elLbBody.innerHTML = rows.map((r, i) => `
    <tr>
      <td><strong>${r.position ?? i + 1}</strong></td>
      <td>#${r.car_number}</td>
      <td>
        <div style="font-weight:600;">${r.driver}</div>
        <div style="font-size:0.75rem;color:var(--clr-text-muted);">${r.team}</div>
      </td>
      <td>${r.laps}</td>
      <td>${r.pit_stops}</td>
      <td>${formatPitTime(r.total_pit_ms)}</td>
    </tr>
  `).join('');
}

// ── DATA QUALITY ────────────────────────────────────────────────────────────
function renderQuality(q) {
  if (!q) return;

  if (elQRowsIn) elQRowsIn.textContent = Number(q.rows_in).toLocaleString();
  if (elQRowsOut) elQRowsOut.textContent = Number(q.rows_out).toLocaleString();
  if (elQQuarantined) elQQuarantined.textContent = Number(q.quarantined).toLocaleString();

  if (elQReason && q.pct_by_reason) {
    const reasons = typeof q.pct_by_reason === 'string' ? JSON.parse(q.pct_by_reason) : q.pct_by_reason;
    elQReason.innerHTML = Object.entries(reasons).map(([reason, pct]) => `
      <div class="quality-reason__row" style="margin-bottom:var(--sp-2);">
        <span class="quality-reason__name" style="font-size:0.8rem;text-transform:capitalize;">${reason.replace(/_/g, ' ')}</span>
        <div class="quality-reason__bar-wrap">
          <div class="quality-reason__bar-fill" style="width:${Math.max(4, Math.min(100, pct))}%;background:var(--clr-amber);"></div>
        </div>
        <span class="quality-reason__pct">${pct}%</span>
      </div>
    `).join('');
  }
}

// ── SELECTION EVENT HANDLERS ────────────────────────────────────────────────
async function onRaceChanged() {
  const raceId = elRaceSelect.value;
  appState.selectedRace = raceId;

  const cars = await fetchCars(raceId);
  appState.cars = cars;

  elCarSelect.innerHTML = cars.map(c => `
    <option value="${c.car_number}">#${c.car_number} — ${c.driver} (${c.team})</option>
  `).join('');

  if (cars.length > 0) {
    elCarSelect.value = cars[0].car_number;
    onCarChanged();
  }

  // Fetch initial leaderboard and quality
  const lb = await fetchLeaderboard(raceId);
  renderLeaderboard(lb);

  const q = await fetchQuality(raceId);
  renderQuality(q);
}

async function onCarChanged() {
  const raceId = elRaceSelect.value;
  const carNumber = Number(elCarSelect.value);
  appState.selectedCar = carNumber;

  // Inform WebSocket of new car selection
  sendCarSelection(raceId, carNumber);

  // Preload history
  const history = await fetchHistory(raceId, carNumber, 60);
  if (history && history.length > 0) {
    history.forEach(reading => pushTelemetry(reading));
    const latest = history[history.length - 1];
    renderKPIs(latest);
    lastTelemetryTime = Date.now();
  }

  // Preload prediction
  const pred = await fetchPrediction(raceId, carNumber);
  renderPrediction(pred);
}

// ── INITIALIZATION ──────────────────────────────────────────────────────────
async function initDashboard() {
  console.log('[F1T] Initializing Live Telemetry Dashboard...');

  // Initialize Chart.js
  initCharts();

  // Populate Races
  try {
    const races = await fetchRaces();
    appState.races = races;
    elRaceSelect.innerHTML = races.map(r => `
      <option value="${r.race_id}">${r.name} (${r.circuit})</option>
    `).join('');

    if (races.length > 0) {
      elRaceSelect.value = races[0].race_id;
      await onRaceChanged();
    }
  } catch (err) {
    console.error('Failed to load races:', err);
  }

  elRaceSelect.addEventListener('change', onRaceChanged);
  elCarSelect.addEventListener('change', onCarChanged);

  // Connect WebSocket
  createSocket(
    (msg) => {
      if (!msg || !msg.type) return;

      if (msg.type === 'telemetry') {
        const tel = msg.data;
        if (Number(tel.car_number) === Number(appState.selectedCar)) {
          lastTelemetryTime = Date.now();
          renderKPIs(tel);
          pushTelemetry(tel);
        }
      } else if (msg.type === 'prediction') {
        const pred = msg.data;
        if (Number(pred.car_number) === Number(appState.selectedCar)) {
          renderPrediction(pred);
        }
      } else if (msg.type === 'leaderboard') {
        renderLeaderboard(msg.data);
      } else if (msg.type === 'quality') {
        renderQuality(msg.data);
      }
    },
    (status) => {
      updateStatusBadge(status);
    }
  );

  // Stale data watchdog (every 1 second)
  setInterval(() => {
    const isStale = (Date.now() - lastTelemetryTime) > STALE_THRESHOLD_MS;
    if (elStaleWarning) {
      elStaleWarning.style.display = isStale ? 'block' : 'none';
    }
  }, 1000);

  // Periodic REST poll fallback (every 3 seconds) in case WebSocket is offline
  setInterval(async () => {
    if (appState.connectionStatus !== 'live' && appState.selectedRace && appState.selectedCar) {
      const latest = await fetchLatest(appState.selectedRace, appState.selectedCar);
      if (latest) {
        lastTelemetryTime = Date.now();
        renderKPIs(latest);
        pushTelemetry(latest);
      }
      const pred = await fetchPrediction(appState.selectedRace, appState.selectedCar);
      if (pred) renderPrediction(pred);

      const lb = await fetchLeaderboard(appState.selectedRace);
      if (lb) renderLeaderboard(lb);
    }
  }, 3000);
}

document.addEventListener('DOMContentLoaded', initDashboard);
