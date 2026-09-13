import { ref } from "vue";
import { api, ApiError } from "../api/client";
import type { User } from "../api/types";

const user = ref<User | null>(null);
let loaded = false;

// One module-level session for the whole app. The server is the source
// of truth: load() asks it who we are, and a 403 means nobody.
export function useSession() {
  async function load(): Promise<User | null> {
    if (loaded) return user.value;
    try {
      user.value = await api.me();
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) user.value = null;
      else throw e;
    }
    loaded = true;
    return user.value;
  }

  async function login(username: string, password: string) {
    user.value = await api.login(username, password);
    loaded = true;
  }

  async function logout() {
    await api.logout();
    user.value = null;
  }

  function clear() {
    user.value = null;
  }

  return { user, load, login, logout, clear };
}
