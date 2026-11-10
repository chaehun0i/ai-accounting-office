/** Reject responses from a previous scope or an older request in the same lane. */
export class RequestScope {
  private epoch = 0;
  private lanes = new Map<string, number>();

  invalidate() { this.epoch += 1; this.lanes.clear(); }

  start(lane: string): () => boolean {
    const epoch = this.epoch;
    const sequence = (this.lanes.get(lane) ?? 0) + 1;
    this.lanes.set(lane, sequence);
    return () => epoch === this.epoch && this.lanes.get(lane) === sequence;
  }
}
