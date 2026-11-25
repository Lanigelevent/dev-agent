import { test } from "node:test";
import assert from "node:assert/strict";
import { clamp } from "./calc.ts";

test("clamp below", () => {
  assert.equal(clamp(-5, 0, 10), 0);
});

test("clamp above", () => {
  assert.equal(clamp(15, 0, 10), 10);
});

test("clamp inside", () => {
  assert.equal(clamp(5, 0, 10), 5);
});
