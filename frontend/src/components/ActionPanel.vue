<script setup lang="ts">
import type { AvailableAction, Option } from "../api/types";
import ActionForm from "./ActionForm.vue";

// Buttons come from the API's list and nothing else. A blocked action is
// shown disabled with its reason (spec: never hidden).
const props = defineProps<{
  actions: AvailableAction[];
  disabled: boolean;
  choiceLabels?: Option[];
  errors: Record<string, string>;
  busy: boolean;
  active: string | null;
}>();
const emit = defineEmits<{ run: [action: string, data: Record<string, string>]; open: [action: string]; close: [] }>();

function click(a: AvailableAction) {
  if (a.fields.length === 0) emit("run", a.action, {});
  else emit("open", a.action);
}

function activeAction() {
  return props.actions.find((a) => a.action === props.active) ?? null;
}
</script>

<template>
  <section>
    <h2>Actions</h2>
    <p v-if="!activeAction() && (errors.detail || Object.keys(errors).length)" class="error" role="alert">
      {{ errors.detail || Object.values(errors).join(" ") }}
    </p>
    <p v-if="actions.length === 0" class="muted">No actions available to you right now.</p>
    <div v-else class="actions">
      <span v-for="a in actions" :key="a.action">
        <button :disabled="disabled || busy || a.blocked_reason !== null" :title="a.blocked_reason ?? ''" @click="click(a)">
          {{ a.label }}
        </button>
        <span v-if="a.blocked_reason" class="hint"> {{ a.blocked_reason }}</span>
      </span>
    </div>
    <ActionForm
      v-if="activeAction()"
      :key="active ?? ''"
      :action="activeAction()!"
      :choice-labels="choiceLabels"
      :errors="errors"
      :busy="busy || disabled"
      @submit="(data) => emit('run', active!, data)"
      @cancel="emit('close')"
    />
  </section>
</template>
