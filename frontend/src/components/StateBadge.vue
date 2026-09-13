<script setup lang="ts">
import { humanize } from "../lib/format";

// Renders whatever state string the API gives. It knows no state names;
// the label comes from /api/meta/ when the caller has it.
defineProps<{ state: string; label?: string }>();
</script>

<template>
  <span class="badge" :data-state="state">{{ label ?? humanize(state) }}</span>
</template>
