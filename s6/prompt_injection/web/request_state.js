/* Request ownership only: no DOM, detector, task inference or authorization policy. */
(function (root) {
  "use strict";
  class RequestState {
    constructor() {
      this.revision = 0;
      this.sequences = new Map();
    }

    invalidate() {
      this.revision += 1;
    }

    begin(channel) {
      const sequence = (this.sequences.get(channel) || 0) + 1;
      this.sequences.set(channel, sequence);
      return Object.freeze({channel, sequence, revision: this.revision});
    }

    latest(ticket) {
      return this.sequences.get(ticket.channel) === ticket.sequence;
    }

    current(ticket) {
      return this.latest(ticket) && ticket.revision === this.revision;
    }
  }
  root.S6RequestState = RequestState;
  if (typeof module !== "undefined" && module.exports) module.exports = RequestState;
})(globalThis);
