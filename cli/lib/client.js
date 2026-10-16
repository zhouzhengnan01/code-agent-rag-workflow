'use strict';
const crypto = require('node:crypto');
const fs = require('node:fs/promises');
const path = require('node:path');
const { safeInteraction } = require('./output');
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const terminal = new Set(['completed', 'failed', 'cancelled']);
const segment = value => encodeURIComponent(value);
class Client {
  constructor(api, store, scope, output, options = {}) {
    Object.assign(this, { api, store, scope, output });
    this.pollInterval = options.pollInterval ?? 700; this.wait = options.wait || delay;
    this.ask = options.ask; this.noninteractive = options.noninteractive ?? false;
    this.thread = null; this.activeMessage = null; this.cancelRequested = false; this.interrupted = false;
  }
  route(suffix = '') { return `/api/threads/${segment(this.thread.id)}${suffix}`; }
  async agents() { return (await this.api.request('/api/resources/agents')).data || []; }
  async resolveAgent(value) {
    const agents = await this.agents();
    const matches = value ? agents.filter(a => a.id === value || a.name === value) : agents.filter(a => a.enabled !== false);
    if (matches.length !== 1 && value) throw new Error('Agent not found or name ambiguous; use an agent ID');
    if (!matches.length) throw new Error('No server agent configured');
    return matches[0];
  }
  async selectModel(value) {
    const models = (await this.api.request('/api/chat/models')).data || [];
    if (!value) { this.output.diagnostic(models.map(m => `${m.provider_id}/${m.model} (${m.provider_name})`).join('\n') || 'No models configured'); return; }
    if (value === 'default') { this.thread = await this.api.request(this.route(), { method: 'PATCH', body: { model_override: {} } }); return; }
    const found = models.filter(m => m.model === value || `${m.provider_id}/${m.model}` === value);
    if (found.length !== 1) throw new Error('Model unavailable or ambiguous; use PROVIDER_ID/MODEL from /model');
    this.thread = await this.api.request(this.route(), { method: 'PATCH', body: { model_override: { provider_id: found[0].provider_id, model: found[0].model } } });
  }
  async save(pending = null) { return this.store.saveSession(this.scope, this.thread, pending); }
  async open(options = {}) {
    const sessions = await this.store.sessions(this.scope);
    let chosen;
    if (options.continue) chosen = sessions[0];
    else if (options.resume === true) {
      if (this.noninteractive) throw new Error('--resume requires a session ID in print mode');
      if (!sessions.length) throw new Error('No saved sessions for this server, user, and working directory');
      this.output.diagnostic(sessions.map((s, i) => `${i + 1}. ${s.name || s.id} (${s.id})`).join('\n'));
      const answer = await this.ask('Resume number or ID: ');
      chosen = sessions[Number(answer) - 1] || sessions.find(s => s.id === answer);
      if (!chosen) throw new Error('Session selection cancelled');
    } else if (typeof options.resume === 'string') chosen = { id: options.resume, ...sessions.find(s => s.id === options.resume) };
    if (options.continue && !chosen) throw new Error('No previous session for this server, user, and working directory');
    if (chosen) this.thread = await this.api.request(`/api/threads/${segment(chosen.id)}`);
    else {
      const agent = options.agent ? await this.resolveAgent(options.agent) : null;
      this.thread = await this.api.request('/api/threads', { method: 'POST', body: { ...(agent ? { agent_id: agent.id } : {}), name: options.name || 'CLI session' } });
    }
    if (chosen && options.agent) {
      const agent = await this.resolveAgent(options.agent);
      this.thread = await this.api.request(this.route(), { method: 'PATCH', body: { agent_id: agent.id } });
    }
    if (chosen && options.name) this.thread = await this.api.request(this.route(), { method: 'PATCH', body: { name: options.name } });
    if (options.model) await this.selectModel(options.model);
    await this.save(chosen?.pending || null);
    if (chosen?.answers && Object.keys(chosen.answers).length) {
      if (this.noninteractive) {
        const items = (await this.api.request(this.route('/interactions'))).data || [];
        const unresolved = [];
        for (const answer of Object.values(chosen.answers)) {
          const item = items.find(i => i.id === answer.interactionId);
          const accepted = answer.body.card_id ? item?.response?.cards?.[answer.body.card_id]?.submission_id === answer.body.submission_id : item?.submission_id === answer.body.submission_id;
          if (accepted) await this.store.clearAnswer(this.scope, this.thread, answer.interactionId, answer.body.card_id);
          else if (item) unresolved.push(item);
          else throw new Error('A saved interaction answer cannot be found; use the web interface to review its state');
        }
        if (unresolved.length) { this.recoveredResult = await this.interactions(unresolved); return this.thread; }
      } else {
        for (const answer of Object.values(chosen.answers)) await this.answerDurable(answer.interactionId, answer.body);
      }
    }
    if (chosen?.pending) {
      this.output.diagnostic('Recovering saved submission with its original ID.');
      const message = await this.submitDurable(chosen.pending);
      this.recoveredResult = await this.runMessage(message, chosen.pending);
    } else if (chosen) {
      const queue = (await this.api.request(this.route('/queue'))).data || [];
      const unfinished = queue.find(m => !terminal.has(m.run_status) && !terminal.has(m.status));
      if (unfinished) this.recoveredResult = await this.runMessage(unfinished);
      else {
        const pending = (await this.api.request(this.route('/interactions'))).data.filter(i => i.status === 'pending');
        if (pending.length) this.recoveredResult = await this.interactions(pending);
      }
    }
    return this.thread;
  }
  async attachments(paths) {
    if (paths.length > 8) throw new Error('At most 8 attachments are allowed');
    const files = [];
    let total = 0;
    // Validate the complete batch before sending any file.
    for (const filename of paths) {
      const full = path.resolve(filename), stat = await fs.stat(full);
      if (!stat.isFile() || stat.size <= 0 || stat.size > 10 * 1024 * 1024) throw new Error('Attachments must be regular files of 1 byte to 10 MiB');
      total += stat.size; files.push({ full, size: stat.size });
    }
    if (total > 20 * 1024 * 1024) throw new Error('Attachments exceed the 20 MiB turn limit');
    const ids = [];
    for (const file of files) {
      const bytes = await fs.readFile(file.full);
      if (bytes.length !== file.size) throw new Error('Attachment changed during upload; retry');
      const form = new FormData(); form.append('file', new Blob([bytes]), path.basename(file.full));
      const result = await this.api.request('/api/chat/attachments', { method: 'POST', form });
      if (!result.id) throw new Error('Attachment upload did not return an ID');
      ids.push(result.id);
    }
    return ids;
  }
  async submitDurable(payload) {
    // Resolve a previously committed request before any resubmission.
    const lookup = async () => (await this.api.request(this.route(`/queue?submission_id=${segment(payload.submission_id)}`))).data || [];
    const existing = await lookup();
    if (existing.length) return existing[0];
    for (let attempt = 0; attempt < 3; attempt++) {
      try { return (await this.api.request(this.route('/queue'), { method: 'POST', body: payload })).message; }
      catch (error) {
        if (error.status && error.status < 500) throw error;
        // If lookup fails, do not submit again: acceptance remains unknown.
        const committed = await lookup();
        if (committed.length) return committed[0];
        if (attempt === 2) throw error;
        await this.wait(this.pollInterval);
      }
    }
  }
  async send(content, attachmentIds = []) {
    if (!content.trim() && !attachmentIds.length) throw new Error('Supply a prompt or attachment');
    if (content.length > 32000) throw new Error('Prompt exceeds the 32000 character limit');
    const payload = { content, agent_id: this.thread.agent_id, attachment_ids: attachmentIds, submission_id: crypto.randomUUID() };
    await this.save(payload);
    this.cancelRequested = false;
    const message = await this.submitDurable(payload);
    return this.runMessage(message, payload);
  }
  async cancel() {
    this.cancelRequested = true;
    if (this.activeMessage) await this.api.request(this.route(`/queue/${segment(this.activeMessage.id)}`), { method: 'DELETE' });
    else if (this.thread) {
      const queue = (await this.api.request(this.route('/queue'))).data || [];
      for (const item of queue.filter(m => !terminal.has(m.run_status) && !terminal.has(m.status))) await this.api.request(this.route(`/queue/${segment(item.id)}`), { method: 'DELETE' });
    }
  }
  async answerDurable(interactionId, originalBody) {
    const saved = (await this.store.sessions(this.scope)).find(s => s.id === this.thread.id);
    const key = `${interactionId}:${originalBody.card_id || ''}`;
    const body = saved?.answers?.[key]?.body || originalBody;
    await this.store.saveAnswer(this.scope, this.thread, interactionId, body);
    const lookup = async () => {
      const item = ((await this.api.request(this.route('/interactions'))).data || []).find(i => i.id === interactionId);
      if (!item) throw new Error('Interaction disappeared; answer remains saved for review');
      const response = body.card_id ? item.response?.cards?.[body.card_id] : item;
      if (response?.submission_id === body.submission_id) return true;
      if (body.card_id ? response : item.status !== 'pending') throw new Error('Interaction was answered elsewhere; saved answer will not be replayed');
      return false;
    };
    if (await lookup()) { await this.store.clearAnswer(this.scope, this.thread, interactionId, body.card_id); return; }
    try {
      await this.api.request(this.route(`/interactions/${segment(interactionId)}/answer`), { method: 'POST', body });
    } catch (error) {
      // A failed status lookup never permits another POST or a new answer ID.
      if (!(await lookup())) {
        const uncertain = new Error(`Answer acceptance unknown; resume ${this.thread.id} to recover the exact saved answer. ${error.message}`);
        uncertain.status = 409; throw uncertain;
      }
    }
    await this.store.clearAnswer(this.scope, this.thread, interactionId, body.card_id);
  }
  async interactions(items, queueMessage) {
    if (this.noninteractive) {
      const result = { status: 'requires_action', thread_id: this.thread.id, message_id: queueMessage?.id, turn_id: queueMessage?.turn_id, interactions: items.map(safeInteraction) };
      this.output.result(result); return result;
    }
    for (const item of items) {
      const safe = safeInteraction(item), body = { submission_id: crypto.randomUUID(), decision: 'denied' };
      this.output.diagnostic(`\n${safe.kind}: ${safe.question}`);
      if (item.kind === 'tool_approval') {
        this.output.diagnostic(`Tool: ${safe.tool_name}\nArguments:\n${JSON.stringify(safe.arguments, null, 2)}`);
        const answer = await this.ask('Allow this server tool action? [y/N] ');
        body.decision = /^y(?:es)?$/i.test(answer.trim()) ? 'approved' : 'denied';
      } else if (item.kind === 'project_confirmation') {
        const projects = (await this.api.request('/api/projects')).data || [];
        this.output.diagnostic(projects.map((p, i) => `${i + 1}. ${p.name} (${p.id})`).join('\n'));
        const answer = await this.ask('Project number/ID, +new name, or Enter to deny: ');
        const project = projects[Number(answer) - 1] || projects.find(p => p.id === answer);
        if (project) Object.assign(body, { decision: 'approved', project_id: project.id });
        else if (answer.startsWith('+') && answer.slice(1).trim()) Object.assign(body, { decision: 'approved', new_project_name: answer.slice(1).trim() });
      } else if (item.kind === 'question') {
        this.output.diagnostic(safe.options.map((o, i) => `${i + 1}. ${o.label}`).join('\n'));
        const answer = await this.ask('Answer or option number (Enter cancels): ');
        const option = safe.options[Number(answer) - 1];
        if (option) Object.assign(body, { decision: 'approved', option_id: option.id });
        else if (answer.trim()) Object.assign(body, { decision: 'approved', answer });
      } else if (item.kind === 'decision_cards') {
        for (const card of safe.cards) {
          if (item.response?.cards?.[card.id]) continue;
          this.output.diagnostic(`${card.title}\n${card.description}\n${card.actions.map((a, i) => `${i + 1}. ${a.label}`).join('\n')}`);
          const answer = await this.ask('Card action number or answer (Enter leaves pending): ');
          if (!answer.trim()) return { status: 'requires_action' };
          const action = card.actions[Number(answer) - 1];
          await this.answerDurable(item.id, { submission_id: crypto.randomUUID(), card_id: card.id, ...(action ? { action_id: action.id } : { answer }) });
        }
        continue;
      } else throw new Error(`Unsupported interaction kind ${safe.kind}; use the web interface`);
      await this.answerDurable(item.id, body);
    }
    return null;
  }
  async runMessage(initial, payload = null) {
    if (!initial?.id) throw new Error('Queue submission returned no message ID; resume to recover');
    let message = initial, sequence = 0, eventTurn = '', errors = 0;
    this.activeMessage = message;
    try {
      for (;;) {
        if (this.cancelRequested) await this.cancel();
        try {
          message = (await this.api.request(this.route(`/queue/${segment(message.id)}`))).message;
          this.activeMessage = message;
          if (message.turn_id) {
            if (eventTurn !== message.turn_id) { eventTurn = message.turn_id; sequence = 0; }
            const events = (await this.api.request(this.route(`/events?turn_id=${segment(eventTurn)}&since=${sequence}`))).data || [];
            for (const row of events) {
              if (Number(row.sequence) <= sequence) continue;
              this.output.event({ ...row.data, sequence: row.sequence }); sequence = Number(row.sequence);
            }
          }
          const all = (await this.api.request(this.route('/interactions'))).data || [];
          const pending = all.filter(i => i.status === 'pending' && (i.queue_message_id === message.id || i.turn_id === message.turn_id));
          if (pending.length) {
            const action = await this.interactions(pending, message);
            if (action) return action;
          }
          if (terminal.has(message.run_status) || terminal.has(message.status)) {
            const thread = await this.api.request(this.route());
            const assistant = (thread.messages || []).filter(m => m.role === 'assistant' && m.turn_id === message.turn_id).at(-1);
            const result = { status: message.run_status || message.status, thread_id: thread.id, message_id: message.id, turn_id: message.turn_id, content: assistant?.content || '', ...(message.error ? { error: message.error } : {}) };
            this.thread = thread; await this.save(); this.output.result(result); return result;
          }
          errors = 0;
        } catch (error) {
          if (error.status && error.status < 500) throw error;
          if (++errors > 5) throw new Error(`Connection lost; task persists on the server. Resume with --resume ${this.thread.id}. ${error.message}`);
          this.output.diagnostic('Connection interrupted; reconnecting to the same server task.');
        }
        await this.wait(this.pollInterval);
      }
    } finally { this.activeMessage = null; }
  }
}
module.exports = { Client, delay };
