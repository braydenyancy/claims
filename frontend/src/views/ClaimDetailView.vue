<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { api, ConflictError, ValidationError } from "../api/client";
import type { ClaimDetail, ClaimEvent, ConflictBody, Meta, Option } from "../api/types";
import ActionPanel from "../components/ActionPanel.vue";
import AlertPanel from "../components/AlertPanel.vue";
import ConflictBanner from "../components/ConflictBanner.vue";
import DraftForm from "../components/DraftForm.vue";
import HistoryTable from "../components/HistoryTable.vue";
import RegistrationBadge from "../components/RegistrationBadge.vue";
import StateBadge from "../components/StateBadge.vue";
import { isSignedOut, useAsync } from "../composables/useAsync";
import { useSession } from "../composables/useSession";
import { money, shortDate, when } from "../lib/format";

const props = defineProps<{ id: number }>();

const session = useSession();
const router = useRouter();
const route = useRoute();

const meta = ref<Meta | null>(null);
const claim = useAsync<ClaimDetail>();
const history = ref<ClaimEvent[]>([]);

const conflict = ref<ConflictBody | null>(null);
const active = ref<string | null>(null);
const actionErrors = ref<Record<string, string>>({});
const actionBusy = ref(false);
const editing = ref(false);
const retryBusy = ref(false);
const retryError = ref("");

function stateOption(value: string): Option | undefined {
  return meta.value?.states.find((s) => s.value === value);
}

function denialLabel(value: string) {
  return meta.value?.denial_reasons.find((d) => d.value === value)?.label ?? value;
}

// The session is gone, not merely insufficient: send the caller to sign in
// rather than showing them a message they can do nothing about.
async function signInAgain() {
  session.clear();
  await router.push({ name: "login", query: { next: route.fullPath } });
}

async function reload() {
  retryError.value = "";
  // A failed history refresh keeps the history already on screen.
  const [c, h] = await Promise.all([
    claim.run(() => api.claims.get(props.id)),
    api.claims.history(props.id).catch(() => null),
  ]);
  if (c && h !== null) history.value = h;
}

async function runAction(action: string, data: Record<string, string>) {
  const current = claim.data.value;
  if (!current) return;
  actionErrors.value = {};
  actionBusy.value = true;
  try {
    claim.set(await api.claims.transition(current.id, action, current.version, data));
    active.value = null;
    editing.value = false;
    history.value = await api.claims.history(current.id).catch(() => history.value);
  } catch (e) {
    if (isSignedOut(e)) await signInAgain();
    else if (e instanceof ConflictError) conflict.value = e.conflict;
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
  retryError.value = "";
  await reload();
}

async function saved(updated: ClaimDetail) {
  claim.set(updated);
  editing.value = false;
  history.value = await api.claims.history(updated.id).catch(() => history.value);
}

let timer: ReturnType<typeof setInterval> | null = null;

async function retry() {
  const current = claim.data.value;
  if (!current) return;
  retryBusy.value = true;
  retryError.value = "";
  try {
    claim.set(await api.claims.retry(current.id));
    history.value = await api.claims.history(current.id).catch(() => history.value);
  } catch (e) {
    if (isSignedOut(e)) await signInAgain();
    else retryError.value = e instanceof Error ? e.message : "Could not retry.";
  } finally {
    retryBusy.value = false;
  }
}

function polling(status: string | undefined) {
  const wants = status === "pending" || status === "in_flight";
  if (wants && timer === null) timer = setInterval(reload, 3000);
  if (!wants && timer !== null) {
    clearInterval(timer);
    timer = null;
  }
}

watch(() => claim.data.value?.registration.status, polling, { immediate: true });
onBeforeUnmount(() => polling(undefined));

onMounted(async () => {
  meta.value = await api.meta().catch(() => null);
  await reload();
});
</script>

<template>
  <main class="page">
    <RouterLink class="crumb" :to="{ name: 'claims' }">← All claims</RouterLink>

    <p v-if="claim.loading.value && !claim.data.value" class="empty">Loading claim…</p>
    <div v-else-if="claim.error.value && !claim.data.value" class="panel">
      <div class="empty" role="alert">
        <strong>Could not load this claim.</strong>
        {{ claim.error.value }}
        <div class="actions center"><button @click="reload">Try again</button></div>
      </div>
    </div>

    <template v-else-if="claim.data.value">
      <div class="page-head">
        <div>
          <div class="detail-head">
            <h1>{{ claim.data.value.reference }}</h1>
            <StateBadge
              :state="claim.data.value.state"
              :label="stateOption(claim.data.value.state)?.label"
              :tone="stateOption(claim.data.value.state)?.tone"
              large
            />
          </div>
          <p class="lede">
            {{ claim.data.value.payer || "No payer yet" }}
            · service {{ shortDate(claim.data.value.service_date) }}
            · billed {{ money(claim.data.value.billed_amount) }}
          </p>
        </div>
        <div class="actions">
          <button v-if="claim.data.value.can_edit && !editing" @click="editing = true">Edit draft</button>
        </div>
      </div>

      <p v-if="claim.error.value" class="notice" data-tone="warning" role="status">
        Could not refresh: {{ claim.error.value }}. Retrying.
      </p>

      <div class="detail-grid">
        <div class="stack">
          <ConflictBanner v-if="conflict" :conflict="conflict" @reload="afterConflict" />

          <DraftForm v-if="editing && claim.data.value.can_edit" :claim="claim.data.value" @saved="saved" @cancel="editing = false" />

          <AlertPanel :alerts="claim.data.value.alerts" :claim-id="claim.data.value.id" @updated="saved" />

          <ActionPanel
            :actions="claim.data.value.available_actions"
            :disabled="conflict !== null"
            :choice-labels="meta?.denial_reasons"
            :errors="actionErrors"
            :busy="actionBusy"
            :active="active"
            @run="runAction"
            @open="(a) => { active = a; actionErrors = {}; }"
            @close="() => { active = null; actionErrors = {}; }"
          />

          <section class="panel">
            <div class="panel-head">
              <h2>History</h2>
              <span class="hint">{{ history.length }} {{ history.length === 1 ? "event" : "events" }}, oldest first</span>
            </div>
            <div class="panel-body tight">
              <HistoryTable :events="history" />
            </div>
          </section>
        </div>

        <aside class="stack">
          <section class="panel">
            <div class="panel-head"><h2>Details</h2></div>
            <div class="panel-body">
              <dl class="kv">
                <dt>Payer</dt><dd>{{ claim.data.value.payer || "—" }}</dd>
                <dt>Service date</dt><dd>{{ shortDate(claim.data.value.service_date) }}</dd>
                <dt>Billed</dt><dd class="num">{{ money(claim.data.value.billed_amount) }}</dd>
                <dt>Approved</dt><dd class="num">{{ money(claim.data.value.approved_amount) }}</dd>
                <template v-if="claim.data.value.denial_reason">
                  <dt>Denial reason</dt><dd>{{ denialLabel(claim.data.value.denial_reason) }}</dd>
                </template>
                <dt>Created by</dt><dd>{{ claim.data.value.created_by }}</dd>
                <dt>Created</dt><dd>{{ when(claim.data.value.created_at) }}</dd>
                <dt>Updated</dt><dd>{{ when(claim.data.value.updated_at) }}</dd>
                <dt>Version</dt><dd class="num">{{ claim.data.value.version }}</dd>
              </dl>
            </div>
          </section>

          <section class="panel">
            <div class="panel-head">
              <h2>Clearinghouse</h2>
              <RegistrationBadge :registration="claim.data.value.registration" :labels="meta?.registration_statuses" />
            </div>
            <div class="panel-body">
              <dl class="kv">
                <template v-if="claim.data.value.registration.submission_id">
                  <dt>Submission</dt><dd class="num">{{ claim.data.value.registration.submission_id }}</dd>
                </template>
                <template v-if="claim.data.value.registration.attempts">
                  <dt>Attempts</dt><dd class="num">{{ claim.data.value.registration.attempts }}</dd>
                </template>
                <template v-if="claim.data.value.registration.next_attempt_at">
                  <dt>Next try</dt><dd>{{ when(claim.data.value.registration.next_attempt_at) }}</dd>
                </template>
                <template v-if="claim.data.value.registration.last_error">
                  <dt>Last error</dt><dd class="error">{{ claim.data.value.registration.last_error }}</dd>
                </template>
              </dl>
              <p v-if="!claim.data.value.registration.submission_id && !claim.data.value.registration.attempts && !claim.data.value.registration.last_error" class="hint">
                Registered with the clearinghouse once the claim is submitted.
              </p>
              <div v-if="claim.data.value.registration.can_retry" class="actions retry">
                <button :disabled="retryBusy" @click="retry">Retry registration</button>
                <span v-if="retryError" class="error small">{{ retryError }}</span>
              </div>
            </div>
          </section>
        </aside>
      </div>
    </template>
  </main>
</template>

<style scoped>
.center { justify-content: center; margin-top: 0.75rem; }
.retry { margin-top: 0.9rem; }
.notice { margin-bottom: 1rem; }
</style>
