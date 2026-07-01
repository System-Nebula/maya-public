/** Alpine auth session store — cookie-backed platform user. */

const JSON_HEADERS = { "Content-Type": "application/json" };

export function formatApiError(data, status) {
  const detail = data?.detail ?? data?.error;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((item) => (typeof item === "string" ? item : item?.msg))
      .filter(Boolean);
    if (msgs.length) return msgs.join("; ");
  }
  if (status === 422) return "Invalid request";
  if (status === 401) return "Invalid email or password";
  if (status === 503) return "Service unavailable";
  return "Request failed";
}

async function jsonFetch(url, init = {}) {
  const res = await fetch(url, { credentials: "include", ...init });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(formatApiError(data, res.status));
  }
  return data;
}

export function greetingForHour(date = new Date()) {
  const h = date.getHours();
  if (h < 12) return "Good morning";
  if (h < 17) return "Good afternoon";
  return "Good evening";
}

function createAuthSessionStore() {
  return {
    authEnabled: false,
    user: null,
    locked: false,
    loading: true,
    gateVisible: false,
    error: null,
    hasPassword: true,
    googleConfigured: false,
    discordConfigured: false,

    get displayName() {
      return (
        this.user?.display_name?.trim() ||
        this.user?.email?.split("@")[0] ||
        "user"
      );
    },

    get shellReady() {
      if (!this.authEnabled) return true;
      return Boolean(this.user);
    },

    async refresh() {
      this.loading = true;
      this.error = null;
      try {
        const me = await jsonFetch("/api/auth/me");
        this.authEnabled = Boolean(me.auth_enabled);
        this.user = me.user || null;
        this.googleConfigured = Boolean(me.google_configured);
        this.discordConfigured = Boolean(me.discord_configured);
        this.gateVisible = this.authEnabled && !this.user;
        this.hasPassword = this.user ? Boolean(me.user?.has_password) : true;
        window.dispatchEvent(
          new CustomEvent("maya:auth:state", {
            detail: {
              authEnabled: this.authEnabled,
              user: this.user,
              shellReady: this.shellReady,
            },
          }),
        );
      } catch (err) {
        this.error = String(err.message || err);
        this.authEnabled = false;
        this.user = null;
        this.gateVisible = false;
      } finally {
        this.loading = false;
      }
    },

    async login(email, password) {
      const me = await jsonFetch("/api/auth/login", {
        method: "POST",
        headers: JSON_HEADERS,
        body: JSON.stringify({ email, password }),
      });
      this.user = me.user;
      this.gateVisible = false;
      await this.refresh();
    },

    async register({ email, password, invite_code, display_name }) {
      const me = await jsonFetch("/api/auth/register", {
        method: "POST",
        headers: JSON_HEADERS,
        body: JSON.stringify({ email, password, invite_code, display_name }),
      });
      this.user = me.user;
      this.gateVisible = false;
      await this.refresh();
    },

    _emitAuthState() {
      window.dispatchEvent(
        new CustomEvent("maya:auth:state", {
          detail: {
            authEnabled: this.authEnabled,
            user: this.user,
            shellReady: this.shellReady,
          },
        }),
      );
    },

    async logout() {
      try {
        await jsonFetch("/api/auth/logout", { method: "POST" });
      } catch {
        /* best-effort — clear local session regardless */
      }
      this.user = null;
      this.locked = false;
      this.gateVisible = this.authEnabled;
      this._emitAuthState();
      location.reload();
    },

    lock() {
      if (!this.authEnabled || !this.user) return;
      this.locked = true;
    },

    async unlock(password) {
      await jsonFetch("/api/auth/unlock", {
        method: "POST",
        headers: JSON_HEADERS,
        body: JSON.stringify({ password }),
      });
      this.locked = false;
    },

    async patchProfile(display_name) {
      const me = await jsonFetch("/api/auth/profile", {
        method: "PATCH",
        headers: JSON_HEADERS,
        body: JSON.stringify({ display_name }),
      });
      this.user = me.user;
      window.dispatchEvent(
        new CustomEvent("maya:auth:profile", {
          detail: { displayName: this.displayName },
        }),
      );
    },
  };
}

function registerStore() {
  if (typeof Alpine === "undefined") return;
  if (!Alpine.store("authSession")) {
    Alpine.store("authSession", createAuthSessionStore());
  }
}

if (typeof document !== "undefined") {
  document.addEventListener("alpine:init", registerStore);
  if (typeof Alpine !== "undefined") registerStore();
}

export { jsonFetch, createAuthSessionStore, formatApiError };
