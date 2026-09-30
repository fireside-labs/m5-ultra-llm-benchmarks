import { describe, it, expect } from 'vitest';
import { createMap, mapToJSON, mapFromJSON } from '../src/map';

describe('m03 map', () => {
  it('creates a map of the right size filled with walls by default', () => {
    const m = createMap(12, 7);
    expect(m.width).toBe(12);
    expect(m.height).toBe(7);
    for (let y = 0; y < 7; y++) for (let x = 0; x < 12; x++) expect(m.get(x, y)).toBe('wall');
  });
  it('get/set and walkability/transparency rules', () => {
    const m = createMap(5, 5, 'wall');
    m.set(1, 1, 'floor'); m.set(2, 1, 'door');
    expect(m.get(1, 1)).toBe('floor');
    expect(m.get(2, 1)).toBe('door');
    expect(m.isWalkable(1, 1)).toBe(true);
    expect(m.isWalkable(2, 1)).toBe(true);
    expect(m.isWalkable(0, 0)).toBe(false);
    expect(m.isTransparent(1, 1)).toBe(true);
    expect(m.isTransparent(0, 0)).toBe(false);
  });
  it('treats out of bounds as wall', () => {
    const m = createMap(4, 3, 'floor');
    for (const [x, y] of [[-1, 0], [0, -1], [4, 0], [0, 3], [100, 100]]) {
      expect(m.inBounds(x, y)).toBe(false);
      expect(m.get(x, y)).toBe('wall');
      expect(m.isWalkable(x, y)).toBe(false);
      expect(m.isTransparent(x, y)).toBe(false);
    }
    expect(m.inBounds(0, 0)).toBe(true);
    expect(m.inBounds(3, 2)).toBe(true);
  });
  it('round-trips through JSON exactly', () => {
    const m = createMap(17, 9, 'wall');
    let s = 12345;
    const kinds = ['wall', 'floor', 'door'] as const;
    for (let y = 0; y < 9; y++) for (let x = 0; x < 17; x++) {
      s = (s * 1103515245 + 12345) & 0x7fffffff;
      m.set(x, y, kinds[s % 3]);
    }
    const json = mapToJSON(m);
    expect(typeof json).toBe('string');
    JSON.parse(json);
    const back = mapFromJSON(json);
    expect(back.width).toBe(17);
    expect(back.height).toBe(9);
    for (let y = 0; y < 9; y++) for (let x = 0; x < 17; x++) expect(back.get(x, y)).toBe(m.get(x, y));
    expect(mapToJSON(back)).toBe(json);
  });
  it('non-square maps keep x as column and y as row', () => {
    const m = createMap(3, 8, 'wall');
    m.set(2, 7, 'floor');
    expect(m.get(2, 7)).toBe('floor');
    expect(m.inBounds(7, 2)).toBe(false);
  });
});
