<script setup lang="ts">
import { computed, ref } from "vue";
import { api, ValidationError } from "../api/client";
import type { ClaimDetail, ClaimEvent } from "../api/types";
import { humanize, when } from "../lib/format";

const props = defineProps<{ events: ClaimEvent[]; claimId: number; canAct: boolean }>();
const emit = defineEmits<{ updated: [claim: ClaimDetail] }>();

const notes = ref<Record<number, string>>({});
const errors = ref<Record<number, string>>({});
const busy = ref<number | null>(null);

// An alert is open until an alert_acknowledged event names its id.
const alerts = computed(() => {
  const acks = new Map<number, ClaimEvent>();
  for (const e of props.events) {
    if (e.action === "alert_acknowledged" && typeof e.data.event_id === "number") acks.set(e.data.event_id, e);
  }
  return props.events.filter((e) => e.severity === "alert").map((e) => ({ event: e, ack: acks.get(e.id) ?? null }));
});

async function acknowledge(eventId: number) {
  errors.value = { ...errors.value, [eventId]: "" };
  busy.value = eventId;
  try {
    const claim = await api.claims.acknowledge(props.claimId, eventId, notes.value[eventId] ?? "");
    notes.value = { ...notes.value, [eventId]: "" };
    emit("updated", claim);
  } catch (e) {
    const msg = e instanceof ValidationError ? Object.values(e.errors).join(" ") : e instanceof Error ? e.message : "Failed.";
    errors.value = { ...errors.value, [eventId]: msg };
  } finally {
    busy.value = null;
  }
}
</script>

<template>
  <section v-if="alerts.length">
    <h2>Alerts</h2>
    <div v-for="{ event, ack } in alerts" :key="event.id" class="card" :class="{ 'alert-row': !ack }">
      <p><strong>{{ humanize(event.action) }}</strong> · {{ when(event.created_at) }}</p>
      <p class="hint">{{ JSON.stringify(event.data) }}</p>
      <p v-if="ack">Acknowledged by {{ ack.actor }} {{ when(ack.created_at) }}: “{{ ack.data.note }}”</p>
      <form v-else-if="canAct" @submit.prevent="acknowledge(event.id)">
        <label>Note <textarea v-model="notes[event.id]" rows="2" required></textarea></label>
        <p v-if="errors[event.id]" class="field-error">{{ errors[event.id] }}</p>
        <button :disabled="busy === event.id">Acknowledge</button>
      </form>
      <p v-else class="muted">Open. Awaiting acknowledgement.</p>
    </div>
  </section>
</template>
