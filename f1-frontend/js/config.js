/**
 * config.js — Single source of truth for environment config.
 *
 * To switch from mock to live backend:
 *   Set USE_MOCK = false  (and ensure the FastAPI server is running on API_BASE)
 *
 * WHY a config module?
 *   All js modules import from here, so "go live" = 1 boolean change, no grep needed.
 */

/** Base URL of the FastAPI REST API */
export const API_BASE = 'http://localhost:8000';

/** Base URL for WebSocket connections */
export const WS_BASE = 'ws://localhost:8000';

/**
 * Master mock toggle.
 * true  → all data comes from mock.js (no network calls)
 * false → all data comes from the real backend
 */
export const USE_MOCK = false;

/** How many seconds of history to fetch for rolling charts */
export const HISTORY_SECONDS = 60;

/** Max data points kept in the rolling chart buffer (60 s × 10 Hz = 600) */
export const CHART_BUFFER_MAX = 600;

/** Stale-data warning threshold in milliseconds */
export const STALE_THRESHOLD_MS = 3000;

/** Tire wear % above which we colour the KPI amber */
export const TIRE_WARN_PCT   = 60;
/** Tire wear % above which we colour the KPI red */
export const TIRE_DANGER_PCT = 80;

/** Brake temp °C above which we colour amber */
export const BRAKE_WARN_C   = 500;
/** Brake temp °C above which we colour red */
export const BRAKE_DANGER_C = 700;

/** WebSocket reconnect config */
export const WS_RECONNECT = {
  baseDelayMs: 1000,
  maxDelayMs:  30000,
  factor:      2,        // exponential back-off multiplier
};
