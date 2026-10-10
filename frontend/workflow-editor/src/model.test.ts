import test from 'node:test';
import assert from 'node:assert/strict';
import {
  ancestors,
  branchValue,
  fromWorkflow,
  hasCycle,
  isBranchDemo,
  layout,
  template,
  toWorkflow,
} from './model';

test('canvas round trip preserves execution fields, extra metadata and viewport', () => {
  const original = template('branch');
  original.nodes[1].timeout = 25;
  original.nodes[1].retries = 2;
  original.nodes[1].custom = { keep: true };
  original.edges[1].when = 'true';
  original.edges[2].when = 'false';
  original.canvas = {
    version: 1,
    positions: { condition_1: { x: 123, y: -55 } },
    viewport: { x: 10, y: 20, zoom: 0.8 },
  };
  const graph = fromWorkflow(original);
  assert.equal(graph.edges[1].sourceHandle, 'true');
  assert.equal(graph.edges[2].sourceHandle, 'false');
  assert.deepEqual(graph.nodes[1].position, { x: 123, y: -55 });
  const exported = toWorkflow({ ...original, id: 'not-portable', kind: 'workflows', updated_at: 5 }, graph);
  assert.deepEqual(exported.nodes, original.nodes);
  assert.deepEqual(exported.edges, original.edges);
  assert.deepEqual(exported.canvas?.viewport, original.canvas.viewport);
  assert.equal(exported.id, undefined);
  assert.equal(exported.updated_at, undefined);
  assert.equal('selected' in exported.nodes[0], false);
});

test('legacy definitions receive stable layout and support missing node type', () => {
  const original = template();
  const graph = fromWorkflow(original);
  assert.ok(graph.nodes[1].position.x > graph.nodes[0].position.x);
  assert.deepEqual(
    layout(graph).nodes.map((n) => n.position),
    graph.nodes.map((n) => n.position),
  );
  assert.equal(
    fromWorkflow({ name: 'legacy', nodes: [{ id: 'old' } as any], edges: [] }).nodes[0].data.definition.type,
    'prompt',
  );
});

test('reject invalid imports and cycles before changing the current graph', () => {
  const graph = fromWorkflow(template());
  assert.equal(hasCycle(graph), false);
  assert.equal(
    hasCycle({ ...graph, edges: [...graph.edges, { id: 'bad', source: 'output_1', target: 'input_1' }] }),
    true,
  );
  assert.throws(
    () => fromWorkflow({ ...template(), edges: [{ source: 'missing', target: 'input_1' }] }),
    /不存在/,
  );
  assert.throws(() => fromWorkflow({ name: 'empty', nodes: [], edges: [] }), /1–100/);
  assert.throws(
    () =>
      fromWorkflow({
        ...template(),
        nodes: [
          { id: 'a', type: 'input' },
          { id: 'a', type: 'output' },
        ],
      }),
    /唯一/,
  );
  assert.throws(
    () => fromWorkflow({ name: 'bad', nodes: [{ id: 'x', type: 'toString' as any }], edges: [] }),
    /不支持/,
  );
  assert.deepEqual(
    fromWorkflow({ name: 'safe', nodes: [{ id: '__proto__', type: 'input' }], edges: [] }).nodes[0].position,
    { x: 50, y: 100 },
  );
});

test('variable picker includes only transitive upstream nodes', () => {
  const graph = fromWorkflow(template('branch'));
  assert.deepEqual(
    ancestors('yes_1', graph).map((n) => n.id),
    ['input_1', 'condition_1'],
  );
  assert.equal(ancestors('input_1', graph).length, 0);
  assert.equal(branchValue('false'), false);
  assert.equal(branchValue('matched'), true);
});

test('answer templates connect Agent results instead of fixed branch messages', () => {
  const chat = template('chat');
  assert.equal(chat.nodes[1].type, 'agent');
  assert.equal(chat.nodes[2].template, '{{agent_1}}');
  const smart = template('smart-rag');
  const graph = fromWorkflow(smart);
  assert.equal(hasCycle(graph), false);
  assert.equal(smart.nodes.filter((n) => n.type === 'router').length, 1);
  assert.equal(smart.nodes.filter((n) => n.type === 'agent').length, 2);
  assert.deepEqual(
    smart.edges.filter((e) => e.source === 'router_1').map((e) => e.when),
    [true, false],
  );
  assert.deepEqual(toWorkflow(smart, graph).nodes, smart.nodes);
  assert.ok(
    smart.nodes
      .filter((n) => n.type === 'agent')
      .every((n) => n.knowledge_mode === 'workflow' && n.tool_mode === 'disabled'),
  );
  assert.ok(ancestors('rag_output', graph).some((n) => n.id === 'knowledge_1'));
  assert.ok(!ancestors('direct_output', graph).some((n) => n.id === 'knowledge_1'));
});

test('only the original routing demo offers automatic replacement', () => {
  const graph = fromWorkflow(template('branch'));
  assert.equal(isBranchDemo(graph), true);
  graph.nodes[2].data.definition.template = 'Custom business output';
  assert.equal(isBranchDemo(graph), false);
  assert.equal(isBranchDemo(fromWorkflow(template('chat'))), false);
});
