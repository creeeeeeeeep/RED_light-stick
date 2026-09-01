/*
 * 백그라운드 서비스워커 — 중계 서버와의 WebSocket 연결 담당.
 *
 * ---------------------------------------------------------------------------
 * 왜 여기서 연결하는가
 * ---------------------------------------------------------------------------
 * 콘텐츠 스크립트는 치지직 페이지의 CSP 를 따르므로 외부 서버로의 연결이
 * 막힐 가능성이 크다. 서비스워커는 확장 자신의 컨텍스트라 그 제약이 없다.
 *
 * MV3 서비스워커는 30초 유휴 시 종료되는데, WebSocket 통신이 그 타이머를
 * 리셋해 준다. 서버가 25초마다 핑을 보내므로 연결이 살아 있는 동안은 워커도
 * 살아 있다. 그래도 종료될 수 있으므로 alarms 로 주기적으로 깨워
 * 연결 상태를 확인한다.
 */

const DEFAULTS = {
  serverUrl: 'ws://localhost:8787/ws',
  room: 'crown-test',
  token: 'change-me',
  enabled: true,
};

let ws = null;
let retryDelay = 1000;
let lastError = '';
let lastDispatch = '아직 없음';
/*
 * 봉이 서버를 거쳐 보내온 마지막 상태. USB 없이도 설정 페이지에서
 * 봉이 살아 있는지 보려고 여기 들고 있는다.
 */
let stickUrl = '';
let lastStick = null;
let lastStickAt = 0;

const log = (...a) => console.log('[크라운봉/bg]', ...a);

async function getConfig() {
  const stored = await chrome.storage.local.get(DEFAULTS);
  return { ...DEFAULTS, ...stored };
}

/*
 * 이 확장 설치본을 가리키는 고정 id.
 *
 * 서비스워커는 수시로 죽었다 살아난다. 그때 새 인스턴스에서는 ws 가 null 이라
 * "연결이 없다"고 판단해 소켓을 새로 여는데, 서버 쪽에는 옛 소켓이 아직 살아
 * 있을 수 있다. 그러면 한 방에 소켓이 둘이 되고 모든 이벤트가 두 번 배달된다
 * (이모티콘이 두 개씩 들어가던 원인).
 *
 * 소켓에 이 id 를 실어 보내면 서버가 같은 id 의 옛 소켓을 끊어준다.
 * 워커가 어떻게 죽든 방에는 항상 하나만 남는다.
 */
async function clientId() {
  const got = await chrome.storage.local.get({ clientId: '' });
  if (got.clientId) return got.clientId;

  const buf = new Uint8Array(12);
  crypto.getRandomValues(buf);
  const id = Array.from(buf, (b) => b.toString(16).padStart(2, '0')).join('');
  await chrome.storage.local.set({ clientId: id });
  return id;
}

async function wsUrl(cfg) {
  const u = new URL(cfg.serverUrl);
  u.searchParams.set('room', cfg.room);
  u.searchParams.set('token', cfg.token);
  u.searchParams.set('cid', await clientId());
  return u.toString();
}

/* --------------------------------------------------------------- 대상 탭 */
/*
 * 명령을 어느 탭에 보낼지 정한다.
 *
 * 처음에는 열려 있는 모든 치지직 탭에 뿌렸는데, 탭을 여러 개 열어두면
 * 엉뚱한 방에 이모티콘이 들어가는 문제가 있었다. 대상은 하나여야 한다.
 *
 * 우선순위
 *   1) 사용자가 팝업에서 직접 지정한 탭 (살아 있는 경우)
 *   2) 치지직 탭이 하나뿐이면 그 탭
 *   3) 가장 최근에 활성화됐던 치지직 탭
 */
const CHZZK = 'https://chzzk.naver.com/';
const isChzzk = (url) => typeof url === 'string' && url.startsWith(CHZZK);

/*
 * 지정한 탭은 반드시 저장소에 남겨야 한다.
 *
 * MV3 서비스워커는 유휴 30초에 종료되고, 그때 모듈 변수가 전부 날아간다.
 * 메모리에만 들고 있으면 워커가 한 번 죽는 순간 고정이 풀려서 엉뚱한 탭
 * (예: 테스트용으로 열어둔 채팅 iframe 탭)으로 명령이 간다.
 *
 * storage.session 은 브라우저를 닫을 때까지 유지되고 디스크에 남지 않아
 * 탭 ID 같은 휘발성 값에 적합하다.
 */
async function getPinned() {
  const { pinnedTabId } = await chrome.storage.session.get({ pinnedTabId: null });
  return pinnedTabId;
}

async function setPinned(id) {
  await chrome.storage.session.set({ pinnedTabId: id ?? null });
}

async function getLastActive() {
  const { lastActiveTabId } = await chrome.storage.session.get({ lastActiveTabId: null });
  return lastActiveTabId;
}

async function aliveChzzkTab(id) {
  if (!id) return null;
  try {
    const t = await chrome.tabs.get(id);
    return isChzzk(t.url) ? t.id : null;
  } catch (e) {
    return null;
  }
}

async function resolveTargetTab() {
  const pinned = await aliveChzzkTab(await getPinned());
  if (pinned) return pinned;

  const tabs = await chrome.tabs.query({ url: 'https://chzzk.naver.com/*' });
  if (tabs.length === 1) return tabs[0].id;

  const recent = await aliveChzzkTab(await getLastActive());
  if (recent) return recent;

  return tabs.length ? tabs[0].id : null;
}

/*
 * 채팅은 iframe 안에 있다. frameId 를 지정하지 않으면 탭의 모든 프레임으로
 * 전달되고, 입력창이 있는 프레임만 처리한다.
 *
 * 응답은 기다리지 않는다. 프레임이 여럿이라 응답 개수가 일정치 않고,
 * 아직 준비 안 된 프레임 때문에 포트가 닫히면서 lastError 가 뜬다.
 * 실제 성공 여부는 페이지가 보내오는 crown-changed 로 확인한다.
 */
/*
 * 채팅 입력창을 실제로 가진 프레임.
 *
 * frameId 없이 보내면 탭의 모든 프레임에 배달된다. 치지직 방송 페이지는
 * 프레임이 여럿이고 그중 둘 이상이 입력창처럼 보이는 요소를 가질 수 있는데,
 * 그러면 한 번의 명령에 이모티콘이 두세 개씩 들어간다.
 *
 * 그래서 crown-ready 를 보낸 프레임을 기억해 두고 거기로만 보낸다.
 * 서비스워커는 수시로 죽으므로 storage.session 에 남긴다.
 */
async function rememberFrame(tabId, frameId) {
  const { readyFrames } = await chrome.storage.session.get({ readyFrames: {} });
  if (readyFrames[tabId] === frameId) return;
  readyFrames[tabId] = frameId;
  await chrome.storage.session.set({ readyFrames });
  log('입력창 프레임:', tabId, '/', frameId);
}

async function getFrame(tabId) {
  const { readyFrames } = await chrome.storage.session.get({ readyFrames: {} });
  const f = readyFrames[tabId];
  return (typeof f === 'number') ? f : null;
}

async function sendToTab(tabId, msg) {
  /*
   * frameId 를 주지 않으므로 탭의 모든 프레임에 뿌려진다. 채팅 입력창이 있는
   * 프레임만 응답하므로, 응답이 오면 그 탭이 실제로 처리했다는 뜻이다.
   *
   * 거부되는 경우는 두 가지다.
   *   - 콘텐츠 스크립트가 없다 (확장을 새로고침한 뒤 탭을 새로고침하지 않음)
   *   - 치지직 탭이긴 한데 채팅이 없는 페이지다
   * 둘 다 "이 탭은 못 쓴다" 는 같은 결론이라 구분하지 않는다.
   */
  const frameId = await getFrame(tabId);
  try {
    const res = (frameId === null)
      ? await chrome.tabs.sendMessage(tabId, msg)                 /* 아직 모르면 전체 */
      : await chrome.tabs.sendMessage(tabId, msg, { frameId });
    return !!(res && res.ok);
  } catch (e) {
    return false;
  }
}

/*
 * 예전에는 대상 탭 하나에 던지고 실패를 통째로 삼켰다. 그래서 명령이
 * 사라져도 아무 흔적이 남지 않아 원인을 찾을 수 없었다. 지금은 결과를
 * lastDispatch 에 남기고, 고정하지 않은 경우에 한해 다른 탭도 시도한다.
 *
 * 사용자가 직접 고정한 탭은 그 선택을 존중한다 — 응답이 없다고 다른 방으로
 * 이모티콘을 보내면 안 된다.
 */
async function dispatchToTabs(msg) {
  const tabs = await chrome.tabs.query({ url: 'https://chzzk.naver.com/*' });
  if (!tabs.length) {
    lastDispatch = '치지직 탭이 없습니다';
    log(lastDispatch, '— 명령을 버립니다:', msg);
    return 0;
  }

  const pinned = await aliveChzzkTab(await getPinned());
  if (pinned) {
    if (await sendToTab(pinned, msg)) {
      lastDispatch = '전달됨 (고정 탭 ' + pinned + ')';
      return 1;
    }
    lastDispatch = '고정 탭 ' + pinned + ' 이 응답하지 않습니다 — 탭을 새로고침하세요';
    log(lastDispatch, msg);
    return 0;
  }

  const target = await resolveTargetTab();
  const order = [target, ...tabs.map((t) => t.id)].filter(
    (id, i, a) => id && a.indexOf(id) === i
  );

  for (const id of order) {
    if (await sendToTab(id, msg)) {
      lastDispatch = '전달됨 (탭 ' + id + ')';
      if (id !== target) log('대상 탭이 응답하지 않아 탭', id, '으로 보냈습니다');
      return 1;
    }
  }

  lastDispatch = '치지직 탭 ' + order.length + '개 중 응답한 탭이 없습니다 — 탭을 새로고침하세요';
  log(lastDispatch, msg);
  return 0;
}

chrome.tabs.onActivated.addListener(async ({ tabId }) => {
  const id = await aliveChzzkTab(tabId);
  if (id) await chrome.storage.session.set({ lastActiveTabId: id });
});

chrome.tabs.onRemoved.addListener(async (tabId) => {
  const s = await chrome.storage.session.get({ pinnedTabId: null, lastActiveTabId: null });
  const patch = {};
  if (s.pinnedTabId === tabId) patch.pinnedTabId = null;
  if (s.lastActiveTabId === tabId) patch.lastActiveTabId = null;

  const { readyFrames } = await chrome.storage.session.get({ readyFrames: {} });
  if (tabId in readyFrames) {
    delete readyFrames[tabId];
    patch.readyFrames = readyFrames;
  }
  if (Object.keys(patch).length) await chrome.storage.session.set(patch);
});

function handleServerMessage(raw) {
  let m;
  try { m = JSON.parse(raw); } catch { return log('JSON 아님:', raw); }

  switch (m.action) {
  case 'add':
    dispatchToTabs({ type: 'crown-add', emojiId: m.emojiId });
    break;
  case 'send':
    dispatchToTabs({ type: 'crown-send' });
    break;
  case 'clear':
    dispatchToTabs({ type: 'crown-clear' });
    break;
  case 'hello':
    log('서버 연결됨, room =', m.room);
    /*
     * 서버가 알려주는 "봉이 써야 할 주소". 서버는 팬의 PC 에서 도는데,
     * 봉은 다른 기기라 localhost 로는 못 온다. 공유기가 준 주소로 와야 한다.
     * 팬이 직접 찾게 하면 거기서 대부분 막히므로 설정 페이지가 이걸로 채운다.
     */
    if (m.stickUrl) stickUrl = m.stickUrl;
    break;
  case 'stick':
    /*
     * age 는 서버가 이 보고를 받은 지 몇 초 지났는지다.
     *
     * 받은 시각을 그냥 Date.now() 로 찍으면 안 된다. 서버는 확장이 새로
     * 붙을 때 마지막 상태를 한 번 되보내주는데, 그걸 "방금 온 것" 으로
     * 취급하면 봉이 꺼진 지 한참인데도 켜져 있는 것처럼 보인다.
     */
    lastStick = m;
    lastStickAt = Date.now() - (Number(m.age) || 0) * 1000;
    break;
  default:
    log('알 수 없는 명령:', m);
  }
}

/* ------------------------------------------------------------------ 연결 */

/*
 * connect() 는 설정과 clientId 를 읽느라 await 를 지난다. 그 사이에 다른
 * 호출(1분 알람, 워커 기동, 팝업의 재연결 요청)이 들어오면 둘 다 "연결이
 * 없다"고 판단해 소켓을 두 개 연다. 들어와 있는 동안은 막는다.
 */
let connecting = false;

async function connect() {
  if (connecting) return;
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    return;
  }

  connecting = true;
  try {
    await connectInner();
  } finally {
    connecting = false;
  }
}

async function connectInner() {
  const cfg = await getConfig();
  if (!cfg.enabled) return;

  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    return;
  }
  /* CLOSING 상태로 남아 있는 것이 있으면 참조를 끊는다 */
  if (ws) { try { ws.close(); } catch (e) { /* 무시 */ } ws = null; }

  let url;
  try {
    url = await wsUrl(cfg);
  } catch (e) {
    lastError = '서버 주소 형식이 잘못되었습니다: ' + cfg.serverUrl;
    return log(lastError);
  }

  log('연결 시도:', cfg.serverUrl, 'room =', cfg.room);

  let sock;
  try {
    sock = new WebSocket(url);
  } catch (e) {
    lastError = e.message;
    return scheduleRetry();
  }
  ws = sock;

  /*
   * 핸들러는 자기 소켓이 아직 현역일 때만 동작해야 한다.
   *
   * 서버는 같은 확장이 새로 붙으면 옛 소켓을 끊는다(코드 4000). 그때 옛
   * 소켓의 onclose 가 뒤늦게 불리는데, 예전에는 여기서 공용 ws 를 무조건
   * null 로 지웠다. 방금 만든 새 소켓 참조까지 날아가니 "연결이 없다"고
   * 판단해 또 붙고, 그게 다시 이전 것을 끊고... 무한히 반복됐다.
   */
  sock.onopen = () => {
    if (ws !== sock) return;
    lastError = '';
    retryDelay = 1000;
    log('연결 성공');
  };

  sock.onmessage = (ev) => {
    if (ws !== sock) return;
    handleServerMessage(ev.data);
  };

  sock.onerror = () => {
    // onerror 는 상세 정보를 주지 않는다. 원인은 onclose 코드로 판단한다.
    if (ws !== sock) return;
    lastError = '연결 오류';
  };

  sock.onclose = (ev) => {
    /* 이미 새 소켓으로 교체된 뒤라면 이 소켓의 죽음은 알 바 아니다 */
    if (ws !== sock) {
      log('옛 연결이 정리되었습니다', ev.code);
      return;
    }

    log('연결 종료', ev.code, ev.reason || '');

    /*
     * 4000 은 서버가 "같은 확장이 새로 붙어서 이걸 끊는다" 는 뜻이다.
     * 그런데 여기까지 왔다는 건 우리가 아는 현역 소켓이 끊긴 것이므로,
     * 새로 붙은 쪽이 우리가 만든 게 아니다 — 다시 붙을 이유가 없다.
     */
    if (ev.code === 4000) {
      lastError = '다른 곳에서 같은 방에 연결했습니다';
      ws = null;
      return;
    }

    if (ev.code === 1008 || ev.code === 4401) {
      lastError = '인증 실패 — 토큰을 확인하세요';
    } else if (!lastError) {
      lastError = '서버에 연결할 수 없습니다';
    }
    ws = null;
    scheduleRetry();
  };
}

function scheduleRetry() {
  const d = retryDelay;
  retryDelay = Math.min(retryDelay * 2, 30000);   // 지수 백오프, 최대 30초
  setTimeout(connect, d);
}

function disconnect() {
  if (ws) {
    try { ws.close(); } catch (e) { /* 무시 */ }
    ws = null;
  }
}

/* -------------------------------------------------------------- 수명 관리 */

/*
 * 서비스워커가 종료됐다 깨어나면 연결이 끊겨 있다.
 * 1분마다 깨워서 연결 상태를 확인한다.
 */
chrome.alarms.create('crown-keepalive', { periodInMinutes: 1 });
chrome.alarms.onAlarm.addListener((a) => {
  if (a.name === 'crown-keepalive') connect();
});

chrome.runtime.onStartup.addListener(connect);
chrome.runtime.onInstalled.addListener(connect);

/* 치지직 탭이 열리면 연결을 확인한다 */
chrome.tabs.onUpdated.addListener((id, info, tab) => {
  if (info.status === 'complete' && tab.url && tab.url.startsWith('https://chzzk.naver.com/')) {
    connect();
  }
});

/* ------------------------------------------------------------ 팝업과 통신 */

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  if (!msg || !msg.type) return;

  if (msg.type === 'crown-ready' && sender.tab) {
    rememberFrame(sender.tab.id, sender.frameId || 0);
    return;
  }

  if (msg.type === 'crown-bg-status') {
    (async () => {
      const cfg = await getConfig();
      const tabId = await resolveTargetTab();
      let tabTitle = '';
      if (tabId) {
        try { tabTitle = (await chrome.tabs.get(tabId)).title || ''; } catch (e) { /* 무시 */ }
      }
      const all = await chrome.tabs.query({ url: 'https://chzzk.naver.com/*' });
      const pinnedId = await getPinned();
      reply({
        connected: !!ws && ws.readyState === WebSocket.OPEN,
        lastError,
        lastDispatch,
        stickUrl,
        stick: lastStick,
        stickAgoSec: lastStickAt ? Math.round((Date.now() - lastStickAt) / 1000) : null,
        targetTabId: tabId,
        targetTitle: tabTitle,
        pinned: pinnedId !== null && pinnedId === tabId,
        tabCount: all.length,
        ...cfg,
      });
    })();
    return true;   // 비동기 응답
  }

  /* 팝업에서 "이 탭을 대상으로" 를 누른 경우 */
  if (msg.type === 'crown-bg-pin') {
    setPinned(msg.tabId || null).then(() => {
      log('대상 탭 지정:', msg.tabId || '(해제)');
      reply({ ok: true, pinned: msg.tabId || null });
    });
    return true;
  }

  /*
   * 팝업의 수동 테스트도 서버 명령과 같은 대상 탭을 쓰게 한다.
   * 예전에는 팝업이 "활성 탭"으로 직접 보내서, 고정한 탭과 다른 곳에
   * 들어가 헷갈렸다.
   */
  if (msg.type === 'crown-bg-relay') {
    dispatchToTabs(msg.payload).then((n) => reply({ ok: n > 0, delivered: n }));
    return true;
  }

  if (msg.type === 'crown-bg-config') {
    chrome.storage.local.set(msg.config).then(() => {
      disconnect();
      retryDelay = 1000;
      connect();
      reply({ ok: true });
    });
    return true;
  }

  if (msg.type === 'crown-bg-reconnect') {
    disconnect();
    retryDelay = 1000;
    connect();
    reply({ ok: true });
    return true;
  }
});

connect();
