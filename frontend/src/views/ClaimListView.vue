<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { api } from "../api/client";
import type { ClaimDetail, ClaimSummary, Meta, Page } from "../api/types";
import DraftForm from "../components/DraftForm.vue";
import StateBadge from "../components/StateBadge.vue";
import { useAsync } from "../composables/useAsync";
import { useSession } from "../composables/useSession";
import { money, when } from "../lib/format";

const router = useRouter();
const session = useSession();
const meta = ref<Meta | null>(null);
const state = ref("");
const openAlerts = ref(false);
const showDraft = ref(false);
const page = useAsync<Page<ClaimSummary>>();

function labelFor(value: string) {
  return meta.value?.states.find((s) => s.value === value)?.label;
}

async function load() {
  const params: Record<string, string> = {};
  if (state.value) params.state = state.value;
  if (openAlerts.value) params.alert = "open";
  await page.run(() => api.claims.list(params));
}

async function created(claim: ClaimDetail) {
  showDraft.value = false;
  await router.push({ name: "claim", params: { id: claim.id } });
}

onMounted(async () => {
  meta.value = await api.meta().catch(() => null);
  await load();
});
watch([state, openAlerts], load);
</script>

<template>
  <main>
    <h1>Claims</h1>

    <section class="filters actions">
      <label>
        State
        <select v-model="state">
          <option value="">all</option>
          <option v-for="s in meta?.states ?? []" :key="s.value" :value="s.value">{{ s.label }}</option>
        </select>
      </label>
      <label><input v-model="openAlerts" type="checkbox" /> open alerts only</label>
      <button v-if="session.user.value?.can_create_claims" @click="showDraft = !showDraft">
        {{ showDraft ? "Cancel" : "New draft" }}
      </button>
    </section>

    <DraftForm v-if="showDraft" @saved="created" />

    <p v-if="page.loading.value" class="muted">Loading claims…</p>
    <p v-else-if="page.error.value" class="error" role="alert">
      {{ page.error.value }} <button @click="load">Retry</button>
    </p>
    <p v-else-if="page.data.value && page.data.value.results.length === 0" class="muted">No claims match.</p>
    <table v-else-if="page.data.value">
      <thead>
        <tr><th>Reference</th><th>Payer</th><th>State</th><th>Billed</th><th>Updated</th><th></th></tr>
      </thead>
      <tbody>
        <tr v-for="c in page.data.value.results" :key="c.id">
          <td><RouterLink :to="{ name: 'claim', params: { id: c.id } }">{{ c.reference }}</RouterLink></td>
          <td>{{ c.payer || "—" }}</td>
          <td><StateBadge :state="c.state" :label="labelFor(c.state)" /></td>
          <td>{{ money(c.billed_amount) }}</td>
          <td>{{ when(c.updated_at) }}</td>
          <td><span v-if="c.has_open_alert" class="badge alert-row">alert</span></td>
        </tr>
      </tbody>
    </table>
    <p v-if="page.data.value && page.data.value.count > page.data.value.results.length" class="hint">
      Showing {{ page.data.value.results.length }} of {{ page.data.value.count }}.
    </p>
  </main>
</template>
