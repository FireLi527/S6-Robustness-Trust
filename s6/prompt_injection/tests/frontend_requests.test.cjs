// Execute real page handlers in a minimal DOM harness. This is not visual QA.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const RequestState = require('../web/request_state.js');

function harness() {
  class Element {
    constructor() {
      this.value = ''; this.checked = false; this.disabled = false;
      this.style = {}; this.dataset = {}; this.children = []; this.listeners = new Map();
      const classes = new Set();
      this.classList = {add: x => classes.add(x), remove: x => classes.delete(x),
        contains: x => classes.has(x), toggle: (x, on) => on ? classes.add(x) : classes.delete(x)};
    }
    addEventListener(event, handler) {
      this.listeners.set(event, [...(this.listeners.get(event) || []), handler]);
    }
    async dispatch(event) { await Promise.all((this.listeners.get(event) || []).map(fn => fn({}))); }
    append(...items) { this.children.push(...items); }
    appendChild(item) { this.children.push(item); return item; }
    replaceChildren(...items) { this.children = items; }
    get options() { return this.children; }
    querySelector() { return this.label || (this.label = new Element()); }
    focus() {}
  }
  const elements = new Map();
  const get = id => { if (!elements.has(id)) elements.set(id, new Element()); return elements.get(id); };
  const document = {getElementById:get, querySelectorAll:() => [], addEventListener:() => {},
    createElement:() => new Element(), createTextNode:text => ({textContent:text})};
  const context = vm.createContext({document, Node:Element, S6RequestState:RequestState,
    localStorage:{getItem:() => 'zh', setItem:() => {}}, TextEncoder, performance:{now:() => 0},
    setTimeout:() => 1, clearTimeout:() => {}, setInterval:() => 1, clearInterval:() => {},
    window:{addEventListener:() => {}, confirm:() => true}});
  const html = fs.readFileSync(path.join(__dirname,'../web/index.html'), 'utf8');
  const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
  assert.equal(scripts.length, 1);
  const script = scripts[0][1].replace(/^    (?:applyLanguage\(state.language\)|loadIntentComparison\(\)|loadStatus\(\));$/gm, '');
  vm.runInContext(script, context);
  const pending = [];
  context.requestJson = (url, options={}) => new Promise((resolve,reject) => pending.push({url,options,resolve,reject}));
  get('content').value = 'First body'; get('question').value = 'Review the document.';
  get('sample-split').value = 'development'; get('sample-encoding').value = 'plain';
  return {context, get, pending, state:vm.runInContext('state',context)};
}

function result(id) {
  return {id, decision:'ALLOW', score:0, reasons:[], highlights:[],
    tool_policy:{permission:'WRITE',approval:{can_approve:true,final_decision:'HUMAN_REVIEW',reasons:[]}}};
}

test('request ownership distinguishes input changes and request order', () => {
  const state = new RequestState();
  const old = state.begin('detect'), latest = state.begin('detect');
  assert.equal(state.current(old),false);
  assert.equal(state.current(latest),true);
  state.invalidate();
  assert.equal(state.current(latest),false);
  assert.equal(state.latest(latest),true); // Owner may clean up its loading indicator.
});

test('old success cannot replace newer detection or its approval state', async () => {
  const h = harness(), first = h.context.runDetection(), second = h.context.runDetection();
  h.pending[1].resolve(result('new')); await second;
  h.pending[0].resolve(result('old')); await first;
  assert.equal(h.state.currentResult.id,'new');
  assert.equal(h.get('approval-actions').style.display,'flex');
});

test('old failure and finally cannot clear new result or stop a newer request', async () => {
  const h = harness(), first = h.context.runDetection(), second = h.context.runDetection();
  h.pending[0].reject(new Error('old failure')); await first;
  assert.equal(h.get('run-detection').disabled,true);
  assert.equal(h.get('request-error').classList.contains('visible'),false);
  h.pending[1].resolve(result('new')); await second;
  assert.equal(h.state.currentResult.id,'new');
});

test('editing input invalidates result and prevents approval buttons reappearing', async () => {
  const h = harness(), request = h.context.runDetection();
  h.get('content').value = 'Edited'; await h.get('content').dispatch('input');
  h.pending[0].resolve(result('old')); await request;
  assert.equal(h.state.currentResult,null);
  assert.equal(h.get('approval-actions').style.display,'none');
  assert.equal(h.get('run-detection').disabled,false);
});

test('new scene beats old email load and clears stale parameters', async () => {
  const h = harness(), email = h.context.loadExample(), scene = h.context.loadScenario();
  h.pending[1].resolve({content:'Scene',question:'Task',tool_name:'send_email',parameters:{body:'exact'}}); await scene;
  h.pending[0].resolve({text:'Old email',question:'Old task'}); await email;
  assert.equal(h.get('content').value,'Scene');
  assert.equal(h.state.toolParameters.body,'exact');
  assert.equal(h.get('load-example').disabled,false);
  const next = h.context.loadExample();
  h.pending[2].resolve({text:'New email',question:'Q'}); await next;
  assert.equal(Object.keys(h.state.toolParameters).length,0);
});

test('editing or clearing during sample load preserves user content', async () => {
  for (const clear of [false,true]) {
    const h = harness(), loading = h.context.loadExample();
    if (clear) h.context.clearForm();
    else { h.get('content').value='Typed'; await h.get('content').dispatch('input'); }
    h.pending[0].resolve({text:'Stale loaded body'}); await loading;
    assert.equal(h.get('content').value,clear ? '' : 'Typed');
    assert.equal(h.get('load-example').disabled,false);
  }
});

test('supervised toggle invalidates an in-flight result', async () => {
  const h = harness(), request = h.context.runDetection();
  await h.get('use-supervised').dispatch('change');
  h.pending[0].resolve(result('old')); await request;
  assert.equal(h.state.currentResult,null);
});

test('scope confirmation cannot return a token for edited inputs', async () => {
  const h = harness(); h.get('task-scope-mode').value='read_only';
  const request = h.get('confirm-task-scope').dispatch('click');
  h.get('question').value='New task'; await h.get('question').dispatch('input');
  h.pending[0].resolve({task_scope_token:'stale',expires_in_seconds:3600}); await request;
  assert.equal(h.state.taskScopeToken,'');
});

test('latest scope confirmation wins even when responses are reversed', async () => {
  const h = harness(); h.get('task-scope-mode').value='read_only';
  const first=h.get('confirm-task-scope').dispatch('click'), second=h.get('confirm-task-scope').dispatch('click');
  h.pending[1].resolve({task_scope_token:'new',expires_in_seconds:3600}); await second;
  h.pending[0].resolve({task_scope_token:'old',expires_in_seconds:3600}); await first;
  assert.equal(h.state.taskScopeToken,'new');
});

test('approval is submitted once with a snapshot and does not rerun on changed input', async () => {
  const h = harness(); h.get('tool-name').value='send_email';
  h.state.currentResult=result('review'); h.state.taskScopeToken='token';
  h.state.toolParameters={body:'original'};
  const approval=h.context.grantApproval('once');
  await h.context.grantApproval('always');
  assert.equal(h.pending.length,1);
  assert.equal(h.get('approval-actions').style.display,'none');
  h.state.toolParameters.body='changed'; await h.get('tool-target').dispatch('input');
  assert.equal(JSON.parse(h.pending[0].options.body).parameters.body,'original');
  h.pending[0].resolve({}); await approval;
  assert.equal(h.pending.length,1);
  assert.equal(h.state.currentResult,null);
  assert.equal(h.state.approvalPending,false);
});

test('unchanged approved input is rechecked and displays the fresh decision', async () => {
  const h = harness(); h.get('tool-name').value='send_email';
  h.state.currentResult=result('review'); h.state.taskScopeToken='token';
  const approval=h.context.grantApproval('once');
  h.pending[0].resolve({});
  await new Promise(setImmediate); // Drain cross-context Promise continuations.
  assert.equal(h.pending.length,2);
  assert.equal(h.pending[1].url,'/api/detect');
  const allowed=result('fresh');
  allowed.tool_policy.approval={can_approve:false,final_decision:'ALLOW',reasons:[]};
  h.pending[1].resolve(allowed); await approval;
  assert.equal(h.state.currentResult.id,'fresh');
  assert.equal(h.get('approval-actions').style.display,'none');
});
