import { describe, it, expect } from 'vitest';
import { applyStatus, tickStatus, hasStatus } from '../src/status';

const mk = (hp = 20) => ({ hp, maxHp: 20, effects: [] as { kind: any; turns: number }[] });

describe('m17 status effects', () => {
  it('effects last exactly their duration', () => {
    for (const kind of ['poison', 'haste', 'slow', 'confusion'] as const) {
      const t = mk();
      applyStatus(t, kind, 3);
      expect(hasStatus(t, kind)).toBe(true);
      tickStatus(t); tickStatus(t);
      expect(hasStatus(t, kind), kind).toBe(true);
      tickStatus(t);
      expect(hasStatus(t, kind), kind).toBe(false);
    }
  });
  it('poison damages each tick and never takes hp below 0', () => {
    const t = mk(20);
    applyStatus(t, 'poison', 3);
    const hp: number[] = [];
    for (let i = 0; i < 3; i++) { tickStatus(t); hp.push(t.hp); }
    expect(hp[0]).toBeLessThan(20);
    expect(hp[1]).toBeLessThan(hp[0]);
    expect(hp[2]).toBeLessThan(hp[1]);
    tickStatus(t);
    expect(t.hp).toBe(hp[2]);
    const weak = mk(1);
    applyStatus(weak, 'poison', 10);
    for (let i = 0; i < 10; i++) tickStatus(weak);
    expect(weak.hp).toBe(0);
  });
  it('non-damaging effects do not change hp', () => {
    const t = mk(15);
    applyStatus(t, 'haste', 5); applyStatus(t, 'confusion', 5);
    for (let i = 0; i < 5; i++) tickStatus(t);
    expect(t.hp).toBe(15);
  });
  it('re-applying refreshes instead of stacking', () => {
    const t = mk();
    applyStatus(t, 'slow', 2);
    applyStatus(t, 'slow', 4);
    expect(t.effects.filter(e => e.kind === 'slow').length).toBe(1);
    for (let i = 0; i < 3; i++) tickStatus(t);
    expect(hasStatus(t, 'slow')).toBe(true);
  });
});
