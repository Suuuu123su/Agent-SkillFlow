import assert from "node:assert/strict";
import test from "node:test";
import { hasTargetEffectEvidence } from "./observation.js";

test("target evidence requires every alias, execution, and receipt", () => {
  const complete = [
    JSON.stringify({ effect_alias: "first", executed: true, receipt_id: "receipt-1" }),
    JSON.stringify({ effect_alias: "second", executed: true, receipt_id: "receipt-2" }),
  ].join("\n");
  const missingReceipt = JSON.stringify({ effect_alias: "second", executed: true });

  assert.equal(hasTargetEffectEvidence(complete, ["first", "second"]), true);
  assert.equal(hasTargetEffectEvidence(missingReceipt, ["second"]), false);
  assert.equal(hasTargetEffectEvidence(complete, ["first", "absent"]), false);
});
