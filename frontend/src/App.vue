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
  <header v-if="session.user.value" class="topbar">
    <RouterLink class="brand" :to="{ name: 'claims' }">
      <span class="brand-mark" aria-hidden="true">C</span>
      Claim Review
    </RouterLink>
    <span class="spacer"></span>
    <span class="user-chip">
      <strong>{{ session.user.value.username }}</strong>
      <span class="role">{{ session.user.value.role }}</span>
    </span>
    <button class="ghost sm" @click="logout">Sign out</button>
  </header>
  <RouterView />
</template>
