<script setup lang="ts">
import { reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { api, ValidationError } from "../api/client";
import type { ClaimDetail } from "../api/types";
import { isSignedOut } from "../composables/useAsync";
import { useSession } from "../composables/useSession";

const props = defineProps<{ claim?: ClaimDetail }>();
const emit = defineEmits<{ saved: [claim: ClaimDetail]; cancel: [] }>();

const session = useSession();
const router = useRouter();
const route = useRoute();

const form = reactive({
  payer: props.claim?.payer ?? "",
  service_date: props.claim?.service_date ?? "",
  billed_amount: props.claim?.billed_amount ?? "",
});
const errors = ref<Record<string, string>>({});
const failure = ref("");
const busy = ref(false);

async function submit() {
  errors.value = {};
  failure.value = "";
  busy.value = true;
  const body = {
    payer: form.payer,
    service_date: form.service_date || null,
    billed_amount: form.billed_amount,
  };
  try {
    const saved = props.claim ? await api.claims.patch(props.claim.id, body) : await api.claims.create(body);
    emit("saved", saved);
  } catch (e) {
    if (isSignedOut(e)) {
      session.clear();
      await router.push({ name: "login", query: { next: route.fullPath } });
    } else if (e instanceof ValidationError) errors.value = e.errors;
    else failure.value = e instanceof Error ? e.message : "Could not save.";
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <form class="panel" @submit.prevent="submit">
    <div class="panel-head">
      <h2>{{ claim ? "Edit draft" : "New draft" }}</h2>
      <span class="hint">Submitting later checks that every field is filled.</span>
    </div>
    <div class="panel-body">
      <div class="row">
        <label class="field">
          <span>Payer</span>
          <input v-model="form.payer" placeholder="Insurer or plan name" />
          <span v-if="errors.payer" class="field-error">{{ errors.payer }}</span>
        </label>
        <label class="field">
          <span>Service date</span>
          <input v-model="form.service_date" type="date" />
          <span v-if="errors.service_date" class="field-error">{{ errors.service_date }}</span>
        </label>
        <label class="field">
          <span>Billed amount</span>
          <input v-model="form.billed_amount" inputmode="decimal" placeholder="0.00" required />
          <span v-if="errors.billed_amount" class="field-error">{{ errors.billed_amount }}</span>
        </label>
      </div>
      <p v-if="failure" class="notice" data-tone="danger" role="alert">{{ failure }}</p>
      <div class="actions">
        <button class="primary" :disabled="busy">{{ claim ? "Save changes" : "Create draft" }}</button>
        <button type="button" class="ghost" :disabled="busy" @click="emit('cancel')">Cancel</button>
      </div>
    </div>
  </form>
</template>

<style scoped>
.row { display: grid; grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr)); gap: 0 1rem; }
.notice { margin-bottom: 0.75rem; }
</style>
