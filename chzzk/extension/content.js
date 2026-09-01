/*
 * 콘텐츠 스크립트 (격리 월드).
 *
 * inject.js 는 manifest 의 world:"MAIN" 설정으로 페이지 컨텍스트에서 따로
 * 실행된다. 격리 월드와 페이지 월드는 서로의 변수에 접근할 수 없으므로,
 * 이 파일은 window CustomEvent 로만 inject.js 와 통신한다.
 *
 * 역할
 *   - 백그라운드(서버에서 온 명령)와 팝업의 요청을 페이지로 넘긴다
 *   - 페이지의 상태 변화를 팝업에 알린다
 *
 * 이 스크립트는 all_frames 로 모든 프레임에 들어간다. 예전에는 여기서
 * URL 경로에 "/chat" 이 있는지로 채팅 프레임을 골라냈는데, 방송 페이지
 * 안의 채팅 iframe 은 주소 형태가 달라서 명령이 통째로 무시됐다.
 * 경로로 추측하지 말고 그냥 모든 프레임에 넘긴 뒤, 실제로 채팅 입력창이
 * 있는 프레임의 inject.js 만 처리하게 한다.
 */

(() => {
  'use strict';

  const LOG = '[크라운봉/content]';
  let ready = false;

  /*
   * 팝업이 닫혀 있으면 수신자가 없어서 sendMessage 가 거부된다.
   * MV3 에서는 프로미스를 반환하므로 catch 를 붙이지 않으면
   * "Could not establish connection" 이 콘솔을 도배한다.
   */
  function notify(msg) {
    try {
      const p = chrome.runtime.sendMessage(msg);
      if (p && typeof p.catch === 'function') p.catch(() => {});
    } catch (e) { /* 무시 */ }
  }

  window.addEventListener('crown:ready', () => {
    ready = true;
    console.log(LOG, '채팅 입력창이 있는 프레임입니다:', location.pathname);
    notify({ type: 'crown-ready', url: location.href });
  });

  window.addEventListener('crown:changed', (ev) => {
    const d = (ev && ev.detail) || {};
    notify({ type: 'crown-changed', count: d.count, failed: !!d.failed });
  });

  /** 페이지 컨텍스트로 명령을 넘긴다 */
  function cmd(detail) {
    window.dispatchEvent(new CustomEvent('crown:cmd', { detail }));
  }

  /*
   * 명령은 탭의 모든 프레임에 도착한다.
   *
   * 예전에는 모든 프레임이 reply() 하고 return true 를 했는데, 두 가지가
   * 잘못이었다.
   *   - reply() 를 동기로 부르고 true 를 반환하면 포트를 열어둔 채 끝나서
   *     "message port closed before a response was received" 가 뜬다
   *   - 프레임이 여럿이라 응답도 여럿인데 크롬은 하나만 받는다
   *
   * 그래서 채팅 입력창이 있는 프레임만 한 번 응답하고, 나머지는 조용히
   * 처리만 한다.
   */
  chrome.runtime.onMessage.addListener((msg, sender, reply) => {
    if (!msg || !msg.type) return;

    switch (msg.type) {
    case 'crown-add':   cmd({ action: 'add', emojiId: msg.emojiId }); break;
    case 'crown-send':  cmd({ action: 'send' }); break;
    case 'crown-clear': cmd({ action: 'clear' }); break;
    default: return;
    }

    if (ready) reply({ ok: true });
    // 동기 처리이므로 true 를 반환하지 않는다
  });
})();
