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

async function submit() {
  error.value = "";
  busy.value = true;
  try {
    await session.login(username.value, password.value);
    await router.push(typeof route.query.next === "string" ? route.query.next : { name: "claims" });
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : "Could not reach the server.";
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <main class="narrow">
    <h1>Sign in</h1>
    <form @submit.prevent="submit">
      <label>Username <input v-model="username" autocomplete="username" required /></label>
      <label>Password <input v-model="password" type="password" autocomplete="current-password" required /></label>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <button :disabled="busy">Sign in</button>
    </form>
    <p class="hint">Seeded users: sam, rita, rob. Password: password.</p>
  </main>
</template>
