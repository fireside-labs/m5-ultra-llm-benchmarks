# Hidden acceptance tests (Deepdelve)

Not shown to the agent. `referee.py` copies this directory into a temp checkout of
each `milestone N:` commit as `__hidden__/` and runs, with the agent's own installed
Vitest but a referee-owned config (node environment, no agent setup files), only the
files `mNN_*.test.ts` with `NN <= max milestone reached so far`. Tests import the
interfaces listed under "Required interfaces" in TASK.md and check behaviour and
invariants only. `_util.ts` holds shared helpers (independent RNG, ASCII maps, BFS).

| file | milestone | checks |
|---|---|---|
| m01_scaffold.test.ts | 1 | package.json has build/test scripts and vite/vitest/typescript deps; tsconfig strict; src/, tests/, README exist |
| m02_rng.test.ts | 2 | `createRng`: determinism, no shared state, seeds differ, `next()` in [0,1) and roughly uniform, `int()` inclusive/integral/full coverage |
| m03_map.test.ts | 3 | `createMap` default walls, get/set, walkable/transparent rules, out of bounds = wall, exact JSON round-trip, x=column |
| m04_dungeon.test.ts | 4 | `generateDungeon` over 200 seeds / 3 sizes: dimensions, non-walkable border, >=2 in-bounds non-overlapping all-walkable rooms, walkable start, 4-dir flood-fill connectivity, sane density; determinism and variety |
| m06_movement.test.ts | 6 | `tryMove`: floor and doors passable, walls and map edge block, input not mutated |
| m07_fov.test.ts | 7 | `computeFov`: open-field radius, room walls lit but not what is behind them, pillar shadow, corridor vs corner, no out-of-bounds keys |
| m10_astar.test.ts | 10 | `findPath`: path length equals BFS distance on 200 random maps, adjacent walkable steps ending at target, null when unreachable, [] when at target, routes through doors |
| m11_scheduler.test.ts | 11 | `Scheduler`: empty -> undefined, equal speeds round-robin, turns proportional to speed, removal, determinism |
| m12_combat.test.ts | 12 | `resolveAttack` with injected seeded RNG: hits and misses occur, misses do 0, crits exist and hit harder, attack/defense monotonic, hp floor 0 and `killed` consistency, determinism |
| m13_items.test.ts | 13 | inventory capacity, drop, equip/replace slots, drop unequips, potions heal capped and are consumed, scrolls consumed, gear not usable |
| m15_levels.test.ts | 15 | `createLevelManager`: stairs walkable and connected, levels differ, changes persist on revisit, determinism |
| m16_save.test.ts | 16 | save JSON has `version === SAVE_VERSION`, serialize/deserialize/serialize is stable, `migrateSave` reaches current version, newer versions rejected |
| m17_status.test.ts | 17 | status effects last exactly their duration, poison damages with floor 0, other effects don't touch hp, re-apply refreshes instead of stacking |

No hidden tests (build/`npm test` checks only): 5 renderer, 8 entities, 9 monster AI,
14 inventory UI, and 18-30.
