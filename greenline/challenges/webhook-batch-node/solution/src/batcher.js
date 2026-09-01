"use strict";

class TenantBatcher {
  constructor(sender, maxBatchSize = 3) {
    if (!Number.isInteger(maxBatchSize) || maxBatchSize < 1) {
      throw new RangeError("maxBatchSize must be a positive integer");
    }
    this.sender = sender;
    this.maxBatchSize = maxBatchSize;
    this.queues = new Map();
  }

  enqueue(event) {
    const queue = this.queues.get(event.tenantId) || [];
    queue.push(event);
    this.queues.set(event.tenantId, queue);
    if (queue.length >= this.maxBatchSize) {
      return this.flush(event.tenantId);
    }
    return 0;
  }

  flush(tenantId) {
    const queue = this.queues.get(tenantId) || [];
    const batch = queue.slice(0, this.maxBatchSize);
    if (batch.length === 0) return 0;

    this.sender.send(tenantId, batch);
    queue.splice(0, batch.length);
    if (queue.length === 0) this.queues.delete(tenantId);
    return batch.length;
  }

  pending(tenantId) {
    return (this.queues.get(tenantId) || []).length;
  }
}

module.exports = { TenantBatcher };
