import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import ConflictBanner from "./ConflictBanner.vue";

describe("ConflictBanner", () => {
  it("renders the 'It is now' line without a last event, with the humanized state", () => {
    const w = mount(ConflictBanner, {
      props: {
        conflict: {
          detail: "Conflict.",
          current_state: "STATE_A",
          current_version: 4,
          last_event: null,
        },
      },
    });
    expect(w.text()).toContain("It is now state a.");
  });

  it("names the actor, the action, and how long ago it happened", () => {
    const w = mount(ConflictBanner, {
      props: {
        conflict: {
          detail: "Conflict.",
          current_state: "STATE_A",
          current_version: 4,
          last_event: {
            id: 7,
            action: "start_review",
            from_state: "STATE_B",
            to_state: "STATE_A",
            actor: "rob",
            data: {},
            severity: "info" as const,
            created_at: new Date(Date.now() - 1000).toISOString(),
          },
        },
      },
    });
    expect(w.text()).toContain("Changed by rob (start review) 1 second ago.");
  });

  it("says the system changed it when no actor is named", () => {
    const w = mount(ConflictBanner, {
      props: {
        conflict: {
          detail: "Conflict.",
          current_state: "STATE_A",
          current_version: 4,
          last_event: {
            id: 8,
            action: "registration_failed",
            from_state: "STATE_A",
            to_state: "STATE_A",
            actor: null,
            data: {},
            severity: "alert" as const,
            created_at: new Date(Date.now() - 120_000).toISOString(),
          },
        },
      },
    });
    expect(w.text()).toContain("Changed by the system (registration failed) 2 minutes ago.");
  });
});
