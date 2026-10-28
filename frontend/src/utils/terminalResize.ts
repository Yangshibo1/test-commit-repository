export interface TerminalSize { rows: number; cols: number }
const equal = (a: TerminalSize | null, b: TerminalSize) => a?.rows === b.rows && a?.cols === b.cols;

/** Commit only a stable grid and never repeat a PTY resize for the same size. */
export class StableTerminalResize {
  private candidate: TerminalSize | null = null;
  private candidateAt = 0;
  private sent: TerminalSize | null = null;
  private delayMs: number;
  constructor(delayMs = 120) { this.delayMs=delayMs; }
  get pending() { return this.candidate !== null; }
  reset() { this.candidate=null; this.sent=null; }
  offer(size: TerminalSize, now: number): TerminalSize | null {
    if (!Number.isFinite(size.rows) || !Number.isFinite(size.cols) || size.rows<2 || size.cols<10) return null;
    if (equal(this.sent,size)) { this.candidate=null; return null; }
    if (!equal(this.candidate,size)) { this.candidate={...size}; this.candidateAt=now; return null; }
    if (now-this.candidateAt<this.delayMs) return null;
    this.sent={...size}; this.candidate=null;
    return {...size};
  }
}
