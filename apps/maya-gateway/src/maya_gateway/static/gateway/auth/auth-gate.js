/** Login / register overlay when auth is enabled and no session cookie. */

const GATE_TEMPLATE = `
<div class="maya-auth-gate" x-show="visible" x-cloak>
  <div class="maya-auth-panel" @click.stop>
    <h1>Maya Gateway</h1>
    <p>Sign in or register with an invite code.</p>
    <div class="maya-auth-tabs">
      <button type="button" :class="{ active: mode === 'login' }" @click="mode = 'login'">Sign in</button>
      <button type="button" :class="{ active: mode === 'register' }" @click="mode = 'register'">Register</button>
    </div>
    <form @submit.prevent="submit">
      <template x-if="mode === 'register'">
        <div class="maya-auth-field">
          <input type="text" placeholder="Display name (optional)" x-model="displayName" />
          <input type="text" placeholder="Invite code" x-model="inviteCode" required />
        </div>
      </template>
      <div class="maya-auth-field">
        <input type="email" placeholder="Email" x-model="email" required autocomplete="email" />
        <input type="password" placeholder="Password" x-model="password" required
               :autocomplete="mode === 'login' ? 'current-password' : 'new-password'" />
        <template x-if="mode === 'register'">
          <input type="password" placeholder="Confirm password" x-model="confirm" required />
        </template>
      </div>
      <p class="maya-auth-error" x-show="error" x-text="error"></p>
      <button class="maya-auth-primary" type="submit" :disabled="submitting" x-text="submitting ? '…' : (mode === 'login' ? 'Sign in' : 'Create account')"></button>
    </form>
    <div class="maya-auth-sso" x-show="store.googleConfigured || store.discordConfigured">
      <a x-show="store.googleConfigured && googleLinkEnabled" :href="googleHref">Continue with Google</a>
      <a x-show="store.discordConfigured && discordLinkEnabled" :href="discordHref">Continue with Discord</a>
      <p class="maya-auth-hint" x-show="(store.googleConfigured || store.discordConfigured) && mode === 'register' && !inviteCode.trim()">
        Enter an invite code to register with Google or Discord.
      </p>
    </div>
  </div>
</div>`;

export function authGateFactory() {
  return {
    mode: "login",
    email: "",
    password: "",
    confirm: "",
    inviteCode: "",
    displayName: "",
    error: "",
    submitting: false,

    get store() {
      return Alpine.store("authSession");
    },

    get visible() {
      return this.store?.gateVisible && !this.store?.loading;
    },

    get googleLinkEnabled() {
      if (this.mode === "login") return true;
      return Boolean(this.inviteCode.trim());
    },

    get discordLinkEnabled() {
      if (this.mode === "login") return true;
      return Boolean(this.inviteCode.trim());
    },

    get googleHref() {
      if (this.mode === "register") {
        return `/auth/google?intent=register&invite_code=${encodeURIComponent(this.inviteCode.trim())}`;
      }
      return "/auth/google?intent=login";
    },

    get discordHref() {
      if (this.mode === "register") {
        return `/auth/discord?intent=register&invite_code=${encodeURIComponent(this.inviteCode.trim())}`;
      }
      return "/auth/discord?intent=login";
    },

    async submit() {
      this.error = "";
      if (this.mode === "register" && this.password !== this.confirm) {
        this.error = "Passwords do not match";
        return;
      }
      this.submitting = true;
      try {
        if (this.mode === "login") {
          await this.store.login(this.email, this.password);
        } else {
          await this.store.register({
            email: this.email,
            password: this.password,
            invite_code: this.inviteCode.trim(),
            display_name: this.displayName.trim() || undefined,
          });
        }
        window.dispatchEvent(new CustomEvent("maya:auth:ready"));
      } catch (err) {
        this.error = err.message || "Authentication failed";
      } finally {
        this.submitting = false;
      }
    },
  };
}

export function mountAuthGate(root) {
  if (!root) return;
  root.innerHTML = `<div x-data="authGate()">${GATE_TEMPLATE}</div>`;
  if (typeof Alpine !== "undefined" && Alpine.initTree) {
    Alpine.initTree(root);
  }
}

function registerAuthGateData() {
  if (typeof Alpine !== "undefined") {
    Alpine.data("authGate", authGateFactory);
  }
}

if (typeof document !== "undefined") {
  document.addEventListener("alpine:init", registerAuthGateData);
  registerAuthGateData();
}
