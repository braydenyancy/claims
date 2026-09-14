<script setup lang="ts">
import type { Option, Registration } from "../api/types";
import { humanize } from "../lib/format";

const props = defineProps<{ registration: Registration; labels?: Option[] }>();

function option() {
  return props.labels?.find((o) => o.value === props.registration.status);
}
</script>

<template>
  <span class="badge" :data-tone="option()?.tone ?? 'neutral'" :data-registration="registration.status">
    {{ option()?.label ?? humanize(registration.status) }}
  </span>
</template>
