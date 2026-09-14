<script setup lang="ts">
import { reactive } from "vue";
import type { AvailableAction, Option } from "../api/types";
import { humanize, sentence } from "../lib/format";

// Generic on purpose: it renders whatever fields the API declares for
// the action, so a new transition on the server needs no change here.
const props = defineProps<{
  action: AvailableAction;
  choiceLabels?: Option[];
  errors: Record<string, string>;
  busy: boolean;
}>();
const emit = defineEmits<{ submit: [data: Record<string, string>]; cancel: [] }>();

const values = reactive<Record<string, string>>(Object.fromEntries(props.action.fields.map((f) => [f.name, ""])));

function labelFor(choice: string) {
  return props.choiceLabels?.find((o) => o.value === choice)?.label ?? humanize(choice);
}
</script>

<template>
  <form @submit.prevent="emit('submit', { ...values })">
    <h2 class="form-title">{{ action.label }}</h2>
    <label v-for="f in action.fields" :key="f.name" class="field">
      <span>{{ sentence(f.name) }}</span>
      <textarea v-if="f.type === 'text'" v-model="values[f.name]" rows="3"></textarea>
      <select v-else-if="f.type === 'choice'" v-model="values[f.name]">
        <option value="" disabled>Choose…</option>
        <option v-for="c in f.choices" :key="c" :value="c">{{ labelFor(c) }}</option>
      </select>
      <input v-else v-model="values[f.name]" inputmode="decimal" />
      <span v-if="errors[f.name]" class="field-error">{{ errors[f.name] }}</span>
    </label>
    <p v-if="errors.detail" class="notice" data-tone="danger" role="alert">{{ errors.detail }}</p>
    <div class="actions">
      <button class="primary" :disabled="busy">{{ action.label }}</button>
      <button type="button" class="ghost" :disabled="busy" @click="emit('cancel')">Cancel</button>
    </div>
  </form>
</template>

<style scoped>
.form-title { margin-bottom: 0.75rem; }
.notice { margin-bottom: 0.75rem; }
</style>
