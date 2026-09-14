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

function blocked() {
  return props.actions.filter((a) => a.blocked_reason);
}
</script>

<template>
  <section class="panel">
    <div class="panel-head">
      <h2>Actions</h2>
      <span v-if="actions.length" class="hint">{{ actions.length - blocked().length }} of {{ actions.length }} available</span>
    </div>
    <div class="panel-body">
      <p v-if="!activeAction() && (errors.detail || Object.keys(errors).length)" class="notice" data-tone="danger" role="alert">
        {{ errors.detail || Object.values(errors).join(" ") }}
      </p>
      <p v-if="actions.length === 0" class="muted">No actions available to you right now.</p>
      <template v-else>
        <div class="actions">
          <button
            v-for="a in actions"
            :key="a.action"
            :class="{ primary: !a.blocked_reason && a === actions.find((x) => !x.blocked_reason) }"
            :disabled="disabled || busy || a.blocked_reason !== null"
            :title="a.blocked_reason ?? ''"
            @click="click(a)"
          >
            {{ a.label }}
          </button>
        </div>
        <ul v-if="blocked().length" class="blocked">
          <li v-for="a in blocked()" :key="a.action" class="hint">
            <strong>{{ a.label }}</strong> {{ a.blocked_reason }}
          </li>
        </ul>
      </template>
    </div>
    <div v-if="activeAction()" class="panel-body">
      <ActionForm
        :key="active ?? ''"
        :action="activeAction()!"
        :choice-labels="choiceLabels"
        :errors="errors"
        :busy="busy || disabled"
        @submit="(data) => emit('run', active!, data)"
        @cancel="emit('close')"
      />
    </div>
  </section>
</template>

<style scoped>
.blocked { margin: 0.75rem 0 0; padding: 0; list-style: none; }
.blocked li + li { margin-top: 0.25rem; }
.blocked strong { font-weight: 500; color: var(--ink-2); }
.notice { margin-bottom: 0.75rem; }
</style>
