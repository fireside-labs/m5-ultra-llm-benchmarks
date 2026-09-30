import { describe, it, expect } from 'vitest';
import { createMap } from '../src/map';
import { tryMove } from '../src/movement';
import { fromAscii } from './_util';

describe('m06 movement', () => {
  const { map, origin } = fromAscii(createMap, [
    '#####',
    '#.@+#',
    '#.#.#',
    '#####',
  ]);
  const o = origin!;
  it('moves onto floor and doors', () => {
    expect(tryMove(map, o, -1, 0)).toEqual({ x: 1, y: 1 });
    expect(tryMove(map, o, 1, 0)).toEqual({ x: 3, y: 1 });
  });
  it('is blocked by walls', () => {
    expect(tryMove(map, o, 0, 1)).toEqual(o);
    expect(tryMove(map, o, 0, -1)).toEqual(o);
  });
  it('is blocked by the map edge', () => {
    const open = createMap(3, 3, 'floor');
    expect(tryMove(open, { x: 0, y: 0 }, -1, 0)).toEqual({ x: 0, y: 0 });
    expect(tryMove(open, { x: 2, y: 2 }, 0, 1)).toEqual({ x: 2, y: 2 });
    expect(tryMove(open, { x: 1, y: 1 }, 1, 0)).toEqual({ x: 2, y: 1 });
  });
  it('does not mutate the input position', () => {
    const p = { x: 2, y: 1 };
    tryMove(map, p, -1, 0);
    expect(p).toEqual({ x: 2, y: 1 });
  });
});
