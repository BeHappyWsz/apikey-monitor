import assert from "node:assert/strict";
import test from "node:test";

import { withBusyButton } from "../static/js/utils.js";

function fakeButton() {
  const attributes = new Map();
  return {
    disabled: false,
    getAttribute(name) { return attributes.get(name) ?? null; },
    setAttribute(name, value) { attributes.set(name, value); },
    removeAttribute(name) { attributes.delete(name); },
  };
}

test("busy button rejects duplicate actions and always restores itself", async () => {
  const button = fakeButton();
  let resolveAction;
  const first = withBusyButton(button, () => new Promise((resolve) => { resolveAction = resolve; }));

  assert.equal(button.disabled, true);
  assert.equal(button.getAttribute("aria-busy"), "true");
  assert.equal(await withBusyButton(button, () => assert.fail("duplicate action ran")), undefined);

  resolveAction("done");
  assert.equal(await first, "done");
  assert.equal(button.disabled, false);
  assert.equal(button.getAttribute("aria-busy"), null);

  await assert.rejects(withBusyButton(button, async () => { throw new Error("request failed"); }), /request failed/);
  assert.equal(button.disabled, false);
  assert.equal(button.getAttribute("aria-busy"), null);
});
