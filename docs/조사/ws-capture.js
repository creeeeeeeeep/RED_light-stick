/*
 * 치지직 채팅 WebSocket 전송 프레임 캡처 스니펫.
 *
 * DevTools 의 Network > Socket 에 아무것도 안 뜨는 경우가 있다 (채팅 소켓이
 * Web Worker 안에서 열리면 메인 Network 패널에 잡히지 않는다). 이 스니펫은
 * WebSocket.prototype.send 를 직접 감싸므로 소켓이 어디서 열렸든 잡힌다.
 *
 * 이 후킹 방식이 곧 확장 프로그램이 쓸 방식이므로, 여기서 동작하면
 * 확장에서도 동작한다고 볼 수 있다.
 *
 * ---------------------------------------------------------------------------
 * 사용법
 * ---------------------------------------------------------------------------
 * 1. 채팅 iframe 을 단독 탭으로 연다 (채널ID는 본인 것으로)
 *      https://chzzk.naver.com/iframe/live/{channelId}/chat?theme=light
 *
 * 2. F12 → Console 탭
 *
 * 3. 크롬이 콘솔 붙여넣기를 막고 경고를 띄우면,
 *    프롬프트에 allow pasting 이라고 입력하고 엔터 (최초 1회만)
 *
 * 4. 이 파일 내용 전체를 붙여넣고 엔터
 *
 * 5. 채팅창에서 이모티콘을 하나 보낸다
 *
 * 6. 콘솔에 __dump() 입력 → 민감값이 가려진 프레임이 클립보드로 복사된다
 *
 * ---------------------------------------------------------------------------
 * 개인정보
 * ---------------------------------------------------------------------------
 * __dump() 는 25자 이상의 랜덤해 보이는 문자열을 <REDACTED> 로 치환한다.
 * 세션 토큰 종류가 여기 걸린다. 구조와 필드 이름은 그대로 남으므로 분석에는
 * 지장이 없다. 붙여넣기 전에 한 번 훑어보고, 남아 있는 긴 값이 있으면
 * 직접 지울 것.
 */

(() => {
  if (window.__wsHooked) {
    console.log('이미 후킹돼 있습니다. __dump() 를 쓰세요.');
    return;
  }
  window.__wsHooked = true;
  window.__frames = [];
  window.__sockets = [];

  // 소켓이 열릴 때 URL 을 기록해 둔다
  const NativeWS = window.WebSocket;
  window.WebSocket = function (url, protocols) {
    const ws = protocols ? new NativeWS(url, protocols) : new NativeWS(url);
    window.__sockets.push({ url, ws });
    console.log('%c[OPEN]', 'color:#08f;font-weight:bold', url);
    return ws;
  };
  window.WebSocket.prototype = NativeWS.prototype;
  Object.assign(window.WebSocket, NativeWS);

  // 나가는 프레임을 가로챈다
  const origSend = NativeWS.prototype.send;
  NativeWS.prototype.send = function (data) {
    try {
      if (typeof data === 'string') {
        window.__frames.push(data);
        console.log('%c[SEND]', 'color:#0a0;font-weight:bold', data);
      }
    } catch (e) { /* 캡처 실패가 채팅을 막으면 안 된다 */ }
    return origSend.call(this, data);
  };

  /*
   * 민감값 마스킹.
   *
   * 처음에는 "긴 랜덤 문자열"을 정규식으로 잡으려 했는데 두 군데서 뚫렸다.
   *   - sid 에는 '!' 가 들어가서 문자 클래스에 안 걸림
   *   - extraToken 은 extras(중첩 JSON 문자열) 안에 있어서 따옴표가 \" 로
   *     이스케이프돼 있어 패턴이 안 맞음
   * 그래서 정규식 대신 JSON 을 파싱해서 키 이름 기준으로 지운다.
   * extras 는 문자열 안에 든 JSON 이므로 한 번 더 파싱한다.
   */
  const SENSITIVE = new Set([
    'sid', 'extraToken', 'accessToken', 'accTkn', 'token',
    'uid', 'userIdHash', 'deviceId', 'did', 'cookie',
  ]);

  const redactObj = (o) => {
    if (Array.isArray(o)) return o.map(redactObj);
    if (o && typeof o === 'object') {
      const r = {};
      for (const [k, v] of Object.entries(o)) {
        r[k] = (SENSITIVE.has(k) && typeof v === 'string' && v.length > 8)
          ? '<REDACTED>'
          : redactObj(v);
      }
      return r;
    }
    return o;
  };

  const redact = (raw) => {
    try {
      const o = JSON.parse(raw);
      if (o && o.bdy && typeof o.bdy.extras === 'string') {
        try { o.bdy.extras = redactObj(JSON.parse(o.bdy.extras)); } catch (e) { /* 평문이면 그대로 */ }
      }
      return JSON.stringify(redactObj(o), null, 2);
    } catch (e) {
      // JSON 이 아니면(하트비트 등) 긴 문자열만 통째로 가린다
      return String(raw).replace(/[A-Za-z0-9_\-+/=!~.]{30,}/g, '<REDACTED>');
    }
  };

  window.__dump = () => {
    if (!window.__frames.length) {
      console.log('캡처된 프레임이 없습니다. 이모티콘을 먼저 보내보세요.');
      return;
    }
    const out = window.__frames.map((f, i) => `--- frame ${i} ---\n${redact(f)}`).join('\n\n');
    console.log(out);
    if (typeof copy === 'function') {
      copy(out);
      console.log('%c클립보드에 복사됨', 'color:#0a0;font-weight:bold');
    }
    return out;
  };

  // 이모티콘 코드가 들어간 프레임만 골라 보기
  window.__emojiFrames = () =>
    window.__frames.filter((f) => f.includes('{:')).map(redact);

  console.log(
    '%c후킹 완료. 이제 채팅창에서 이모티콘을 하나 보내세요.\n' +
    '그 다음 __dump() 를 입력하면 정리된 결과가 클립보드로 복사됩니다.',
    'color:#0a0;font-weight:bold'
  );
})();
