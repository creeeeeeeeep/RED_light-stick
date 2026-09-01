/*
 * 크라운 응원봉 — 치지직 채팅 이모티콘 전송 코어
 *
 * 이 파일은 반드시 **페이지 컨텍스트**에서 돌아야 한다. 확장의 콘텐츠 스크립트는
 * 격리된 월드에서 실행돼 페이지가 만든 WebSocket 객체에 손댈 수 없기 때문이다.
 * content.js 가 <script> 태그로 이 파일을 페이지에 주입한다.
 *
 * ---------------------------------------------------------------------------
 * 동작 원리
 * ---------------------------------------------------------------------------
 * 치지직 채팅 전송 프레임에는 세션마다 바뀌는 값이 셋 들어간다 (cid, sid,
 * extraToken). 하드코딩할 수 없으므로 WebSocket.send 를 후킹해 지나가는
 * 전송 프레임(cmd 3101)에서 이 값들을 관찰해 템플릿으로 저장한다.
 * 그 뒤에는 템플릿에서 msg / emojis / msgTime / tid 만 갈아끼워 전송한다.
 *
 * 이 방식이면 치지직이 세션 관리 방식을 바꿔도 재학습만으로 따라간다.
 *
 * ---------------------------------------------------------------------------
 * 브라우저만으로 테스트하기 (봉 없이)
 * ---------------------------------------------------------------------------
 * 1. 채팅 iframe 을 단독 탭으로 연다
 *      https://chzzk.naver.com/iframe/live/{channelId}/chat?theme=light
 * 2. F12 → Console. 붙여넣기가 막히면 allow pasting 입력 후 엔터
 * 3. 이 파일 전체를 붙여넣고 엔터
 * 4. 채팅창에 아무 말이나 한 번 친다   ← extraToken 학습에 필요
 * 5. crown.list()          사용 가능한 이모티콘 확인
 *    crown.send('redredLight')   전송
 */

(() => {
  'use strict';

  const VERSION = '0.2.0';
  const LOG = '[크라운봉]';

  /*
   * 재설치를 허용한다.
   *
   * 처음에는 "이미 설치됨"이면 그냥 빠지게 했는데, 개발 중 콘솔에 새 버전을
   * 붙여넣어도 옛 코드가 계속 도는 문제가 있었다. 그래서 대신
   *   - 원본 send 는 최초 1회만 보관해서 후킹이 겹겹이 쌓이지 않게 하고
   *   - 학습된 상태(템플릿/소켓/이모티콘)는 이어받아
   * 새로고침이나 채팅 재입력 없이 코드만 갈아끼울 수 있게 한다.
   */
  const origSend = window.__crownOrigSend
    || (window.__crownOrigSend = WebSocket.prototype.send);

  const prev = window.__crownState;
  if (prev) {
    console.log(`${LOG} 기존 설치를 교체합니다 (학습 상태는 유지)`);
  }
  const CMD_SEND_CHAT = 3101;
  const IMAGE_SUFFIX = '?type=f60_60';   // 웹 클라이언트가 붙이는 리사이즈 파라미터

  const state = {
    socket: null,
    template: null,
    tid: 0,
    emojis: new Map(),      // emojiId -> imageUrl
    locked: new Set(),      // 미구독이라 못 쓰는 emojiId
    lastSentAt: 0,
    cooldownMs: 3000,       // 도배 방지. 치지직 자체 제한에 걸리지 않도록

    /*
     * 한 메시지에 넣을 이모티콘 개수/길이 상한.
     *
     * 공식 API 문서에는 메시지가 100자 제한이라고 돼 있으나 웹 채팅의 실제
     * 상한은 확인하지 못했다. {:redredLight:} 처럼 ID 가 긴 이모티콘은 하나에
     * 15자를 먹어서 8개면 120자가 된다 — 길이 쪽이 먼저 걸릴 수 있다.
     * crown.setLimits() 로 올려가며 실제 상한을 찾을 것.
     */
    maxCount: 8,
    maxLength: 100,

    queue: [],              // 버튼 누를 때까지 쌓아두는 이모티콘
  };

  /*
   * 이전 설치에서 학습해 둔 것만 골라 이어받는다.
   * 상한/쿨다운 같은 설정값은 새 코드의 기본값을 쓴다.
   */
  if (prev) {
    state.socket   = prev.socket;
    state.template = prev.template;
    state.tid      = prev.tid || 0;
    if (prev.emojis instanceof Map && prev.emojis.size) state.emojis = prev.emojis;
    if (prev.locked instanceof Set) state.locked = prev.locked;
  }
  window.__crownState = state;

  /* ------------------------------------------------------------------ 후킹 */

  WebSocket.prototype.send = function (data) {
    try {
      learnFrom(this, data);
    } catch (e) {
      /* 학습 실패가 실제 채팅을 막아서는 안 된다 */
    }
    return origSend.call(this, data);
  };

  function learnFrom(ws, data) {
    if (typeof data !== 'string' || data.length < 20) return;

    let frame;
    try { frame = JSON.parse(data); } catch (e) { return; }
    if (!frame || frame.cmd !== CMD_SEND_CHAT || !frame.bdy) return;

    let extras;
    try { extras = JSON.parse(frame.bdy.extras); } catch (e) { return; }
    if (!extras || !extras.extraToken) return;

    const first = !state.template;
    state.socket = ws;
    state.template = {
      ver: frame.ver,
      svcid: frame.svcid,
      cid: frame.cid,
      sid: frame.sid,
      chatType: extras.chatType,
      osType: extras.osType,
      extraToken: extras.extraToken,
      streamingChannelId: extras.streamingChannelId,
    };
    // 서버가 tid 중복을 싫어할 수 있으니 관측값보다 항상 크게 유지
    state.tid = Math.max(state.tid, Number(frame.tid) || 0);

    if (first) {
      console.log(`%c${LOG} 템플릿 학습 완료`, 'color:#0a0;font-weight:bold');
      loadEmojis().catch((e) => console.warn(LOG, '이모티콘 목록 로드 실패:', e.message));
      window.dispatchEvent(new CustomEvent('crown:ready'));
    }
  }

  /* -------------------------------------------------------- 이모티콘 카탈로그 */

  function channelId() {
    if (state.template && state.template.streamingChannelId) {
      return state.template.streamingChannelId;
    }
    // /iframe/live/{channelId}/chat 에서 뽑는다
    const m = location.pathname.match(/\/live\/([0-9a-f]{32})/i);
    return m ? m[1] : null;
  }

  /*
   * emoji-packs 는 Origin 이 https://chzzk.naver.com 으로 고정돼 있고
   * credentials 를 요구한다. 그래서 이 호출은 페이지 컨텍스트에서만 가능하다.
   * (확장 백그라운드에서 부르면 CORS 로 막힌다)
   */
  async function loadEmojis() {
    const id = channelId();
    if (!id) throw new Error('채널 ID를 찾지 못했습니다');

    const res = await fetch(
      `https://api.chzzk.naver.com/service/v1/channels/${id}/emoji-packs`,
      {
        credentials: 'include',
        headers: {
          'Front-Client-Platform-Type': 'PC',
          'Front-Client-Product-Type': 'web',
        },
      }
    );
    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const json = await res.json();
    const content = json && json.content;
    if (!content) throw new Error('응답 형식이 예상과 다릅니다');

    state.emojis.clear();
    state.locked.clear();

    // 기본 팩 — 누구나 사용 가능
    for (const pack of content.emojiPacks || []) {
      for (const e of pack.emojis || []) state.emojis.set(e.emojiId, e.imageUrl);
    }

    // 구독 팩 — 잠금 상태를 반영한다
    for (const pack of content.subscriptionEmojiPacks || []) {
      const t1 = pack.tier1Emojis || pack.emojis || [];
      const t2 = pack.tier2Emojis || [];

      for (const e of [...t1, ...t2]) state.emojis.set(e.emojiId, e.imageUrl);

      if (pack.emojiPackLocked) {
        // 이 채널 미구독 → 팩 전체 사용 불가
        for (const e of [...t1, ...t2]) state.locked.add(e.emojiId);
      } else if (pack.emojiTier2Locked) {
        // 티어1만 구독 → 티어2만 사용 불가
        for (const e of t2) state.locked.add(e.emojiId);
      }
    }

    const usable = state.emojis.size - state.locked.size;
    console.log(`${LOG} 이모티콘 ${state.emojis.size}개 로드 (사용 가능 ${usable}개)`);
    return usable;
  }

  /* -------------------------------------------------------------------- 전송 */

  /** 이모티콘 ID 하나가 메시지에서 차지하는 글자 수 */
  const tokenLen = (id) => id.length + 4;   // "{:" + id + ":}"

  function assertUsable(emojiId) {
    if (state.locked.has(emojiId)) {
      throw new Error(`구독하지 않아 사용할 수 없는 이모티콘입니다: ${emojiId}`);
    }
    const url = state.emojis.get(emojiId);
    if (!url) {
      throw new Error(`이모티콘을 찾을 수 없습니다: ${emojiId}`);
    }
    return url;
  }

  /**
   * 이모티콘을 한 메시지로 전송한다.
   *
   * @param {string|string[]} emojiIds  하나 또는 여러 개. 같은 것을 반복해도 된다.
   *
   * 여러 개를 붙일 때 msg 는 "{:a:}{:a:}{:b:}" 처럼 이어 붙이고,
   * emojis 는 맵이므로 중복 ID 는 한 항목으로 합쳐진다. 이게 웹 클라이언트가
   * 하는 방식과 같다.
   */
  function send(emojiIds, opts) {
    const ignoreCooldown = opts && opts.force;
    const ids = Array.isArray(emojiIds) ? emojiIds.slice() : [emojiIds];

    if (!ids.length) throw new Error('보낼 이모티콘이 없습니다.');
    if (!state.template) {
      throw new Error('아직 준비되지 않았습니다. 채팅을 아무거나 한 번 쳐주세요.');
    }
    if (!state.socket || state.socket.readyState !== WebSocket.OPEN) {
      throw new Error('채팅 연결이 끊겼습니다. 페이지를 새로고침하세요.');
    }
    if (ids.length > state.maxCount) {
      throw new Error(`이모티콘이 너무 많습니다 (${ids.length} > ${state.maxCount}).`);
    }

    // 전부 사용 가능한지 먼저 확인 — 중간에 실패해서 반만 나가는 일이 없도록
    const urls = new Map();
    for (const id of ids) urls.set(id, assertUsable(id));

    const msg = ids.map((id) => `{:${id}:}`).join('');
    if (msg.length > state.maxLength) {
      throw new Error(
        `메시지가 너무 깁니다 (${msg.length}자 > ${state.maxLength}자). ` +
        `ID가 긴 이모티콘은 개수를 줄이거나 crown.setLimits() 로 상한을 조정하세요.`
      );
    }

    const now = Date.now();
    if (!ignoreCooldown && now - state.lastSentAt < state.cooldownMs) {
      const left = Math.ceil((state.cooldownMs - (now - state.lastSentAt)) / 100) / 10;
      throw new Error(`쿨다운 중입니다 (${left}초 남음)`);
    }

    const t = state.template;

    // 중복 ID 는 자동으로 하나로 합쳐진다 (맵이므로)
    const emojis = {};
    for (const [id, url] of urls) {
      emojis[id] = url + (url.includes('?') ? '' : IMAGE_SUFFIX);
    }

    /*
     * extras 는 객체가 아니라 JSON '문자열'이다. 이중 인코딩이라
     * stringify 를 두 번 거쳐야 하며, 이를 빠뜨리면 서버가 프레임을 거부한다.
     */
    const extras = JSON.stringify({
      chatType: t.chatType,
      osType: t.osType,
      extraToken: t.extraToken,
      streamingChannelId: t.streamingChannelId,
      emojis,
    });

    const frame = JSON.stringify({
      ver: t.ver,
      cmd: CMD_SEND_CHAT,
      svcid: t.svcid,
      cid: t.cid,
      sid: t.sid,
      bdy: {
        msg,
        msgTypeCode: 1,
        extras,
        msgTime: now,
      },
      tid: ++state.tid,
    });

    // 우리 후킹을 다시 타지 않도록 원본 send 를 직접 부른다
    origSend.call(state.socket, frame);
    state.lastSentAt = now;
    return { count: ids.length, length: msg.length };
  }

  /* --------------------------------------------------------------- 큐 -- */
  /*
   * "흔들면 쌓이고 버튼 누르면 전송" 컨셉의 브라우저 쪽 구현.
   * 실제 제품에서는 봉 펌웨어가 큐를 들고 LED 로 보여주지만, 봉 없이
   * 테스트할 때와 봉이 개별 이벤트만 보내는 경우를 위해 여기에도 둔다.
   */

  function push(emojiId) {
    assertUsable(emojiId);

    if (state.queue.length >= state.maxCount) {
      return { added: false, reason: 'full', queue: state.queue.length };
    }
    const projected = [...state.queue, emojiId].reduce((n, id) => n + tokenLen(id), 0);
    if (projected > state.maxLength) {
      return { added: false, reason: 'length', queue: state.queue.length };
    }

    state.queue.push(emojiId);
    window.dispatchEvent(new CustomEvent('crown:queue', {
      detail: { queue: state.queue.slice(), full: state.queue.length >= state.maxCount },
    }));
    return { added: true, queue: state.queue.length };
  }

  function flush(opts) {
    if (!state.queue.length) throw new Error('큐가 비어 있습니다.');
    const ids = state.queue.slice();
    const result = send(ids, opts);       // 실패하면 큐를 비우지 않는다
    state.queue.length = 0;
    window.dispatchEvent(new CustomEvent('crown:queue', { detail: { queue: [], full: false } }));
    return result;
  }

  /* -------------------------------------------------------------- 외부 API */

  window.crown = {
    send,
    push,
    flush,

    /** 현재 큐 상태 */
    queue() {
      return state.queue.slice();
    },

    clear() {
      state.queue.length = 0;
      return true;
    },

    /**
     * 한 메시지의 이모티콘 개수/길이 상한 조정.
     * 실제 상한이 확인되지 않았으므로 올려가며 찾을 때 쓴다.
     */
    setLimits({ count, length } = {}) {
      if (count != null) state.maxCount = Math.max(1, Number(count));
      if (length != null) state.maxLength = Math.max(1, Number(length));
      return { maxCount: state.maxCount, maxLength: state.maxLength };
    },

    /** 사용 가능한 이모티콘 목록. filter 로 부분 일치 검색 */
    list(filter) {
      const out = [];
      for (const [id] of state.emojis) {
        if (state.locked.has(id)) continue;
        if (filter && !id.toLowerCase().includes(String(filter).toLowerCase())) continue;
        out.push(id);
      }
      return out;
    },

    /** 잠긴(미구독) 이모티콘 목록 */
    listLocked() {
      return [...state.locked];
    },

    /** 현재 상태 확인 */
    status() {
      return {
        준비됨: !!state.template,
        연결됨: !!state.socket && state.socket.readyState === WebSocket.OPEN,
        이모티콘수: state.emojis.size,
        사용가능: state.emojis.size - state.locked.size,
        큐: state.queue.slice(),
        최대개수: state.maxCount,
        최대길이: state.maxLength,
        쿨다운ms: state.cooldownMs,
        채널: channelId(),
      };
    },

    setCooldown(ms) {
      state.cooldownMs = Math.max(0, Number(ms) || 0);
      return state.cooldownMs;
    },

    reloadEmojis: loadEmojis,
  };

  /*
   * 콘텐츠 스크립트가 봉 이벤트를 이 이벤트로 전달한다.
   * 페이지와 콘텐츠 스크립트는 격리된 월드라 window 이벤트로만 통신할 수 있다.
   */
  // 재설치 시 리스너가 중첩되지 않도록 이전 것을 먼저 뗀다
  if (window.__crownHandler) {
    window.removeEventListener('crown:emoji', window.__crownHandler);
  }
  window.__crownHandler = (ev) => {
    const d = (ev && ev.detail) || {};
    try {
      // action: 'push' 는 큐에 쌓기만, 'flush' 는 큐 전송, 기본은 즉시 전송
      if (d.action === 'push') push(d.emojiId);
      else if (d.action === 'flush') flush();
      else if (d.emojiId || d.emojiIds) send(d.emojiIds || d.emojiId);
    } catch (e) {
      console.warn(LOG, e.message);
    }
  };
  window.addEventListener('crown:emoji', window.__crownHandler);

  // 상태를 이어받았는데 이모티콘 목록이 비어 있으면 지금 불러온다
  if (state.template && state.emojis.size === 0) {
    loadEmojis().catch((e) => console.warn(LOG, '이모티콘 목록 로드 실패:', e.message));
  }

  const ready = state.template
    ? '준비 완료 (학습된 상태를 이어받음)'
    : '채팅을 아무거나 한 번 치면 준비가 끝납니다.';

  console.log(
    `%c${LOG} v${VERSION} 설치 완료 — ${ready}\n\n` +
    "  crown.send('redredLight')                        하나 전송\n" +
    "  crown.send(['redredLight','redredLight'])         여러 개 한 메시지로\n" +
    "  crown.push('redredLight'); crown.flush()          쌓았다가 전송\n" +
    "  crown.list('redred')                             사용 가능 목록\n" +
    "  crown.setLimits({count:12, length:200})          상한 조정 (실제 한계 탐색용)\n" +
    '  crown.status()                                   현재 상태',
    'color:#0a0;font-weight:bold'
  );
})();
