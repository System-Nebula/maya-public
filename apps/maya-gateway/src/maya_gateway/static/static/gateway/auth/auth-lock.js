/** Password lock overlay when auth is enabled. */

const LOCK_TEMPLATE = `
<div class="maya-auth-lock" x-show="visible" x-cloak>
  <div class="maya-auth-panel" @click.stop>
    <h1>Locked</h1>
    <p x-show="store.hasPassword">Enter your password to unlock.</p>
    <p x-show="!store.hasPassword">OAuth-only account — sign in again.</p>
    <template x-if="store.hasPassword">
      <form @submit.prevent="submit">
        <div class="maya-auth-field">
          <input type="email" :value="store.user?.email || ''" disabled />
          <input type="password" placeholder="Password" x-model="password" required autofocus />
        </div>
        <p class="maya-auth-error" x-show="error" x-text="error"></p>
        <button class="maya-auth-primary" type="submit" :disabled="submitting">Unlock</button>
      </form>
    </template>
    <template x-if="!store.hasPassword">
      <button class="maya-auth-primary" type="button" @click="signInAgain">Sign in again</button>
    </template>
  </div>
</div>`;

export function authLockFactory() {
  return {
    password: "",
    error: "",
    submitting: false,

    get store() {
      return Alpine.store("authSession");
    },

    get visible() {
      return this.store?.authEnabled && this.store?.locked && Boolean(this.store?.user);
    },

    async submit() {
      this.error = "";
      this.submitting = true;
      try {
        await this.store.unlock(this.password);
        this.password = "";
      } catch (err) {
        this.error = err.message || "Invalid password";
      } finally {
        this.submitting = false;
      }
    },

    signInAgain() {
      this.store.logout();
    },
  };
}

export function mountAuthLock(root) {
  if (!root) return;
  root.innerHTML = `<div x-data="authLock()">${LOCK_TEMPLATE}</div>`;
  if (typeof Alpine !== "undefined" && Alpine.initTree) {
    Alpine.initTree(root);
  }
}

function registerAuthLockData() {
  if (typeof Alpine !== "undefined") {
    Alpine.data("authLock", authLockFactory);
  }
}

if (typeof document !== "undefined") {
  document.addEventListener("alpine:init", registerAuthLockData);
  registerAuthLockData();
}
