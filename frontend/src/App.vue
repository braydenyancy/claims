<script setup lang="ts">
import { onMounted, ref } from "vue";

const status = ref("checking…");

onMounted(async () => {
  try {
    const res = await fetch("/api/health/");
    const body = await res.json();
    status.value = `api ${body.status}, database ${body.database}`;
  } catch {
    status.value = "api unreachable";
  }
});
</script>

<template>
  <main>
    <h1>Claims</h1>
    <p>{{ status }}</p>
  </main>
</template>
