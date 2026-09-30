import { describe, it, expect } from 'vitest';
import { createLevelManager } from '../src/levels';
import { mapToJSON } from '../src/map';
import { bfs } from './_util';

describe('m15 levels and stairs', () => {
  it('each level has reachable stairs', () => {
    const lm = createLevelManager(4242);
    for (let d = 1; d <= 6; d++) {
      const lvl = lm.getLevel(d);
      expect(lvl.depth).toBe(d);
      expect(lvl.map.isWalkable(lvl.stairsDown.x, lvl.stairsDown.y), `depth ${d} down`).toBe(true);
      if (d >= 2) {
        expect(lvl.stairsUp, `depth ${d} up`).toBeDefined();
        const up = lvl.stairsUp!;
        expect(lvl.map.isWalkable(up.x, up.y)).toBe(true);
        expect(bfs(lvl.map, up).has(`${lvl.stairsDown.x},${lvl.stairsDown.y}`), `depth ${d} connected`).toBe(true);
      }
    }
  });
  it('levels differ from each other and persist when revisited', () => {
    const lm = createLevelManager(7);
    const l1 = lm.getLevel(1), l2 = lm.getLevel(2);
    expect(mapToJSON(l1.map)).not.toBe(mapToJSON(l2.map));
    // modify level 1, go down and back up
    const t = l1.stairsDown;
    const x = t.x === 1 ? 2 : 1;
    l1.map.set(x, 1, 'door');
    lm.getLevel(2); lm.getLevel(3);
    const again = lm.getLevel(1);
    expect(again.map.get(x, 1)).toBe('door');
    expect(mapToJSON(again.map)).toBe(mapToJSON(l1.map));
  });
  it('is deterministic per seed', () => {
    const a = createLevelManager(99), b = createLevelManager(99);
    for (const d of [3, 1, 2]) expect(mapToJSON(a.getLevel(d).map)).toBe(mapToJSON(b.getLevel(d).map));
  });
});
