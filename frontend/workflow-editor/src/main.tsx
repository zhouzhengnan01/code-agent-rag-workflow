import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  Panel,
  applyNodeChanges,
  applyEdgeChanges,
  useReactFlow,
  type Connection,
  type Viewport,
} from '@xyflow/react';
import {
  ArrowLeft,
  Braces,
  CheckCircle2,
  ChevronRight,
  Code2,
  Download,
  History,
  LayoutGrid,
  LoaderCircle,
  Play,
  Plus,
  Redo2,
  RefreshCw,
  Save,
  Search,
  Settings2,
  Undo2,
  Upload,
  X,
  Trash2,
  Copy,
  CircleHelp,
  Workflow as WorkflowIcon,
} from 'lucide-react';
import { api } from './api';
import { isActiveRun, mergeRun } from './run-state';
import {
  ancestors,
  branchValue,
  fromWorkflow,
  hasCycle,
  isBranchDemo,
  kinds,
  layout,
  newNode,
  randomId,
  template,
  toWorkflow,
  type CanvasNode,
  type Graph,
  type Kind,
  type Workflow,
} from './model';
import { Dialog, Field, NodeCard, NodeInspector, icons, statusLabels, type Resources } from './components';
import '@xyflow/react/dist/style.css';
import './style.css';

const nodeTypes = { workflow: NodeCard };
interface Document {
  meta: Workflow;
  graph: Graph;
}
interface Trace {
  node_id: string;
  status: string;
  type: Kind;
  output?: unknown;
  error?: string;
  attempts?: number;
  started_at?: number;
  completed_at?: number;
  elapsed_ms?: number;
  agent_name?: string;
  runtime?: { provider?: string; model?: string };
  usage?: Record<string, unknown>;
  retrieval?: Record<string, unknown>;
}
interface Run {
  id: string;
  workflow_id: string;
  status: string;
  input: unknown;
  output: unknown;
  trace: Trace[] | null;
  error?: string;
  created_at: number;
  workflow_version?: number | null;
}
const signature = (value: Workflow) => JSON.stringify({ ...value, version: undefined });
const pretty = (value: unknown) =>
  typeof value === 'string' ? value : JSON.stringify(value, null, 2) || '暂无输出';
const emptyResources: Resources = { agents: [], knowledge: [], mcp_servers: [], projects: [] };

function App() {
  const params = useRef(new URLSearchParams(location.search));
  const [workflowId, setWorkflowId] = useState(params.current.get('id') || '');
  const [draftId, setDraftId] = useState(params.current.get('draft_id') || '');
  const draftRevision = useRef<string | undefined>(undefined);
  const initial = useMemo(() => template('chat'), []);
  const [doc, setDoc] = useState<Document>({ meta: initial, graph: fromWorkflow(initial) });
  const docRef = useRef(doc);
  docRef.current = doc;
  const [viewport, setViewport] = useState<Viewport | undefined>();
  const flow = useReactFlow<CanvasNode>();
  const [ready, setReady] = useState(false);
  const [loadError, setLoadError] = useState('');
  const [resources, setResources] = useState<Resources>(emptyResources);
  const [resourceError, setResourceError] = useState('');
  const [baseline, setBaseline] = useState('');
  const [selected, setSelected] = useState('');
  const [selectedEdge, setSelectedEdge] = useState('');
  const [tab, setTab] = useState<'node' | 'settings'>('settings');
  const [search, setSearch] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; error?: boolean }>();
  const [modal, setModal] = useState<'json' | 'templates' | 'versions' | 'help' | ''>('');
  const [json, setJson] = useState('');
  const [jsonError, setJsonError] = useState('');
  const [versions, setVersions] = useState<
    { version: number; created_at: number; workflow_version?: number | null }[]
  >([]);
  const [runOpen, setRunOpen] = useState(false);
  const [testInput, setTestInput] = useState('Codezzn');
  const [inputMode, setInputMode] = useState('text');
  const [run, setRun] = useState<Run>();
  const [cancelPending, setCancelPending] = useState(false);
  const cancelInFlight = useRef(false);
  const [runTab, setRunTab] = useState<'output' | 'trace' | 'history'>('output');
  const [runs, setRuns] = useState<Run[]>([]);
  const [historyTick, setHistoryTick] = useState(0);
  const history = useRef<{ past: Document[]; future: Document[] }>({ past: [], future: [] });
  const fileInput = useRef<HTMLInputElement>(null);
  const recoveryKey = useRef('');
  const [recovery, setRecovery] = useState<Workflow>();
  const [issues, setIssues] = useState<Record<string, string>>({});

  const value = useMemo(() => toWorkflow(doc.meta, doc.graph, viewport), [doc, viewport]);
  const dirty = ready && signature(value) !== baseline;
  const notify = useCallback((text: string, error = false) => setMessage({ text, error }), []);
  const reportError = useCallback(
    (error: unknown) => {
      const text = error instanceof Error ? error.message : String(error);
      const nodeId = text.match(/节点\s+(\S+)\s/)?.[1];
      if (nodeId && docRef.current.graph.nodes.some((node) => node.id === nodeId)) {
        setIssues({ [nodeId]: text });
        setSelected(nodeId);
        setSelectedEdge('');
        setTab('node');
        void flow.fitView({ nodes: [{ id: nodeId }], padding: 0.3, maxZoom: 1.1, duration: 250 });
      }
      notify(text, true);
    },
    [flow, notify],
  );
  useEffect(() => {
    if (!message) return;
    const timer = setTimeout(() => setMessage(undefined), message.error ? 9000 : 4500);
    return () => clearTimeout(timer);
  }, [message]);
  const updateDoc = useCallback((action: (current: Document) => Document, track = true) => {
    setDoc((current) => {
      if (track) {
        history.current.past.push(structuredClone(current));
        history.current.past = history.current.past.slice(-80);
        history.current.future = [];
      }
      return action(current);
    });
    setHistoryTick((t) => t + 1);
    setIssues({});
  }, []);
  const undo = useCallback((redo = false) => {
    const source = redo ? history.current.future : history.current.past;
    const target = redo ? history.current.past : history.current.future;
    const old = source.pop();
    if (!old) return;
    target.push(structuredClone(docRef.current));
    // Undo graph and metadata changes without reverting the optimistic version.
    setDoc({ ...old, meta: { ...old.meta, version: docRef.current.meta.version } });
    setHistoryTick((t) => t + 1);
    setIssues({});
  }, []);
  const refreshResources = useCallback(async () => {
    const results = await Promise.allSettled(
      ['agents', 'knowledge', 'mcp_servers']
        .map((kind) => api(`/api/resources/${kind}`))
        .concat(api('/api/projects')),
    );
    const next = { ...emptyResources };
    results.forEach((result, i) => {
      if (result.status === 'fulfilled') {
        const key = (['agents', 'knowledge', 'mcp_servers', 'projects'] as const)[i];
        next[key] = result.value.data || result.value.projects || [];
      }
    });
    setResources(next);
    setResourceError(
      results.some((result) => result.status === 'rejected') ? '部分资源加载失败，请检查连接后刷新。' : '',
    );
  }, []);
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        let loaded: Workflow = template('chat');
        if (draftId) {
          const draft = await api(`/api/workflow-drafts/${encodeURIComponent(draftId)}`);
          draftRevision.current = draft.revision;
          if (draft.status !== 'draft') throw new Error('此草稿已处理，请从工作台打开正式工作流');
          loaded = {
            ...draft.definition,
            name: draft.name,
            description: draft.description,
            project_id: draft.project_id,
          };
        } else if (workflowId)
          loaded = await api(`/api/resources/workflows/${encodeURIComponent(workflowId)}`);
        const graph = fromWorkflow(loaded);
        if (!active) return;
        setDoc({ meta: loaded, graph });
        setViewport(loaded.canvas?.viewport);
        setBaseline(
          workflowId || draftId ? signature(toWorkflow(loaded, graph, loaded.canvas?.viewport)) : '',
        );
        try {
          const session = await api('/api/auth/me').catch(() => ({}));
          recoveryKey.current = `codezzn:workflow:${session.user?.id || 'local'}:${draftId || workflowId || 'new'}`;
          const cached = sessionStorage.getItem(recoveryKey.current);
          if (cached) setRecovery(JSON.parse(cached));
        } catch {
          /* Private mode may disable session storage. */
        }
        if (active) setReady(true);
      } catch (e) {
        if (active) setLoadError((e as Error).message);
      }
    })();
    void refreshResources();
    return () => {
      active = false;
    };
    // Resource IDs are loaded once; changing the URL after first save does not reload the editor.
  }, []);
  useEffect(() => {
    if (!ready || !recoveryKey.current || recovery) return;
    const timer = setTimeout(() => {
      try {
        if (dirty) sessionStorage.setItem(recoveryKey.current, JSON.stringify(value));
        else sessionStorage.removeItem(recoveryKey.current);
      } catch {
        /* Storage full: saving/exporting still works. */
      }
    }, 500);
    return () => clearTimeout(timer);
  }, [dirty, ready, value, recovery]);
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (dirty) {
        e.preventDefault();
        e.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [dirty]);
  const selectedNode = doc.graph.nodes.find((n) => n.id === selected);
  const selectedLink = doc.graph.edges.find((e) => e.id === selectedEdge);
  const activeRun = isActiveRun(run);
  const editingLocked = busy || activeRun || cancelPending;

  useEffect(() => {
    if (!activeRun || !run) return;
    let stopped = false,
      timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const result = await api<Run>(`/api/workflow-runs/${encodeURIComponent(run.id)}`);
        if (stopped) return;
        setRun((current) => (current?.id === result.id ? mergeRun(current, result) : current));
        if (!isActiveRun(result)) {
          notify(
            result.status === 'cancelled'
              ? '已停止工作流运行'
              : result.status === 'completed'
                ? '工作流运行完成'
                : result.error || '工作流运行失败',
            result.status === 'failed',
          );
          return;
        }
      } catch (e) {
        if (!stopped) notify(`运行状态查询失败：${(e as Error).message}`, true);
      }
      if (!stopped) timer = setTimeout(poll, 1500);
    };
    timer = setTimeout(poll, 500);
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [run?.id, activeRun, notify]);

  const save = useCallback(async (): Promise<string | undefined> => {
    if (editingLocked) return;
    setBusy(true);
    const snapshot = toWorkflow(docRef.current.meta, docRef.current.graph, flow.getViewport());
    try {
      let saved: Workflow;
      if (draftId) {
        const updated = await api(
          `/api/workflow-drafts/${encodeURIComponent(draftId)}`,
          { ...snapshot, expected_revision: draftRevision.current },
          'PUT',
        );
        draftRevision.current = updated.revision;
        const result = await api(`/api/workflow-drafts/${encodeURIComponent(draftId)}/save`, {
          expected_revision: updated.revision,
        });
        saved = await api(`/api/resources/workflows/${encodeURIComponent(result.workflow_id)}`);
        setDraftId('');
      } else
        saved = await api(
          `/api/resources/workflows${workflowId ? '/' + encodeURIComponent(workflowId) : ''}`,
          { ...snapshot, expected_version: workflowId ? docRef.current.meta.version || 0 : undefined },
          workflowId ? 'PUT' : 'POST',
        );
      setWorkflowId(saved.id!);
      window.history.replaceState(null, '', `/workflow.html?id=${encodeURIComponent(saved.id!)}`);
      setDoc((current) => ({ ...current, meta: { ...current.meta, id: saved.id, version: saved.version } }));
      setViewport(snapshot.canvas?.viewport);
      setBaseline(signature(snapshot));
      try {
        if (recoveryKey.current) {
          sessionStorage.removeItem(recoveryKey.current);
          recoveryKey.current = `${recoveryKey.current.slice(0, recoveryKey.current.lastIndexOf(':'))}:${saved.id}`;
        }
      } catch {
        /* optional */
      }
      notify(`已保存版本 v${saved.version}`);
      return saved.id;
    } catch (e) {
      reportError(e);
      return undefined;
    } finally {
      setBusy(false);
    }
  }, [editingLocked, workflowId, draftId, flow, notify, reportError]);
  const runWorkflow = async () => {
    if (activeRun || busy || cancelPending) return;
    try {
      const input = inputMode === 'json' ? JSON.parse(testInput) : testInput;
      const result = await api('/api/workflow-validation', value);
      if (result.warnings?.length) notify(result.warnings.join('；'));
      const id = dirty || !workflowId || draftId ? await save() : workflowId;
      if (!id) return;
      setBusy(true);
      setRunTab('trace');
      const queued = await api(`/api/workflows/${encodeURIComponent(id)}/enqueue`, {
        input,
        max_attempts: 1,
      });
      setRun({
        id: queued.run_id,
        workflow_id: id,
        status: 'queued',
        input,
        output: null,
        trace: [],
        created_at: Date.now() / 1000,
        workflow_version: docRef.current.meta.version,
      });
    } catch (e) {
      reportError(e);
    } finally {
      setBusy(false);
    }
  };
  const stopRun = async () => {
    if (!run || !isActiveRun(run) || cancelInFlight.current) return;
    cancelInFlight.current = true;
    setCancelPending(true);
    try {
      const result = await api<{ cancelled: boolean; status: string; run: Run }>(
        `/api/workflow-runs/${encodeURIComponent(run.id)}/cancel`,
        {},
      );
      setRun((current) => (current?.id === result.run.id ? mergeRun(current, result.run) : current));
      notify(
        result.cancelled ? '已停止工作流运行' : `任务状态：${statusLabels[result.status] || result.status}`,
      );
    } catch (e) {
      notify(`停止失败：${(e as Error).message}。可再次点击停止。`, true);
    } finally {
      cancelInFlight.current = false;
      setCancelPending(false);
    }
  };
  const validate = async () => {
    setBusy(true);
    try {
      const result = await api('/api/workflow-validation', value);
      notify(
        result.warnings?.length
          ? `校验通过。${result.warnings.join('；')}`
          : '校验通过：图结构、变量与资源配置有效',
      );
    } catch (e) {
      reportError(e);
    } finally {
      setBusy(false);
    }
  };
  const addNode = (kind: Kind, position?: { x: number; y: number }) => {
    const id = `${kind}_${randomId().slice(0, 12)}`;
    const p = position || flow.screenToFlowPosition({ x: innerWidth * 0.48, y: innerHeight * 0.4 });
    updateDoc((d) => ({
      ...d,
      graph: {
        ...d.graph,
        nodes: [
          ...d.graph.nodes,
          { id, type: 'workflow', position: p, data: { definition: newNode(kind, id) } },
        ],
      },
    }));
    setSelected(id);
    setSelectedEdge('');
    setTab('node');
  };
  const removeSelection = useCallback(() => {
    updateDoc((d) => ({
      ...d,
      graph: {
        nodes: d.graph.nodes.filter((n) => !n.selected && n.id !== selected),
        edges: d.graph.edges.filter(
          (e) =>
            !e.selected &&
            e.id !== selectedEdge &&
            e.source !== selected &&
            e.target !== selected &&
            !d.graph.nodes.some((n) => n.selected && (e.source === n.id || e.target === n.id)),
        ),
      },
    }));
    setSelected('');
    setSelectedEdge('');
  }, [selected, selectedEdge, updateDoc]);
  const duplicate = useCallback(() => {
    const node = docRef.current.graph.nodes.find((n) => n.id === selected);
    if (!node) return;
    const id = `${node.data.definition.type}_${randomId().slice(0, 12)}`;
    updateDoc((d) => ({
      ...d,
      graph: {
        ...d.graph,
        nodes: [
          ...d.graph.nodes,
          {
            ...structuredClone(node),
            id,
            selected: false,
            position: { x: node.position.x + 35, y: node.position.y + 165 },
            data: {
              definition: {
                ...node.data.definition,
                id,
                label: `${node.data.definition.label || kinds[node.data.definition.type].title} 副本`,
              },
            },
          },
        ],
      },
    }));
    setSelected(id);
  }, [selected, updateDoc]);
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (!ready || editingLocked || modal) return;
      const textEditing = (e.target as HTMLElement).matches('input,textarea,select,[contenteditable="true"]');
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
        e.preventDefault();
        void save();
      }
      if (!textEditing && (e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') {
        e.preventDefault();
        undo(e.shiftKey);
      }
      if (!textEditing && (e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'd') {
        e.preventDefault();
        duplicate();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [ready, editingLocked, modal, save, undo, duplicate]);
  const isValidConnection = (
    connection: Connection | { source: string; target: string; sourceHandle?: string | null },
  ) => {
    const { source, target } = connection;
    if (!source || !target || source === target) return false;
    const from = doc.graph.nodes.find((n) => n.id === source),
      to = doc.graph.nodes.find((n) => n.id === target);
    if (!from || !to || from.data.definition.type === 'output' || to.data.definition.type === 'input')
      return false;
    if (
      doc.graph.edges.some(
        (e) => e.source === source && e.target === target && e.sourceHandle === connection.sourceHandle,
      )
    )
      return false;
    return !hasCycle({ ...doc.graph, edges: [...doc.graph.edges, { id: 'candidate', source, target }] });
  };
  const connect = (connection: Connection) => {
    if (!isValidConnection(connection)) {
      notify('此连线会形成环、重复连接或连接了错误的端口', true);
      return;
    }
    const branch =
      connection.sourceHandle === 'true' ? true : connection.sourceHandle === 'false' ? false : undefined;
    const edge = {
      ...connection,
      id: randomId(),
      type: 'smoothstep',
      label: branch === undefined ? undefined : branch ? '是' : '否',
      data: {
        definition: {
          source: connection.source,
          target: connection.target,
          ...(branch === undefined ? {} : { when: branch }),
        },
      },
    };
    updateDoc((d) => ({ ...d, graph: { ...d.graph, edges: [...d.graph.edges, edge] } }));
  };
  const importValue = (imported: Workflow) => {
    const next = {
      ...doc.meta,
      ...imported,
      canvas: imported.canvas,
      version: doc.meta.version,
      name: imported.name || doc.meta.name,
    };
    const graph = fromWorkflow(next);
    updateDoc(() => ({ meta: next, graph }));
    setViewport(next.canvas?.viewport);
    setSelected('');
    setSelectedEdge('');
    if (!activeRun) setRun(undefined);
    requestAnimationFrame(() =>
      next.canvas?.viewport
        ? void flow.setViewport(next.canvas.viewport)
        : void flow.fitView({ padding: 0.2 }),
    );
  };
  const exportJSON = () => {
    const blob = new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${doc.meta.name || 'workflow'}.json`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const showVersions = async () => {
    try {
      const result = await api(`/api/workflows/${encodeURIComponent(workflowId)}/versions`);
      setVersions(result.data || result.versions || []);
      setModal('versions');
    } catch (e) {
      notify((e as Error).message, true);
    }
  };
  const showRuns = async () => {
    setRunTab('history');
    if (!workflowId) {
      setRuns([]);
      return;
    }
    try {
      const result = await api(`/api/workflow-runs?workflow_id=${encodeURIComponent(workflowId)}`);
      setRuns(result.data || []);
    } catch (e) {
      notify((e as Error).message, true);
    }
  };
  const traces = new Map(
    (run?.workflow_version && run.workflow_version !== doc.meta.version ? [] : run?.trace || []).map((t) => [
      t.node_id,
      t,
    ]),
  );
  const displayNodes = doc.graph.nodes.map((n) => ({
    ...n,
    data: { ...n.data, status: traces.get(n.id)?.status, issue: issues[n.id] },
  }));
  const displayEdges = doc.graph.edges.map((e) => ({
    ...e,
    animated: traces.get(e.source)?.status === 'running',
    className:
      traces.get(e.target)?.status === 'skipped'
        ? 'edge-skipped'
        : traces.get(e.target)?.status === 'completed'
          ? 'edge-completed'
          : '',
  }));

  if (loadError)
    return (
      <main className="load-screen">
        <WorkflowIcon size={36} />
        <h1>无法打开工作流</h1>
        <p>{loadError}</p>
        <div>
          <a className="secondary" href="/workbench.html#workflows">
            返回工作台
          </a>
          <button className="primary" onClick={() => location.reload()}>
            重试
          </button>
        </div>
      </main>
    );
  if (!ready)
    return (
      <main className="load-screen">
        <LoaderCircle size={30} className="spin" />
        <h1>正在准备工作流画布</h1>
        <p>读取节点、资源和画布布局…</p>
      </main>
    );
  return (
    <main className="editor-shell">
      <header className="topbar">
        <a className="back-link" href="/workbench.html#workflows" aria-label="返回工作流列表">
          <ArrowLeft size={18} />
        </a>
        <span className="brand">
          C<span>z</span>
        </span>
        <span className="breadcrumb">
          工作流
          <ChevronRight size={14} />
        </span>
        <div className="title-group">
          <input
            disabled={editingLocked}
            aria-label="工作流名称"
            value={doc.meta.name}
            maxLength={100}
            onChange={(e) => updateDoc((d) => ({ ...d, meta: { ...d.meta, name: e.target.value } }))}
          />
          <span className={`save-state ${dirty ? 'unsaved' : ''}`}>
            <i />
            {draftId ? 'Agent 草稿' : dirty ? '有未保存的更改' : `已保存 · v${doc.meta.version || 0}`}
          </span>
        </div>
        <div className="top-actions">
          <button className="secondary" disabled={editingLocked} onClick={validate}>
            <CheckCircle2 size={16} />
            <span>校验</span>
          </button>
          <button className="secondary" disabled={editingLocked} onClick={() => void save()}>
            {busy ? <LoaderCircle size={16} className="spin" /> : <Save size={16} />}
            <span>保存</span>
          </button>
          <button className="primary" onClick={() => setRunOpen((v) => !v)}>
            <Play size={15} fill="currentColor" />
            <span>测试运行</span>
          </button>
        </div>
      </header>
      <div className="workspace">
        <aside className="palette">
          <div className="section-heading">
            <span>节点库</span>
            <small>8 个节点</small>
          </div>
          <label className="palette-search">
            <Search size={15} />
            <input
              aria-label="搜索节点"
              placeholder="搜索节点…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
          <p className="palette-hint">点击添加，或拖到画布</p>
          {isBranchDemo(doc.graph) && (
            <div className="workflow-notice">
              <strong>当前是规则路由演示</strong>
              <p>还没有接入智能体回答。打开工作流设置可升级为智能分支问答。</p>
              <button className="secondary full" onClick={() => setTab('settings')}>
                配置智能问答
              </button>
            </div>
          )}
          <div className="palette-items">
            {(Object.keys(kinds) as Kind[])
              .filter((k) => `${kinds[k].title}${kinds[k].code}`.toLowerCase().includes(search.toLowerCase()))
              .map((kind) => {
                const info = kinds[kind],
                  Icon = icons[kind];
                return (
                  <button
                    className="palette-item"
                    key={kind}
                    draggable
                    disabled={editingLocked}
                    onDragStart={(e) => {
                      e.dataTransfer.setData('application/codezzn-node', kind);
                      e.dataTransfer.effectAllowed = 'move';
                    }}
                    onClick={() => addNode(kind)}
                  >
                    <span className="palette-icon" style={{ color: info.color }}>
                      <Icon size={18} />
                    </span>
                    <span>
                      <strong>{info.title}</strong>
                      <small>{info.subtitle}</small>
                    </span>
                    <Plus size={13} />
                  </button>
                );
              })}
          </div>
          <div className="palette-bottom">
            <button className="secondary full" disabled={editingLocked} onClick={() => setModal('templates')}>
              <LayoutGrid size={16} />
              从模板开始
            </button>
            <p>连线决定顺序，变量传递数据。</p>
            <button className="quiet full" onClick={() => setModal('help')}>
              <CircleHelp size={15} />
              画布操作与快捷键
            </button>
          </div>
        </aside>
        <section
          className="canvas-region"
          aria-label="工作流画布"
          onDragOver={(e) => {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
          }}
          onDrop={(e) => {
            e.preventDefault();
            const kind = e.dataTransfer.getData('application/codezzn-node') as Kind;
            if (Object.hasOwn(kinds, kind) && !editingLocked)
              addNode(kind, flow.screenToFlowPosition({ x: e.clientX, y: e.clientY }));
          }}
        >
          <div className="canvas-toolbar">
            <div className="toolbar-group">
              <button
                className="icon-button"
                title="撤销 Ctrl+Z"
                aria-label="撤销"
                disabled={!history.current.past.length || editingLocked}
                onClick={() => undo()}
              >
                <Undo2 size={17} />
              </button>
              <button
                className="icon-button"
                title="重做 Ctrl+Shift+Z"
                aria-label="重做"
                disabled={!history.current.future.length || editingLocked}
                onClick={() => undo(true)}
              >
                <Redo2 size={17} />
              </button>
              <span className="divider" />
              <button
                className="quiet"
                disabled={editingLocked}
                onClick={() => {
                  updateDoc((d) => ({ ...d, graph: layout(d.graph) }));
                  setTimeout(() => void flow.fitView({ padding: 0.2, duration: 250 }), 50);
                }}
              >
                <LayoutGrid size={15} />
                自动布局
              </button>
            </div>
            <div className="toolbar-group">
              <button
                className="quiet"
                disabled={editingLocked}
                onClick={() => {
                  setJson(JSON.stringify(value, null, 2));
                  setJsonError('');
                  setModal('json');
                }}
              >
                <Code2 size={15} />
                JSON
              </button>
              <button
                className="icon-button"
                title="导入 JSON"
                aria-label="导入 JSON"
                disabled={editingLocked}
                onClick={() => fileInput.current?.click()}
              >
                <Upload size={16} />
              </button>
              <button className="icon-button" title="导出 JSON" aria-label="导出 JSON" onClick={exportJSON}>
                <Download size={16} />
              </button>
              <button
                className="icon-button"
                title="版本历史"
                aria-label="版本历史"
                disabled={!workflowId || editingLocked}
                onClick={showVersions}
              >
                <History size={16} />
              </button>
            </div>
          </div>
          {recovery && (
            <div className="recovery-banner">
              <span>检测到本标签页未保存的编辑。</span>
              <button
                onClick={() => {
                  try {
                    importValue(recovery);
                    setRecovery(undefined);
                  } catch (e) {
                    notify((e as Error).message, true);
                  }
                }}
              >
                恢复编辑
              </button>
              <button
                onClick={() => {
                  setRecovery(undefined);
                  try {
                    sessionStorage.removeItem(recoveryKey.current);
                  } catch {
                    /* optional */
                  }
                }}
              >
                丢弃
              </button>
            </div>
          )}
          <ReactFlow
            nodes={displayNodes}
            edges={displayEdges}
            nodeTypes={nodeTypes}
            colorMode="light"
            minZoom={0.1}
            maxZoom={4}
            defaultViewport={doc.meta.canvas?.viewport}
            fitView={!doc.meta.canvas?.viewport}
            fitViewOptions={{ padding: 0.2 }}
            nodesDraggable={!editingLocked}
            nodesConnectable={!editingLocked}
            deleteKeyCode={editingLocked ? null : ['Backspace', 'Delete']}
            isValidConnection={isValidConnection}
            onConnect={connect}
            onNodesChange={(changes) => {
              const deleting = changes.some((c) => c.type === 'remove');
              updateDoc((d) => {
                const nodes = applyNodeChanges(changes, d.graph.nodes);
                const ids = new Set(nodes.map((n) => n.id));
                return {
                  ...d,
                  graph: {
                    nodes,
                    edges: d.graph.edges.filter((e) => ids.has(e.source) && ids.has(e.target)),
                  },
                };
              }, deleting);
            }}
            onEdgesChange={(changes) =>
              updateDoc(
                (d) => ({ ...d, graph: { ...d.graph, edges: applyEdgeChanges(changes, d.graph.edges) } }),
                changes.some((c) => c.type === 'remove'),
              )
            }
            onNodeDragStart={() => {
              history.current.past.push(structuredClone(doc));
              history.current.future = [];
              setHistoryTick(historyTick + 1);
            }}
            onNodeClick={(_, node) => {
              setSelected(node.id);
              setSelectedEdge('');
              setTab('node');
            }}
            onEdgeClick={(_, edge) => {
              setSelectedEdge(edge.id);
              setSelected('');
              setTab('node');
            }}
            onPaneClick={() => {
              setSelected('');
              setSelectedEdge('');
            }}
            onMoveEnd={(_, next) => setViewport(next)}
            onInit={(instance) => {
              if (doc.meta.canvas?.viewport) void instance.setViewport(doc.meta.canvas.viewport);
            }}
            proOptions={{ hideAttribution: false }}
          >
            <Background variant={BackgroundVariant.Dots} gap={22} size={1} color="#d1d5db" />
            <Controls showInteractive={false} />
            <MiniMap
              nodeColor={(n) => kinds[(n.data.definition as any).type as Kind].color}
              maskColor="rgba(248,249,253,.75)"
              pannable
              zoomable
            />
            <Panel position="bottom-center">
              <span className="canvas-footnote">
                {doc.graph.nodes.length} 节点 · {doc.graph.edges.length} 连线
                <span>拖动画布平移 · 滚轮缩放</span>
              </span>
            </Panel>
          </ReactFlow>
          {runOpen && (
            <section className="run-panel" aria-label="工作流测试">
              <div className="run-panel-header">
                <div>
                  <Play size={15} />
                  <strong>测试工作流</strong>
                  {run && (
                    <span className={`run-status ${run.status}`}>
                      {statusLabels[run.status] || run.status}
                      {run.workflow_version ? ` · v${run.workflow_version}` : ''}
                    </span>
                  )}
                </div>
                <div>
                  {(activeRun || cancelPending) && (
                    <button
                      type="button"
                      className="secondary danger"
                      disabled={cancelPending}
                      aria-busy={cancelPending}
                      onClick={stopRun}
                    >
                      {cancelPending && <LoaderCircle size={14} className="spin" />}
                      {cancelPending ? '正在停止…' : '停止运行'}
                    </button>
                  )}
                  <button className="icon-button" aria-label="关闭测试面板" onClick={() => setRunOpen(false)}>
                    <X size={17} />
                  </button>
                </div>
              </div>
              <div className="run-body">
                <div className="test-input">
                  <div className="section-heading">
                    <label htmlFor="test-input">工作流输入</label>
                    <select
                      aria-label="输入格式"
                      value={inputMode}
                      onChange={(e) => setInputMode(e.target.value)}
                    >
                      <option value="text">文本</option>
                      <option value="json">JSON</option>
                    </select>
                  </div>
                  <textarea
                    id="test-input"
                    placeholder="输入你的测试问题"
                    value={testInput}
                    onChange={(e) => setTestInput(e.target.value)}
                  />
                  <button
                    className="primary full"
                    disabled={busy || activeRun || cancelPending}
                    onClick={runWorkflow}
                  >
                    {activeRun ? <LoaderCircle size={14} className="spin" /> : <Play size={14} />}
                    {activeRun
                      ? '正在执行…'
                      : dirty || !workflowId || draftId
                        ? '保存并运行'
                        : '运行当前版本'}
                  </button>
                  <small>测试调用实际模型和工具。后台任务会在关闭面板后继续。</small>
                </div>
                <div className="test-results">
                  <nav className="result-tabs">
                    <button
                      className={runTab === 'output' ? 'active' : ''}
                      onClick={() => setRunTab('output')}
                    >
                      最终输出
                    </button>
                    <button className={runTab === 'trace' ? 'active' : ''} onClick={() => setRunTab('trace')}>
                      节点日志 <small>{run?.trace?.length || 0}</small>
                    </button>
                    <button className={runTab === 'history' ? 'active' : ''} onClick={showRuns}>
                      运行历史
                    </button>
                    {run && <code title={run.id}>{run.id.slice(0, 15)}</code>}
                  </nav>
                  <div className="result-scroll">
                    {runTab === 'output' &&
                      (run ? (
                        <>
                          {run.error && <p className="error-text">{run.error}</p>}
                          <pre>
                            {run.status === 'cancelled'
                              ? '运行已停止，可在节点日志查看停止前的执行记录。'
                              : activeRun
                                ? '正在执行，完成后在这里显示结果…'
                                : pretty(run.output)}
                          </pre>
                        </>
                      ) : (
                        <div className="result-empty">
                          <Play size={24} />
                          <strong>准备好运行了</strong>
                          <p>输入测试内容，观察每个节点的结果。</p>
                        </div>
                      ))}
                    {runTab === 'trace' &&
                      ((run?.trace || []).length ? (
                        run!.trace!.map((t) => (
                          <details className={`trace-record ${t.status}`} key={t.node_id}>
                            <summary>
                              <span className={`status-dot ${t.status}`} />
                              <button
                                onClick={(e) => {
                                  e.preventDefault();
                                  setSelected(t.node_id);
                                  setTab('node');
                                  void flow.fitView({
                                    nodes: [{ id: t.node_id }],
                                    duration: 250,
                                    maxZoom: 1.2,
                                  });
                                }}
                              >
                                {doc.graph.nodes.find((n) => n.id === t.node_id)?.data.definition.label ||
                                  t.node_id}
                              </button>
                              <code>{t.node_id}</code>
                              <span>
                                {statusLabels[t.status]}
                                {t.attempts ? ` · ${t.attempts} 次` : ''}
                                {t.elapsed_ms !== undefined
                                  ? ` · ${(t.elapsed_ms / 1000).toFixed(2)}s`
                                  : t.completed_at && t.started_at
                                    ? ` · ${t.completed_at - t.started_at}s`
                                    : ''}
                              </span>
                            </summary>
                            {t.agent_name && (
                              <p className="trace-model">
                                {t.agent_name}
                                {t.runtime?.model ? ` · ${t.runtime.model}` : ''}
                                {t.runtime?.provider ? ` · ${t.runtime.provider}` : ''}
                              </p>
                            )}
                            <pre>
                              {t.error ||
                                (t.status === 'skipped' ? '上游条件不匹配，节点已跳过。' : pretty(t.output))}
                            </pre>
                            {t.retrieval && <pre>{pretty(t.retrieval)}</pre>}
                          </details>
                        ))
                      ) : (
                        <div className="result-empty">
                          {activeRun ? '任务已入队，等待节点开始…' : '运行后查看节点输出、耗时和错误。'}
                        </div>
                      ))}
                    {runTab === 'history' &&
                      (runs.length ? (
                        runs.map((r) => (
                          <button
                            className="run-history-row"
                            key={r.id}
                            disabled={editingLocked}
                            title={activeRun ? '请先停止或等待当前运行完成，再查看其他运行详情' : undefined}
                            onClick={() => {
                              setRun(r);
                              setRunTab('output');
                            }}
                          >
                            <span className={`status-dot ${r.status}`} />
                            <div>
                              <strong>{pretty(r.input).slice(0, 48)}</strong>
                              <small>{new Date(r.created_at * 1000).toLocaleString()}</small>
                            </div>
                            <span>{statusLabels[r.status]}</span>
                            <ChevronRight size={15} />
                          </button>
                        ))
                      ) : (
                        <div className="result-empty">尚无运行记录。</div>
                      ))}
                  </div>
                </div>
              </div>
            </section>
          )}
        </section>
        <aside className="inspector">
          <nav className="inspector-tabs">
            <button className={tab === 'node' ? 'active' : ''} onClick={() => setTab('node')}>
              <Settings2 size={15} />
              节点配置
            </button>
            <button className={tab === 'settings' ? 'active' : ''} onClick={() => setTab('settings')}>
              <WorkflowIcon size={15} />
              流程设置
            </button>
          </nav>
          <fieldset disabled={editingLocked} className="inspector-content">
            {tab === 'node' ? (
              selectedNode ? (
                <NodeInspector
                  key={selectedNode.id}
                  node={selectedNode}
                  graph={doc.graph}
                  resources={resources}
                  update={(patch) =>
                    updateDoc((d) => ({
                      ...d,
                      graph: {
                        ...d.graph,
                        nodes: d.graph.nodes.map((n) =>
                          n.id === selected
                            ? { ...n, data: { definition: { ...n.data.definition, ...patch } } }
                            : n,
                        ),
                      },
                    }))
                  }
                  duplicate={duplicate}
                  remove={removeSelection}
                />
              ) : selectedLink ? (
                <>
                  <h3>连线配置</h3>
                  <p className="info-note">
                    <code>{selectedLink.source}</code>
                    <ChevronRight size={13} />
                    <code>{selectedLink.target}</code>
                  </p>
                  {['condition', 'router'].includes(
                    doc.graph.nodes.find((n) => n.id === selectedLink.source)?.data.definition.type || '',
                  ) && (
                    <Field label="分支条件">
                      <select
                        aria-label="分支条件"
                        value={
                          selectedLink.data?.definition.when === undefined
                            ? 'always'
                            : branchValue(selectedLink.data.definition.when)
                              ? 'true'
                              : 'false'
                        }
                        onChange={(e) => {
                          const when = e.target.value;
                          updateDoc((d) => ({
                            ...d,
                            graph: {
                              ...d.graph,
                              edges: d.graph.edges.map((edge) => {
                                if (edge.id !== selectedEdge) return edge;
                                const definition = { ...edge.data!.definition };
                                delete definition.when;
                                if (when !== 'always') definition.when = when === 'true';
                                return {
                                  ...edge,
                                  sourceHandle: when === 'always' ? 'out' : when,
                                  label: when === 'always' ? undefined : when === 'true' ? '是' : '否',
                                  data: { definition },
                                };
                              }),
                            },
                          }));
                        }}
                      >
                        <option value="true">是 · 条件成立</option>
                        <option value="false">否 · 条件不成立</option>
                        <option value="always">总是执行（兼容旧 JSON）</option>
                      </select>
                    </Field>
                  )}
                  <button className="danger secondary full" onClick={removeSelection}>
                    <Trash2 size={15} />
                    删除连线
                  </button>
                </>
              ) : (
                <div className="inspector-empty">
                  <Settings2 size={29} />
                  <h3>选中节点开始配置</h3>
                  <p>在画布中点击节点，配置模型、知识库、工具或变量。</p>
                  <button className="secondary" onClick={() => setModal('templates')}>
                    查看工作流模板
                  </button>
                </div>
              )
            ) : (
              <>
                <div className="inspector-title">
                  <span className="node-icon">
                    <WorkflowIcon size={19} />
                  </span>
                  <div>
                    <strong>工作流设置</strong>
                    <small>定义可重复运行的任务</small>
                  </div>
                </div>
                <Field label="描述">
                  <textarea
                    aria-label="工作流描述"
                    rows={4}
                    maxLength={2000}
                    placeholder="描述这个工作流的用途…"
                    value={doc.meta.description || ''}
                    onChange={(e) =>
                      updateDoc((d) => ({ ...d, meta: { ...d.meta, description: e.target.value } }))
                    }
                  />
                </Field>
                {!doc.graph.nodes.some((n) => n.data.definition.type === 'agent') && (
                  <div className="workflow-notice">
                    <strong>此流程还没有智能体回答节点</strong>
                    <p>文本模板、条件和输出节点只处理数据，不会生成模型回答。</p>
                    {isBranchDemo(doc.graph) && (
                      <button
                        className="secondary full"
                        onClick={() => {
                          importValue({ ...template('smart-rag'), name: doc.meta.name });
                          setTab('settings');
                          notify('已升级画布，请选择智能体和知识库，再保存为新版本');
                        }}
                      >
                        升级为智能分支问答
                      </button>
                    )}
                  </div>
                )}
                {doc.graph.nodes.some((n) => ['agent', 'router'].includes(n.data.definition.type)) && (
                  <Field
                    label="统一选择智能体"
                    hint="为所有回答与决策节点设置同一个 Agent；也可在每个节点中单独更改。"
                  >
                    <select
                      aria-label="统一选择智能体"
                      value={(() => {
                        const ids = [
                          ...new Set(
                            doc.graph.nodes
                              .filter((n) => ['agent', 'router'].includes(n.data.definition.type))
                              .map((n) => n.data.definition.agent_id || ''),
                          ),
                        ];
                        return ids.length === 1 ? ids[0] : '';
                      })()}
                      onChange={(e) =>
                        updateDoc((d) => ({
                          ...d,
                          graph: {
                            ...d.graph,
                            nodes: d.graph.nodes.map((n) =>
                              ['agent', 'router'].includes(n.data.definition.type)
                                ? {
                                    ...n,
                                    data: {
                                      ...n.data,
                                      definition: { ...n.data.definition, agent_id: e.target.value },
                                    },
                                  }
                                : n,
                            ),
                          },
                        }))
                      }
                    >
                      <option value="">请选择（或当前使用多个智能体）</option>
                      {resources.agents.map((a) => (
                        <option key={a.id} value={a.id} disabled={a.enabled === false}>
                          {a.name}
                          {a.model ? ` · ${a.model}` : ''}
                        </option>
                      ))}
                    </select>
                  </Field>
                )}
                {doc.graph.nodes.some((n) => ['knowledge', 'router'].includes(n.data.definition.type)) && (
                  <Field
                    label="统一选择知识库"
                    hint="同步设置检索决策范围和检索节点；需要不同范围时可单独修改节点。"
                  >
                    <div className="check-list">
                      {resources.knowledge.map((k) => (
                        <label key={k.id}>
                          <input
                            type="checkbox"
                            disabled={k.enabled === false}
                            checked={doc.graph.nodes
                              .filter((n) => ['knowledge', 'router'].includes(n.data.definition.type))
                              .every((n) => n.data.definition.knowledge_ids?.includes(k.id))}
                            onChange={(e) =>
                              updateDoc((d) => ({
                                ...d,
                                graph: {
                                  ...d.graph,
                                  nodes: d.graph.nodes.map((n) => {
                                    if (!['knowledge', 'router'].includes(n.data.definition.type)) return n;
                                    const ids = n.data.definition.knowledge_ids || [];
                                    return {
                                      ...n,
                                      data: {
                                        ...n.data,
                                        definition: {
                                          ...n.data.definition,
                                          knowledge_ids: e.target.checked
                                            ? [...new Set([...ids, k.id])]
                                            : ids.filter((id) => id !== k.id),
                                        },
                                      },
                                    };
                                  }),
                                },
                              }))
                            }
                          />
                          {k.name}
                          <small className="knowledge-backend">
                            {k.backend === 'ragflow' ? 'RAGFlow' : '本地'}
                          </small>
                        </label>
                      ))}
                      {!resources.knowledge.length && <small>请先在工作台创建知识库。</small>}
                    </div>
                    <small>本地知识库需在工作台选择“本地 Milvus”后端创建并上传文档。</small>
                  </Field>
                )}
                <Field label="最大并发数" hint="同一批就绪节点可同时执行，范围 1–16。">
                  <input
                    aria-label="最大并发数"
                    type="number"
                    min={1}
                    max={16}
                    value={doc.meta.max_parallel ?? 4}
                    onChange={(e) =>
                      updateDoc((d) => ({ ...d, meta: { ...d.meta, max_parallel: Number(e.target.value) } }))
                    }
                  />
                </Field>
                <Field label="关联项目">
                  <select
                    aria-label="关联项目"
                    value={doc.meta.project_id || ''}
                    disabled={!!draftId}
                    onChange={(e) =>
                      updateDoc((d) => ({ ...d, meta: { ...d.meta, project_id: e.target.value || null } }))
                    }
                  >
                    <option value="">独立工作流</option>
                    {resources.projects.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                </Field>
                <label className="toggle-field">
                  <input
                    type="checkbox"
                    checked={doc.meta.enabled !== false}
                    onChange={(e) =>
                      updateDoc((d) => ({ ...d, meta: { ...d.meta, enabled: e.target.checked } }))
                    }
                  />
                  <span>
                    <strong>启用工作流</strong>
                    <small>允许在工作台和 Agent 中调用</small>
                  </span>
                </label>
                <section className="workflow-guide">
                  <span className="eyebrow">HOW IT WORKS</span>
                  <h3>让每一步都有明确去向</h3>
                  <ol>
                    <li>从左侧添加节点并连线</li>
                    <li>配置节点，引用上游变量</li>
                    <li>校验、保存，然后测试运行</li>
                  </ol>
                  <p>画布和 JSON 使用同一份定义，可在两种编辑方式之间切换。</p>
                </section>
                {workflowId && (
                  <Field label="工作流 ID">
                    <input readOnly className="code-input" value={workflowId} />
                  </Field>
                )}
              </>
            )}
            {resourceError && (
              <p className="error-text" role="alert">
                {resourceError}
              </p>
            )}
            <button className="quiet full refresh-resources" onClick={() => void refreshResources()}>
              <RefreshCw size={14} />
              刷新智能体与知识库资源
            </button>
          </fieldset>
        </aside>
      </div>
      <input
        ref={fileInput}
        type="file"
        accept=".json,application/json"
        hidden
        onChange={async (e) => {
          const file = e.target.files?.[0];
          if (!file) return;
          try {
            if (file.size > 2 * 1024 * 1024) throw new Error('JSON 文件不能超过 2 MB');
            const imported = JSON.parse(await file.text());
            importValue(imported);
            notify('JSON 已导入，请检查资源配置后保存');
          } catch (error) {
            notify((error as Error).message, true);
          } finally {
            e.target.value = '';
          }
        }}
      />
      {message && (
        <div className={`toast ${message.error ? 'error' : ''}`} role={message.error ? 'alert' : 'status'}>
          <span>{message.text}</span>
          <button className="icon-button" aria-label="关闭提示" onClick={() => setMessage(undefined)}>
            <X size={15} />
          </button>
        </div>
      )}
      {modal === 'json' && (
        <Dialog title="编辑工作流 JSON" close={() => setModal('')} wide>
          <p className="modal-note">保留旧 JSON 格式。canvas 用于保存节点坐标与视口；应用后请保存工作流。</p>
          <textarea
            className="json-editor"
            aria-label="工作流 JSON"
            spellCheck={false}
            value={json}
            onChange={(e) => setJson(e.target.value)}
          />
          {jsonError && (
            <p className="error-text" role="alert">
              {jsonError}
            </p>
          )}
          <footer>
            <button className="secondary" onClick={() => setModal('')}>
              取消
            </button>
            <button
              className="primary"
              onClick={() => {
                try {
                  importValue(JSON.parse(json));
                  setModal('');
                  notify('JSON 已应用到画布');
                } catch (e) {
                  setJsonError((e as Error).message);
                }
              }}
            >
              应用到画布
            </button>
          </footer>
        </Dialog>
      )}
      {modal === 'templates' && (
        <Dialog title="选择工作流模板" close={() => setModal('')}>
          <p className="modal-note">模板将替换当前画布；可以使用撤销恢复之前的编辑。</p>
          <div className="template-list">
            {[
              ['chat', '智能体问答', '输入 → 智能体 → 输出。选择 Agent 后即可得到真实回答。', icons.agent],
              [
                'smart-rag',
                '智能分支问答',
                '模型判断检索需求；检索和直接回答两条路径均接入 Agent。',
                icons.router,
              ],
              ['hello', '入门 · 文本处理', '输入 → 模板 → 输出。无需 API 密钥，可立即运行。', Braces],
              [
                'branch',
                '规则分支 · 路由演示',
                '仅演示文本匹配与分支，不调用模型，不生成智能回答。',
                icons.condition,
              ],
              ['rag', '知识库问答', '检索 → 智能体 → 输出。需要选择知识库与智能体。', BookOpenIcon],
            ].map(([name, title, description, Icon]) => {
              const Component = Icon as typeof Braces;
              return (
                <button
                  className="template-card"
                  key={String(name)}
                  onClick={() => {
                    importValue(template(String(name)));
                    setModal('');
                  }}
                >
                  <Component size={23} />
                  <div>
                    <strong>{String(title)}</strong>
                    <p>{String(description)}</p>
                  </div>
                  <ChevronRight size={18} />
                </button>
              );
            })}
          </div>
        </Dialog>
      )}
      {modal === 'versions' && (
        <Dialog title="工作流版本历史" close={() => setModal('')}>
          <p className="modal-note">载入版本用于预览和编辑；点击保存后生成新版本。</p>
          <div className="version-list">
            {versions.length ? (
              versions.map((v) => (
                <button
                  className="run-history-row"
                  key={v.version}
                  onClick={async () => {
                    try {
                      const definition = await api(
                        `/api/workflows/${encodeURIComponent(workflowId)}/versions/${v.version}`,
                      );
                      importValue(definition);
                      setModal('');
                      notify(`已载入 v${v.version}，保存后将生成新版本`);
                    } catch (e) {
                      notify((e as Error).message, true);
                    }
                  }}
                >
                  <History size={18} />
                  <div>
                    <strong>版本 v{v.version}</strong>
                    <small>{new Date(v.created_at * 1000).toLocaleString()}</small>
                  </div>
                  <span>载入画布</span>
                  <ChevronRight size={15} />
                </button>
              ))
            ) : (
              <p>旧工作流将在首次画布保存后开始记录版本。</p>
            )}
          </div>
        </Dialog>
      )}
      {modal === 'help' && (
        <Dialog title="画布使用指南" close={() => setModal('')}>
          <div className="help-content">
            <p>
              点击或拖动左侧节点添加到画布。从节点右侧端口拖向下一个节点左侧端口建立连线。选中连线按 Delete
              可删除；条件节点右侧有「是」和「否」两条分支。
            </p>
            <dl>
              <dt>保存</dt>
              <dd>Ctrl / ⌘ + S</dd>
              <dt>撤销 / 重做</dt>
              <dd>Ctrl / ⌘ + Z / Shift + Z</dd>
              <dt>复制节点</dt>
              <dd>Ctrl / ⌘ + D</dd>
              <dt>删除选中节点或连线</dt>
              <dd>Delete / Backspace</dd>
              <dt>平移 / 缩放</dt>
              <dd>拖动空白处 / 滚轮</dd>
              <dt>多选</dt>
              <dd>Shift + 点击</dd>
            </dl>
            <p>
              连线控制执行顺序，变量控制传递内容。使用右侧变量选择器插入 <code>{'{{节点ID}}'}</code>，支持{' '}
              <code>{'{{节点ID.字段}}'}</code>。分支汇合会等待全部上游结束，再收集执行过的分支。
            </p>
            <p>
              知识检索节点可明确检索范围；智能体本身的自动检索设置也会生效。请检查智能体的知识库配置，避免重复检索。
            </p>
          </div>
        </Dialog>
      )}
    </main>
  );
}
const BookOpenIcon = icons.knowledge;

class ErrorBoundary extends React.Component<{ children: React.ReactNode }, { error: string }> {
  state = { error: '' };
  static getDerivedStateFromError(error: Error) {
    return { error: error.message };
  }
  render() {
    return this.state.error ? (
      <main className="load-screen">
        <h1>画布加载出错</h1>
        <p>{this.state.error}</p>
        <a href="/workbench.html#workflows">返回工作台</a>
      </main>
    ) : (
      this.props.children
    );
  }
}
createRoot(document.getElementById('root')!).render(
  <ErrorBoundary>
    <ReactFlowProvider>
      <App />
    </ReactFlowProvider>
  </ErrorBoundary>,
);
