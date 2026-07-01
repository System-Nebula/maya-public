/** Waybar session indicator chip with session menu. */

const CHIP_TEMPLATE = `
<div class="maya-auth-waybar-wrap" x-show="visible" x-cloak @keydown.escape.window="menuOpen = false">
  <button
    type="button"
    class="maya-auth-waybar-chip"
    @click.stop="toggleMenu()"
    :title="tooltip"
    :aria-expanded="menuOpen"
  >
    <span class="initial" x-text="initial"></span>
    <span class="name" x-text="store.displayName"></span>
    <span class="verified" x-show="store.user?.verified" title="Verified on Discord"></span>
  </button>
  <div
    class="maya-auth-waybar-menu"
    x-show="menuOpen"
    x-cloak
    @click.outside="menuOpen = false"
  >
    <button type="button" @click="openAccounts()">Accounts</button>
    <button type="button" @click="lockSession()">Lock</button>
    <button type="button" class="danger" @click="signOut()">Sign out</button>
  </div>
</div>`;

export function authWaybarChipFactory() {
  return {
    menuOpen: false,

    get store() {
      return Alpine.store("authSession");
    },

    get visible() {
      return this.store?.authEnabled && Boolean(this.store?.user);
    },

    get initial() {
      return (this.store?.displayName || "?").slice(0, 1).toUpperCase();
    },

    get tooltip() {
      const u = this.store?.user;
      if (!u) return "";
      return `${u.email || u.display_name} · ${u.operator_id}`;
    },

    toggleMenu() {
      this.menuOpen = !this.menuOpen;
    },

    openAccounts() {
      this.menuOpen = false;
      window.dispatchEvent(new CustomEvent("maya:auth:open-accounts"));
    },

    lockSession() {
      this.menuOpen = false;
      if (this.store?.authEnabled) {
        this.store.lock();
      } else {
        window.dispatchEvent(new CustomEvent("maya:auth:react-lock"));
      }
    },

    signOut() {
      this.menuOpen = false;
      if (this.store?.authEnabled) {
        void this.store.logout();
      } else {
        window.dispatchEvent(new CustomEvent("maya:auth:react-logout"));
      }
    },
  };
}

export function mountAuthWaybarChip(root) {
  if (!root) return;
  root.innerHTML = `<div x-data="authWaybarChip()">${CHIP_TEMPLATE}</div>`;
  if (typeof Alpine !== "undefined" && Alpine.initTree) {
    Alpine.initTree(root);
  }
}

function registerAuthWaybarChipData() {
  if (typeof Alpine !== "undefined") {
    Alpine.data("authWaybarChip", authWaybarChipFactory);
  }
}

if (typeof document !== "undefined") {
  document.addEventListener("alpine:init", registerAuthWaybarChipData);
  registerAuthWaybarChipData();
}
