import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import {
  ArrowRight,
  Bot,
  BookOpen,
  GitBranch,
  Braces,
  Combine,
  LogIn,
  LogOut,
  Copy,
  Trash2,
  X,
  Check,
  AlertCircle,
  LoaderCircle,
} from 'lucide-react';
import { ancestors, kinds, type CanvasNode, type DefinitionNode, type Graph, type Kind } from './model';
import { api } from './api';

export const icons = {
  input: LogIn,
  prompt: Braces,
  agent: Bot,
  knowledge: BookOpen,
  condition: GitBranch,
  router: GitBranch,
  mcp: ArrowRight,
  parallel: Combine,
  output: LogOut,
};
export const statusLabels: Record<string, string> = {
  queued: '排队中',
  running: '运行中',
  completed: '已完成',
  failed: '失败',
  skipped: '已跳过',
  cancelled: '已取消',
};
export function NodeCard({ data, selected }: NodeProps<CanvasNode>) {
  const n = data.definition,
    info = kinds[n.type],
    Icon = icons[n.type];
  const summary =
    n.type === 'agent'
      ? '执行智能体任务'
      : n.type === 'knowledge'
        ? `${n.knowledge_ids?.length || 0} 个知识库 · Top ${n.limit || 5}`
        : n.type === 'router'
          ? `${n.agent_id ? '模型决策' : '请选择决策智能体'} · ${n.knowledge_ids?.length || 0} 个知识库范围`
          : n.type === 'condition'
            ? `${n.value || '{{input}}'} ${n.operator || 'equals'} ${n.equals || ''}`
            : n.type === 'mcp'
              ? n.tool || '选择 MCP 工具'
              : n.type === 'parallel'
                ? '等待分支完成并收集结果'
                : n.template || (n.type === 'input' ? '接收测试或 API 输入' : info.subtitle);
  return (
    <article
      className={`node-card ${selected ? 'selected' : ''} ${data.status || ''} ${data.issue ? 'has-issue' : ''}`}
      style={{ '--node-color': info.color } as React.CSSProperties}
    >
      {n.type !== 'input' && (
        <Handle
          type="target"
          position={Position.Left}
          id="in"
          aria-label={`${n.label || info.title}输入端口`}
        />
      )}
      <div className="node-card-head">
        <span className="node-icon">
          <Icon size={18} />
        </span>
        <strong>{n.label || info.title}</strong>
        <small>{info.code}</small>
      </div>
      <div className="node-summary">{summary}</div>
      <footer>
        <code>{n.id}</code>
        {data.status ? (
          <span className={`run-status ${data.status}`}>
            {data.status === 'running' ? (
              <LoaderCircle size={12} className="spin" />
            ) : data.status === 'completed' ? (
              <Check size={12} />
            ) : data.status === 'failed' ? (
              <AlertCircle size={12} />
            ) : null}
            {statusLabels[data.status] || data.status}
          </span>
        ) : (
          <span>{info.title}</span>
        )}
      </footer>
      {['condition', 'router'].includes(n.type) ? (
        <>
          <span className="port-label yes">是</span>
          <Handle
            type="source"
            position={Position.Right}
            id="true"
            style={{ top: '39%' }}
            aria-label="条件成立"
          />
          <span className="port-label no">否</span>
          <Handle
            type="source"
            position={Position.Right}
            id="false"
            style={{ top: '76%' }}
            aria-label="条件不成立"
          />
          <Handle
            type="source"
            position={Position.Bottom}
            id="out"
            title="总是执行（兼容无 when 的旧连线）"
            aria-label="总是执行"
          />
        </>
      ) : (
        n.type !== 'output' && (
          <Handle
            type="source"
            position={Position.Right}
            id="out"
            aria-label={`${n.label || info.title}输出端口`}
          />
        )
      )}
    </article>
  );
}

export interface Resource {
  id: string;
  name: string;
  enabled?: boolean;
  model?: string;
  backend?: string;
}
export interface Resources {
  agents: Resource[];
  knowledge: Resource[];
  mcp_servers: Resource[];
  projects: Resource[];
}
export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
      {hint && <small>{hint}</small>}
    </label>
  );
}

function JsonField({
  value,
  onChange,
}: {
  value: Record<string, unknown>;
  onChange: (value: Record<string, unknown>) => void;
}) {
  const [text, setText] = useState(JSON.stringify(value, null, 2));
  const [error, setError] = useState('');
  const previous = useRef(value);
  useEffect(() => {
    if (JSON.stringify(value) !== JSON.stringify(previous.current)) {
      setText(JSON.stringify(value, null, 2));
      setError('');
      previous.current = value;
    }
  }, [value]);
  return (
    <>
      <textarea
        className="code-input"
        rows={7}
        aria-label="工具参数 JSON"
        value={text}
        onChange={(event) => {
          setText(event.target.value);
          try {
            const result = JSON.parse(event.target.value);
            if (!result || typeof result !== 'object' || Array.isArray(result))
              throw new Error('需要 JSON 对象');
            previous.current = result;
            onChange(result);
            setError('');
          } catch {
            setError('请输入有效 JSON 对象；无效内容不会写入节点。');
          }
        }}
      />
      {error && (
        <small className="error-text" role="alert">
          {error}
        </small>
      )}
    </>
  );
}

export function NodeInspector({
  node,
  graph,
  resources,
  update,
  duplicate,
  remove,
}: {
  node: CanvasNode;
  graph: Graph;
  resources: Resources;
  update: (patch: Partial<DefinitionNode>) => void;
  duplicate: () => void;
  remove: () => void;
}) {
  const n = node.data.definition,
    info = kinds[n.type],
    Icon = icons[n.type];
  const [tools, setTools] = useState<{ name: string; description?: string; inputSchema?: unknown }[]>([]);
  const [toolError, setToolError] = useState('');
  const [toolsLoading, setToolsLoading] = useState(false);
  const [activeField, setActiveField] = useState(
    ['prompt', 'query', 'value'].find((key) => key in n) || 'template',
  );
  const textRef = useRef<HTMLTextAreaElement | HTMLInputElement | null>(null);
  useEffect(() => {
    setTools([]);
    setToolError('');
  }, [n.server_id]);
  const loadTools = async () => {
    setToolsLoading(true);
    setToolError('');
    try {
      const result = await api(`/api/mcp_servers/${encodeURIComponent(n.server_id!)}/test`, {});
      setTools(result.tools || []);
    } catch (e) {
      setToolError((e as Error).message);
    } finally {
      setToolsLoading(false);
    }
  };
  const text = (key: keyof DefinitionNode, label: string, rows = 4) => (
    <Field label={label}>
      <textarea
        className="code-input"
        rows={rows}
        value={String(n[key] ?? '')}
        aria-label={label}
        onFocus={(e) => {
          setActiveField(String(key));
          textRef.current = e.target;
        }}
        onChange={(e) => update({ [key]: e.target.value })}
      />
    </Field>
  );
  const select = (key: keyof DefinitionNode, label: string, items: Resource[]) => (
    <Field label={label}>
      <select
        aria-label={label}
        value={String(n[key] || '')}
        onChange={(e) => update({ [key]: e.target.value, ...(key === 'server_id' ? { tool: '' } : {}) })}
      >
        <option value="">请选择{label}</option>
        {Boolean(n[key]) && !items.some((item) => item.id === n[key]) && (
          <option value={String(n[key])}>资源已删除 · {String(n[key])}</option>
        )}
        {items.map((item) => (
          <option key={item.id} value={item.id} disabled={item.enabled === false}>
            {item.name}
            {item.enabled === false ? '（已禁用）' : ''}
          </option>
        ))}
      </select>
      {!items.length && <small>暂无资源，请在工作台配置后点击刷新资源。</small>}
    </Field>
  );
  const insert = (value: string) => {
    const old = String(n[activeField] || ''),
      el = textRef.current;
    const start = el?.selectionStart ?? old.length,
      end = el?.selectionEnd ?? old.length;
    update({ [activeField]: old.slice(0, start) + value + old.slice(end) });
    requestAnimationFrame(() => {
      el?.focus();
      el?.setSelectionRange(start + value.length, start + value.length);
    });
  };
  return (
    <>
      <div className="inspector-title">
        <span className="node-icon" style={{ color: info.color }}>
          <Icon size={19} />
        </span>
        <div>
          <strong>{info.title}</strong>
          <small>{info.subtitle}</small>
        </div>
      </div>
      <Field label="节点名称">
        <input
          aria-label="节点名称"
          value={n.label || ''}
          placeholder={info.title}
          maxLength={100}
          onChange={(e) => update({ label: e.target.value })}
        />
      </Field>
      <Field label="节点 ID" hint="变量使用此 ID；JSON 模式可修改 ID 与相关引用。">
        <input aria-label="节点 ID" className="code-input" value={n.id} readOnly />
      </Field>
      {n.type === 'input' && (
        <p className="info-note">
          接收工作流的输入。使用 <code>{'{{input}}'}</code> 可在后续节点中引用。
        </p>
      )}
      {['prompt', 'output'].includes(n.type) &&
        text('template', n.type === 'output' ? '输出模板' : '文本模板', 7)}
      {n.type === 'output' && (
        <p className="info-note">
          输出节点只返回文本或上游结果，不会调用模型。生成回答请先连接智能体节点，再引用它的输出。
        </p>
      )}
      {n.type === 'agent' && (
        <>
          {select('agent_id', '智能体', resources.agents)}
          {text('prompt', '任务提示词', 8)}
          <Field label="知识检索方式">
            <select
              aria-label="知识检索方式"
              value={n.knowledge_mode || 'inherit'}
              onChange={(e) => update({ knowledge_mode: e.target.value as DefinitionNode['knowledge_mode'] })}
            >
              <option value="inherit">继承智能体知识库配置</option>
              <option value="workflow">由工作流控制检索</option>
            </select>
          </Field>
          <Field label="工具调用方式">
            <select
              aria-label="工具调用方式"
              value={n.tool_mode || 'inherit'}
              onChange={(e) => update({ tool_mode: e.target.value as DefinitionNode['tool_mode'] })}
            >
              <option value="inherit">继承智能体工具与权限</option>
              <option value="disabled">仅生成回答，不调用工具</option>
            </select>
          </Field>
          <p className="info-note">
            复用所选智能体的模型与系统提示词。由工作流控制检索时，不再自动检索该 Agent
            绑定的知识库；显式检索结果通过提示词变量传入。
          </p>
          {resources.agents.find((a) => a.id === n.agent_id)?.model && (
            <p className="info-note">
              当前模型：<code>{resources.agents.find((a) => a.id === n.agent_id)?.model}</code>
            </p>
          )}
        </>
      )}
      {n.type === 'router' && (
        <>
          {select('agent_id', '决策智能体', resources.agents)}
          {text('query', '待判断的问题', 3)}
          {text('prompt', '决策说明', 5)}
          <p className="info-note">
            仅用模型判断，不调用工具或检索。根据下方知识库名称与描述判断，是 → 检索，否 → 直接回答。输出包含
            matched、reason、query，可在节点日志中查看。
          </p>
        </>
      )}
      {['knowledge', 'router'].includes(n.type) && (
        <>
          <Field
            label="知识库"
            hint={
              n.type === 'router'
                ? '提供知识范围供模型判断，不在此节点检索。请填写知识库描述，帮助模型理解范围。'
                : '仅检索勾选的知识库，支持本地 Milvus 和 RAGFlow。'
            }
          >
            <div className="check-list">
              {resources.knowledge.map((k) => (
                <label key={k.id}>
                  <input
                    type="checkbox"
                    disabled={k.enabled === false}
                    checked={(n.knowledge_ids || []).includes(k.id)}
                    onChange={(e) =>
                      update({
                        knowledge_ids: e.target.checked
                          ? [...(n.knowledge_ids || []), k.id]
                          : (n.knowledge_ids || []).filter((id) => id !== k.id),
                      })
                    }
                  />
                  {k.name}
                  <small className="knowledge-backend">{k.backend === 'ragflow' ? 'RAGFlow' : '本地'}</small>
                </label>
              ))}
              {!resources.knowledge.length && <small>暂无知识库，请先在工作台创建并上传文档。</small>}
              {(n.knowledge_ids || [])
                .filter((id) => !resources.knowledge.some((k) => k.id === id))
                .map((id) => (
                  <label key={id} className="error-text">
                    <input
                      type="checkbox"
                      checked
                      onChange={() => update({ knowledge_ids: n.knowledge_ids!.filter((k) => k !== id) })}
                    />
                    已删除 · {id}
                  </label>
                ))}
            </div>
            <small>使用本地知识库：在工作台新建知识库，后端类型选择“本地 Milvus”，上传文档后刷新资源。</small>
          </Field>
          {n.type === 'knowledge' && (
            <>
              {text('query', '检索问题')}
              <Field label="返回片段数量">
                <input
                  aria-label="返回片段数量"
                  type="number"
                  min={1}
                  max={100}
                  value={n.limit ?? 5}
                  onChange={(e) => update({ limit: Number(e.target.value) })}
                />
              </Field>
            </>
          )}
        </>
      )}
      {n.type === 'condition' && (
        <>
          {text('value', '待判断的值', 3)}
          <Field label="判断方式">
            <select
              aria-label="判断方式"
              value={n.operator || 'equals'}
              onChange={(e) => update({ operator: e.target.value })}
            >
              {Object.entries({
                equals: '等于',
                not_equals: '不等于',
                contains: '包含',
                not_contains: '不包含',
                is_empty: '为空',
                not_empty: '不为空',
              }).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </Field>
          {!['is_empty', 'not_empty'].includes(n.operator || '') && text('equals', '比较值', 2)}
          <p className="info-note">
            从右侧「是 / 否」端口拖出分支。条件匹配时执行「是」，另一路会记录为跳过。
          </p>
        </>
      )}
      {n.type === 'mcp' && (
        <>
          {select('server_id', 'MCP 服务', resources.mcp_servers)}
          <Field label="工具名称">
            <input
              aria-label="工具名称"
              list="mcp-tools"
              value={n.tool || ''}
              placeholder="填写工具名或从服务加载"
              onChange={(e) => update({ tool: e.target.value })}
            />
            <datalist id="mcp-tools">
              {tools.map((t) => (
                <option key={t.name} value={t.name}>
                  {t.description}
                </option>
              ))}
            </datalist>
          </Field>
          <button
            className="secondary full"
            type="button"
            disabled={!n.server_id || toolsLoading}
            onClick={loadTools}
          >
            {toolsLoading ? '连接服务中…' : '连接服务并加载工具'}
          </button>
          {toolError && (
            <p className="error-text" role="alert">
              {toolError}
            </p>
          )}
          {tools.find((t) => t.name === n.tool)?.inputSchema !== undefined && (
            <details>
              <summary>工具参数结构</summary>
              <pre>{JSON.stringify(tools.find((t) => t.name === n.tool)?.inputSchema, null, 2)}</pre>
            </details>
          )}
          <Field label="工具参数（JSON）" hint="支持在字符串及嵌套对象中使用上游变量。">
            <JsonField
              value={n.arguments || {}}
              onChange={(argumentsValue) => update({ arguments: argumentsValue })}
            />
          </Field>
        </>
      )}
      {n.type === 'parallel' && (
        <p className="info-note">
          等待所有上游分支结束，输出已执行分支的结果数组。并行执行由 DAG
          调度器自动处理，在流程设置中调整最大并发数。
        </p>
      )}
      {['prompt', 'output', 'agent', 'knowledge', 'condition'].includes(n.type) && (
        <section className="variables">
          <h4>
            插入变量 <small>→ {activeField}</small>
          </h4>
          <button onClick={() => insert('{{input}}')} type="button">
            {'{{input}}'}
            <small>原始输入</small>
          </button>
          {ancestors(n.id, graph).map((parent) => (
            <button key={parent.id} type="button" onClick={() => insert(`{{${parent.id}}}`)}>
              <code>{`{{${parent.id}}}`}</code>
              <small>{parent.data.definition.label || kinds[parent.data.definition.type].title}</small>
            </button>
          ))}
          <p>
            支持路径：<code>{'{{condition_1.matched}}'}</code>。引用的节点须在上游。
          </p>
        </section>
      )}
      <details className="advanced">
        <summary>执行设置</summary>
        <Field label="超时（秒）">
          <input
            aria-label="超时（秒）"
            type="number"
            min={1}
            max={3600}
            value={n.timeout ?? 120}
            onChange={(e) => update({ timeout: Number(e.target.value) })}
          />
        </Field>
        <Field label="失败重试次数">
          <input
            aria-label="失败重试次数"
            type="number"
            min={0}
            max={5}
            value={n.retries ?? 0}
            onChange={(e) => update({ retries: Number(e.target.value) })}
          />
        </Field>
      </details>
      <div className="node-actions">
        <button className="secondary" onClick={duplicate}>
          <Copy size={15} />
          复制节点
        </button>
        <button className="danger secondary" onClick={remove}>
          <Trash2 size={15} />
          删除
        </button>
      </div>
    </>
  );
}

export function Dialog({
  title,
  children,
  close,
  wide = false,
}: {
  title: string;
  children: ReactNode;
  close: () => void;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const initialClose = useRef(close);
  initialClose.current = close;
  useEffect(() => {
    const previous = document.activeElement as HTMLElement;
    const el = ref.current;
    el?.querySelector<HTMLElement>('input,textarea,button')?.focus();
    const handler = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation();
        initialClose.current();
      }
      if (event.key !== 'Tab') return;
      const targets = Array.from(
        el?.querySelectorAll<HTMLElement>('button:not(:disabled), input, textarea, select, a[href]') || [],
      );
      const first = targets[0],
        last = targets[targets.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      }
      if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    };
    document.addEventListener('keydown', handler, true);
    return () => {
      document.removeEventListener('keydown', handler, true);
      previous?.focus();
    };
  }, []);
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <div
        ref={ref}
        className={`modal ${wide ? 'wide' : ''}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <header>
          <h2>{title}</h2>
          <button className="icon-button" aria-label="关闭" onClick={close}>
            <X size={19} />
          </button>
        </header>
        {children}
      </div>
    </div>
  );
}
