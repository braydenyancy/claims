import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, ConflictError, ValidationError, request } from "./client";

function respond(status: number, body: unknown) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  });
}

describe("request", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("returns the body on success", async () => {
    vi.stubGlobal("fetch", respond(200, { id: 1 }));
    await expect(request("GET", "/api/x/")).resolves.toEqual({ id: 1 });
  });

  it("maps 409 to ConflictError carrying the conflict body", async () => {
    const body = { detail: "changed", current_state: "STATE_A", current_version: 3, last_event: null };
    vi.stubGlobal("fetch", respond(409, body));
    const err = await request("POST", "/api/x/", {}).catch((e) => e);
    expect(err).toBeInstanceOf(ConflictError);
    expect(err.conflict).toEqual(body);
  });

  it("maps a unified 400 to ValidationError with field errors", async () => {
    vi.stubGlobal("fetch", respond(400, { detail: "no", errors: { note: "A note is required." } }));
    const err = await request("POST", "/api/x/", {}).catch((e) => e);
    expect(err).toBeInstanceOf(ValidationError);
    expect(err.errors).toEqual({ note: "A note is required." });
  });

  it("flattens a DRF-shaped 400 into the same field errors", async () => {
    vi.stubGlobal("fetch", respond(400, { billed_amount: ["A valid number is required."], payer: ["Too long.", "Really."] }));
    const err = await request("POST", "/api/x/", {}).catch((e) => e);
    expect(err).toBeInstanceOf(ValidationError);
    expect(err.errors).toEqual({ billed_amount: "A valid number is required.", payer: "Too long. Really." });
  });

  it("maps other failures to ApiError with the status", async () => {
    vi.stubGlobal("fetch", respond(403, { detail: "Forbidden" }));
    const err = await request("GET", "/api/x/").catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(403);
    expect(err.message).toBe("Forbidden");
  });

  it("sends the CSRF header on non-GET from the cookie", async () => {
    document.cookie = "csrftoken=abc123";
    const fetchMock = respond(204, null);
    vi.stubGlobal("fetch", fetchMock);
    await request("POST", "/api/x/");
    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers["X-CSRFToken"]).toBe("abc123");
    expect(init.credentials).toBe("same-origin");
  });
});
