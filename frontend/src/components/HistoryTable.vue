<script setup lang="ts">
import type { ClaimEvent } from "../api/types";
import { describe, humanize, sentence, when } from "../lib/format";

defineProps<{ events: ClaimEvent[] }>();

// Severity is a closed, generic vocabulary from the API (info, warning,
// alert), so mapping it to a colour here decides nothing about claims.
const tone: Record<ClaimEvent["severity"], string> = { info: "neutral", warning: "warning", alert: "danger" };
</script>

<template>
  <p v-if="events.length === 0" class="empty">No history yet.</p>
  <div v-else class="table-wrap">
    <table class="data">
      <thead>
        <tr><th>When</th><th>Who</th><th>Event</th><th>State</th><th>Details</th></tr>
      </thead>
      <tbody>
        <tr v-for="e in events" :key="e.id" :data-severity="e.severity === 'info' ? null : e.severity">
          <td class="dim mono nowrap">{{ when(e.created_at) }}</td>
          <td>{{ e.actor ?? "system" }}</td>
          <td>
            {{ sentence(e.action) }}
            <span v-if="e.severity !== 'info'" class="badge" :data-tone="tone[e.severity]">{{ e.severity }}</span>
          </td>
          <td>
            <span v-if="e.from_state !== e.to_state">{{ humanize(e.from_state) }} → {{ humanize(e.to_state) }}</span>
            <span v-else class="dim">{{ humanize(e.to_state) }}</span>
          </td>
          <td class="details">{{ describe(e.data) }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
