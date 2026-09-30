import { describe, it, expect } from 'vitest';
import { createRng } from '../src/rng';
import { resolveAttack } from '../src/combat';

const mk = (attack: number, defense: number, hp = 1_000_000) => ({ hp, maxHp: hp, attack, defense });

function sample(att: number, def: number, n: number, seed = 1) {
  const rng = createRng(seed);
  let hits = 0, crits = 0, critDmg = 0, normDmg = 0;
  for (let i = 0; i < n; i++) {
    const d = mk(0, def);
    const r = resolveAttack(mk(att, 0), d, rng);
    expect(r.damage).toBeGreaterThanOrEqual(0);
    expect(d.hp).toBe(1_000_000 - r.damage);
    if (!r.hit) { expect(r.damage).toBe(0); expect(r.critical).toBe(false); continue; }
    hits++;
    if (r.critical) { crits++; critDmg += r.damage; } else normDmg += r.damage;
  }
  return { hitRate: hits / n, crits, critAvg: critDmg / Math.max(1, crits), normAvg: normDmg / Math.max(1, hits - crits) };
}

describe('m12 combat', () => {
  it('both hits and misses happen, and hits usually do damage', () => {
    const s = sample(10, 5, 4000);
    expect(s.hitRate).toBeGreaterThan(0.05);
    expect(s.hitRate).toBeLessThan(1);
    expect(s.normAvg).toBeGreaterThan(0);
  });
  it('criticals happen and hit harder on average', () => {
    const s = sample(10, 5, 20000);
    expect(s.crits).toBeGreaterThan(0);
    expect(s.critAvg).toBeGreaterThan(s.normAvg);
  });
  it('more attack means more expected damage; more defense means less', () => {
    const exp = (att: number, def: number) => {
      const rng = createRng(3); let t = 0;
      for (let i = 0; i < 4000; i++) t += resolveAttack(mk(att, 0), mk(0, def), rng).damage;
      return t;
    };
    expect(exp(20, 5)).toBeGreaterThan(exp(8, 5));
    expect(exp(10, 2)).toBeGreaterThan(exp(10, 12));
  });
  it('death: hp never below 0 and killed exactly when hp reaches 0', () => {
    const rng = createRng(11);
    for (let i = 0; i < 300; i++) {
      const d = { hp: 5, maxHp: 5, attack: 1, defense: 0 };
      let killed = false, guard = 0;
      while (!killed && guard++ < 10000) {
        const r = resolveAttack(mk(50, 0), d, rng);
        expect(d.hp).toBeGreaterThanOrEqual(0);
        expect(r.killed).toBe(d.hp === 0);
        killed = r.killed;
      }
      expect(killed).toBe(true);
    }
  });
  it('is deterministic given the injected rng', () => {
    const go = () => { const rng = createRng(99); const d = mk(0, 4); return Array.from({ length: 200 }, () => resolveAttack(mk(9, 0), d, rng)); };
    expect(go()).toEqual(go());
  });
});
