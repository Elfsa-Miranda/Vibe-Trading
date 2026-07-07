import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

async function loadApiModule() {
  vi.resetModules();
  return import("../api");
}

describe("Alpha Foundry API client", () => {
  beforeEach(() => {
    vi.stubGlobal("localStorage", {
      getItem: vi.fn(() => ""),
      setItem: vi.fn(),
      removeItem: vi.fn(),
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it("uses GET-only read endpoints", async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(
      new Response(JSON.stringify({ status: "ok" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    ));
    vi.stubGlobal("fetch", fetchMock);
    const { api } = await loadApiModule();

    await api.getAlphaFoundryReport("aaf-report");
    await api.getAlphaFoundryFactor("limit_queue_pressure_proxy");
    await api.getAlphaFoundryForwardPlan("plan-limit-queue-pressure");
    await api.getAlphaFoundryTrials("limit_liquidity");

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/research/alpha-foundry/reports/aaf-report",
      expect.objectContaining({ headers: expect.any(Object) }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/research/alpha-foundry/factors/limit_queue_pressure_proxy",
      expect.objectContaining({ headers: expect.any(Object) }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "/research/alpha-foundry/forward/plan-limit-queue-pressure",
      expect.objectContaining({ headers: expect.any(Object) }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      "/research/alpha-foundry/trials/limit_liquidity",
      expect.objectContaining({ headers: expect.any(Object) }),
    );
    for (const call of fetchMock.mock.calls) {
      expect(call[1]?.method).toBeUndefined();
    }
  });
});
