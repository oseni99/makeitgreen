"use strict";

class TenantBatcher {
  constructor(sender, maxBatchSize = 3) {
    if (!Number.isInteger(maxBatchSize) || maxBatchSize < 1) {
      throw new RangeError("maxBatchSize must be a positive integer");
    }
    this.sender = sender;
    this.maxBatchSize = maxBatchSize;
    this.queue = [];
  }

  enqueue(event) {
    this.queue.push(event);
    if (this.queue.length > this.maxBatchSize) {
      return this.flush(event.tenantId);
    }
    return 0;
  }

  flush(tenantId) {
    const batch = this.queue.splice(0, this.maxBatchSize);
    if (batch.length === 0) return 0;
    this.sender.send(tenantId, batch);
    return batch.length;
  }

  pending(tenantId) {
    return this.queue.filter((event) => event.tenantId === tenantId).length;
  }
}

module.exports = { TenantBatcher };
