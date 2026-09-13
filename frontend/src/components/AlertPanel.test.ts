import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";
import type { Alert } from "../api/types";
import AlertPanel from "./AlertPanel.vue";

function router() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/", component: { template: "<div/>" } },
      { path: "/login", name: "login", component: { template: "<div/>" } },
    ],
  });
}

const alert: Alert = {
  event_id: 11,
  action: "registration_failed",
  created_at: "2026-09-13T10:00:00Z",
  data: { reason: "down" },
  acknowledgement: null,
  can_acknowledge: false,
};

function panel(a: Alert) {
  return mount(AlertPanel, {
    props: { alerts: [a], claimId: 1 },
    global: { plugins: [router()] },
  });
}

describe("AlertPanel", () => {
  it("shows the form only when the server says the caller may acknowledge", () => {
    const closed = panel(alert);
    expect(closed.text()).toContain("Open. Awaiting acknowledgement.");
    expect(closed.find("form").exists()).toBe(false);

    const open = panel({ ...alert, can_acknowledge: true });
    expect(open.find("form").exists()).toBe(true);
    expect(open.text()).not.toContain("Awaiting acknowledgement.");
  });

  it("renders the acknowledgement the detail payload carries", () => {
    const w = panel({
      ...alert,
      acknowledgement: { actor: "rob", note: "Called the clearinghouse.", created_at: "2026-09-13T11:00:00Z" },
    });
    expect(w.text()).toContain("Acknowledged by rob");
    expect(w.text()).toContain("Called the clearinghouse.");
    expect(w.find("form").exists()).toBe(false);
  });
});
