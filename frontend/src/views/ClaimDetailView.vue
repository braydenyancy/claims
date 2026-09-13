<script setup lang="ts">
import { onMounted, ref } from "vue";
import { api, ConflictError, ValidationError } from "../api/client";
import type { ClaimDetail, ClaimEvent, ConflictBody, Meta } from "../api/types";
import ActionPanel from "../components/ActionPanel.vue";
import ConflictBanner from "../components/ConflictBanner.vue";
import DraftForm from "../components/DraftForm.vue";
import HistoryTable from "../components/HistoryTable.vue";
import RegistrationBadge from "../components/RegistrationBadge.vue";
import StateBadge from "../components/StateBadge.vue";
import { useAsync } from "../composables/useAsync";
import { money, when } from "../lib/format";

const props = defineProps<{ id: number }>();

const meta = ref<Meta | null>(null);
const claim = useAsync<ClaimDetail>();
const history = ref<ClaimEvent[]>([]);

const conflict = ref<ConflictBody | null>(null);
const active = ref<string | null>(null);
const actionErrors = ref<Record<string, string>>({});
const actionBusy = ref(false);
const editing = ref(false);

function stateLabel(value: string) {
  return meta.value?.states.find((s) => s.value === value)?.label;
}

async function reload() {
  const [c, h] = await Promise.all([claim.run(() => api.claims.get(props.id)), api.claims.history(props.id).catch(() => [])]);
  if (c) history.value = h;
}

async function runAction(action: string, data: Record<string, string>) {
  const current = claim.data.value;
  if (!current) return;
  actionErrors.value = {};
  actionBusy.value = true;
  try {
    claim.data.value = await api.claims.transition(current.id, action, current.version, data);
    active.value = null;
    history.value = await api.claims.history(current.id).catch(() => history.value);
  } catch (e) {
    if (e instanceof ConflictError) conflict.value = e.conflict;
    else if (e instanceof ValidationError) actionErrors.value = e.errors;
    else actionErrors.value = { detail: e instanceof Error ? e.message : "Could not perform the action." };
  } finally {
    actionBusy.value = false;
  }
}

async function afterConflict() {
  conflict.value = null;
  active.value = null;
  actionErrors.value = {};
  await reload();
}

async function saved(updated: ClaimDetail) {
  claim.data.value = updated;
  editing.value = false;
  history.value = await api.claims.history(updated.id).catch(() => history.value);
}

onMounted(async () => {
  meta.value = await api.meta().catch(() => null);
  await reload();
});
</script>

<template>
  <main>
    <p><RouterLink :to="{ name: 'claims' }">← Claims</RouterLink></p>

    <p v-if="claim.loading.value && !claim.data.value" class="muted">Loading claim…</p>
    <p v-else-if="claim.error.value" class="error" role="alert">{{ claim.error.value }} <button @click="reload">Retry</button></p>

    <template v-else-if="claim.data.value">
      <h1>
        {{ claim.data.value.reference }}
        <StateBadge :state="claim.data.value.state" :label="stateLabel(claim.data.value.state)" />
      </h1>
      <p><RegistrationBadge :registration="claim.data.value.registration" :labels="meta?.registration_statuses" /></p>

      <ConflictBanner v-if="conflict" :conflict="conflict" @reload="afterConflict" />

      <ActionPanel
        :actions="claim.data.value.available_actions"
        :disabled="conflict !== null"
        :choice-labels="meta?.denial_reasons"
        :errors="actionErrors"
        :busy="actionBusy"
        :active="active"
        @run="runAction"
        @open="(a) => { active = a; actionErrors = {}; }"
        @close="active = null"
      />

      <p v-if="claim.data.value.can_edit && !editing"><button @click="editing = true">Edit draft</button></p>
      <DraftForm v-if="editing" :claim="claim.data.value" @saved="saved" />

      <section class="card">
        <dl>
          <dt>Payer</dt><dd>{{ claim.data.value.payer || "—" }}</dd>
          <dt>Service date</dt><dd>{{ claim.data.value.service_date ?? "—" }}</dd>
          <dt>Billed</dt><dd>{{ money(claim.data.value.billed_amount) }}</dd>
          <dt>Approved</dt><dd>{{ money(claim.data.value.approved_amount) }}</dd>
          <dt v-if="claim.data.value.denial_reason">Denial reason</dt><dd v-if="claim.data.value.denial_reason">{{ claim.data.value.denial_reason }}</dd>
          <dt>Created by</dt><dd>{{ claim.data.value.created_by }} · {{ when(claim.data.value.created_at) }}</dd>
          <dt>Version</dt><dd>{{ claim.data.value.version }}</dd>
        </dl>
      </section>

      <h2>History</h2>
      <HistoryTable :events="history" />
    </template>
  </main>
</template>
