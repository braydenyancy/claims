<script setup lang="ts">
import { onMounted, ref } from "vue";
import { api } from "../api/client";
import type { ClaimDetail, ClaimEvent, Meta } from "../api/types";
import HistoryTable from "../components/HistoryTable.vue";
import RegistrationBadge from "../components/RegistrationBadge.vue";
import StateBadge from "../components/StateBadge.vue";
import { useAsync } from "../composables/useAsync";
import { money, when } from "../lib/format";

const props = defineProps<{ id: number }>();

const meta = ref<Meta | null>(null);
const claim = useAsync<ClaimDetail>();
const history = ref<ClaimEvent[]>([]);

function stateLabel(value: string) {
  return meta.value?.states.find((s) => s.value === value)?.label;
}

async function reload() {
  const [c, h] = await Promise.all([claim.run(() => api.claims.get(props.id)), api.claims.history(props.id).catch(() => [])]);
  if (c) history.value = h;
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
