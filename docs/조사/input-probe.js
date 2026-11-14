/*
 * 치지직 채팅 입력창 조사 스크립트.
 *
 * 목적: "이모티콘을 입력창에 넣으면 전송 시 이미지로 렌더링되게" 하려면
 * 치지직이 이모티콘 정보를 어디에 들고 있는지 알아야 한다.
 *
 * 확인된 사실:
 *   - 입력창에 {:redredLight:} 를 손으로 타이핑하면 글자 그대로 전송된다
 *   - 이모티콘 피커로 고르면 정상 렌더링된다
 *   → 따라서 페이지가 본문 텍스트와 별개로 "이 메시지에 쓰인 이모티콘" 목록을
 *     어딘가(리액트 state 등)에 들고 있다가 전송 시 extras.emojis 로 직렬화한다.
 *
 * 이 스크립트는 그 '어딘가'를 찾는다.
 *
 * ---------------------------------------------------------------------------
 * 사용법
 * ---------------------------------------------------------------------------
 * 1. 채팅 iframe 을 단독 탭으로 연다
 *      https://chzzk.naver.com/iframe/live/{channelId}/chat?theme=light
 * 2. F12 → Console (붙여넣기가 막히면 allow pasting 입력 후 엔터)
 * 3. 이 파일 전체를 붙여넣는다
 * 4. probe.input()      입력창을 찾았는지 확인
 * 5. probe.before()     상태 스냅샷을 뜬다
 * 6. 이모티콘 피커에서 이모티콘을 하나 고른다 (전송은 하지 말 것)
 * 7. probe.after()      무엇이 달라졌는지 출력된다  ← 여기가 핵심
 *
 * 6번에서 늘어난 필드가 곧 우리가 조작해야 할 대상이다.
 */

(() => {
  'use strict';

  const LOG = '[probe]';

  /* ---------------------------------------------------- 리액트 내부 접근 */

  const fiberKey = (el) =>
    Object.keys(el).find((k) => k.startsWith('__reactFiber$')
      || k.startsWith('__reactInternalInstance$'));

  const propsKey = (el) =>
    Object.keys(el).find((k) => k.startsWith('__reactProps$'));

  const getFiber = (el) => {
    const k = el && fiberKey(el);
    return k ? el[k] : null;
  };

  /* ---------------------------------------------------------- 입력창 찾기 */

  function findInput() {
    // 치지직 입력창은 textarea 이거나 contenteditable 일 수 있다. 둘 다 훑는다.
    const cands = [
      ...document.querySelectorAll('textarea'),
      ...document.querySelectorAll('[contenteditable="true"]'),
      ...document.querySelectorAll('input[type="text"]'),
    ];
    if (!cands.length) return null;

    // 화면에 실제로 보이는 것 중 가장 큰 것을 고른다
    const visible = cands.filter((el) => {
      const r = el.getBoundingClientRect();
      return r.width > 40 && r.height > 10;
    });
    const pick = (visible.length ? visible : cands)
      .sort((a, b) => {
        const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
        return (rb.width * rb.height) - (ra.width * ra.height);
      })[0];
    return pick || null;
  }

  /* ------------------------------------------- 값을 안전하게 요약해 출력 */

  function summarize(v, depth = 0) {
    if (v === null || v === undefined) return String(v);
    const t = typeof v;
    if (t === 'function') return 'ƒ()';
    if (t === 'string') return v.length > 80 ? `"${v.slice(0, 80)}…"(${v.length})` : `"${v}"`;
    if (t !== 'object') return String(v);
    if (v instanceof Map) return `Map(${v.size}) {${[...v.keys()].slice(0, 5).join(', ')}}`;
    if (v instanceof Set) return `Set(${v.size})`;
    if (Array.isArray(v)) {
      if (depth > 1) return `Array(${v.length})`;
      return `[${v.slice(0, 4).map((x) => summarize(x, depth + 1)).join(', ')}${v.length > 4 ? ', …' : ''}]`;
    }
    if (v instanceof HTMLElement) return `<${v.tagName.toLowerCase()}>`;
    const keys = Object.keys(v);
    if (depth > 1) return `{${keys.slice(0, 6).join(', ')}}`;
    return `{ ${keys.slice(0, 8).map((k) => `${k}: ${summarize(v[k], depth + 1)}`).join(', ')}${keys.length > 8 ? ', …' : ''} }`;
  }

  /*
   * 리액트 훅 state 는 fiber.memoizedState 에 연결 리스트로 달려 있다.
   * 조상 fiber 를 거슬러 올라가며 각 컴포넌트의 state/props 를 평평하게 모은다.
   */
  function collectState(el, maxDepth = 14) {
    const out = [];
    let fiber = getFiber(el);
    let depth = 0;

    while (fiber && depth < maxDepth) {
      const name = typeof fiber.type === 'function'
        ? (fiber.type.displayName || fiber.type.name || 'Anonymous')
        : (typeof fiber.type === 'string' ? fiber.type : '?');

      // 훅 체인 순회
      let hook = fiber.memoizedState;
      let idx = 0;
      while (hook && idx < 40) {
        if (hook.memoizedState !== undefined && typeof hook.memoizedState !== 'function') {
          out.push({ path: `${depth}:${name}#hook${idx}`, value: hook.memoizedState });
        }
        hook = hook.next;
        idx++;
      }

      if (fiber.memoizedProps && typeof fiber.memoizedProps === 'object') {
        for (const [k, v] of Object.entries(fiber.memoizedProps)) {
          if (k === 'children' || typeof v === 'function') continue;
          out.push({ path: `${depth}:${name}.props.${k}`, value: v });
        }
      }

      fiber = fiber.return;
      depth++;
    }
    return out;
  }

  const KEYWORDS = ['emoji', 'emoticon', 'emote', '이모티콘', 'sticker'];

  function looksRelevant(entry) {
    const p = entry.path.toLowerCase();
    if (KEYWORDS.some((k) => p.includes(k))) return true;
    const s = summarize(entry.value).toLowerCase();
    return KEYWORDS.some((k) => s.includes(k)) || s.includes('{:');
  }

  /* -------------------------------------------------------------- 스냅샷 */

  let snapshot = null;

  window.probe = {
    input() {
      const el = findInput();
      if (!el) {
        console.warn(LOG, '입력창을 찾지 못했습니다. 채팅 iframe 탭이 맞는지 확인하세요.');
        return null;
      }
      console.log(LOG, '입력창:', el);
      console.log(LOG, '태그:', el.tagName,
        '| contenteditable:', el.getAttribute('contenteditable'),
        '| 리액트 fiber:', !!getFiber(el),
        '| 리액트 props:', !!propsKey(el));
      console.log(LOG, '현재 값:', JSON.stringify(el.value ?? el.textContent));
      return el;
    },

    /** 이모티콘을 고르기 '전' 상태를 기록 */
    before() {
      const el = findInput();
      if (!el) return console.warn(LOG, '입력창 없음');
      const entries = collectState(el);
      snapshot = new Map(entries.map((e) => [e.path, summarize(e.value)]));
      console.log(`${LOG} 스냅샷 저장 (${snapshot.size}개 항목).`);
      console.log('%c이제 이모티콘 피커에서 이모티콘을 하나 고르세요. 전송은 하지 마세요.',
        'color:#08f;font-weight:bold');
      console.log('그 다음 probe.after() 를 실행하세요.');
    },

    /** 고른 '후' 상태와 비교 */
    after() {
      if (!snapshot) return console.warn(LOG, 'probe.before() 를 먼저 실행하세요.');
      const el = findInput();
      if (!el) return console.warn(LOG, '입력창 없음');

      const entries = collectState(el);
      const changed = [];
      for (const e of entries) {
        const now = summarize(e.value);
        const was = snapshot.get(e.path);
        if (was !== now) changed.push({ path: e.path, 이전: was ?? '(없음)', 이후: now });
      }

      console.log(`${LOG} 달라진 항목 ${changed.length}개`);
      if (changed.length) console.table(changed);

      const hot = changed.filter((c) =>
        KEYWORDS.some((k) => c.path.toLowerCase().includes(k))
        || String(c.이후).includes('{:')
        || String(c.이후).toLowerCase().includes('emoji'));

      if (hot.length) {
        console.log('%c▼ 이모티콘 관련으로 보이는 것 — 여기가 조작 대상입니다',
          'color:#0a0;font-weight:bold');
        console.table(hot);
      } else {
        console.log(LOG, '키워드로는 못 찾았습니다. 위 전체 표에서 배열/객체가 늘어난 항목을 보세요.');
      }
      return changed;
    },

    /** 현재 상태에서 이모티콘 관련으로 보이는 것만 훑어보기 */
    scan() {
      const el = findInput();
      if (!el) return console.warn(LOG, '입력창 없음');
      const hits = collectState(el).filter(looksRelevant);
      console.log(`${LOG} 관련 후보 ${hits.length}개`);
      console.table(hits.map((h) => ({ path: h.path, 값: summarize(h.value) })));
      return hits;
    },

    /** 전송 버튼으로 보이는 것들 (버튼 누름을 재현할 때 필요) */
    sendButton() {
      const btns = [...document.querySelectorAll('button')];
      const info = btns.map((b, i) => ({
        i,
        text: (b.textContent || '').trim().slice(0, 20),
        aria: b.getAttribute('aria-label'),
        cls: (b.className || '').toString().slice(0, 50),
        disabled: b.disabled,
      }));
      console.log(`${LOG} 버튼 ${btns.length}개`);
      console.table(info);
      console.log('실제 요소는 probe.buttons[i] 로 접근하세요.');
      window.probe.buttons = btns;
      return btns;
    },
  };

  console.log(
    `%c${LOG} 준비 완료\n\n` +
    '  probe.input()        입력창 찾기\n' +
    '  probe.before()       이모티콘 고르기 전 스냅샷\n' +
    '  (이모티콘 피커에서 하나 고르기 — 전송 금지)\n' +
    '  probe.after()        무엇이 달라졌는지 비교  ← 핵심\n' +
    '  probe.scan()         현재 상태에서 이모티콘 관련 항목 훑기\n' +
    '  probe.sendButton()   전송 버튼 후보 목록',
    'color:#0a0;font-weight:bold'
  );
})();
