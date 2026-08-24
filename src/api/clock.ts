import { useEffect, useSyncExternalStore } from "react";

interface GameClockState {
  active: boolean;
  value: number;
  base: number;
  startedAt: number;
}

type ClockListener = () => void;

let state: GameClockState = { active: false, value: 0, base: 0, startedAt: Date.now() };
const listeners = new Set<ClockListener>();
let ticker: ReturnType<typeof setInterval> | null = null;

function notify() {
  for (const listener of listeners) listener();
}

function tick() {
  if (!state.active) return;
  const value = state.base + Math.floor((Date.now() - state.startedAt) / 1_000);
  if (value === state.value) return;
  state = { ...state, value };
  notify();
}

function startTicker() {
  if (ticker !== null || !state.active || listeners.size === 0) return;
  ticker = setInterval(tick, 500);
}

function stopTicker() {
  if (ticker === null) return;
  clearInterval(ticker);
  ticker = null;
}

function setServerClock(active: boolean, serverClock: number) {
  const base = Math.max(0, Math.floor(serverClock));
  state = { active, value: base, base, startedAt: Date.now() };
  if (active) startTicker();
  else stopTicker();
  notify();
}

function subscribeClock(listener: ClockListener) {
  listeners.add(listener);
  startTicker();
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0) {
      stopTicker();
      state = { active: false, value: 0, base: 0, startedAt: Date.now() };
    }
  };
}

function getClock() {
  return state.value;
}

/** Keeps the shared clock aligned with the latest server snapshot. */
export function useGameClockSource(active: boolean, serverClock: number) {
  useEffect(() => {
    setServerClock(active, serverClock);
  }, [active, serverClock]);
}

/** Subscribes only the clock consumer to the 500ms ticker. */
export function useGameClock() {
  return useSyncExternalStore(subscribeClock, getClock, getClock);
}
