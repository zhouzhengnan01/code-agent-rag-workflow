'use strict';
function redact(value) {
  return String(value ?? '')
    .replace(/\x1b\][\s\S]*?(?:\x07|\x1b\\)/g, '')
    .replace(/\x1b\[[0-?]*[ -/]*[@-~]/g, '')
    .replace(/[\x00-\x08\x0b-\x1f\x7f\x80-\x9f]/g, '')
    .replace(/\bBearer\s+[^\s"']+/gi, 'Bearer [REDACTED]')
    .replace(/\b(?:sk|ck|ghp|github_pat|czzn|czz_cli)[-_][A-Za-z0-9_-]{12,}/g, '[REDACTED]')
    .replace(/((?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret|authorization)\s*["']?\s*[:=]\s*["']?)[^\s,"'}]+/gi, '$1[REDACTED]')
    .replace(/(https?:\/\/)[^\s/@]+:[^\s/@]+@/gi, '$1[REDACTED]@');
}
function sanitize(value) {
  if (typeof value === 'string') return redact(value);
  if (Array.isArray(value)) return value.map(sanitize);
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, /(?:api[_-]?key|token|password|secret|authorization)/i.test(key) ? '[REDACTED]' : sanitize(item)]));
  return value;
}
function safeInteraction(item) {
  const p = item.payload || {};
  return { id: item.id, kind: item.kind, question: redact(item.question), ...(item.kind === 'tool_approval' ? { tool_name: redact(p.tool_name || p.name), arguments: sanitize(p.args || p.arguments || {}) } : {}), options: (p.options || []).map(o => ({ id: o.id, label: redact(o.label) })), cards: (p.cards || []).map(c => ({ id: c.id, title: redact(c.title), description: redact(c.description), actions: (c.actions || []).map(a => ({ id: a.id, label: redact(a.label) })) })) };
}
function safeEvent(event) {
  const allowed = ['assistant_delta', 'token_delta', 'tool_started', 'tool_completed', 'tool_failed', 'assistant_status', 'turn_started', 'turn_resumed', 'turn_completed', 'turn_cancelled', 'approval_required', 'model_selected', 'model_fallback', 'knowledge_started', 'knowledge_completed', 'knowledge_failed'];
  if (!allowed.includes(event.type)) return null;
  const result = { type: event.type };
  for (const key of ['id', 'turn_id', 'sequence', 'status', 'name', 'model', 'provider', 'count', 'approval_id']) if (event[key] !== undefined) result[key] = typeof event[key] === 'string' ? redact(event[key]) : event[key];
  if (['assistant_delta', 'token_delta'].includes(event.type)) result.content = redact(event.content ?? event.delta ?? '');
  return result;
}
class Output {
  constructor(format = 'text', stdout = process.stdout, stderr = process.stderr) { this.format = format; this.stdout = stdout; this.stderr = stderr; this.streamed = false; this.deltaBuffer = ''; }
  diagnostic(message) { this.stderr.write(`${redact(message)}\n`); }
  event(event) {
    const safe = safeEvent(event); if (!safe) return;
    // Keep a short tail so credentials spanning chunks are redacted together.
    if (['assistant_delta', 'token_delta'].includes(safe.type)) {
      this.deltaBuffer += event.content ?? event.delta ?? '';
      if (this.format !== 'json') {
        const words = [...this.deltaBuffer.matchAll(/\S+/g)];
        let cutoff = words.length > 4 ? words[words.length - 4].index : 0;
        // Chinese prose has no spaces; emit complete non-ASCII text while
        // retaining a trailing ASCII identifier that could be a split token.
        if (/[\u0100-\uffff]/.test(this.deltaBuffer)) cutoff = Math.max(cutoff, this.deltaBuffer.length - (this.deltaBuffer.match(/[A-Za-z0-9_\/.:=-]+$/)?.[0].length || 0));
        if (cutoff > 0) {
          // An incomplete label is still sensitive context. Preserve it even
          // when a Chinese chunk can otherwise be emitted immediately, and
          // through whitespace/newlines until its value arrives.
          const pendingCredential = this.deltaBuffer.match(/\b(?:Bearer(?:\s+)?|(?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret|authorization)(?:\s*["']?\s*[:=]?\s*["']?)(?:Bearer\s*)?)$/i);
          if (pendingCredential) cutoff = Math.min(cutoff, pendingCredential.index);
          for (const match of this.deltaBuffer.matchAll(/\b(?:Bearer\s+\S+|(?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret|authorization)\s*["']?\s*[:=]\s*["']?[^\s,"'}]+)/gi)) if (match.index < cutoff && match.index + match[0].length > cutoff) cutoff = match.index;
          if (cutoff > 0) { this.emitDelta(this.deltaBuffer.slice(0, cutoff)); this.deltaBuffer = this.deltaBuffer.slice(cutoff); }
        }
      }
      return;
    }
    if (safe.type === 'turn_completed' || safe.type === 'turn_cancelled') this.flushDeltas();
    if (this.format === 'stream-json') this.stdout.write(`${JSON.stringify(safe)}\n`);
    else if (this.format === 'text' && safe.type.startsWith('tool_')) this.diagnostic(`[${safe.type}] ${safe.name || ''}`);
  }
  flushDeltas() {
    if (!this.deltaBuffer) return;
    this.emitDelta(this.deltaBuffer); this.deltaBuffer = '';
  }
  emitDelta(value) {
    const content = redact(value); this.streamed = true;
    if (this.format === 'stream-json') this.stdout.write(`${JSON.stringify({ type: 'assistant_delta', content })}\n`);
    else if (this.format === 'text') this.stdout.write(content);
  }
  result(result) {
    this.flushDeltas();
    const safe = { ...result, ...(result.content !== undefined ? { content: redact(result.content) } : {}) };
    if (result.error) safe.error = redact(result.error);
    if (this.format === 'stream-json') this.stdout.write(`${JSON.stringify({ type: 'result', ...safe })}\n`);
    else if (this.format === 'json') this.stdout.write(`${JSON.stringify(safe)}\n`);
    else {
      if (safe.content && !this.streamed) this.stdout.write(safe.content);
      if (safe.content || this.streamed) this.stdout.write('\n');
      if (safe.status === 'requires_action') this.diagnostic(`requires_action: ${safe.interactions.map(i => `${i.kind}: ${i.question}`).join('; ')}. Resume interactively with --resume ${safe.thread_id}`);
      if (safe.error) this.diagnostic(safe.error);
    }
    this.streamed = false;
  }
}
module.exports = { Output, redact, safeEvent, safeInteraction, sanitize };
