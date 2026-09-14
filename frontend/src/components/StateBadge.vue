<script setup lang="ts">
import { humanize } from "../lib/format";

// Renders whatever state string the API gives. It knows no state names;
// label and tone come from /api/meta/ when the caller has them.
defineProps<{ state: string; label?: string; tone?: string; large?: boolean }>();
</script>

<template>
  <span class="badge" :class="{ lg: large }" :data-tone="tone ?? 'neutral'" :data-state="state">{{ label ?? humanize(state) }}</span>
</template>
