import asyncio
from fastapi import APIRouter, Cookie, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import db
from engines import get_engine, list_engines

router = APIRouter(prefix="/admin", tags=["Admin Console"])
COOKIE_NAME = "search_admin_session"


def _require_admin(session_cookie: str | None) -> str:
    username = db.verify_session_token(session_cookie or "")
    if not username:
        raise HTTPException(status_code=401, detail="请先登录管理员账号")
    return username


class AuthPayload(BaseModel):
    username: str
    password: str


class CreateKeyPayload(BaseModel):
    name: str


class ToggleKeyPayload(BaseModel):
    is_active: bool


class SettingsPayload(BaseModel):
    require_api_key: bool
    default_engine: str
    brave_api_key: str = ""


class PasswordPayload(BaseModel):
    new_password: str


@router.get("", response_class=HTMLResponse, include_in_schema=False)
@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def admin_page():
    return HTMLResponse(_ADMIN_HTML)


@router.get("/api/status", include_in_schema=False)
async def admin_status(request: Request):
    has_adm = db.has_admin()
    user = db.verify_session_token(request.cookies.get(COOKIE_NAME, ""))
    return {"has_admin": has_adm, "authenticated": bool(user), "username": user}


@router.post("/api/setup", include_in_schema=False)
async def admin_setup(payload: AuthPayload, response: Response):
    if db.has_admin():
        raise HTTPException(status_code=400, detail="管理员已存在，请直接登录")
    try:
        db.create_admin(payload.username, payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    token = db.create_session_token(payload.username.strip())
    response.set_cookie(COOKIE_NAME, token, httponly=True, samesite="lax", max_age=86400 * 7)
    return {"ok": True, "username": payload.username.strip()}


@router.post("/api/login", include_in_schema=False)
async def admin_login(payload: AuthPayload, response: Response):
    if not db.verify_admin(payload.username, payload.password):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = db.create_session_token(payload.username.strip())
    response.set_cookie(COOKIE_NAME, token, httponly=True, samesite="lax", max_age=86400 * 7)
    return {"ok": True, "username": payload.username.strip()}


@router.post("/api/logout", include_in_schema=False)
async def admin_logout(response: Response):
    response.delete_cookie(COOKIE_NAME)
    return {"ok": True}


@router.post("/api/password", include_in_schema=False)
async def change_password(
    payload: PasswordPayload,
    search_admin_session: str | None = Cookie(default=None),
):
    user = _require_admin(search_admin_session)
    try:
        db.update_admin_password(user, payload.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


@router.get("/api/dashboard", include_in_schema=False)
async def admin_dashboard(search_admin_session: str | None = Cookie(default=None)):
    _require_admin(search_admin_session)
    return {
        "stats": db.get_stats(),
        "keys": db.list_api_keys(),
        "engines": list_engines(),
        "settings": {
            "require_api_key": db.get_setting("require_api_key", "1") == "1",
            "default_engine": db.get_setting("default_engine", "so_qq"),
            "brave_api_key": db.get_setting("brave_api_key", ""),
        },
        "logs": db.get_recent_logs(30),
    }


@router.post("/api/keys", include_in_schema=False)
async def create_key(
    payload: CreateKeyPayload,
    search_admin_session: str | None = Cookie(default=None),
):
    _require_admin(search_admin_session)
    return db.create_api_key(payload.name)


@router.patch("/api/keys/{key_id}", include_in_schema=False)
async def toggle_key(
    key_id: int,
    payload: ToggleKeyPayload,
    search_admin_session: str | None = Cookie(default=None),
):
    _require_admin(search_admin_session)
    db.toggle_api_key(key_id, payload.is_active)
    return {"ok": True}


@router.delete("/api/keys/{key_id}", include_in_schema=False)
async def remove_key(
    key_id: int,
    search_admin_session: str | None = Cookie(default=None),
):
    _require_admin(search_admin_session)
    db.delete_api_key(key_id)
    return {"ok": True}


@router.post("/api/settings", include_in_schema=False)
async def save_settings(
    payload: SettingsPayload,
    search_admin_session: str | None = Cookie(default=None),
):
    _require_admin(search_admin_session)
    # 校验引擎是否存在
    get_engine(payload.default_engine)
    db.set_setting("require_api_key", "1" if payload.require_api_key else "0")
    db.set_setting("default_engine", payload.default_engine)
    db.set_setting("brave_api_key", payload.brave_api_key.strip())
    return {"ok": True}


@router.get("/api/test-search", include_in_schema=False)
async def test_search(
    q: str,
    engine: str = "so_qq",
    page: int = 1,
    limit: int = 5,
    search_admin_session: str | None = Cookie(default=None),
):
    _require_admin(search_admin_session)
    eng = get_engine(engine)
    return await asyncio.to_thread(eng.search, query=q.strip(), page=page, limit=limit)


_ADMIN_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>AI Search · 控制台</title>
<style>
  :root {
    --bg: #09090b;
    --surface: #111114;
    --surface-2: #18181b;
    --border: rgba(255, 255, 255, 0.08);
    --border-hover: rgba(255, 255, 255, 0.16);
    --text: #fafafa;
    --text-2: #a1a1aa;
    --text-3: #71717a;
    --accent: #3b82f6;
    --accent-hover: #2563eb;
    --ok: #22c55e;
    --danger: #ef4444;
    --radius: 10px;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", Roboto, sans-serif;
    font-size: 14px;
    line-height: 1.5;
    -webkit-font-smoothing: antialiased;
  }
  .wrap { max-width: 960px; margin: 0 auto; padding: 32px 20px 72px; }
  .hidden { display: none !important; }

  /* Header */
  .topbar {
    display: flex; align-items: center; justify-content: space-between;
    padding-bottom: 20px; margin-bottom: 24px;
    border-bottom: 1px solid var(--border);
  }
  .brand { display: flex; align-items: center; gap: 10px; }
  .brand-mark {
    width: 28px; height: 28px; border-radius: 7px;
    background: var(--surface-2); border: 1px solid var(--border-hover);
    display: grid; place-items: center; color: var(--text);
  }
  .brand h1 { font-size: 15px; font-weight: 600; margin: 0; letter-spacing: -0.01em; }
  .brand span { font-size: 12px; color: var(--text-3); margin-left: 6px; font-weight: 400; }

  /* Controls */
  .row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  input, select {
    background: var(--bg);
    border: 1px solid var(--border);
    color: var(--text);
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 13px;
    outline: none;
    transition: border-color 0.15s ease;
  }
  input:focus, select:focus { border-color: var(--accent); }
  input::placeholder { color: var(--text-3); }

  button {
    display: inline-flex; align-items: center; justify-content: center; gap: 6px;
    background: var(--text); color: var(--bg);
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 8px 14px;
    font-size: 13px; font-weight: 500;
    cursor: pointer;
    transition: opacity 0.15s ease, background 0.15s ease, border-color 0.15s ease;
  }
  button:hover { opacity: 0.9; }
  button.primary { background: var(--accent); color: #fff; }
  button.primary:hover { background: var(--accent-hover); opacity: 1; }
  button.ghost {
    background: transparent; color: var(--text-2);
    border-color: var(--border);
  }
  button.ghost:hover { color: var(--text); border-color: var(--border-hover); background: var(--surface-2); opacity: 1; }
  button.danger-ghost { background: transparent; color: var(--text-3); border-color: transparent; }
  button.danger-ghost:hover { color: var(--danger); background: rgba(239, 68, 68, 0.1); opacity: 1; }
  button.sm { padding: 5px 10px; font-size: 12px; border-radius: 6px; }

  /* Stats */
  .stats {
    display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px;
    margin-bottom: 20px;
  }
  @media (max-width: 640px) { .stats { grid-template-columns: 1fr; } }
  .stat {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 16px 18px;
  }
  .stat-label { font-size: 12px; color: var(--text-3); }
  .stat-val {
    font-size: 26px; font-weight: 600; margin-top: 4px;
    font-variant-numeric: tabular-nums; letter-spacing: -0.02em;
  }

  /* Tabs */
  .tabs {
    display: inline-flex; gap: 4px; padding: 4px;
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 9px; margin-bottom: 16px;
  }
  .tab {
    background: transparent; color: var(--text-2); border: 0;
    padding: 6px 14px; border-radius: 6px; font-size: 13px; font-weight: 500;
  }
  .tab:hover { color: var(--text); opacity: 1; }
  .tab.active { background: var(--surface-2); color: var(--text); border: 1px solid var(--border); }

  /* Card & Table */
  .card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 20px;
  }
  .card-head {
    display: flex; align-items: center; justify-content: space-between;
    gap: 12px; flex-wrap: wrap; margin-bottom: 14px;
  }
  .card-title { font-size: 14px; font-weight: 600; margin: 0; }
  .card-sub { font-size: 12px; color: var(--text-3); margin-top: 2px; }

  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th {
    text-align: left; padding: 10px 8px; color: var(--text-3);
    font-weight: 500; font-size: 12px; border-bottom: 1px solid var(--border);
  }
  td { padding: 11px 8px; border-bottom: 1px solid var(--border); vertical-align: middle; }
  tr:last-child td { border-bottom: 0; }
  .mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; color: var(--text-2); }
  .num { font-variant-numeric: tabular-nums; }

  .dot { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; }
  .dot::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: var(--ok); }
  .dot.off { color: var(--text-3); }
  .dot.off::before { background: var(--text-3); }

  /* Switch */
  .switch-row {
    display: flex; align-items: center; justify-content: space-between;
    padding: 14px 0; border-bottom: 1px solid var(--border);
  }
  .switch-row:last-of-type { border-bottom: 0; }
  .toggle {
    appearance: none; width: 38px; height: 22px; border-radius: 99px;
    background: var(--surface-2); border: 1px solid var(--border-hover);
    position: relative; cursor: pointer; padding: 0; transition: background 0.15s ease;
  }
  .toggle::after {
    content: ""; position: absolute; top: 2px; left: 2px;
    width: 16px; height: 16px; border-radius: 50%;
    background: var(--text-2); transition: transform 0.15s ease, background 0.15s ease;
  }
  .toggle:checked { background: var(--accent); border-color: var(--accent); }
  .toggle:checked::after { transform: translateX(16px); background: #fff; }

  /* Auth */
  .auth-wrap { max-width: 360px; margin: 96px auto 0; }
  .auth-wrap .card { padding: 28px 24px; }
  .auth-wrap input { width: 100%; margin-bottom: 10px; padding: 10px 12px; }
  .auth-wrap button { width: 100%; padding: 10px; margin-top: 4px; }

  /* Code / Output */
  pre {
    margin: 14px 0 0;
    background: var(--bg); border: 1px solid var(--border);
    border-radius: 8px; padding: 14px;
    max-height: 340px; overflow: auto;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 12px; color: var(--text-2);
  }

  /* Toast */
  .toast {
    position: fixed; right: 20px; bottom: 20px; z-index: 50;
    background: var(--surface-2); border: 1px solid var(--border-hover);
    color: var(--text); padding: 10px 14px; border-radius: 8px;
    font-size: 13px; box-shadow: 0 10px 30px rgba(0, 0, 0, 0.45);
    opacity: 0; transform: translateY(8px); pointer-events: none;
    transition: opacity 0.18s ease, transform 0.18s ease;
  }
  .toast.show { opacity: 1; transform: translateY(0); }
</style>
</head>
<body>
<div class="wrap">
  <!-- Auth View -->
  <div id="authView" class="auth-wrap hidden">
    <div class="card">
      <div class="brand" style="margin-bottom:16px;">
        <div class="brand-mark">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
        </div>
        <h1 id="authTitle">管理员登录</h1>
      </div>
      <p id="authDesc" class="card-sub" style="margin:0 0 18px;"></p>
      <input id="authUser" placeholder="用户名" autocomplete="username" />
      <input id="authPass" type="password" placeholder="密码（至少 6 位）" autocomplete="current-password" onkeydown="if(event.key==='Enter')submitAuth()" />
      <button id="authBtn" class="primary" onclick="submitAuth()">登录</button>
      <p id="authErr" style="color:var(--danger);font-size:12px;margin:10px 0 0;"></p>
    </div>
  </div>

  <!-- Main View -->
  <div id="mainView" class="hidden">
    <header class="topbar">
      <div class="brand">
        <div class="brand-mark">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
        </div>
        <h1>AI Search<span>REST API &amp; MCP</span></h1>
      </div>
      <div class="row">
        <span id="curUser" class="card-sub" style="margin-right:4px;"></span>
        <button class="ghost sm" onclick="changePwd()">修改密码</button>
        <button class="ghost sm" onclick="logout()">退出</button>
      </div>
    </header>

    <section class="stats">
      <div class="stat"><div class="stat-label">API Key 总数</div><div id="stTotal" class="stat-val">-</div></div>
      <div class="stat"><div class="stat-label">启用中</div><div id="stActive" class="stat-val">-</div></div>
      <div class="stat"><div class="stat-label">累计调用</div><div id="stCalls" class="stat-val">-</div></div>
    </section>

    <nav class="tabs">
      <button class="tab active" data-tab="keys" onclick="switchTab('keys')">密钥管理</button>
      <button class="tab" data-tab="settings" onclick="switchTab('settings')">引擎与安全</button>
      <button class="tab" data-tab="debug" onclick="switchTab('debug')">测试与日志</button>
    </nav>

    <!-- Tab: Keys -->
    <section id="tab-keys" class="card">
      <div class="card-head">
        <div>
          <h2 class="card-title">API Keys</h2>
          <div class="card-sub">用于 REST API（Authorization: Bearer）与远程 MCP（/mcp/）鉴权</div>
        </div>
        <div class="row">
          <input id="newKeyName" placeholder="备注名称（如 Cursor MCP）" onkeydown="if(event.key==='Enter')createKey()" />
          <button class="primary" onclick="createKey()">+ 新建 Key</button>
        </div>
      </div>
      <table>
        <thead><tr><th>备注</th><th>密钥</th><th>状态</th><th>调用</th><th>最近使用</th><th style="text-align:right;">操作</th></tr></thead>
        <tbody id="keysBody"></tbody>
      </table>
    </section>

    <!-- Tab: Settings -->
    <section id="tab-settings" class="card hidden">
      <div class="card-head">
        <div>
          <h2 class="card-title">引擎与安全配置</h2>
          <div class="card-sub">配置默认搜索引擎、外部引擎密钥与全局鉴权策略</div>
        </div>
        <button class="primary" onclick="saveSettings()">保存配置</button>
      </div>
      <div class="switch-row">
        <div>
          <div style="font-weight:500;">强制校验 API Key</div>
          <div class="card-sub">公网部署建议保持开启，防止接口被未授权调用</div>
        </div>
        <input id="reqKey" type="checkbox" class="toggle" />
      </div>
      <div class="switch-row">
        <div>
          <div style="font-weight:500;">默认搜索引擎</div>
          <div class="card-sub">未显式指定 engine 参数时使用的默认引擎</div>
        </div>
        <select id="defEngine" style="min-width:240px;"></select>
      </div>
      <div class="switch-row">
        <div>
          <div style="font-weight:500;">Brave Search API Key</div>
          <div class="card-sub">仅在使用 brave 引擎时需要填写</div>
        </div>
        <input id="braveKey" type="password" placeholder="BSA..." style="min-width:240px;" />
      </div>
      <div style="margin-top:16px;">
        <div class="card-sub" style="margin-bottom:8px;">已注册引擎</div>
        <div id="enginesDesc" class="card-sub" style="line-height:1.8;"></div>
      </div>
    </section>

    <!-- Tab: Debug & Logs -->
    <section id="tab-debug" class="hidden">
      <div class="card" style="margin-bottom:16px;">
        <div class="card-head">
          <div>
            <h2 class="card-title">在线搜索测试</h2>
            <div class="card-sub">直接验证各引擎返回结构与翻页效果</div>
          </div>
        </div>
        <div class="row">
          <select id="testEngine"></select>
          <input id="testQ" value="大肥鱼" placeholder="搜索关键词" style="flex:1;min-width:200px;" onkeydown="if(event.key==='Enter')runTest()" />
          <button class="primary" onclick="runTest()">运行测试</button>
        </div>
        <pre id="testOut" class="hidden"></pre>
      </div>

      <div class="card">
        <div class="card-head">
          <div>
            <h2 class="card-title">最近调用记录</h2>
            <div class="card-sub">SQLite 仅保留最近 500 条，此处展示最新 30 条</div>
          </div>
        </div>
        <table>
          <thead><tr><th>时间</th><th>Key</th><th>引擎</th><th>关键词</th><th>页码</th></tr></thead>
          <tbody id="logsBody"></tbody>
        </table>
      </div>
    </section>
  </div>
</div>

<div id="toast" class="toast"></div>

<script>
let isSetup = false;
const $ = id => document.getElementById(id);
const fmtTime = ts => ts ? new Date(ts * 1000).toLocaleString('zh-CN', { hour12: false }) : '—';
const maskKey = k => k.length > 12 ? k.slice(0, 7) + '••••' + k.slice(-4) : k;

let toastTimer;
function toast(msg) {
  const el = $('toast');
  el.textContent = msg;
  el.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), 2200);
}

function switchTab(name) {
  document.querySelectorAll('.tab').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
  ['keys', 'settings', 'debug'].forEach(t => $('tab-' + t).classList.toggle('hidden', t !== name));
}

async function api(url, opts = {}) {
  const res = await fetch(url, { headers: { 'Content-Type': 'application/json' }, ...opts });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || '请求失败');
  }
  return res.json();
}

async function init() {
  const st = await api('/admin/api/status');
  if (!st.authenticated) {
    isSetup = !st.has_admin;
    $('authTitle').textContent = isSetup ? '初始化管理员' : '管理员登录';
    $('authDesc').textContent = isSetup
      ? '首次启动，请设置管理员账号（保存在本地 SQLite）。'
      : '输入管理员账号密码以继续。';
    $('authBtn').textContent = isSetup ? '创建并登录' : '登录';
    $('authView').classList.remove('hidden');
    $('mainView').classList.add('hidden');
    return;
  }
  $('curUser').textContent = st.username;
  $('authView').classList.add('hidden');
  $('mainView').classList.remove('hidden');
  await loadDashboard();
}

async function submitAuth() {
  $('authErr').textContent = '';
  try {
    await api(isSetup ? '/admin/api/setup' : '/admin/api/login', {
      method: 'POST',
      body: JSON.stringify({ username: $('authUser').value, password: $('authPass').value }),
    });
    await init();
  } catch (e) { $('authErr').textContent = e.message; }
}

async function logout() {
  await api('/admin/api/logout', { method: 'POST' });
  location.reload();
}

async function changePwd() {
  const np = prompt('请输入新密码（至少 6 位）：');
  if (!np) return;
  try {
    await api('/admin/api/password', { method: 'POST', body: JSON.stringify({ new_password: np }) });
    toast('密码已更新');
  } catch (e) { toast(e.message); }
}

async function loadDashboard() {
  const d = await api('/admin/api/dashboard');
  $('stTotal').textContent = d.stats.total_keys;
  $('stActive').textContent = d.stats.active_keys;
  $('stCalls').textContent = d.stats.total_calls;

  $('keysBody').innerHTML = d.keys.map(k => `
    <tr>
      <td style="font-weight:500;">${k.name}</td>
      <td>
        <span class="mono">${maskKey(k.api_key)}</span>
        <button class="ghost sm" style="margin-left:6px;" onclick="copyText('${k.api_key}')">复制</button>
      </td>
      <td><span class="dot ${k.is_active ? '' : 'off'}">${k.is_active ? '启用' : '禁用'}</span></td>
      <td class="num">${k.usage_count}</td>
      <td class="card-sub">${fmtTime(k.last_used_at)}</td>
      <td style="text-align:right;">
        <button class="ghost sm" onclick="toggleKey(${k.id}, ${!k.is_active})">${k.is_active ? '禁用' : '启用'}</button>
        <button class="danger-ghost sm" onclick="delKey(${k.id})">删除</button>
      </td>
    </tr>
  `).join('') || '<tr><td colspan="6" class="card-sub" style="text-align:center;padding:24px;">暂无 API Key，点击右上角新建</td></tr>';

  const opts = d.engines.map(e => `<option value="${e.name}">${e.name} · ${e.label}</option>`).join('');
  $('defEngine').innerHTML = opts;
  $('testEngine').innerHTML = opts;
  $('defEngine').value = d.settings.default_engine;
  $('testEngine').value = d.settings.default_engine;
  $('reqKey').checked = d.settings.require_api_key;
  $('braveKey').value = d.settings.brave_api_key || '';
  $('enginesDesc').innerHTML = d.engines.map(e => `<span class="mono">${e.name}</span> — ${e.description}`).join('<br/>');

  $('logsBody').innerHTML = d.logs.map(l => `
    <tr>
      <td class="card-sub">${fmtTime(l.created_at)}</td>
      <td>${l.key_name}</td>
      <td><span class="mono">${l.engine}</span></td>
      <td>${l.query}</td>
      <td class="num">${l.page}</td>
    </tr>
  `).join('') || '<tr><td colspan="5" class="card-sub" style="text-align:center;padding:24px;">暂无调用记录</td></tr>';
}

function copyText(t) {
  navigator.clipboard.writeText(t).then(() => toast('已复制完整 API Key'));
}

async function createKey() {
  const name = $('newKeyName').value.trim() || 'default';
  const created = await api('/admin/api/keys', { method: 'POST', body: JSON.stringify({ name }) });
  $('newKeyName').value = '';
  navigator.clipboard?.writeText(created.api_key).catch(() => {});
  toast('已创建 Key 并复制到剪贴板');
  await loadDashboard();
}

async function toggleKey(id, active) {
  await api(`/admin/api/keys/${id}`, { method: 'PATCH', body: JSON.stringify({ is_active: active }) });
  toast(active ? '已启用' : '已禁用');
  await loadDashboard();
}

async function delKey(id) {
  if (!confirm('确认删除该 API Key？')) return;
  await api(`/admin/api/keys/${id}`, { method: 'DELETE' });
  toast('已删除');
  await loadDashboard();
}

async function saveSettings() {
  try {
    await api('/admin/api/settings', {
      method: 'POST',
      body: JSON.stringify({
        require_api_key: $('reqKey').checked,
        default_engine: $('defEngine').value,
        brave_api_key: $('braveKey').value,
      }),
    });
    toast('配置已保存');
  } catch (e) { toast(e.message); }
}

async function runTest() {
  const q = $('testQ').value.trim();
  if (!q) return;
  const engine = $('testEngine').value;
  $('testOut').classList.remove('hidden');
  $('testOut').textContent = '请求中...';
  try {
    const res = await api(`/admin/api/test-search?q=${encodeURIComponent(q)}&engine=${encodeURIComponent(engine)}&limit=5`);
    $('testOut').textContent = JSON.stringify(res, null, 2);
  } catch (e) { $('testOut').textContent = '错误：' + e.message; }
}

init();
</script>
</body>
</html>
"""
