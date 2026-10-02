import { describe, it, expect } from 'vitest';
import { createRng } from '../src/rng';
import { createMap, mapToJSON, mapFromJSON } from '../src/map';
import { generateDungeon } from '../src/dungeon';
import { tryMove } from '../src/movement';
import { computeFov } from '../src/fov';
import { findPath } from '../src/pathfinding';
import { Scheduler } from '../src/scheduler';
import { resolveAttack } from '../src/combat';
import * as invm from '../src/inventory';
import { createLevelManager } from '../src/levels';
import * as save from '../src/save';
import * as st from '../src/status';

function bfs(map: any, a: any, b: any): number {
  const key = (x: number, y: number) => y * map.width + x;
  const dist = new Map<number, number>([[key(a.x, a.y), 0]]);
  const q = [a];
  while (q.length) {
    const c = q.shift();
    const d = dist.get(key(c.x, c.y))!;
    if (c.x === b.x && c.y === b.y) return d;
    for (const [dx, dy] of [[1,0],[-1,0],[0,1],[0,-1]]) {
      const nx = c.x + dx, ny = c.y + dy;
      if (!map.isWalkable(nx, ny) || dist.has(key(nx, ny))) continue;
      dist.set(key(nx, ny), d + 1); q.push({ x: nx, y: ny });
    }
  }
  return -1;
}

describe('conformance', () => {
  it('rng', () => {
    const a = createRng(5), b = createRng(5), c = createRng(6);
    const sa = Array.from({ length: 50 }, () => a.next());
    const sb = Array.from({ length: 50 }, () => b.next());
    expect(sa).toEqual(sb);
    expect(Array.from({ length: 50 }, () => c.next())).not.toEqual(sa);
    const r = createRng(1); const seen = new Set<number>();
    for (let i = 0; i < 5000; i++) { const v = r.int(3, 5); expect(v).toBeGreaterThanOrEqual(3); expect(v).toBeLessThanOrEqual(5); expect(Number.isInteger(v)).toBe(true); seen.add(v); const f = r.next(); expect(f >= 0 && f < 1).toBe(true); }
    expect(seen.size).toBe(3);
    expect(createRng(9).int(4, 4)).toBe(4);
  });
  it('map', () => {
    const m = createMap(5, 4);
    expect(m.get(0, 0)).toBe('wall'); expect(m.get(-1, 0)).toBe('wall'); expect(m.get(5, 0)).toBe('wall');
    m.set(1, 1, 'floor'); m.set(2, 1, 'door');
    expect(m.isWalkable(1, 1)).toBe(true); expect(m.isWalkable(2, 1)).toBe(true); expect(m.isWalkable(0, 0)).toBe(false);
    expect(m.isTransparent(1, 1)).toBe(true); expect(m.isTransparent(0, 0)).toBe(false); expect(m.isTransparent(99, 0)).toBe(false);
    m.set(99, 99, 'floor');
    const r = mapFromJSON(mapToJSON(m));
    expect(r.width).toBe(5); expect(r.height).toBe(4);
    for (let y = 0; y < 4; y++) for (let x = 0; x < 5; x++) expect(r.get(x, y)).toBe(m.get(x, y));
    expect(createMap(2, 2, 'floor').get(1, 1)).toBe('floor');
  });
  it('dungeon over 50 seeds incl. odd sizes', () => {
    for (let s = 0; s < 50; s++) {
      for (const [w, h] of [[80, 50], [40, 30], [31, 23]]) {
        const d = generateDungeon(s, w, h);
        const d2 = generateDungeon(s, w, h);
        expect(mapToJSON(d.map)).toBe(mapToJSON(d2.map));
        for (let x = 0; x < w; x++) { expect(d.map.isWalkable(x, 0)).toBe(false); expect(d.map.isWalkable(x, h - 1)).toBe(false); }
        for (let y = 0; y < h; y++) { expect(d.map.isWalkable(0, y)).toBe(false); expect(d.map.isWalkable(w - 1, y)).toBe(false); }
        expect(d.map.isWalkable(d.start.x, d.start.y)).toBe(true);
        for (const r of d.rooms) for (let y = r.y; y < r.y + r.h; y++) for (let x = r.x; x < r.x + r.w; x++) expect(d.map.isWalkable(x, y)).toBe(true);
        for (let i = 0; i < d.rooms.length; i++) for (let j = i + 1; j < d.rooms.length; j++) {
          const a = d.rooms[i], b = d.rooms[j];
          const ov = a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
          expect(ov).toBe(false);
        }
        // connectivity
        let total = 0; for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) if (d.map.isWalkable(x, y)) total++;
        const seen = new Set<string>([`${d.start.x},${d.start.y}`]); const q = [d.start];
        while (q.length) { const c = q.pop()!; for (const [dx, dy] of [[1,0],[-1,0],[0,1],[0,-1]]) { const k = `${c.x+dx},${c.y+dy}`; if (!seen.has(k) && d.map.isWalkable(c.x+dx, c.y+dy)) { seen.add(k); q.push({ x: c.x+dx, y: c.y+dy }); } } }
        expect(seen.size).toBe(total);
      }
    }
  });
  it('movement', () => {
    const m = createMap(3, 3); m.set(1, 1, 'floor');
    expect(tryMove(m, { x: 1, y: 1 }, 1, 0)).toEqual({ x: 1, y: 1 });
    m.set(2, 1, 'door');
    expect(tryMove(m, { x: 1, y: 1 }, 1, 0)).toEqual({ x: 2, y: 1 });
  });
  it('fov', () => {
    const m = createMap(21, 21, 'floor');
    m.set(10, 8, 'wall');
    const v = computeFov(m, { x: 10, y: 10 }, 5);
    expect(v.has('10,10')).toBe(true);
    expect(v.has('10,8')).toBe(true);  // wall seen
    expect(v.has('10,7')).toBe(false); // behind wall
    expect(v.has('10,6')).toBe(false);
    for (const k of v) { const [x, y] = k.split(',').map(Number); expect(Math.hypot(x - 10, y - 10)).toBeLessThanOrEqual(5); }
    expect(v.has('15,10')).toBe(true);
    // corner origin: no out-of-bounds keys
    const v2 = computeFov(m, { x: 0, y: 0 }, 4);
    for (const k of v2) { const [x, y] = k.split(',').map(Number); expect(m.inBounds(x, y)).toBe(true); }
    // symmetric-ish: closed room should not leak
    const r = createMap(11, 11); for (let y = 1; y < 4; y++) for (let x = 1; x < 4; x++) r.set(x, y, 'floor');
    for (let y = 6; y < 10; y++) for (let x = 6; x < 10; x++) r.set(x, y, 'floor');
    const v3 = computeFov(r, { x: 2, y: 2 }, 20);
    for (const k of v3) { const [x, y] = k.split(',').map(Number); expect(x <= 4 && y <= 4).toBe(true); }
    // radius 0
    expect([...computeFov(m, { x: 5, y: 5 }, 0)]).toEqual(['5,5']);
    // door is not transparent? only floor required; walls block
  });
  it('pathfinding optimal on random dungeons', () => {
    for (let s = 0; s < 30; s++) {
      const d = generateDungeon(s, 60, 40); const rng = createRng(s);
      const cells: any[] = []; for (let y = 0; y < 40; y++) for (let x = 0; x < 60; x++) if (d.map.isWalkable(x, y)) cells.push({ x, y });
      for (let k = 0; k < 10; k++) {
        const a = cells[rng.int(0, cells.length - 1)], b = cells[rng.int(0, cells.length - 1)];
        const p = findPath(d.map, a, b)!;
        expect(p).not.toBeNull();
        expect(p.length).toBe(bfs(d.map, a, b));
        if (p.length) expect(p[p.length - 1]).toEqual(b);
        let prev = a; for (const q of p) { expect(Math.abs(q.x - prev.x) + Math.abs(q.y - prev.y)).toBe(1); expect(d.map.isWalkable(q.x, q.y)).toBe(true); prev = q; }
      }
    }
    const m = createMap(5, 5); m.set(1, 1, 'floor'); m.set(3, 3, 'floor');
    expect(findPath(m, { x: 1, y: 1 }, { x: 3, y: 3 })).toBeNull();
    expect(findPath(m, { x: 1, y: 1 }, { x: 1, y: 1 })).toEqual([]);
  });
  it('scheduler fairness', () => {
    const s = new Scheduler<string>();
    s.add('a', 100); s.add('b', 200); s.add('c', 50);
    const counts: Record<string, number> = { a: 0, b: 0, c: 0 };
    for (let i = 0; i < 700; i++) counts[s.next()!]++;
    expect(counts.b / counts.a).toBeCloseTo(2, 1);
    expect(counts.a / counts.c).toBeCloseTo(2, 1);
    s.remove('b');
    for (let i = 0; i < 30; i++) expect(s.next()).not.toBe('b');
    const e = new Scheduler<number>(); expect(e.next()).toBeUndefined();
    // equal speeds alternate
    const t = new Scheduler<string>(); t.add('x', 100); t.add('y', 100);
    const seq = Array.from({ length: 6 }, () => t.next());
    expect(seq.filter(v => v === 'x').length).toBe(3);
  });
  it('combat', () => {
    for (let s = 0; s < 200; s++) {
      const att = { hp: 10, maxHp: 10, attack: 50, defense: 0 };
      const def = { hp: 5, maxHp: 5, attack: 1, defense: 1 };
      const r = resolveAttack(att, def, createRng(s));
      expect(def.hp).toBeGreaterThanOrEqual(0);
      expect(r.killed).toBe(def.hp === 0);
      if (!r.hit) { expect(r.damage).toBe(0); expect(r.critical).toBe(false); }
      expect(def.hp).toBe(Math.max(0, 5 - r.damage) );
    }
    const a1 = { hp: 10, maxHp: 10, attack: 5, defense: 2 }, d1 = { hp: 30, maxHp: 30, attack: 5, defense: 2 };
    const a2 = { ...a1 }, d2 = { ...d1 };
    expect(resolveAttack(a1, d1, createRng(3))).toEqual(resolveAttack(a2, d2, createRng(3)));
  });
  it('inventory', () => {
    const inv = invm.createInventory(2);
    expect(invm.addItem(inv, { id: 'p', name: 'P', kind: 'potion', power: 5 })).toBe(true);
    expect(invm.addItem(inv, { id: 's', name: 'S', kind: 'weapon', power: 2 })).toBe(true);
    expect(invm.addItem(inv, { id: 'x', name: 'X', kind: 'armor' })).toBe(false);
    expect(invm.equip(inv, 'p')).toBe(false);
    expect(invm.equip(inv, 's')).toBe(true);
    expect(inv.equipped.weapon?.id).toBe('s');
    expect(inv.items.length).toBe(2);
    const t = { hp: 8, maxHp: 10, attack: 1, defense: 1 };
    expect(invm.useItem(inv, 's', t)).toBe(false);
    expect(invm.useItem(inv, 'p', t)).toBe(true);
    expect(t.hp).toBe(10);
    expect(inv.items.find(i => i.id === 'p')).toBeUndefined();
    expect(invm.removeItem(inv, 's')?.id).toBe('s');
    expect(inv.equipped.weapon).toBeUndefined();
    expect(invm.removeItem(inv, 'zz')).toBeUndefined();
    const inv2 = invm.createInventory(5);
    invm.addItem(inv2, { id: 'sc', name: 'Sc', kind: 'scroll' });
    expect(invm.useItem(inv2, 'sc', t)).toBe(true);
    expect(inv2.items.length).toBe(0);
  });
  it('levels', () => {
    const lm = createLevelManager(42);
    const l1 = lm.getLevel(1); expect(l1.depth).toBe(1); expect(l1.stairsUp).toBeUndefined();
    expect(l1.map.isWalkable(l1.stairsDown.x, l1.stairsDown.y)).toBe(true);
    const l2 = lm.getLevel(2); expect(l2.stairsUp).toBeDefined();
    l1.map.set(1, 1, 'floor');
    expect(lm.getLevel(1)).toBe(l1);
    expect(lm.getLevel(1).map.get(1, 1)).toBe('floor');
    const lm2 = createLevelManager(42);
    expect(mapToJSON(lm2.getLevel(2).map)).toBe(mapToJSON(l2.map));
  });
  it('save', () => {
    const g = save.createGameState(7);
    const j = save.serializeGame(g);
    expect(typeof JSON.parse(j).version).toBe('number');
    expect(JSON.parse(j).version).toBe(save.SAVE_VERSION);
    const g2 = save.deserializeGame(j);
    expect(save.serializeGame(g2)).toBe(j);
    expect(() => save.deserializeGame(JSON.stringify({ ...JSON.parse(j), version: save.SAVE_VERSION + 1 }))).toThrow();
    expect(save.migrateSave({ version: 1 } as any).version).toBe(save.SAVE_VERSION);
  });
  it('status', () => {
    const t = { hp: 3, maxHp: 10, effects: [] as any[] };
    st.applyStatus(t, 'poison', 2); st.applyStatus(t, 'poison', 5);
    expect(t.effects.length).toBe(1); expect(t.effects[0].turns).toBe(5);
    st.applyStatus(t, 'haste', 1);
    st.tickStatus(t);
    expect(t.hp).toBeLessThanOrEqual(2);
    expect(st.hasStatus(t, 'haste')).toBe(false);
    expect(st.hasStatus(t, 'poison')).toBe(true);
    for (let i = 0; i < 10; i++) st.tickStatus(t);
    expect(t.hp).toBeGreaterThanOrEqual(0);
    expect(t.effects.length).toBe(0);
  });
});
