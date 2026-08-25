import assert from "node:assert/strict";
import test from "node:test";
import { diagnosticOutput, isExpectedProbeFailure } from "./child-process.js";

test("diagnosticOutput exposes captured stderr before stdout", () => {
  assert.equal(diagnosticOutput("gateway-out", "gateway-error"), "gateway-error\ngateway-out");
});

test("diagnosticOutput makes an empty capture explicit", () => {
  assert.equal(diagnosticOutput("", ""), "<no output>");
});

test("HTTP readiness polling ignores only connection and timeout failures", () => {
  assert.equal(isExpectedProbeFailure(new TypeError("connection refused")), true);
  assert.equal(isExpectedProbeFailure(new DOMException("deadline", "TimeoutError")), true);
  assert.equal(isExpectedProbeFailure(new Error("invalid response handling")), false);
});
