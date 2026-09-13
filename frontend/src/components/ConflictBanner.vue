<script setup lang="ts">
import type { ConflictBody } from "../api/types";
import { ago, humanize } from "../lib/format";

defineProps<{ conflict: ConflictBody }>();
defineEmits<{ reload: [] }>();
</script>

<template>
  <div class="banner" role="alert">
    <strong>This claim changed while you were looking at it.</strong>
    <p v-if="conflict.last_event">
      Changed by {{ conflict.last_event.actor ?? "the system" }} ({{ humanize(conflict.last_event.action) }})
      {{ ago(conflict.last_event.created_at) }}. It is now {{ humanize(conflict.current_state) }}.
    </p>
    <p v-else>It is now {{ humanize(conflict.current_state) }}.</p>
    <button @click="$emit('reload')">Reload</button>
  </div>
</template>
