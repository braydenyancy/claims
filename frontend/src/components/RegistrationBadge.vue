<script setup lang="ts">
import type { Option, Registration } from "../api/types";
import { humanize, when } from "../lib/format";

const props = defineProps<{ registration: Registration; labels?: Option[] }>();

function label() {
  return props.labels?.find((o) => o.value === props.registration.status)?.label ?? humanize(props.registration.status);
}
</script>

<template>
  <span class="badge" :data-registration="registration.status">registration: {{ label() }}</span>
  <span v-if="registration.submission_id" class="muted"> · {{ registration.submission_id }}</span>
  <span v-if="registration.attempts" class="muted"> · attempts {{ registration.attempts }}</span>
  <span v-if="registration.next_attempt_at" class="muted"> · next try {{ when(registration.next_attempt_at) }}</span>
  <span v-if="registration.last_error" class="error"> · {{ registration.last_error }}</span>
</template>
