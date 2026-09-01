/*
 * 설정 페이지.
 *
 * 확장 페이지라서 Web Serial(봉)과 chrome.storage(확장)를 둘 다 쓸 수 있다.
 * 그래서 방 코드를 한 번 만들어 양쪽에 동시에 기록할 수 있고, 팬이 코드를
 * 옮겨 적을 일이 없다.
 *
 * 봉과는 줄 단위 텍스트로 주고받는다 (console.c 참고).
 *   보내기: PING / SCAN / WIFI <ssid> <pw> / SERVER <url> / ROOM / TOKEN / STATUS
 *   받기  : OK ... / ERR ... / AP <rssi> <open|lock> <ssid> / ST <k>=<v>
 */

const $ = (id) => document.getElementById(id);
const NL = String.fromCharCode(10);

let port = null;
let reader = null;
let writer = null;
let keepReading = false;

/* 명령을 보내고 OK/ERR 가 올 때까지 기다리는 용도 */
let pending = null;      // { resolve, reject, lines, timer }

function log(msg) {
  const el = $('log');
  el.textContent += NL + msg;
  el.scrollTop = el.scrollHeight;
}

function setPill(el, text, cls) {
  el.textContent = text;
  el.className = 'pill' + (cls ? ' ' + cls : '');
}

function markDone(stepId, done) {
  $(stepId).classList.toggle('done', !!done);
}

/* ------------------------------------------------------------- 시리얼 */

async function connect() {
  if (!('serial' in navigator)) {
    log('이 브라우저는 Web Serial 을 지원하지 않습니다 (크롬/엣지 필요)');
    return;
  }
  try {
    port = await navigator.serial.requestPort();
    await port.open({ baudRate: 115200 });
    /*
     * RTS 는 ESP32-S3 에서 EN(리셋) 핀에 물려 있다. 브라우저가 포트를 열 때
     * 이 신호를 활성화하는 게 기본이라, 내려주지 않으면 보드가 리셋 상태로
     * 붙잡혀 아무 응답도 오지 않는다.
     */
    await port.setSignals({ dataTerminalReady: false, requestToSend: false });
  } catch (e) {
    log('연결 실패: ' + e.message);
    port = null;
    return;
  }

  writer = port.writable.getWriter();
  keepReading = true;
  readLoop();

  $('connect').disabled = true;
  $('disconnect').disabled = false;
  $('scan').disabled = false;
  $('pass').disabled = false;
  $('save').disabled = false;
  $('status').disabled = false;
  $('applyLed').disabled = false;
  setPill($('connState'), '연결됨', 'ok');
  markDone('step1', true);
  log('봉에 연결되었습니다.');

  try {
    await send('PING', 2000);
    log('봉이 응답했습니다.');
    await doScan();
  } catch (e) {
    log('응답 없음: ' + e.message + ' — 보드를 리셋해 보세요.');
  }
}

async function disconnect() {
  keepReading = false;
  try { if (reader) await reader.cancel(); } catch (e) {}
  for (let i = 0; i < 40 && reader; i++) await new Promise((r) => setTimeout(r, 25));
  try { if (writer) writer.releaseLock(); } catch (e) {}
  writer = null;
  try { if (port) await port.close(); } catch (e) {}
  port = null;

  $('connect').disabled = false;
  $('disconnect').disabled = true;
  $('scan').disabled = true;
  $('pass').disabled = true;
  $('save').disabled = true;
  $('status').disabled = true;
  $('applyLed').disabled = true;
  setPill($('connState'), '연결 안 됨');
  markDone('step1', false);
  log('연결을 해제했습니다.');
}

async function readLoop() {
  const decoder = new TextDecoder();
  let buf = '';
  try {
    reader = port.readable.getReader();
    while (keepReading) {
      const res = await reader.read();
      if (res.done) break;
      buf += decoder.decode(res.value, { stream: true });

      let i = buf.indexOf(NL);
      while (i >= 0) {
        const line = buf.slice(0, i).replace(/\r$/, '');
        buf = buf.slice(i + 1);
        if (line) handleLine(line);
        i = buf.indexOf(NL);
      }
      if (buf.length > 8192) buf = '';
    }
  } catch (e) {
    if (keepReading) log('읽기 오류: ' + e.message);
  } finally {
    if (reader) {
      try { reader.releaseLock(); } catch (e) {}
      reader = null;
    }
  }
}

function handleLine(line) {
  // 제스처 로그는 설정 화면에서 시끄럽기만 하다
  if (line.indexOf('TUNE,') === 0) return;

  if (pending) {
    pending.lines.push(line);
    if (line.indexOf('OK ') === 0) {
      const p = pending; pending = null;
      clearTimeout(p.timer);
      p.resolve(p.lines);
      return;
    }
    if (line.indexOf('ERR ') === 0) {
      const p = pending; pending = null;
      clearTimeout(p.timer);
      p.reject(new Error(line.slice(4)));
      return;
    }
    return;   // AP / ST 같은 중간 줄은 모아둔다
  }
  // 명령과 무관하게 올라온 로그
  if (line.indexOf('I (') !== 0) log(line);
}

/* 한 줄 보내고 OK/ERR 까지 기다린다 */
function send(cmd, timeoutMs) {
  if (!writer) return Promise.reject(new Error('연결되지 않음'));
  if (pending) return Promise.reject(new Error('이전 명령 처리 중'));

  return new Promise((resolve, reject) => {
    pending = {
      resolve, reject, lines: [],
      timer: setTimeout(() => {
        pending = null;
        reject(new Error('응답 시간 초과'));
      }, timeoutMs || 5000),
    };
    writer.write(new TextEncoder().encode(cmd + NL)).catch((e) => {
      const p = pending; pending = null;
      if (p) { clearTimeout(p.timer); p.reject(e); }
    });
  });
}

/* 값에 공백이 있으면 따옴표로 감싼다 */
function quote(v) {
  return /[ \t"]/.test(v) ? '"' + v.replace(/"/g, '') + '"' : v;
}

/* ------------------------------------------------------------- 동작 */

async function doScan() {
  const sel = $('ssidList');
  sel.innerHTML = '<option value="">검색 중…</option>';
  try {
    const lines = await send('SCAN', 15000);
    const seen = new Set();
    const aps = [];
    for (const l of lines) {
      const m = l.match(/^AP (-?\d+) (open|lock) (.+)$/);
      if (!m) continue;
      const ssid = m[3];
      if (seen.has(ssid)) continue;
      seen.add(ssid);
      aps.push({ ssid, rssi: +m[1], open: m[2] === 'open' });
    }
    aps.sort((a, b) => b.rssi - a.rssi);

    sel.innerHTML = '';
    if (!aps.length) {
      sel.innerHTML = '<option value="">찾은 네트워크 없음</option>';
      log('주변 WiFi 를 찾지 못했습니다.');
      return;
    }
    for (const a of aps) {
      const o = document.createElement('option');
      o.value = a.ssid;
      o.textContent = a.ssid + '   ' + a.rssi + 'dBm' + (a.open ? '  (개방)' : '');
      sel.appendChild(o);
    }
    log('WiFi ' + aps.length + '개를 찾았습니다.');
  } catch (e) {
    sel.innerHTML = '<option value="">검색 실패</option>';
    log('검색 실패: ' + e.message);
  }
}

/*
 * 봉은 http:// 로 POST 하고 확장은 ws:// 로 붙는다.
 * 같은 주소에서 둘 다 만들어낸다.
 */
function toWsUrl(base) {
  const u = new URL(base);
  u.protocol = (u.protocol === 'https:') ? 'wss:' : 'ws:';
  u.pathname = '/ws';
  u.search = '';
  return u.toString();
}

function randomCode(n) {
  const abc = 'abcdefghjkmnpqrstuvwxyz23456789';   // 헷갈리는 글자 제외
  const buf = new Uint8Array(n);
  crypto.getRandomValues(buf);
  return Array.from(buf, (b) => abc[b % abc.length]).join('');
}

async function save() {
  const ssid   = $('ssidList').value.trim();
  const pass   = $('pass').value;
  const server = $('server').value.trim();
  const room   = $('room').value.trim();
  const token  = $('token').value.trim();

  if (!ssid)   return log('WiFi 를 선택하세요.');
  if (!server) return log('서버 주소를 입력하세요.');

  let wsUrl;
  try {
    wsUrl = toWsUrl(server);
  } catch (e) {
    return log('서버 주소 형식이 올바르지 않습니다. http://주소:포트 형태여야 합니다.');
  }

  try {
    $('save').disabled = true;

    await send('SERVER ' + quote(server));      log('서버 주소 저장');
    await send('ROOM ' + quote(room));          log('방 코드 저장');
    await send('TOKEN ' + quote(token));        log('토큰 저장');
    await send('WIFI ' + quote(ssid) + ' ' + quote(pass), 8000);
    log('WiFi 저장, 접속 시도 중…');

    // 확장에도 같은 값을 저장한다 — 팬이 코드를 옮겨 적을 필요가 없다
    await chrome.storage.local.set({
      serverUrl: wsUrl, room, token, enabled: true,
    });
    await chrome.runtime.sendMessage({ type: 'crown-bg-reconnect' }).catch(() => {});
    log('확장에도 저장했습니다.');

    markDone('step2', true);
    markDone('step3', true);
    markDone('step4', true);

    log('');
    log('설정이 끝났습니다. 아래 상태판을 확인하세요.');
    setTimeout(refreshState, 2500);
  } catch (e) {
    log('저장 실패: ' + e.message);
  } finally {
    $('save').disabled = false;
  }
}

/* --------------------------------------------------------------- 상태판 */

function fmtAgo(sec) {
  if (sec === null || sec === undefined) return '방금';
  if (sec < 60) return sec + '초';
  if (sec < 3600) return Math.round(sec / 60) + '분';
  return Math.round(sec / 3600) + '시간';
}

function fmtUptime(sec) {
  sec = Number(sec) || 0;
  if (sec < 60) return sec + '초';
  if (sec < 3600) return Math.round(sec / 60) + '분';
  if (sec < 86400) return Math.round(sec / 3600) + '시간';
  return Math.round(sec / 86400) + '일';
}

function setV(id, text, cls) {
  const el = $(id);
  if (!el) return;
  el.textContent = text;
  el.className = 'v ' + (cls || 'dim');
}

/* 봉에 STATUS 를 물어본다. 연결돼 있지 않으면 건너뛴다. */
async function readBoard() {
  /* 다른 명령이 처리 중이면 건너뛴다. 5초마다 도는 갱신이 사용자의 조작을
     밀어내면 안 되고, 밀린 쪽이 실패로 보이면 상태판이 깜빡인다. */
  if (pending) return null;
  if (!writer) return null;   /* USB 가 없으면 서버를 거쳐 온 것으로 채운다 */
  try {
    const lines = await send('STATUS', 4000);
    const st = {};
    for (const l of lines) {
      const m = l.match(/^ST ([^=]+)=(.*)$/);
      if (m) st[m[1]] = m[2];
    }
    setV('stBoard', '연결됨', 'ok');
    setV('stFw', st.fw ? ('v' + st.fw + (st.ota ? '  (' + st.ota + ')' : '')) : '-',
         st.fw ? 'ok' : 'dim');
    setV('stLed', st.ledbudget || '-', st.ledbudget ? 'ok' : 'dim');

    if (st.wifi === 'connected') {
      setV('stWifi', (st.ssid || '연결됨') + '   ' + (st.ip || ''), 'ok');
      markDone('step2', true);
    } else {
      setV('stWifi', st.ssid && st.ssid !== '(없음)'
           ? (st.ssid + ' 에 붙는 중… 비밀번호를 확인하세요')
           : '설정되지 않음', 'no');
      markDone('step2', false);
    }
    setV('stServer', st.server && st.server !== '(없음)' ? st.server : '설정되지 않음',
         st.server && st.server !== '(없음)' ? 'ok' : 'no');
    return st;
  } catch (e) {
    setV('stBoard', '응답 없음 — 보드를 리셋해 보세요', 'no');
    return null;
  }
}

/*
 * 서버·방·탭 상태는 백그라운드가 이미 다 알고 있다.
 *
 * 여기서 서버로 직접 fetch 하지 않는 이유가 있다. 확장 페이지의 fetch 는
 * host_permissions 를 요구하는데, 팬마다 서버 주소가 다르니 미리 적어둘 수가
 * 없다. "모든 사이트" 권한을 달라고 하면 설치할 때 경고가 뜬다.
 * WebSocket 은 그 제약을 받지 않으므로, 이미 붙어 있는 백그라운드에게
 * 물어보는 편이 권한도 안 늘고 정확하다.
 */
async function readRelay() {
  let st;
  try {
    st = await chrome.runtime.sendMessage({ type: 'crown-bg-status' });
    if (!st) throw new Error('무응답');
  } catch (e) {
    setV('stRoom', '백그라운드가 응답하지 않습니다', 'no');
    setV('stTab', '-', 'dim');
    return;
  }

  /*
   * 서버 주소는 팬이 찾아 넣기 가장 어려운 값이다. 서버가 자기 주소를
   * 알려주므로, 비어 있으면 그대로 채운다. 이미 뭔가 적어 뒀으면 건드리지 않는다.
   */
  if (st.stickUrl && !$('server').value.trim() && document.activeElement !== $('server')) {
    $('server').value = st.stickUrl;
    log('서버 주소를 자동으로 채웠습니다: ' + st.stickUrl);
  }

  const room = $('room').value.trim();
  if (st.connected) {
    const same = !room || st.room === room;
    setV('stRoom', st.room + (same ? '  —  서버 연결됨' : '  —  이 페이지의 방과 다릅니다'),
         same ? 'ok' : 'no');
    markDone('step3', same);
  } else {
    setV('stRoom', st.lastError || '서버에 붙지 못했습니다', 'no');
    markDone('step3', false);
  }

  /*
   * 봉이 20초마다 서버로 알려온 상태. USB 를 꽂지 않아도 여기서 보인다.
   * USB 로 직접 읽은 값이 있으면 그쪽이 더 정확하므로 덮어쓰지 않는다.
   */
  if (!writer) {
    const s2 = st.stick;
    const ago = st.stickAgoSec;
    if (!s2) {
      setV('stBoard', '봉이 아직 알려온 적이 없습니다 (USB 로 연결해 설정하세요)', 'dim');
      setV('stFw', '-', 'dim');
      setV('stWifi', '-', 'dim');
      setV('stLed', '-', 'dim');
    } else if (ago !== null && ago > 60) {
      setV('stBoard', `${fmtAgo(ago)} 전까지 켜져 있었습니다 — 지금은 꺼졌거나 WiFi 가 끊겼습니다`, 'no');
      setV('stFw', s2.fw ? 'v' + s2.fw : '-', 'dim');
      setV('stWifi', s2.ip || '-', 'no');
      setV('stLed', s2.led || '-', 'dim');
    } else {
      setV('stBoard', `켜져 있습니다 (${fmtAgo(ago)} 전 신호, ${fmtUptime(s2.uptime)}째 동작)`, 'ok');
      setV('stFw', s2.fw ? 'v' + s2.fw : '-', 'ok');
      setV('stWifi', s2.ip ? `연결됨   ${s2.ip}` : '연결됨', 'ok');
      setV('stLed', s2.led || '-', s2.led ? 'ok' : 'dim');
      markDone('step2', true);
    }
  }

  if (!st.targetTabId) {
    setV('stTab', '치지직 탭이 열려 있지 않습니다', 'no');
  } else {
    const mark = st.pinned ? '고정됨' : '자동 선택';
    setV('stTab', mark + ': ' + (st.targetTitle || '(제목 없음)'), 'ok');
    if (st.tabCount > 1 && !st.pinned) {
      setV('stTab', mark + ': ' + (st.targetTitle || '(제목 없음)') +
           '   (치지직 탭 ' + st.tabCount + '개 — 팝업에서 고정하세요)', 'no');
    }
  }
}

async function refreshState() {
  /* 봉은 시리얼이라 한 번에 하나씩. 중계 상태는 그동안 같이 읽는다. */
  await Promise.all([readBoard(), readRelay()]);
}

/* ------------------------------------------------------------- 초기화 */

$('connect').onclick = connect;
$('disconnect').onclick = disconnect;
$('scan').onclick = doScan;
$('save').onclick = save;
$('status').onclick = refreshState;

/*
 * LED 전력 예산을 직접 정한다.
 *
 * 원래는 시리얼 모니터에 LED 1200 을 치면 되지만, 개발자 빌드는 모션 로그가
 * 초당 20줄씩 쏟아져 타이핑이 사실상 불가능하다. 여기서 눌러 보내는 편이 낫다.
 */
$('applyLed').onclick = async () => {
  const v = $('ledBudget').value;
  try {
    $('applyLed').disabled = true;
    const lines = await send('LED ' + (v === '0' ? 'auto' : v), 4000);
    const ok = lines.find((l) => l.indexOf('OK LED') === 0);
    log('LED 전력: ' + (ok ? ok.slice(7) : '적용됨'));
    setTimeout(refreshState, 300);
  } catch (e) {
    log('LED 전력 설정 실패: ' + e.message);
  } finally {
    $('applyLed').disabled = !writer;
  }
};
/*
 * 방 코드와 토큰은 한 쌍이다. 서버는 방을 처음 본 순간 그 토큰으로 등록하고
 * 이후로는 그 토큰만 받는다. 그러니 토큰만 바꾸면 그 방에 다시 못 들어간다.
 * 항상 둘을 같이 새로 만든다.
 */
function newPair() {
  $('room').value = 'crown-' + randomCode(12);
  $('token').value = randomCode(32);
}
$('regen').onclick = newPair;
$('showPass').onchange = (e) => {
  $('pass').type = e.target.checked ? 'text' : 'password';
};

/* 상태판은 스스로 갱신한다 — 사용자가 버튼을 누르지 않아도 보이게 */
setInterval(refreshState, 5000);

(async function init() {
  const cur = await chrome.storage.local.get({ serverUrl: '', room: '', token: '' });
  if (cur.room && cur.token) {
    $('room').value = cur.room;
    $('token').value = cur.token;
  } else {
    newPair();
  }
  refreshState();

  if (cur.serverUrl) {
    try {
      const u = new URL(cur.serverUrl);
      u.protocol = (u.protocol === 'wss:') ? 'https:' : 'http:';
      u.pathname = '';
      $('server').value = u.toString().replace(/\/$/, '');
    } catch (e) { /* 무시 */ }
  }
})();
