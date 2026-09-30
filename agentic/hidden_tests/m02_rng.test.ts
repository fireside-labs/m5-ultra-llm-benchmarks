import { describe, it, expect } from 'vitest';
import { createRng } from '../src/rng';

describe('m02 rng', () => {
  it('is deterministic for the same seed', () => {
    for (const seed of [0, 1, 42, 123456789, 2 ** 31 - 1]) {
      const a = createRng(seed), b = createRng(seed);
      for (let i = 0; i < 1000; i++) expect(a.next()).toBe(b.next());
    }
  });
  it('instances do not share state', () => {
    const a = createRng(7), b = createRng(7);
    const seqA = Array.from({ length: 50 }, () => a.next());
    const c = createRng(99); for (let i = 0; i < 17; i++) c.next();
    const seqB = Array.from({ length: 50 }, () => b.next());
    expect(seqB).toEqual(seqA);
  });
  it('different seeds give different sequences', () => {
    const seqs = new Set<string>();
    for (let s = 1; s <= 50; s++) {
      const r = createRng(s);
      seqs.add(Array.from({ length: 8 }, () => r.next()).join(','));
    }
    expect(seqs.size).toBe(50);
  });
  it('next() is in [0, 1) and roughly uniform', () => {
    const r = createRng(2024);
    const buckets = new Array(10).fill(0);
    const N = 20000;
    for (let i = 0; i < N; i++) {
      const v = r.next();
      expect(v).toBeGreaterThanOrEqual(0);
      expect(v).toBeLessThan(1);
      buckets[Math.floor(v * 10)]++;
    }
    for (const b of buckets) expect(Math.abs(b - N / 10)).toBeLessThan(N / 10 * 0.15);
  });
  it('int(min, max) is inclusive, integral and covers the range', () => {
    const r = createRng(5);
    for (const [min, max] of [[1, 6], [-3, 3], [0, 0], [10, 11]]) {
      const seen = new Set<number>();
      for (let i = 0; i < 2000; i++) {
        const v = r.int(min, max);
        expect(Number.isInteger(v)).toBe(true);
        expect(v).toBeGreaterThanOrEqual(min);
        expect(v).toBeLessThanOrEqual(max);
        seen.add(v);
      }
      expect(seen.size).toBe(max - min + 1);
    }
  });
});
