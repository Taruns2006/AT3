/**
 * ws.js — High-frequency WebSocket manager with auto-reconnect.
 */

import { WS_BASE, WS_RECONNECT } from './config.js';

let socket = null;
let reconnectTimer = null;
let currentDelay = WS_RECONNECT.baseDelayMs;
let isIntentionallyClosed = false;

export function createSocket(onMessage, onStatusChange) {
  if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
    return socket;
  }

  isIntentionallyClosed = false;
  const url = `${WS_BASE}/ws/telemetry`;

  try {
    socket = new WebSocket(url);
  } catch (err) {
    console.warn('[WS] Failed to create WebSocket:', err);
    if (onStatusChange) onStatusChange('offline');
    scheduleReconnect(onMessage, onStatusChange);
    return null;
  }

  socket.onopen = () => {
    console.log('[WS] Connected to live telemetry feed');
    currentDelay = WS_RECONNECT.baseDelayMs;
    if (onStatusChange) onStatusChange('live');
  };

  socket.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      if (onMessage) onMessage(msg);
    } catch (err) {
      console.warn('[WS] Failed to parse message:', err);
    }
  };

  socket.onclose = () => {
    if (!isIntentionallyClosed) {
      console.log('[WS] Disconnected. Reconnecting...');
      if (onStatusChange) onStatusChange('reconnecting');
      scheduleReconnect(onMessage, onStatusChange);
    } else {
      if (onStatusChange) onStatusChange('offline');
    }
  };

  socket.onerror = (err) => {
    console.warn('[WS] Socket error:', err);
    socket.close();
  };

  return socket;
}

export function sendCarSelection(raceId, carNumber) {
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ race_id: raceId, car_number: carNumber }));
  }
}

function scheduleReconnect(onMessage, onStatusChange) {
  if (reconnectTimer) clearTimeout(reconnectTimer);
  reconnectTimer = setTimeout(() => {
    console.log(`[WS] Attempting reconnect (delay: ${currentDelay}ms)...`);
    currentDelay = Math.min(currentDelay * WS_RECONNECT.factor, WS_RECONNECT.maxDelayMs);
    createSocket(onMessage, onStatusChange);
  }, currentDelay);
}

export function closeSocket() {
  isIntentionallyClosed = true;
  if (reconnectTimer) clearTimeout(reconnectTimer);
  if (socket) {
    socket.close();
    socket = null;
  }
}
