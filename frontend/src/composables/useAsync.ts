import { ref, shallowRef } from "vue";
import { useRouter } from "vue-router";
import { ApiError } from "../api/client";
import { useSession } from "./useSession";

// The server answers 401 when the session is gone and 403 when the caller
// is simply not allowed. Only the first means "sign in again".
export function isSignedOut(e: unknown): boolean {
  return e instanceof ApiError && e.status === 401;
}

// Loading, error, and "you are no longer signed in" handled once, so
// every view gets the same three states for free.
export function useAsync<T>() {
  const data = shallowRef<T | null>(null);
  const error = ref("");
  const loading = ref(false);
  const router = useRouter();
  const session = useSession();
  let seq = 0;

  async function run(fn: () => Promise<T>): Promise<T | null> {
    const mine = ++seq;
    loading.value = true;
    error.value = "";
    try {
      const result = await fn();
      // Only the most recent call may write; a slower earlier response must not overwrite a newer one.
      if (mine === seq) data.value = result;
      return result;
    } catch (e) {
      if (isSignedOut(e)) {
        if (mine === seq) {
          session.clear();
          await router.push({ name: "login", query: { next: router.currentRoute.value.fullPath } });
        }
        return null;
      }
      if (mine === seq) error.value = e instanceof Error ? e.message : "Something went wrong.";
      return null;
    } finally {
      if (mine === seq) loading.value = false;
    }
  }

  // A write that already has the fresh claim joins the same sequence, so a
  // poll still in flight when it lands cannot overwrite it.
  function set(value: T) {
    seq++;
    data.value = value;
    error.value = "";
  }

  return { data, error, loading, run, set };
}
