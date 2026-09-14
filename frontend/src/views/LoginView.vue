<script setup lang="ts">
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ApiError } from "../api/client";
import { useSession } from "../composables/useSession";

const session = useSession();
const router = useRouter();
const route = useRoute();
const username = ref("");
const password = ref("");
const error = ref("");
const busy = ref(false);

// Only a path on this app is a safe place to land: "//evil.example" is a
// protocol-relative URL, and anything else is not ours to navigate to.
function nextPath(): string | null {
  const next = route.query.next;
  if (typeof next !== "string" || !next.startsWith("/") || next.startsWith("//")) return null;
  return next;
}

async function submit() {
  error.value = "";
  busy.value = true;
  try {
    await session.login(username.value, password.value);
    await router.push(nextPath() ?? { name: "claims" });
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : "Could not reach the server.";
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <main class="page narrow">
    <div class="brand auth-brand">
      <span class="brand-mark" aria-hidden="true">C</span>
      Claim Review
    </div>
    <form class="panel" @submit.prevent="submit">
      <div class="panel-body">
        <h1 class="title">Sign in</h1>
        <label class="field">
          <span>Username</span>
          <input v-model="username" autocomplete="username" required />
        </label>
        <label class="field">
          <span>Password</span>
          <input v-model="password" type="password" autocomplete="current-password" required />
        </label>
        <p v-if="error" class="notice" data-tone="danger" role="alert">{{ error }}</p>
        <button class="primary wide" :disabled="busy">Sign in</button>
      </div>
    </form>
    <p class="hint seeded">Seeded users: sam, rita, rob. Password: password.</p>
  </main>
</template>

<style scoped>
.auth-brand { justify-content: center; margin-bottom: 1.25rem; font-size: 1.1rem; }
.title { margin-bottom: 1rem; }
.wide { width: 100%; margin-top: 0.25rem; }
.notice { margin-bottom: 0.75rem; }
.seeded { text-align: center; margin-top: 1rem; }
</style>
