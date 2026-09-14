import { describe, expect, it } from "vitest";
import { sentence, shortDate } from "./format";

describe("shortDate", () => {
  it("shows a date-only value on its own day in every time zone", () => {
    expect(shortDate("2026-08-01")).toBe("Aug 1, 2026");
  });
  it("shows a dash for nothing", () => {
    expect(shortDate(null)).toBe("—");
  });
});

describe("sentence", () => {
  it("humanizes and capitalizes", () => {
    expect(sentence("denial_reason")).toBe("Denial reason");
  });
});
