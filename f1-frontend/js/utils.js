/**
 * utils.js — Shared pure helper functions.
 * No DOM access, no side effects. Import anywhere.
 */

/**
 * Format milliseconds into "m:ss.SSS" (pit stop time display).
 * @param {number} ms
 * @returns {string}
 */
export function formatPitTime(ms) {
  if (ms == null || isNaN(ms)) return '—';
  const totalSec = ms / 1000;
  const m = Math.floor(totalSec / 60);
  const s = (totalSec % 60).toFixed(3).padStart(6, '0');
  return m > 0 ? `${m}:${s}` : `${s}s`;
}

/**
 * Format a number with fixed decimal places, falling back to '—'.
 * @param {number|null} val
 * @param {number} dp  decimal places
 * @returns {string}
 */
export function fmt(val, dp = 1) {
  if (val == null || isNaN(val)) return '—';
  return Number(val).toFixed(dp);
}

/**
 * Clamp a value between min and max.
 * @param {number} val
 * @param {number} min
 * @param {number} max
 * @returns {number}
 */
export function clamp(val, min, max) {
  return Math.min(max, Math.max(min, val));
}

/**
 * Linear interpolation between a and b by t ∈ [0, 1].
 */
export function lerp(a, b, t) {
  return a + (b - a) * clamp(t, 0, 1);
}

/**
 * Format an ISO-8601 timestamp to a short local time string "HH:MM:SS".
 * @param {string} isoStr
 * @returns {string}
 */
export function fmtTime(isoStr) {
  if (!isoStr) return '—';
  try {
    return new Date(isoStr).toLocaleTimeString('en-GB', { hour12: false });
  } catch {
    return '—';
  }
}

/**
 * Relative time from now: "2 s ago", "45 s ago", etc.
 * Used for stale-data warnings.
 * @param {Date|string} ts
 * @returns {string}
 */
export function relativeTime(ts) {
  const diff = Date.now() - new Date(ts).getTime();
  if (diff < 5000)    return 'just now';
  if (diff < 60000)   return `${Math.round(diff / 1000)} s ago`;
  if (diff < 3600000) return `${Math.round(diff / 60000)} min ago`;
  return 'a while ago';
}

/**
 * Debounce: only call fn after `wait` ms of no further calls.
 * @param {Function} fn
 * @param {number}   wait
 * @returns {Function}
 */
export function debounce(fn, wait) {
  let timer;
  return function (...args) {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), wait);
  };
}

/**
 * Throttle: call fn at most once per `limit` ms.
 * @param {Function} fn
 * @param {number}   limit
 * @returns {Function}
 */
export function throttle(fn, limit) {
  let lastCall = 0;
  return function (...args) {
    const now = Date.now();
    if (now - lastCall >= limit) {
      lastCall = now;
      return fn.apply(this, args);
    }
  };
}

/**
 * Pick a colour token based on a numeric value and two thresholds.
 * Returns one of: 'ok' | 'warn' | 'danger'
 * @param {number} val
 * @param {number} warnAt
 * @param {number} dangerAt
 * @param {boolean} inverse  if true, lower = worse (e.g. grip %)
 */
export function thresholdLevel(val, warnAt, dangerAt, inverse = false) {
  if (inverse) {
    if (val <= dangerAt) return 'danger';
    if (val <= warnAt)   return 'warn';
    return 'ok';
  }
  if (val >= dangerAt) return 'danger';
  if (val >= warnAt)   return 'warn';
  return 'ok';
}

/**
 * Map a prediction `level` string to its CSS modifier class.
 * @param {'green'|'amber'|'red'} level
 * @returns {string}
 */
export function predLevelClass(level) {
  return { green: '--green', amber: '--amber', red: '--red' }[level] ?? '--green';
}

/**
 * Map `confidence` string to human label.
 * @param {'low'|'medium'|'high'} c
 * @returns {string}
 */
export function confLabel(c) {
  return { low: 'Low Confidence', medium: 'Medium Confidence', high: 'High Confidence' }[c] ?? c;
}

/**
 * A capped circular buffer. Pushing to a full buffer drops the oldest item.
 * WHY: Prevents unbounded memory growth from the 10 Hz telemetry stream.
 *      After 10 minutes at 10 Hz, uncapped arrays would hold 6000 points.
 *      We cap at CHART_BUFFER_MAX (600) = 60 seconds of data.
 */
export class RingBuffer {
  /**
   * @param {number} capacity  Max number of items before oldest is dropped
   */
  constructor(capacity) {
    this._cap  = capacity;
    this._data = [];
  }

  push(item) {
    if (this._data.length >= this._cap) {
      this._data.shift(); // O(n) — acceptable for n ≤ 600
    }
    this._data.push(item);
  }

  /** Returns a shallow copy so callers can't mutate internal state */
  toArray() {
    return [...this._data];
  }

  get length() { return this._data.length; }

  clear() { this._data = []; }
}

/**
 * Generate a random number in [min, max].
 * Used only by mock.js.
 */
export function rand(min, max) {
  return min + Math.random() * (max - min);
}

/**
 * Smoothly step a value toward a target by `step` amount.
 * Used by mock.js to simulate realistic sensor drifts.
 */
export function step(current, target, stepSize) {
  const diff = target - current;
  if (Math.abs(diff) <= stepSize) return target;
  return current + Math.sign(diff) * stepSize;
}

/**
 * Toast helper — dispatch a custom DOM event that toast.js listens to.
 * This avoids circular imports between modules.
 * @param {'info'|'warn'|'error'|'success'} type
 * @param {string} title
 * @param {string} [message]
 */
export function showToast(type, title, message = '') {
  window.dispatchEvent(new CustomEvent('f1:toast', {
    detail: { type, title, message }
  }));
}
