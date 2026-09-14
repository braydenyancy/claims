import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";
import { api, ApiError } from "../api/client";
import type { ClaimDetail, ClaimEvent } from "../api/types";
import ClaimDetailView from "./ClaimDetailView.vue";

function router() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/", component: { template: "<div/>" } },
      { path: "/claims", name: "claims", component: { template: "<div/>" } },
      { path: "/login", name: "login", component: { template: "<div/>" } },
    ],
  });
}

function detail(canReconcile: boolean): ClaimDetail {
  return {
    id: 1,
    reference: "CLM-1",
    payer: "Payer",
    service_date: "2026-09-01",
    billed_amount: "100.00",
    state: "SUBMITTED",
    version: 2,
    has_open_alert: true,
    created_by: "sam",
    created_at: "2026-09-01T10:00:00Z",
    updated_at: "2026-09-01T10:00:00Z",
    approved_amount: null,
    denial_reason: "",
    submission_id: "",
    available_actions: [],
    registration: { status: "uncertain", can_reconcile: canReconcile, last_error: "Submission outcome unknown." },
    can_edit: false,
    alerts: [],
  };
}

const event: ClaimEvent = {
  id: 10,
  action: "registration_reconciled",
  from_state: "SUBMITTED",
  to_state: "SUBMITTED",
  actor: "rita",
  data: {},
  severity: "info",
  created_at: "2026-09-01T11:00:00Z",
};

describe("uncertain registration", () => {
  afterEach(() => vi.restoreAllMocks());

  async function view(canReconcile: boolean) {
    vi.spyOn(api, "meta").mockResolvedValue({ states: [], denial_reasons: [], registration_statuses: [] });
    vi.spyOn(api.claims, "get").mockResolvedValue(detail(canReconcile));
    vi.spyOn(api.claims, "history").mockResolvedValue([]);
    const wrapper = mount(ClaimDetailView, { props: { id: 1 }, global: { plugins: [router()] } });
    await flushPromises();
    return wrapper;
  }

  it("offers a lookup only when the server permits it and updates the claim and history", async () => {
    const wrapper = await view(true);
    expect(wrapper.text()).toContain("Status uncertain");
    expect(wrapper.text()).toContain("no further submission is sent");

    const registered = { ...detail(false), registration: { status: "done", submission_id: "CH-10" } };
    const reconcile = vi.spyOn(api.claims, "reconcile").mockResolvedValue(registered);
    vi.mocked(api.claims.history).mockResolvedValue([event]);

    await wrapper.get("button").trigger("click");
    await flushPromises();

    expect(reconcile).toHaveBeenCalledWith(1);
    expect(wrapper.text()).toContain("CH-10");
    expect(wrapper.text()).toContain("Registration reconciled");
    expect(wrapper.text()).not.toContain("Check clearinghouse status");
    wrapper.unmount();
  });

  it("does not offer the lookup when the server denies it", async () => {
    const wrapper = await view(false);
    expect(wrapper.text()).toContain("A reviewer can check its status");
    expect(wrapper.find("button").exists()).toBe(false);
    wrapper.unmount();
  });

  it("keeps an uncertain claim visible when lookup fails", async () => {
    const wrapper = await view(true);
    vi.spyOn(api.claims, "reconcile").mockRejectedValue(new ApiError(503, { detail: "Clearinghouse unavailable" }));

    await wrapper.get("button").trigger("click");
    await flushPromises();

    expect(wrapper.text()).toContain("Status uncertain");
    expect(wrapper.get('[role="alert"]').text()).toContain("Clearinghouse unavailable");
    expect(wrapper.text()).toContain("Check clearinghouse status");
    wrapper.unmount();
  });
});
