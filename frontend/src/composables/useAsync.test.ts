import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import { defineComponent, h } from "vue";
import { createMemoryHistory, createRouter } from "vue-router";
import { useAsync } from "./useAsync";

// useAsync needs a router (it redirects a signed-out caller to /login), so
// the composable is exercised inside a component with one installed.
const Harness = defineComponent({
  setup() {
    return { state: useAsync<number>() };
  },
  render: () => h("div"),
});

function harness() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/", component: { template: "<div/>" } },
      { path: "/login", name: "login", component: { template: "<div/>" } },
    ],
  });
  return mount(Harness, { global: { plugins: [router] } }).vm.state;
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

describe("useAsync", () => {
  it("keeps a value written with set when an in-flight call resolves afterwards", async () => {
    const state = harness();
    const slow = deferred<number>();

    const running = state.run(() => slow.promise);
    state.set(2);
    slow.resolve(1);
    await running;

    expect(state.data.value).toBe(2);
  });

  it("lets the newest run win whichever order the responses arrive in", async () => {
    const state = harness();
    const a = deferred<number>();
    const b = deferred<number>();

    const first = state.run(() => a.promise);
    const second = state.run(() => b.promise);
    a.resolve(1);
    b.resolve(2);
    await Promise.all([first, second]);

    expect(state.data.value).toBe(2);
  });

  it("still lets the newest run win when it answers first", async () => {
    const state = harness();
    const a = deferred<number>();
    const b = deferred<number>();

    const first = state.run(() => a.promise);
    const second = state.run(() => b.promise);
    b.resolve(2);
    await second;
    a.resolve(1);
    await first;

    expect(state.data.value).toBe(2);
  });
});
