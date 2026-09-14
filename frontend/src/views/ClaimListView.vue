<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { api } from "../api/client";
import type { ClaimDetail, ClaimSummary, Meta, Option, Page, Summary } from "../api/types";
import DraftForm from "../components/DraftForm.vue";
import StateBadge from "../components/StateBadge.vue";
import { useAsync } from "../composables/useAsync";
import { useSession } from "../composables/useSession";
import { money, shortDate, when } from "../lib/format";

const router = useRouter();
const route = useRoute();
const session = useSession();
const meta = ref<Meta | null>(null);
const summary = ref<Summary | null>(null);
// Filters live in the URL so a reload, a shared link, or the back button
// lands on the same slice.
const state = ref(typeof route.query.state === "string" ? route.query.state : "");
const openAlerts = ref(route.query.alert === "open");
const showDraft = ref(false);
const page = useAsync<Page<ClaimSummary>>();

function optionFor(value: string): Option | undefined {
  return meta.value?.states.find((s) => s.value === value);
}

async function load() {
  const params: Record<string, string> = {};
  if (state.value) params.state = state.value;
  if (openAlerts.value) params.alert = "open";
  // The strip counts the whole scope; the table shows the filtered slice.
  const [, s] = await Promise.all([page.run(() => api.claims.list(params)), api.claims.summary().catch(() => null)]);
  if (s) summary.value = s;
}

function pick(value: string) {
  state.value = state.value === value ? "" : value;
}

function clear() {
  state.value = "";
  openAlerts.value = false;
}

async function created(claim: ClaimDetail) {
  showDraft.value = false;
  await router.push({ name: "claim", params: { id: claim.id } });
}

onMounted(async () => {
  meta.value = await api.meta().catch(() => null);
  await load();
});
watch([state, openAlerts], () => {
  const query: Record<string, string> = {};
  if (state.value) query.state = state.value;
  if (openAlerts.value) query.alert = "open";
  router.replace({ query });
  load();
});
</script>

<template>
  <main class="page">
    <div class="page-head">
      <div>
        <h1>Claims</h1>
        <p class="lede">Everything you can see, newest change first.</p>
      </div>
      <div class="actions">
        <button v-if="session.user.value?.can_create_claims" :class="showDraft ? 'ghost' : 'primary'" @click="showDraft = !showDraft">
          {{ showDraft ? "Close" : "New draft" }}
        </button>
      </div>
    </div>

    <DraftForm v-if="showDraft" class="draft" @saved="created" @cancel="showDraft = false" />

    <nav v-if="summary" class="strip" aria-label="Filter by state">
      <button class="chip" :aria-pressed="state === '' && !openAlerts" @click="clear">
        All <span class="count">{{ summary.total }}</span>
      </button>
      <button v-for="s in summary.states" :key="s.value" class="chip" :aria-pressed="state === s.value" @click="pick(s.value)">
        <span class="dot" :data-tone="s.tone"></span>{{ s.label }} <span class="count">{{ s.count }}</span>
      </button>
      <button class="chip apart" :class="{ danger: summary.open_alerts > 0 }" :aria-pressed="openAlerts" @click="openAlerts = !openAlerts">
        <span class="dot" data-tone="danger"></span>Open alerts <span class="count">{{ summary.open_alerts }}</span>
      </button>
    </nav>

    <div class="toolbar">
      <span class="spacer"></span>
      <span v-if="page.data.value">
        <template v-if="page.data.value.count > page.data.value.results.length">
          Showing {{ page.data.value.results.length }} of {{ page.data.value.count }}
        </template>
        <template v-else>{{ page.data.value.count }} {{ page.data.value.count === 1 ? "claim" : "claims" }}</template>
      </span>
      <button v-if="state || openAlerts" class="ghost sm" @click="clear">Clear filters</button>
    </div>

    <section class="panel">
      <p v-if="page.loading.value && !page.data.value" class="empty">Loading claims…</p>
      <div v-else-if="page.error.value" class="empty" role="alert">
        <strong>Could not load claims.</strong>
        {{ page.error.value }}
        <div class="actions center"><button @click="load">Try again</button></div>
      </div>
      <div v-else-if="page.data.value && page.data.value.results.length === 0" class="empty">
        <strong>No claims match.</strong>
        <template v-if="state || openAlerts">Widen the filter to see more.</template>
        <template v-else-if="session.user.value?.can_create_claims">Start with a new draft.</template>
        <template v-else>Nothing has been submitted for review yet.</template>
      </div>
      <div v-else-if="page.data.value" class="table-wrap">
        <table class="data">
          <thead>
            <tr>
              <th>Reference</th>
              <th>Payer</th>
              <th class="optional">Service date</th>
              <th>State</th>
              <th class="num">Billed</th>
              <th class="optional">Updated</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in page.data.value.results" :key="c.id">
              <td class="ref"><RouterLink :to="{ name: 'claim', params: { id: c.id } }">{{ c.reference }}</RouterLink></td>
              <td>{{ c.payer || "—" }}</td>
              <td class="dim optional">{{ shortDate(c.service_date) }}</td>
              <td><StateBadge :state="c.state" :label="optionFor(c.state)?.label" :tone="optionFor(c.state)?.tone" /></td>
              <td class="num">{{ money(c.billed_amount) }}</td>
              <td class="dim optional nowrap">{{ when(c.updated_at) }}</td>
              <td><span v-if="c.has_open_alert" class="badge" data-tone="danger">Alert</span></td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </main>
</template>

<style scoped>
.draft { margin-bottom: 1.25rem; }
.center { justify-content: center; margin-top: 0.75rem; }
</style>
