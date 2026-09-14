import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import ActionForm from "./ActionForm.vue";

const base = { action: "x", label: "X", blocked_reason: null };

describe("ActionForm", () => {
  it("renders a textarea for a text field and submits its value", async () => {
    const w = mount(ActionForm, {
      props: { action: { ...base, fields: [{ name: "note", type: "text", choices: [] }] }, errors: {}, busy: false },
    });
    await w.find("textarea").setValue("Please attach the report.");
    await w.find("form").trigger("submit");
    expect(w.emitted("submit")?.[0]).toEqual([{ note: "Please attach the report." }]);
  });

  it("renders a select with the declared choices and their labels", () => {
    const w = mount(ActionForm, {
      props: {
        action: { ...base, fields: [{ name: "denial_reason", type: "choice", choices: ["duplicate", "not_covered"] }] },
        choiceLabels: [{ value: "duplicate", label: "Duplicate claim" }],
        errors: {},
        busy: false,
      },
    });
    const options = w.findAll("option").map((o) => [o.attributes("value"), o.text()]);
    expect(options).toEqual([
      ["", "Choose…"],
      ["duplicate", "Duplicate claim"],
      ["not_covered", "not covered"],
    ]);
  });

  it("renders a decimal input and shows the field error it is given", () => {
    const w = mount(ActionForm, {
      props: {
        action: { ...base, fields: [{ name: "approved_amount", type: "decimal", choices: [] }] },
        errors: { approved_amount: "Approved amount cannot exceed the billed amount." },
        busy: false,
      },
    });
    expect(w.find("input[inputmode=decimal]").exists()).toBe(true);
    expect(w.text()).toContain("cannot exceed");
  });
});
