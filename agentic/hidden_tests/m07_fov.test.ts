import { describe, it, expect } from 'vitest';
import { createMap } from '../src/map';
import { computeFov } from '../src/fov';
import { fromAscii } from './_util';

const key = (x: number, y: number) => `${x},${y}`;

describe('m07 fov', () => {
  it('open area: origin and everything well inside the radius is visible, nothing beyond it', () => {
    const map = createMap(31, 31, 'floor');
    const o = { x: 15, y: 15 }, r = 8;
    const vis = computeFov(map, o, r);
    expect(vis.has(key(15, 15))).toBe(true);
    for (let y = 0; y < 31; y++) for (let x = 0; x < 31; x++) {
      const dx = x - o.x, dy = y - o.y;
      if (dx * dx + dy * dy <= (r - 1) * (r - 1)) expect(vis.has(key(x, y)), key(x, y)).toBe(true);
      if (Math.max(Math.abs(dx), Math.abs(dy)) > r + 1) expect(vis.has(key(x, y)), key(x, y)).toBe(false);
    }
  });
  it('lights the walls of a room but not what lies behind them', () => {
    const { map, origin } = fromAscii(createMap, [
      '###########',
      '#.........#',
      '#....@....#',
      '#.........#',
      '###########',
      '#.........#',
      '###########',
    ]);
    const vis = computeFov(map, origin!, 20);
    for (let x = 1; x < 10; x++) { expect(vis.has(key(x, 0)), `top wall ${x}`).toBe(true); expect(vis.has(key(x, 4)), `bottom wall ${x}`).toBe(true); }
    for (let x = 1; x < 10; x++) expect(vis.has(key(x, 5)), `behind wall ${x}`).toBe(false);
  });
  it('a pillar casts a shadow', () => {
    const { map, origin } = fromAscii(createMap, [
      '#############',
      '#...........#',
      '#...........#',
      '#.@.#.......#',
      '#...........#',
      '#...........#',
      '#############',
    ]);
    const vis = computeFov(map, origin!, 20);
    expect(vis.has(key(4, 3))).toBe(true);    // the pillar itself
    expect(vis.has(key(6, 3))).toBe(false);   // directly behind it
    expect(vis.has(key(8, 3))).toBe(false);
    expect(vis.has(key(6, 1))).toBe(true);    // off to the side stays visible
  });
  it('sees down a straight corridor but not around a corner', () => {
    const { map, origin } = fromAscii(createMap, [
      '##########',
      '#@.......#',
      '########.#',
      '########.#',
      '########.#',
      '##########',
    ]);
    const vis = computeFov(map, origin!, 20);
    for (let x = 1; x <= 8; x++) expect(vis.has(key(x, 1)), `corridor ${x}`).toBe(true);
    expect(vis.has(key(8, 4))).toBe(false);
  });
  it('never returns out-of-bounds keys', () => {
    const map = createMap(6, 6, 'floor');
    const vis = computeFov(map, { x: 0, y: 0 }, 10);
    for (const k of vis) {
      const [x, y] = k.split(',').map(Number);
      expect(x >= 0 && y >= 0 && x < 6 && y < 6, k).toBe(true);
    }
    expect(vis.has(key(5, 5))).toBe(true);
  });
});
