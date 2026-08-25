import assert from "node:assert/strict";
import test from "node:test";
import { openClawSessionKey } from "./session-key.js";

test("openClawSessionKey normalizes scenario and session identifiers", () => {
  assert.equal(
    openClawSessionKey("G0", "Session-0"),
    "agent:main:openresponses:t15-g0-session-0",
  );
});
