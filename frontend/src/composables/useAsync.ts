import { ref, shallowRef } from "vue";
import { useRouter } from "vue-router";
import { ApiError } from "../api/client";
import { useSession } from "./useSession";

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
      if (e instanceof ApiError && e.status === 403) {
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

  return { data, error, loading, run };
}
