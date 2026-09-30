import { describe, it, expect } from 'vitest';
import { SAVE_VERSION, createGameState, serializeGame, deserializeGame, migrateSave } from '../src/save';

describe('m16 save/load', () => {
  it('serializes to JSON with the current numeric version', () => {
    const json = serializeGame(createGameState(1));
    const data = JSON.parse(json);
    expect(typeof SAVE_VERSION).toBe('number');
    expect(data.version).toBe(SAVE_VERSION);
  });
  it('round-trips (serialize -> deserialize -> serialize is stable)', () => {
    for (const seed of [1, 2, 3, 12345]) {
      const json = serializeGame(createGameState(seed));
      expect(serializeGame(deserializeGame(json))).toBe(json);
    }
  });
  it('different seeds produce different saves', () => {
    expect(serializeGame(createGameState(1))).not.toBe(serializeGame(createGameState(2)));
  });
  it('migrateSave brings data to the current version', () => {
    const data = JSON.parse(serializeGame(createGameState(5)));
    expect(migrateSave(data).version).toBe(SAVE_VERSION);
  });
  it('rejects saves from a newer version', () => {
    const data = JSON.parse(serializeGame(createGameState(5)));
    data.version = SAVE_VERSION + 1;
    expect(() => deserializeGame(JSON.stringify(data))).toThrow();
  });
});
