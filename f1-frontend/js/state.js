/**
 * state.js — Centralised application state (Phase 3 stub)
 * Full implementation arrives in Phase 3.
 */

export const appState = {
  selectedRace: null,
  selectedCar:  null,
  races:        [],
  cars:         [],
  latestTelemetry: null,
  latestPrediction: null,
  leaderboard:  [],
  quality:      null,
  connectionStatus: 'mock', // 'live' | 'reconnecting' | 'offline' | 'mock'
};
