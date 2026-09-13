import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import ConflictBanner from "./ConflictBanner.vue";

describe("ConflictBanner", () => {
  it("renders the 'It is now' line without a last event, with the humanized state", () => {
    const w = mount(ConflictBanner, {
      props: {
        conflict: {
          detail: "Conflict.",
          current_state: "UNDER_REVIEW",
          current_version: 4,
          last_event: null,
        },
      },
    });
    expect(w.text()).toContain("It is now under review.");
  });
});
