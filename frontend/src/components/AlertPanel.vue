<script setup lang="ts">
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { api, ValidationError } from "../api/client";
import type { Alert, ClaimDetail } from "../api/types";
import { isSignedOut } from "../composables/useAsync";
import { useSession } from "../composables/useSession";
import { describe, sentence, when } from "../lib/format";

// The server says which alerts exist, which are answered, and whether this
// caller may answer them. Nothing here is derived from history or a role.
defineProps<{ alerts: Alert[]; claimId: number }>();
const emit = defineEmits<{ updated: [claim: ClaimDetail] }>();

const session = useSession();
const router = useRouter();
const route = useRoute();

const notes = ref<Record<number, string>>({});
const errors = ref<Record<number, string>>({});
const busy = ref<number | null>(null);

async function acknowledge(claimId: number, eventId: number) {
  errors.value = { ...errors.value, [eventId]: "" };
  busy.value = eventId;
  try {
    const claim = await api.claims.acknowledge(claimId, eventId, notes.value[eventId] ?? "");
    notes.value = { ...notes.value, [eventId]: "" };
    emit("updated", claim);
  } catch (e) {
    if (isSignedOut(e)) {
      session.clear();
      await router.push({ name: "login", query: { next: route.fullPath } });
      return;
    }
    const msg = e instanceof ValidationError ? Object.values(e.errors).join(" ") : e instanceof Error ? e.message : "Failed.";
    errors.value = { ...errors.value, [eventId]: msg };
  } finally {
    busy.value = null;
  }
}
</script>

<template>
  <section v-if="alerts.length" class="panel" :data-tone="alerts.some((a) => !a.acknowledgement) ? 'danger' : null">
    <div class="panel-head">
      <h2>Alerts</h2>
      <span class="hint">{{ alerts.filter((a) => !a.acknowledgement).length }} open</span>
    </div>
    <div v-for="alert in alerts" :key="alert.event_id" class="panel-body">
      <div class="alert-head">
        <span class="badge" :data-tone="alert.acknowledgement ? 'success' : 'danger'">
          {{ alert.acknowledgement ? "Acknowledged" : "Open" }}
        </span>
        <strong>{{ sentence(alert.action) }}</strong>
        <span class="hint">{{ when(alert.created_at) }}</span>
      </div>
      <p class="hint detail">{{ describe(alert.data) }}</p>
      <p v-if="alert.acknowledgement" class="ack">
        Acknowledged by {{ alert.acknowledgement.actor ?? "the system" }}
        {{ when(alert.acknowledgement.created_at) }}: “{{ alert.acknowledgement.note }}”
      </p>
      <form v-else-if="alert.can_acknowledge" @submit.prevent="acknowledge(claimId, alert.event_id)">
        <label class="field">
          <span>Note</span>
          <textarea v-model="notes[alert.event_id]" rows="2" required placeholder="What was checked, and what happens next"></textarea>
        </label>
        <p v-if="errors[alert.event_id]" class="field-error">{{ errors[alert.event_id] }}</p>
        <button class="primary" :disabled="busy === alert.event_id">Acknowledge</button>
      </form>
      <p v-else class="muted">Open. Awaiting acknowledgement.</p>
    </div>
  </section>
</template>

<style scoped>
.alert-head { display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap; }
.detail { margin: 0.35rem 0 0.75rem; }
.ack { color: var(--ink-2); }
</style>
