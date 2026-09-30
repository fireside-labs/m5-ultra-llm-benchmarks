import { describe, it, expect } from 'vitest';
import { createMap } from '../src/map';
import { findPath } from '../src/pathfinding';
import { bfs, testRng, walkableTiles, fromAscii } from './_util';

function checkPath(map: any, from: any, to: any, path: any[], ctx: string) {
  let prev = from;
  for (const p of path) {
    expect(Math.abs(p.x - prev.x) + Math.abs(p.y - prev.y), `${ctx} step adjacency`).toBe(1);
    expect(map.isWalkable(p.x, p.y), `${ctx} step walkable`).toBe(true);
    prev = p;
  }
  if (path.length) expect({ x: prev.x, y: prev.y }, ctx).toEqual({ x: to.x, y: to.y });
}

describe('m10 A* pathfinding', () => {
  it('finds optimal paths (length equals BFS distance) on 200 random maps', () => {
    for (let s = 1; s <= 200; s++) {
      const rng = testRng(s);
      const w = rng.int(8, 30), h = rng.int(8, 30);
      const map = createMap(w, h, 'floor');
      const density = 0.15 + rng.next() * 0.25;
      for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) if (rng.next() < density) map.set(x, y, 'wall');
      const tiles = walkableTiles(map);
      if (tiles.length < 2) continue;
      for (let k = 0; k < 3; k++) {
        const from = tiles[rng.int(0, tiles.length - 1)], to = tiles[rng.int(0, tiles.length - 1)];
        const d = bfs(map, from).get(`${to.x},${to.y}`);
        const path = findPath(map, from, to);
        const ctx = `seed ${s} ${JSON.stringify(from)}->${JSON.stringify(to)}`;
        if (d === undefined) expect(path, ctx).toBeNull();
        else {
          expect(path, ctx).not.toBeNull();
          expect(path!.length, ctx).toBe(d);
          checkPath(map, from, to, path!, ctx);
        }
      }
    }
  });
  it('returns [] when already there and null for walls / sealed areas', () => {
    const { map, marks } = fromAscii(createMap, [
      '#######',
      '#a.#b.#',
      '#..#..#',
      '#######',
    ]);
    expect(findPath(map, marks.a, marks.a)).toEqual([]);
    expect(findPath(map, marks.a, marks.b)).toBeNull();
    expect(findPath(map, marks.a, { x: 3, y: 1 })).toBeNull();
  });
  it('routes around obstacles through a door', () => {
    const { map, marks } = fromAscii(createMap, [
      '#########',
      '#a..#..b#',
      '#...+...#',
      '#...#...#',
      '#########',
    ]);
    const path = findPath(map, marks.a, marks.b)!;
    expect(path).not.toBeNull();
    checkPath(map, marks.a, marks.b, path, 'door');
    expect(path.some(p => p.x === 4 && p.y === 2)).toBe(true);
    expect(path.length).toBe(bfs(map, marks.a).get(`${marks.b.x},${marks.b.y}`));
  });
});
