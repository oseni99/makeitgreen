"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { EmptyQueue, NotificationQueue } = require("../src/queue");

const item = (id, options = {}) => ({ id, ...options });

test("plain notifications preserve FIFO behavior", () => {
  const queue = new NotificationQueue();
  queue.enqueue(item("first"));
  queue.enqueue(item("second"));

  assert.equal(queue.take(0).id, "first");
  assert.equal(queue.take(0).id, "second");
});

test("a notification is eligible at the exact delivery time", () => {
  const queue = new NotificationQueue();
  queue.enqueue(item("scheduled", { deliverAt: 50 }));

  assert.equal(queue.take(50).id, "scheduled");
});

test("future urgent work never blocks ready normal work", () => {
  const queue = new NotificationQueue();
  queue.enqueue(item("future", { deliverAt: 100, urgency: 10 }));
  queue.enqueue(item("ready", { deliverAt: 10, urgency: 1 }));

  assert.equal(queue.take(10).id, "ready");
  assert.equal(queue.size(), 1);
});

test("only-future work is pending but not dispatchable", () => {
  const queue = new NotificationQueue();
  queue.enqueue(item("later", { deliverAt: 100 }));

  assert.throws(() => queue.take(99), EmptyQueue);
  assert.equal(queue.size(), 1);
});

test("highest urgency wins among eligible notifications", () => {
  const queue = new NotificationQueue();
  queue.enqueue(item("normal", { urgency: 1 }));
  queue.enqueue(item("urgent", { urgency: 4 }));
  queue.enqueue(item("medium", { urgency: 2 }));

  assert.deepEqual(
    [queue.take(0).id, queue.take(0).id, queue.take(0).id],
    ["urgent", "medium", "normal"],
  );
});

test("equal urgency remains stable by insertion order", () => {
  const queue = new NotificationQueue();
  queue.enqueue(item("one", { urgency: 3 }));
  queue.enqueue(item("two", { urgency: 3 }));
  queue.enqueue(item("three", { urgency: 3 }));

  assert.deepEqual(
    [queue.take(0).id, queue.take(0).id, queue.take(0).id],
    ["one", "two", "three"],
  );
});
