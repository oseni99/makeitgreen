"use strict";

class EmptyQueue extends Error {}

class NotificationQueue {
  constructor() {
    this.items = [];
    this.sequence = 0;
  }

  enqueue(notification) {
    this.items.push({
      ...notification,
      deliverAt: notification.deliverAt ?? 0,
      urgency: notification.urgency ?? 0,
      sequence: this.sequence++,
    });
  }

  take(now) {
    if (this.items.length === 0) throw new EmptyQueue("nothing ready");

    // BUG: ranking the whole queue allows future urgent work to block ready work.
    this.items.sort((left, right) =>
      right.urgency - left.urgency || left.sequence - right.sequence,
    );
    return this.items.shift();
  }

  size() {
    return this.items.length;
  }
}

module.exports = { EmptyQueue, NotificationQueue };
