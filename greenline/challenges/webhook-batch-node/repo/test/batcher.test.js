"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { TenantBatcher } = require("../src/batcher");

class Sender {
  constructor() {
    this.calls = [];
    this.failTenant = null;
  }

  send(tenantId, events) {
    if (this.failTenant === tenantId) throw new Error("delivery unavailable");
    this.calls.push({ tenantId, ids: events.map((event) => event.id) });
  }
}

const event = (tenantId, id) => ({ tenantId, id, payload: `payload-${id}` });

test("rejects an invalid maximum batch size", () => {
  assert.throws(() => new TenantBatcher(new Sender(), 0), /positive integer/);
});

test("flushes at the exact batch-size boundary", () => {
  const sender = new Sender();
  const batcher = new TenantBatcher(sender, 3);

  batcher.enqueue(event("acme", "1"));
  batcher.enqueue(event("acme", "2"));
  assert.equal(batcher.enqueue(event("acme", "3")), 3);

  assert.deepEqual(sender.calls, [{ tenantId: "acme", ids: ["1", "2", "3"] }]);
  assert.equal(batcher.pending("acme"), 0);
});

test("never mixes tenant events in a delivery", () => {
  const sender = new Sender();
  const batcher = new TenantBatcher(sender, 2);

  batcher.enqueue(event("acme", "a1"));
  batcher.enqueue(event("globex", "g1"));
  batcher.enqueue(event("acme", "a2"));
  batcher.enqueue(event("globex", "g2"));

  assert.deepEqual(sender.calls, [
    { tenantId: "acme", ids: ["a1", "a2"] },
    { tenantId: "globex", ids: ["g1", "g2"] },
  ]);
});

test("failed delivery remains queued in FIFO order for retry", () => {
  const sender = new Sender();
  const batcher = new TenantBatcher(sender, 2);
  sender.failTenant = "acme";

  batcher.enqueue(event("acme", "1"));
  assert.throws(() => batcher.enqueue(event("acme", "2")), /unavailable/);
  assert.equal(batcher.pending("acme"), 2);

  sender.failTenant = null;
  assert.equal(batcher.flush("acme"), 2);
  assert.deepEqual(sender.calls, [{ tenantId: "acme", ids: ["1", "2"] }]);
});

test("one tenant failure does not block another tenant", () => {
  const sender = new Sender();
  const batcher = new TenantBatcher(sender, 2);
  sender.failTenant = "acme";
  batcher.enqueue(event("acme", "a1"));
  assert.throws(() => batcher.enqueue(event("acme", "a2")));

  batcher.enqueue(event("globex", "g1"));
  batcher.enqueue(event("globex", "g2"));

  assert.deepEqual(sender.calls, [{ tenantId: "globex", ids: ["g1", "g2"] }]);
  assert.equal(batcher.pending("acme"), 2);
});

test("manual flush sends at most one configured batch", () => {
  const sender = new Sender();
  const batcher = new TenantBatcher(sender, 3);
  batcher.enqueue(event("acme", "1"));
  batcher.enqueue(event("acme", "2"));

  assert.equal(batcher.flush("acme"), 2);
  assert.equal(batcher.flush("acme"), 0);
});

for (const batchSize of [1, 2, 4, 5]) {
  test(`automatically flushes exactly at boundary ${batchSize}`, () => {
    const sender = new Sender();
    const batcher = new TenantBatcher(sender, batchSize);

    let flushed = 0;
    for (let number = 1; number <= batchSize; number += 1) {
      flushed = batcher.enqueue(event("acme", String(number)));
    }

    assert.equal(flushed, batchSize);
    assert.equal(batcher.pending("acme"), 0);
    assert.deepEqual(sender.calls[0].ids, Array.from(
      { length: batchSize },
      (_, index) => String(index + 1),
    ));
  });
}

for (const [firstTenant, secondTenant, suffix] of [
  ["acme", "globex", "alpha"],
  ["north", "south", "beta"],
  ["red", "blue", "gamma"],
]) {
  test(`keeps ${suffix} tenant interleaving isolated`, () => {
    const sender = new Sender();
    const batcher = new TenantBatcher(sender, 2);

    batcher.enqueue(event(firstTenant, `${suffix}-1`));
    batcher.enqueue(event(secondTenant, `${suffix}-2`));
    batcher.enqueue(event(firstTenant, `${suffix}-3`));

    assert.deepEqual(sender.calls, [{
      tenantId: firstTenant,
      ids: [`${suffix}-1`, `${suffix}-3`],
    }]);
    assert.equal(batcher.pending(secondTenant), 1);
  });
}

for (const queuedCount of [1, 3]) {
  test(`retains ${queuedCount} queued event(s) after a manual delivery failure`, () => {
    const sender = new Sender();
    const batcher = new TenantBatcher(sender, queuedCount + 1);
    for (let number = 1; number <= queuedCount; number += 1) {
      batcher.enqueue(event("acme", String(number)));
    }
    sender.failTenant = "acme";

    assert.throws(() => batcher.flush("acme"), /unavailable/);
    assert.equal(batcher.pending("acme"), queuedCount);
  });
}
