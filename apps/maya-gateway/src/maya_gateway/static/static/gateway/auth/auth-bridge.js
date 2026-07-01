/** Bridge Alpine auth islands into React hyprstart mount slots. */

import { bindAuthGreeting } from "./auth-greeting.js";
import { mountAuthGate } from "./auth-gate.js";
import { mountAuthLock } from "./auth-lock.js";
import { mountAuthWaybarChip } from "./auth-waybar-chip.js";

export function dispatchAuthEvent(action) {
  window.dispatchEvent(new CustomEvent("maya:auth", { detail: { action } }));
}

function waitForAlpine() {
  return new Promise((resolve) => {
    if (typeof Alpine !== "undefined" && Alpine.store("authSession")) {
      resolve();
      return;
    }
    document.addEventListener(
      "alpine:init",
      () => resolve(),
      { once: true },
    );
    const poll = setInterval(() => {
      if (typeof Alpine !== "undefined" && Alpine.store("authSession")) {
        clearInterval(poll);
        resolve();
      }
    }, 50);
  });
}

function resolveRoot(el, id) {
  return el || document.getElementById(id);
}

export function ensureAuthIslandsMounted({ gateRoot, lockRoot } = {}) {
  const gate = resolveRoot(gateRoot, "maya-auth-gate-root");
  const lock = resolveRoot(lockRoot, "maya-auth-lock-root");
  if (gate && !gate.querySelector("[x-data]")) mountAuthGate(gate);
  if (lock && !lock.querySelector("[x-data]")) mountAuthLock(lock);
}

function bindGlobalAuthActions() {
  if (typeof window === "undefined" || window.__mayaAuthBridgeBound) return;
  window.__mayaAuthBridgeBound = true;

  window.addEventListener("maya:auth", (ev) => {
    if (typeof Alpine === "undefined" || !Alpine.store("authSession")) return;
    const store = Alpine.store("authSession");
    const action = ev.detail?.action;

    if (action === "lock") {
      if (store.authEnabled) store.lock();
      else window.dispatchEvent(new CustomEvent("maya:auth:react-lock"));
    } else if (action === "logout") {
      if (store.authEnabled) {
        void store.logout();
      } else {
        window.dispatchEvent(new CustomEvent("maya:auth:react-logout"));
      }
    }
  });
}

async function initAuthBridge() {
  await waitForAlpine();
  bindGlobalAuthActions();
  const store = Alpine.store("authSession");
  await store.refresh();
  ensureAuthIslandsMounted();
}

export async function bindAuthShell({
  gateRoot,
  lockRoot,
  waybarSlot,
  greetingEl,
  fallbackName = "user",
} = {}) {
  await waitForAlpine();
  bindGlobalAuthActions();
  const store = Alpine.store("authSession");
  await store.refresh();

  ensureAuthIslandsMounted({
    gateRoot: resolveRoot(gateRoot, "maya-auth-gate-root"),
    lockRoot: resolveRoot(lockRoot, "maya-auth-lock-root"),
  });

  let unbindGreeting = () => {};
  const waybar = waybarSlot || document.getElementById("maya-auth-waybar-slot");
  if (waybar) mountAuthWaybarChip(waybar);
  const greeting =
    greetingEl || document.getElementById("maya-auth-greeting");
  if (greeting) {
    unbindGreeting = bindAuthGreeting(greeting, fallbackName);
  }

  return {
    store,
    destroy() {
      unbindGreeting();
    },
    rebindWidgets({ waybarSlot: ws, greetingEl: ge, fallbackName: fb } = {}) {
      const slot = ws || document.getElementById("maya-auth-waybar-slot");
      if (slot) mountAuthWaybarChip(slot);
      unbindGreeting();
      const geEl = ge || document.getElementById("maya-auth-greeting");
      if (geEl) unbindGreeting = bindAuthGreeting(geEl, fb || fallbackName);
    },
  };
}

if (typeof window !== "undefined") {
  window.bindAuthShell = bindAuthShell;
  window.dispatchAuthEvent = dispatchAuthEvent;
  void initAuthBridge();
}
