<script setup lang="ts">
import { useRouter } from "vue-router";
import { useSession } from "./composables/useSession";

const session = useSession();
const router = useRouter();

async function logout() {
  await session.logout();
  await router.push({ name: "login" });
}
</script>

<template>
  <nav v-if="session.user.value">
    <RouterLink :to="{ name: 'claims' }">Claims</RouterLink>
    <span class="spacer"></span>
    <span class="muted">{{ session.user.value.username }} · {{ session.user.value.role }}</span>
    <button @click="logout">Sign out</button>
  </nav>
  <RouterView />
</template>
