/** Bind desktop greeting line to auth session display name. */

import { greetingForHour } from "./auth-session.js";

export function bindAuthGreeting(el, fallbackName = "user") {
  if (!el) return () => {};

  function render() {
    const store = typeof Alpine !== "undefined" ? Alpine.store("authSession") : null;
    const name =
      (store?.authEnabled && store?.user && store.displayName) ||
      fallbackName;
    const prefix = greetingForHour();
    el.textContent = `${prefix}, ${name}`;
  }

  render();
  const onState = () => render();
  const onProfile = (ev) => {
    if (ev.detail?.displayName) render();
  };

  window.addEventListener("maya:auth:state", onState);
  window.addEventListener("maya:auth:profile", onProfile);
  window.addEventListener("maya:auth:ready", onState);

  return () => {
    window.removeEventListener("maya:auth:state", onState);
    window.removeEventListener("maya:auth:profile", onProfile);
    window.removeEventListener("maya:auth:ready", onState);
  };
}
