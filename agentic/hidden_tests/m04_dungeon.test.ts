import { describe, it, expect } from 'vitest';
import { generateDungeon } from '../src/dungeon';
import { mapToJSON } from '../src/map';
import { bfs, walkableTiles } from './_util';

const SIZES: [number, number][] = [[80, 50], [60, 40], [100, 60]];

describe('m04 dungeon', () => {
  it('invariants hold over 200 seeds', () => {
    for (let seed = 1; seed <= 200; seed++) {
      const [w, h] = SIZES[seed % SIZES.length];
      const { map, rooms, start } = generateDungeon(seed, w, h);
      const ctx = `seed ${seed} ${w}x${h}`;
      expect(map.width, ctx).toBe(w);
      expect(map.height, ctx).toBe(h);
      // border never walkable
      for (let x = 0; x < w; x++) {
        expect(map.isWalkable(x, 0), ctx).toBe(false);
        expect(map.isWalkable(x, h - 1), ctx).toBe(false);
      }
      for (let y = 0; y < h; y++) {
        expect(map.isWalkable(0, y), ctx).toBe(false);
        expect(map.isWalkable(w - 1, y), ctx).toBe(false);
      }
      // rooms: in bounds, walkable inside, no overlaps
      expect(rooms.length, ctx).toBeGreaterThanOrEqual(2);
      for (const r of rooms) {
        expect(r.w, ctx).toBeGreaterThan(0);
        expect(r.h, ctx).toBeGreaterThan(0);
        expect(r.x, ctx).toBeGreaterThanOrEqual(1);
        expect(r.y, ctx).toBeGreaterThanOrEqual(1);
        expect(r.x + r.w, ctx).toBeLessThanOrEqual(w - 1);
        expect(r.y + r.h, ctx).toBeLessThanOrEqual(h - 1);
        for (let y = r.y; y < r.y + r.h; y++)
          for (let x = r.x; x < r.x + r.w; x++) expect(map.isWalkable(x, y), `${ctx} room tile ${x},${y}`).toBe(true);
      }
      for (let i = 0; i < rooms.length; i++)
        for (let j = i + 1; j < rooms.length; j++) {
          const a = rooms[i], b = rooms[j];
          const overlap = a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
          expect(overlap, `${ctx} rooms ${i} and ${j} overlap`).toBe(false);
        }
      // start walkable; everything walkable reachable from start (4-dir flood fill)
      expect(map.isWalkable(start.x, start.y), ctx).toBe(true);
      const reach = bfs(map, start);
      const all = walkableTiles(map);
      expect(reach.size, `${ctx} connectivity`).toBe(all.length);
      // not degenerate
      expect(all.length, ctx).toBeGreaterThan(w * h * 0.05);
      expect(all.length, ctx).toBeLessThan(w * h * 0.9);
    }
  });
  it('is deterministic per seed and varies across seeds', () => {
    const a = generateDungeon(77, 80, 50), b = generateDungeon(77, 80, 50);
    expect(mapToJSON(a.map)).toBe(mapToJSON(b.map));
    expect(a.start).toEqual(b.start);
    const distinct = new Set<string>();
    for (let s = 1; s <= 20; s++) distinct.add(mapToJSON(generateDungeon(s, 80, 50).map));
    expect(distinct.size).toBeGreaterThanOrEqual(18);
  });
});
