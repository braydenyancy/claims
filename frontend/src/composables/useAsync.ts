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

  async function run(fn: () => Promise<T>): Promise<T | null> {
    loading.value = true;
    error.value = "";
    try {
      const result = await fn();
      data.value = result;
      return result;
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) {
        session.clear();
        await router.push({ name: "login", query: { next: router.currentRoute.value.fullPath } });
        return null;
      }
      error.value = e instanceof Error ? e.message : "Something went wrong.";
      return null;
    } finally {
      loading.value = false;
    }
  }

  return { data, error, loading, run };
}
