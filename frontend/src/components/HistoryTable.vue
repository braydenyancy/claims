<script setup lang="ts">
import type { ClaimEvent } from "../api/types";
import { humanize, when } from "../lib/format";

defineProps<{ events: ClaimEvent[] }>();

function summary(data: Record<string, unknown>): string {
  return Object.entries(data)
    .map(([k, v]) => `${humanize(k)}: ${typeof v === "object" ? JSON.stringify(v) : String(v)}`)
    .join(" · ");
}
</script>

<template>
  <p v-if="events.length === 0" class="muted">No history yet.</p>
  <table v-else>
    <thead>
      <tr><th>When</th><th>Who</th><th>What</th><th>State</th><th>Details</th></tr>
    </thead>
    <tbody>
      <tr v-for="e in events" :key="e.id" :class="{ 'alert-row': e.severity === 'alert', 'warning-row': e.severity === 'warning' }">
        <td>{{ when(e.created_at) }}</td>
        <td>{{ e.actor ?? "system" }}</td>
        <td>{{ humanize(e.action) }}<span v-if="e.severity !== 'info'" class="hint"> ({{ e.severity }})</span></td>
        <td>
          <span v-if="e.from_state !== e.to_state">{{ humanize(e.from_state) }} → {{ humanize(e.to_state) }}</span>
          <span v-else class="muted">{{ humanize(e.to_state) }}</span>
        </td>
        <td class="hint">{{ summary(e.data) }}</td>
      </tr>
    </tbody>
  </table>
</template>
