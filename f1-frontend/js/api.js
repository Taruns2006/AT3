/**
 * api.js — REST API client connecting to FastAPI backend
 */

import { API_BASE } from './config.js';

async function fetchJSON(path) {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`HTTP ${res.status} from ${url}`);
  }
  return res.json();
}

export async function fetchHealth() {
  try {
    return await fetchJSON('/api/health');
  } catch (err) {
    console.warn('[API] Health check failed:', err);
    return { status: 'offline', cassandra: 'down', model_loaded: false };
  }
}

export async function fetchRaces() {
  try {
    return await fetchJSON('/api/races');
  } catch (err) {
    console.warn('[API] fetchRaces failed:', err);
    return [{ race_id: 'R001', name: 'Formula 1 Grand Prix 2026', circuit: 'Silverstone Circuit', laps_total: 5, status: 'live' }];
  }
}

export async function fetchCars(raceId = 'R001') {
  try {
    return await fetchJSON(`/api/races/${raceId}/cars`);
  } catch (err) {
    console.warn('[API] fetchCars failed:', err);
    return [
      { race_id: raceId, car_number: 1, driver: 'Max Verstappen', team: 'Red Bull Racing' },
      { race_id: raceId, car_number: 44, driver: 'Lewis Hamilton', team: 'Mercedes-AMG' },
      { race_id: raceId, car_number: 16, driver: 'Charles Leclerc', team: 'Ferrari' },
    ];
  }
}

export async function fetchLatest(raceId = 'R001', carNumber = 1) {
  try {
    return await fetchJSON(`/api/races/${raceId}/cars/${carNumber}/latest`);
  } catch (err) {
    console.warn('[API] fetchLatest failed:', err);
    return null;
  }
}

export async function fetchHistory(raceId = 'R001', carNumber = 1, seconds = 60) {
  try {
    return await fetchJSON(`/api/races/${raceId}/cars/${carNumber}/history?seconds=${seconds}`);
  } catch (err) {
    console.warn('[API] fetchHistory failed:', err);
    return [];
  }
}

export async function fetchPrediction(raceId = 'R001', carNumber = 1) {
  try {
    return await fetchJSON(`/api/races/${raceId}/cars/${carNumber}/prediction`);
  } catch (err) {
    console.warn('[API] fetchPrediction failed:', err);
    return null;
  }
}

export async function fetchLeaderboard(raceId = 'R001') {
  try {
    return await fetchJSON(`/api/races/${raceId}/leaderboard`);
  } catch (err) {
    console.warn('[API] fetchLeaderboard failed:', err);
    return [];
  }
}

export async function fetchQuality(raceId = 'R001') {
  try {
    return await fetchJSON(`/api/races/${raceId}/quality`);
  } catch (err) {
    console.warn('[API] fetchQuality failed:', err);
    return null;
  }
}
