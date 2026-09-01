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
    let selected = -1;
    for (let index = 0; index < this.items.length; index += 1) {
      const candidate = this.items[index];
      if (candidate.deliverAt > now) continue;
      if (selected < 0) {
        selected = index;
        continue;
      }
      const current = this.items[selected];
      if (
        candidate.urgency > current.urgency ||
        (candidate.urgency === current.urgency && candidate.sequence < current.sequence)
      ) {
        selected = index;
      }
    }
    if (selected < 0) throw new EmptyQueue("nothing ready");
    return this.items.splice(selected, 1)[0];
  }

  size() {
    return this.items.length;
  }
}

module.exports = { EmptyQueue, NotificationQueue };
