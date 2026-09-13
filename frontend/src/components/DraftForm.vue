<script setup lang="ts">
import { reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { api, ValidationError } from "../api/client";
import type { ClaimDetail } from "../api/types";
import { isSignedOut } from "../composables/useAsync";
import { useSession } from "../composables/useSession";

const props = defineProps<{ claim?: ClaimDetail }>();
const emit = defineEmits<{ saved: [claim: ClaimDetail] }>();

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
  <form class="card" @submit.prevent="submit">
    <h2>{{ claim ? "Edit draft" : "New draft" }}</h2>
    <label>
      Payer
      <input v-model="form.payer" />
      <span v-if="errors.payer" class="field-error">{{ errors.payer }}</span>
    </label>
    <label>
      Service date
      <input v-model="form.service_date" type="date" />
      <span v-if="errors.service_date" class="field-error">{{ errors.service_date }}</span>
    </label>
    <label>
      Billed amount
      <input v-model="form.billed_amount" inputmode="decimal" required />
      <span v-if="errors.billed_amount" class="field-error">{{ errors.billed_amount }}</span>
    </label>
    <p v-if="failure" class="error" role="alert">{{ failure }}</p>
    <button :disabled="busy">{{ claim ? "Save" : "Create draft" }}</button>
  </form>
</template>
