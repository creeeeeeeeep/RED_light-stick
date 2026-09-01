/*
 * 팝업 — 중계 서버 설정과 봉 없이 하는 수동 테스트.
 */
const $ = (id) => document.getElementById(id);
const log = (m) => { $('log').textContent = m; };

/* ------------------------------------------------------------ 서버 상태 */

async function refresh() {
  try {
    const s = await chrome.runtime.sendMessage({ type: 'crown-bg-status' });
    if (!s) return;

    const el = $('conn');
    el.textContent = s.connected ? '연결됨' : (s.lastError || '끊김');
    el.className = 'stat ' + (s.connected ? 'ok' : 'no');

    // 사용자가 입력 중이면 덮어쓰지 않는다
    if (document.activeElement !== $('serverUrl')) $('serverUrl').value = s.serverUrl || '';

    // 명령이 어느 탭으로 가는지 보여준다
    if (!s.targetTabId) {
      $('target').textContent = '치지직 탭이 없습니다.';
    } else {
      const mark = s.pinned ? '📌 고정됨' : '자동 선택';
      const warn = (!s.pinned && s.tabCount > 1)
        ? `\n⚠ 치지직 탭이 ${s.tabCount}개입니다. 원하는 탭에서 "이 탭을 대상으로"를 누르세요.`
        : '';
      $('target').textContent = `${mark}: ${s.targetTitle || '(제목 없음)'}${warn}`;
    }

    // 마지막 명령이 실제로 탭에 닿았는지. 서버까지 왔는데 화면에 아무 일도
    // 일어나지 않을 때 어디서 끊겼는지 여기서 바로 보인다.
    const d = s.lastDispatch || '아직 없음';
    $('dispatch').textContent = '마지막 전달: ' + d;
    $('dispatch').style.color = d.startsWith('전달됨') ? '#2e7d32' : '#b3261e';

    /*
     * 봉은 20초마다 서버로 살아있다고 알린다. USB 를 꽂지 않아도 여기서 보인다.
     * 60초 넘게 소식이 없으면 꺼졌거나 WiFi 가 끊긴 것으로 본다.
     */
    const st = s.stick;
    const ago = s.stickAgoSec;
    const se = $('stick');
    if (!st) {
        se.textContent = '봉: 아직 신호가 없습니다';
        se.style.color = '#888';
    } else if (ago !== null && ago > 60) {
        se.textContent = `봉: 끊김 (마지막 신호 ${ago < 3600 ? Math.round(ago/60)+'분' : Math.round(ago/3600)+'시간'} 전)`;
        se.style.color = '#b3261e';
    } else {
        const up = st.uptime < 3600 ? Math.round(st.uptime/60)+'분' : Math.round(st.uptime/3600)+'시간';
        se.textContent = `봉: 연결됨  ${st.ip || ''}  v${st.fw || '?'}  ${up}째  쌓임 ${st.count}` +
            (st.led ? `  ·  LED ${st.led}` : '');
        se.style.color = '#2e7d32';
    }
  } catch (e) {
    $('conn').textContent = '백그라운드 응답 없음';
    $('conn').className = 'stat no';
  }
}

$('save').addEventListener('click', async () => {
  await chrome.runtime.sendMessage({
    type: 'crown-bg-config',
    config: { serverUrl: $('serverUrl').value.trim() },
  });
  log('저장했습니다. 다시 연결하는 중...');
  setTimeout(refresh, 600);
});

/* -------------------------------------------------------------- 대상 탭 */

$('pin').addEventListener('click', async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || !/^https:\/\/chzzk\.naver\.com\//.test(tab.url || '')) {
    return log('치지직 탭에서 눌러주세요.');
  }
  await chrome.runtime.sendMessage({ type: 'crown-bg-pin', tabId: tab.id });
  log('이 탭을 대상으로 지정했습니다.');
  refresh();
});

$('unpin').addEventListener('click', async () => {
  await chrome.runtime.sendMessage({ type: 'crown-bg-pin', tabId: null });
  log('지정을 해제했습니다. 자동 선택으로 돌아갑니다.');
  refresh();
});

/* ------------------------------------------------------ 수동 테스트 */

/*
 * 수동 테스트도 백그라운드를 거쳐 서버 명령과 같은 대상 탭으로 보낸다.
 * 팝업이 직접 "활성 탭"에 보내면 고정한 탭과 달라져 헷갈린다.
 */
async function dispatch(msg, okText) {
  try {
    const r = await chrome.runtime.sendMessage({ type: 'crown-bg-relay', payload: msg });
    if (r && r.ok) log(okText);
    else log('대상 탭에 전달하지 못했습니다.\n치지직 탭이 열려 있는지, 페이지를 새로고침했는지 확인하세요.');
  } catch (e) {
    log('백그라운드가 응답하지 않습니다.\n확장을 새로고침해 보세요.');
  }
}

$('add').addEventListener('click', () => {
  const emojiId = $('emojiId').value.trim();
  if (!emojiId) return log('이모티콘 ID를 입력하세요.');
  dispatch({ type: 'crown-add', emojiId }, `추가: ${emojiId}`);
});

$('send').addEventListener('click', () => dispatch({ type: 'crown-send' }, '전송했습니다.'));
$('clear').addEventListener('click', () => dispatch({ type: 'crown-clear' }, '입력창을 비웠습니다.'));

/* 입력창 이모티콘 개수 표시 */
chrome.runtime.onMessage.addListener((msg) => {
  if (msg && msg.type === 'crown-changed') {
    log(msg.failed ? '전송 실패 — 입력창이 그대로입니다.'
                   : `입력창 이모티콘: ${msg.count}개`);
  }
});

refresh();
setInterval(refresh, 2000);
