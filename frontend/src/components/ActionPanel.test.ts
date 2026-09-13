import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import ActionPanel from "./ActionPanel.vue";

describe("ActionPanel", () => {
  it("renders a blocked action's button disabled with the reason visible", () => {
    const w = mount(ActionPanel, {
      props: {
        actions: [{ action: "submit", label: "Submit", fields: [], blocked_reason: "Payer is required." }],
        disabled: false,
        errors: {},
        busy: false,
        active: null,
      },
    });
    const button = w.find("button");
    expect(button.attributes("disabled")).toBeDefined();
    expect(w.text()).toContain("Payer is required.");
  });

  it("shows a fieldless action's error even with no form open", () => {
    const w = mount(ActionPanel, {
      props: {
        actions: [{ action: "submit", label: "Submit", fields: [], blocked_reason: null }],
        disabled: false,
        errors: { detail: "Cannot submit a claim in state X." },
        busy: false,
        active: null,
      },
    });
    expect(w.text()).toContain("Cannot submit a claim in state X.");
  });

  it("leaves the message to the open form instead of showing it twice", () => {
    const w = mount(ActionPanel, {
      props: {
        actions: [
          {
            action: "deny",
            label: "Deny",
            fields: [{ name: "denial_reason", type: "choice" as const, choices: ["duplicate"] }],
            blocked_reason: null,
          },
        ],
        disabled: false,
        errors: { detail: "Pick a reason." },
        busy: false,
        active: "deny",
      },
    });
    const alerts = w.findAll("[role=alert]");
    expect(alerts).toHaveLength(1);
    expect(alerts[0].element.closest("form")).not.toBeNull();
  });
});
