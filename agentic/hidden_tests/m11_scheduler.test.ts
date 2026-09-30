import { describe, it, expect } from 'vitest';
import { Scheduler } from '../src/scheduler';

function run(s: Scheduler<string>, n: number) {
  const counts: Record<string, number> = {};
  const order: string[] = [];
  for (let i = 0; i < n; i++) {
    const a = s.next()!;
    order.push(a);
    counts[a] = (counts[a] ?? 0) + 1;
  }
  return { counts, order };
}

describe('m11 scheduler', () => {
  it('returns undefined when empty', () => {
    expect(new Scheduler<string>().next()).toBeUndefined();
  });
  it('equal speeds share turns fairly', () => {
    const s = new Scheduler<string>();
    s.add('a', 100); s.add('b', 100); s.add('c', 100);
    const { counts, order } = run(s, 300);
    for (const k of ['a', 'b', 'c']) expect(counts[k]).toBe(100);
    // no actor acts twice in a row while others wait
    for (let i = 1; i < order.length; i++) expect(order[i]).not.toBe(order[i - 1]);
  });
  it('turn frequency is proportional to speed', () => {
    const s = new Scheduler<string>();
    s.add('fast', 200); s.add('normal', 100); s.add('slow', 50);
    const { counts } = run(s, 700);
    expect(counts.fast / counts.normal).toBeGreaterThan(1.8);
    expect(counts.fast / counts.normal).toBeLessThan(2.2);
    expect(counts.normal / counts.slow).toBeGreaterThan(1.8);
    expect(counts.normal / counts.slow).toBeLessThan(2.2);
  });
  it('removed actors never act again', () => {
    const s = new Scheduler<string>();
    s.add('a', 100); s.add('b', 100); s.add('c', 150);
    run(s, 10);
    s.remove('b');
    const { counts } = run(s, 100);
    expect(counts.b ?? 0).toBe(0);
    expect(counts.a).toBeGreaterThan(0);
    expect(counts.c).toBeGreaterThan(counts.a);
  });
  it('is deterministic', () => {
    const mk = () => { const s = new Scheduler<string>(); s.add('x', 130); s.add('y', 70); s.add('z', 100); return s; };
    expect(run(mk(), 200).order).toEqual(run(mk(), 200).order);
  });
});
