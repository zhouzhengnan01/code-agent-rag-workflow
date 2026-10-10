import test from 'node:test';
import assert from 'node:assert/strict';
import { isActiveRun, mergeRun } from './run-state';

test('late polling cannot undo cancellation or completion', () => {
  for (const status of ['cancelled', 'completed', 'failed']) {
    const terminal = { id: 'run1', status, output: 'saved' };
    for (const previous of ['queued', 'running']) {
      assert.equal(mergeRun(terminal, { ...terminal, status: previous }), terminal);
    }
    assert.equal(isActiveRun(terminal), false);
  }
});

test('polling advances a running task and a subsequent test can start', () => {
  const running = { id: 'run1', status: 'running' };
  assert.equal(mergeRun(running, { ...running, status: 'queued' }), running);
  assert.equal(mergeRun(running, { ...running, status: 'cancelled' }).status, 'cancelled');
  const next = { id: 'run2', status: 'queued' };
  assert.equal(mergeRun({ ...running, status: 'cancelled' }, next), next);
  assert.equal(isActiveRun(next), true);
  assert.equal(isActiveRun(undefined), false);
});
