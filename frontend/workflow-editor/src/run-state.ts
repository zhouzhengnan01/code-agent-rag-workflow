const active = new Set(['queued', 'running']);

export function isActiveRun(run?: { status: string }) {
  return !!run && active.has(run.status);
}

// A poll sent before cancellation can arrive after the cancel response.
export function mergeRun<T extends { id: string; status: string }>(current: T | undefined, incoming: T): T {
  if (current?.id !== incoming.id) return incoming;
  if (!isActiveRun(current) && isActiveRun(incoming)) return current!;
  if (current?.status === 'running' && incoming.status === 'queued') return current;
  return incoming;
}
