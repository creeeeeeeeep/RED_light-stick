/*
 * 크라운 응원봉 — 치지직 채팅 이모티콘 입력 코어
 *
 * 페이지 컨텍스트(world: "MAIN")에서 실행된다.
 *
 * ---------------------------------------------------------------------------
 * 왜 피커를 클릭하는가
 * ---------------------------------------------------------------------------
 * 이모티콘을 채팅에 넣는 방법을 순서대로 시도했고, 앞의 셋은 전부 실패했다.
 *
 *   1) 입력창에 {:id:} 텍스트 입력      → 글자 그대로 전송된다
 *   2) DOM 에 <img> 직접 삽입           → 리렌더 시 새니타이즈되어 텍스트가 된다
 *   3) 리액트 state 에 HTML 직접 주입    → 이미지는 보이는데 전송이 안 된다
 *   4) 피커 버튼을 클릭                 → 동작
 *
 * 3번이 실패한다는 건 입력창 HTML 말고도 치지직이 전송 시 참조하는 상태가
 * 더 있다는 뜻이다. 그걸 계속 추적하는 대신 피커를 실제로 클릭해서 치지직
 * 자기 코드가 필요한 상태를 전부 채우게 한다.
 *
 * 부수 효과로, 사람이 마우스로 하는 동작과 완전히 같은 경로가 된다.
 * 전송 프레임도 치지직이 스스로 만든다.
 *
 * ---------------------------------------------------------------------------
 * 치지직 피커 DOM 구조 (실측)
 * ---------------------------------------------------------------------------
 *   피커      [role="dialog"][aria-modal="true"] 중 #emoji_area 를 가진 것
 *   이모티콘  #emoji_area 안의 button[type="button"] (안에 <img>)
 *   식별자    그 <img> 의 alt 속성 = "{:redredLight:}" 형태
 *
 * 전송에는 별도 버튼이 없다. 엔터 키 이벤트로만 보낸다.
 */

(() => {
  'use strict';

  const VERSION = '0.8.0';
  const LOG = '[크라운봉]';

  const DIALOG_SEL = '[role="dialog"][aria-modal="true"], [role="alertdialog"][aria-modal="true"]';
  const ALT_RE = /^\{:([^:]+):\}$/;
  const ORIGIN = 'https://chzzk.naver.com';   // 프레임 간 postMessage 대상 제한

  const prev = window.__crownState;
  const state = {
    emojis: new Map(),      // emojiId -> imageUrl (목록/잠금 판별용)
    locked: new Set(),
    lastSentAt: 0,
    /*
     * 전송 최소 간격.
     *
     * 치지직에서 "사람 조작 1회 = 채팅 1건"이면 된다는 답을 받았으므로,
     * 이 값은 도배 방지가 아니라 버튼 오작동(더블클릭) 방지 용도다.
     * 그래서 짧아도 된다.
     */
    cooldownMs: 1000,

    /*
     * 한 메시지에 넣을 이모티콘 개수 상한.
     * 치지직 채팅 입력창이 10개까지 받는다 (실측). 글자 수가 아니라
     * 개수로 세므로 ID 길이와 무관하다.
     */
    maxCount: 10,
  };
  if (prev) {
    if (prev.emojis instanceof Map && prev.emojis.size) state.emojis = prev.emojis;
    if (prev.locked instanceof Set) state.locked = prev.locked;
  }
  window.__crownState = state;

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  function isVisible(el) {
    if (!(el instanceof Element) || !el.isConnected) return false;
    const r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return false;
    const s = getComputedStyle(el);
    return s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0';
  }

  /* ---------------------------------------------------------------- 입력창 */

  /*
   * 입력창 찾기.
   *
   * [contenteditable] 만 보면 안 된다. 치지직 채팅 입력창은 한 번 클릭해서
   * 활성화되기 전까지 contenteditable 이 붙어 있지 않은 상태가 있다.
   * 그래서 role="textbox" 등 후보를 넓게 잡고, 라벨에 "채팅"이 들어간 것을
   * 우선한다.
   */
  const INPUT_SEL = [
    '[contenteditable="true"]',
    '[contenteditable="plaintext-only"]',
    '[role="textbox"]',
    'textarea',
    'input[type="text"]',
    'pre[class*="_input_"]',
  ].join(', ');

  function isInputLike(el) {
    if (!(el instanceof HTMLElement)) return false;
    return el.isContentEditable
      || el.getAttribute('role') === 'textbox'
      || el instanceof HTMLTextAreaElement
      || el instanceof HTMLInputElement
      || /(^|\s)_input_/.test(el.className || '');
  }

  function labelOf(el) {
    return ['aria-label', 'placeholder', 'data-placeholder', 'title']
      .map((a) => el.getAttribute(a) || '')
      .join(' ');
  }

  function findInput() {
    // 이미 포커스가 입력창에 있으면 그게 정답이다
    const active = document.activeElement;
    if (active && isInputLike(active) && isVisible(active)) return active;

    const cands = [...document.querySelectorAll(INPUT_SEL)].filter((e) => {
      const r = e.getBoundingClientRect();
      return r.width > 40 && r.height > 8;
    });
    if (!cands.length) return null;

    // 라벨에 채팅이 들어간 것을 우선
    const labeled = cands.filter((e) => /채팅|chat/i.test(labelOf(e)));
    const pool = labeled.length ? labeled : cands;

    // 그래도 여럿이면 가장 넓은 것
    return pool.sort((a, b) => {
      const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
      return (rb.width * rb.height) - (ra.width * ra.height);
    })[0];
  }

  /** 캐럿을 내용 끝으로 */
  function caretToEnd(el) {
    const sel = window.getSelection();
    if (!sel) return;
    const r = document.createRange();
    r.selectNodeContents(el);
    r.collapse(false);
    sel.removeAllRanges();
    sel.addRange(r);
  }

  /*
   * 입력창을 활성화한다.
   *
   * 치지직 입력창은 포커스를 받아야 contenteditable 이 붙는 구조라, 이걸
   * 먼저 하지 않으면 이모티콘을 넣어도 반영되지 않는다. 사용자가 손으로
   * 채팅창을 한 번 클릭해야 동작했던 이유가 이것이다.
   *
   * preventScroll 로 페이지가 튀지 않게 한다.
   */
  async function focusInput() {
    let el = findInput();
    if (!el) return null;

    try { el.focus({ preventScroll: true }); } catch (e) { el.focus(); }
    await raf();

    // 포커스를 받으면서 요소가 바뀌었을 수 있다 (placeholder → contenteditable)
    const after = findInput() || el;
    if (after !== el) {
      try { after.focus({ preventScroll: true }); } catch (e) { after.focus(); }
      await raf();
    }
    if (after.isContentEditable) caretToEnd(after);
    return after;
  }

  /* ---------------------------------------------------------- 피커 감추기 */
  /*
   * 피커를 열고 클릭하는 동안 화면에 보이지 않게 한다.
   *
   * clip-path 로 시각적으로만 지운다. display:none 이나 visibility:hidden 과
   * 달리 레이아웃에서 사라지지 않으므로 버튼의 위치·크기 계산이 정상으로
   * 유지되고 .click() 도 그대로 동작한다.
   *
   * animation/transition 을 끄는 것이 신뢰성의 핵심이다. 피커가 열리는
   * 애니메이션이 끝나기 전에는 버튼이 아직 제자리에 없어 클릭이 자주 실패한다
   * (이걸 안 껐을 때 10번 중 3번만 성공했다).
   *
   * 후원 다이얼로그 안의 이모티콘 영역은 제외한다 — 사용자가 직접 쓰는
   * 화면까지 감추면 안 된다.
   */
  const STEALTH_CLASS = 'crown-picker-stealth';
  const STEALTH_STYLE_ID = 'crown-picker-stealth-style';

  function ensureStealthStyle() {
    if (document.getElementById(STEALTH_STYLE_ID)) return;
    const sel = (role) =>
      `html.${STEALTH_CLASS} [role="${role}"][aria-modal="true"]`
      + ':has(#emoji_area):not(:has(#donation-money))';
    const style = document.createElement('style');
    style.id = STEALTH_STYLE_ID;
    style.textContent =
      `${sel('dialog')}, ${sel('alertdialog')} {`
      + 'clip-path: inset(100%) !important;'
      + 'pointer-events: none !important;'
      + 'transition: none !important;'
      + 'animation: none !important;'
      + '}';
    (document.head || document.documentElement).appendChild(style);
  }

  function stealthOn() {
    ensureStealthStyle();
    document.documentElement.classList.add(STEALTH_CLASS);
  }

  function stealthOff() {
    document.documentElement.classList.remove(STEALTH_CLASS);
  }

  /*
   * 감춘 채로 피커를 열어두면 사용자가 채팅을 쓸 때 방해가 될 수 있으므로,
   * 일정 시간 추가 요청이 없으면 자동으로 닫고 감추기를 해제한다.
   */
  let idleTimer = 0;
  function scheduleClose(ms = 2500) {
    clearTimeout(idleTimer);
    idleTimer = setTimeout(() => {
      closePicker();
      stealthOff();
    }, ms);
  }

  /* ------------------------------------------------------------------ 피커 */

  function findPicker() {
    return [...document.querySelectorAll(DIALOG_SEL)]
      .filter(isVisible)
      .find((d) => d.querySelector('#emoji_area')) || null;
  }

  /** 피커를 여는 버튼. 클래스명은 빌드마다 바뀌므로 라벨로 찾는다. */
  function findTrigger() {
    const input = findInput();
    const scope = (input && input.closest('form, section, [class*="chat"], [class*="Chat"]'))
      || document;
    const btns = [...scope.querySelectorAll('button, [role="button"]')].filter(isVisible);

    return btns.find((b) => {
      const labels = [b.getAttribute('aria-label'), b.getAttribute('title'), b.textContent]
        .map((s) => String(s || '').replace(/\s+/g, ' ').trim());
      return labels.some((t) => t.startsWith('이모티콘'));
    }) || null;
  }

  /** 피커 안 이모티콘 버튼들 */
  function emoteButtons(picker) {
    const area = picker && picker.querySelector('#emoji_area');
    if (!area) return [];
    return [...area.querySelectorAll('button[type="button"]')].filter((b) => {
      const img = b.querySelector('img');
      if (!img) return false;
      if (!ALT_RE.test(img.getAttribute('alt') || '')) return false;
      return isVisible(b);
    });
  }

  function emojiIdOf(btn) {
    const alt = btn.querySelector('img')?.getAttribute('alt') || '';
    const m = alt.match(ALT_RE);
    return m ? m[1] : '';
  }

  async function openPicker(timeoutMs = 1500) {
    let p = findPicker();
    if (p) return p;

    const trigger = findTrigger();
    if (!trigger) throw new Error('이모티콘 버튼을 찾지 못했습니다 (crown.diag() 참고)');
    trigger.click();

    const t0 = Date.now();
    while (Date.now() - t0 < timeoutMs) {
      await sleep(50);
      p = findPicker();
      if (p) return p;
    }
    throw new Error('이모티콘 피커가 열리지 않았습니다');
  }

  function closePicker() {
    if (!findPicker()) return false;
    const trigger = findTrigger();
    if (trigger) trigger.click();
    return true;
  }

  /* -------------------------------------------------------- 이모티콘 목록 */

  function channelId() {
    const m = location.pathname.match(/\/live\/([0-9a-f]{32})/i);
    return m ? m[1] : null;
  }

  /*
   * 카탈로그는 "어떤 이모티콘이 있고 무엇이 잠겨 있는지" 확인용이다.
   * 실제 삽입은 피커 클릭으로 하므로 URL 은 쓰지 않는다.
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
    const content = (await res.json()).content;
    if (!content) throw new Error('응답 형식이 예상과 다릅니다');

    state.emojis.clear();
    state.locked.clear();

    for (const pack of content.emojiPacks || []) {
      for (const e of pack.emojis || []) state.emojis.set(e.emojiId, e.imageUrl);
    }
    for (const pack of content.subscriptionEmojiPacks || []) {
      const t1 = pack.tier1Emojis || pack.emojis || [];
      const t2 = pack.tier2Emojis || [];
      for (const e of [...t1, ...t2]) state.emojis.set(e.emojiId, e.imageUrl);
      if (pack.emojiPackLocked) {
        for (const e of [...t1, ...t2]) state.locked.add(e.emojiId);
      } else if (pack.emojiTier2Locked) {
        for (const e of t2) state.locked.add(e.emojiId);
      }
    }

    const usable = state.emojis.size - state.locked.size;
    console.log(`${LOG} 이모티콘 ${state.emojis.size}개 (사용 가능 ${usable}개)`);
    return usable;
  }

  /* -------------------------------------------------------------- 핵심 동작 */

  function count() {
    const el = findInput();
    return el ? el.querySelectorAll('img').length : 0;
  }

  const raf = () => new Promise((r) => requestAnimationFrame(() => r()));

  /* 이 프레임의 상태 요약 */
  function frameDiag() {
    const el = findInput();
    const p = findPicker();
    return {
      '버전': VERSION,
      '프레임': window.top === window.self ? '최상위' : 'iframe',
      '경로': location.pathname.slice(0, 46),
      '채널ID': channelId() ? '있음' : '없음',
      '입력창': el ? `<${el.tagName.toLowerCase()}>` : '없음',
      '이모티콘 버튼': findTrigger() ? '찾음' : '없음',
      '피커': p ? `열림 (${emoteButtons(p).length})` : '닫힘',
      '카탈로그': state.emojis.size || 0,
      '입력된 개수': el ? count() : '-',
    };
  }

  /* -------------------------------------------------- 피커에서 찾아내기 */
  /*
   * 방마다 피커가 처음 보여주는 팩이 다르다. 내가 구독한 채널의 이모티콘이라도
   * 다른 스트리머 방에서는 다른 탭에 있거나 스크롤 아래에 있어서 당장
   * 렌더링돼 있지 않다. 그래서 세 단계로 찾는다.
   *
   *   1) 지금 보이는 것 중에서
   *   2) #emoji_area 를 위에서 아래까지 스크롤하며
   *   3) 팩 탭을 하나씩 눌러가며 1~2 반복
   *
   * 전부 감춰진(stealth) 상태에서 일어나므로 화면에는 보이지 않는다.
   */

  function findVisible(picker, emojiId) {
    return emoteButtons(picker).find((b) => emojiIdOf(b) === emojiId) || null;
  }

  /** #emoji_area 안에서 실제로 스크롤되는 컨테이너를 찾는다 */
  function scrollBox(picker) {
    const area = picker.querySelector('#emoji_area');
    if (!area) return null;
    if (area.scrollHeight > area.clientHeight + 8) return area;
    for (const el of area.querySelectorAll('*')) {
      if (el.scrollHeight > el.clientHeight + 8) {
        const s = getComputedStyle(el);
        if (/auto|scroll/.test(s.overflowY)) return el;
      }
    }
    return area;
  }

  async function searchByScroll(picker, emojiId) {
    const box = scrollBox(picker);
    if (!box) return null;

    const original = box.scrollTop;
    const step = Math.max(80, box.clientHeight - 40);

    for (let y = 0; y <= box.scrollHeight; y += step) {
      box.scrollTop = y;
      await raf();
      const hit = findVisible(picker, emojiId);
      if (hit) return hit;
      if (y >= box.scrollHeight - box.clientHeight) break;
    }
    box.scrollTop = original;
    return null;
  }

  /*
   * 팩 탭 후보. 이모티콘 버튼(#emoji_area 안)이 아니면서 다이얼로그 안에 있는
   * 클릭 요소들이다. 보통 팩 아이콘이 가로로 늘어서 있다.
   */
  function packTabs(picker) {
    const area = picker.querySelector('#emoji_area');
    return [...picker.querySelectorAll('button, [role="tab"], [role="button"]')]
      .filter((b) => isVisible(b))
      .filter((b) => !area || !area.contains(b) || !b.querySelector('img[alt^="{:"]'));
  }

  async function findEmoteButton(picker, emojiId) {
    let hit = findVisible(picker, emojiId);
    if (hit) return hit;

    hit = await searchByScroll(picker, emojiId);
    if (hit) return hit;

    // 탭을 하나씩 눌러본다
    const tabs = packTabs(picker);
    for (const tab of tabs) {
      try { tab.click(); } catch (e) { continue; }
      await raf();
      await raf();

      const p = findPicker();
      if (!p) return null;          // 탭인 줄 알았는데 닫기 버튼이었다

      hit = findVisible(p, emojiId) || await searchByScroll(p, emojiId);
      if (hit) return hit;
    }
    return null;
  }

  /** 한 번 시도. 성공 여부만 돌려준다. */
  /*
   * baseline 은 add() 가 시작할 때 센 개수다. addOnce 안에서 다시 세면 안 된다.
   *
   * 예전에는 이 함수가 직접 before 를 쟀는데, 그러면 앞선 시도의 클릭이 아직
   * 반영되지 않은 상태에서 새 기준점을 잡게 된다. 곧이어 앞 클릭과 이번 클릭이
   * 둘 다 들어가면서 이모티콘이 두 개씩 붙었다.
   */
  async function addOnce(emojiId, baseline) {
    const picker = findPicker() || await openPicker();
    const btn = await findEmoteButton(picker, emojiId);
    if (!btn) return { ok: false, reason: 'not-found' };

    if (count() > baseline) return { ok: true, late: true };
    btn.click();

    /*
     * 입력창에 반영될 때까지 기다린다. 12프레임(약 200ms)은 너무 짧아서
     * 치지직이 조금만 굼떠도 실패로 보고 다시 눌렀다. 30프레임이면 약 500ms 다.
     */
    for (let i = 0; i < 30; i++) {
      await raf();
      if (count() > baseline) return { ok: true };
    }
    return { ok: false, reason: 'no-change' };
  }

  /**
   * 입력창에 이모티콘 하나를 추가한다. 전송하지 않는다.
   *
   * 피커를 감춘 채로 열고 해당 버튼을 클릭한다. 한 번에 실패하는 경우가
   * 흔해서(피커가 아직 준비되지 않았거나 리렌더 중) 여러 번 재시도한다.
   */
  async function add(emojiId) {
    if (state.locked.has(emojiId)) {
      throw new Error(`구독하지 않아 사용할 수 없는 이모티콘입니다: ${emojiId}`);
    }
    if (count() >= state.maxCount) {
      return { added: false, reason: 'full', count: count() };
    }

    stealthOn();
    clearTimeout(idleTimer);

    /*
     * 피커를 열기 전에 입력창을 활성화한다.
     * 이걸 안 하면 사용자가 채팅창을 손으로 한 번 클릭해야만 동작한다.
     */
    if (!await focusInput()) {
      stealthOff();
      throw new Error('채팅 입력창을 찾지 못했습니다 (채팅이 보이는지, 로그인 상태인지 확인)');
    }

    const baseline = count();
    let last = null;
    try {
      for (let attempt = 0; attempt < 6; attempt++) {
        last = await addOnce(emojiId, baseline);
        if (last.ok) break;

        /*
         * 다시 누르기 전에 늦게 반영됐는지 한 번 더 본다.
         * 여기서 안 보면 이미 들어간 것 위에 하나를 더 얹는다.
         */
        await raf();
        await raf();
        if (count() > baseline) { last = { ok: true, late: true }; break; }
        // 피커가 이상해졌으면 닫았다 다시 연다
        if (attempt === 2) {
          closePicker();
          await raf();
        }
        await raf();
      }
    } finally {
      scheduleClose();
    }

    const after = count();
    window.dispatchEvent(new CustomEvent('crown:changed', { detail: { count: after } }));

    if (!last || !last.ok) {
      if (last && last.reason === 'not-found') {
        throw new Error(
          `피커에서 '${emojiId}' 를 찾지 못했습니다. `
          + '다른 카테고리에 있거나 스크롤이 필요할 수 있습니다 (crown.picker() 확인).'
        );
      }
      throw new Error(`'${emojiId}' 추가에 실패했습니다 (재시도 6회).`);
    }

    return { added: true, count: after };
  }

  /**
   * 입력창 내용을 전송한다. 치지직에는 전송 버튼이 없어 엔터로만 보낸다.
   */
  async function send() {
    let el = findInput();
    if (!el) throw new Error('채팅 입력창을 찾지 못했습니다');
    if (!el.innerHTML.trim()) throw new Error('입력창이 비어 있습니다');

    const now = Date.now();
    if (now - state.lastSentAt < state.cooldownMs) {
      const left = Math.ceil((state.cooldownMs - (now - state.lastSentAt)) / 100) / 10;
      throw new Error(`쿨다운 중입니다 (${left}초 남음)`);
    }

    // 피커가 열려 있으면 포커스를 뺏어 엔터가 먹지 않는다
    clearTimeout(idleTimer);
    closePicker();
    stealthOff();

    const n = count();
    const before = el.innerHTML;

    el = await focusInput() || el;

    const target = (document.activeElement && el.contains(document.activeElement))
      ? document.activeElement : el;
    for (const type of ['keydown', 'keypress', 'keyup']) {
      target.dispatchEvent(new KeyboardEvent(type, {
        key: 'Enter', code: 'Enter', keyCode: 13, which: 13,
        bubbles: true, cancelable: true, composed: true,
      }));
    }
    state.lastSentAt = now;

    // 전송되면 치지직이 입력창을 비운다. 그대로면 실패다.
    setTimeout(() => {
      const el2 = findInput();
      const after = el2 ? el2.innerHTML : '';
      if (after === before && before.trim()) {
        console.warn(`${LOG} 전송되지 않았습니다 — 입력창 내용이 그대로입니다.`);
        window.dispatchEvent(new CustomEvent('crown:changed', { detail: { count: n, failed: true } }));
      } else {
        window.dispatchEvent(new CustomEvent('crown:changed', { detail: { count: 0 } }));
      }
    }, 400);

    return { sent: n };
  }

  /*
   * 입력창 비우기.
   *
   * execCommand 는 지원 중단(deprecated)이라 DevTools 문제 패널에 경고가 쌓인다.
   * 자식 노드를 직접 지우고 input 이벤트를 발생시키면 react-contenteditable 이
   * 알아서 상태를 맞춘다. inputType 을 명시해야 리액트가 삭제로 인식한다.
   */
  function clear() {
    const el = findInput();
    if (!el || !el.innerHTML.trim()) return false;

    el.focus();
    while (el.firstChild) el.removeChild(el.firstChild);

    try {
      el.dispatchEvent(new InputEvent('input', {
        bubbles: true, cancelable: false,
        inputType: 'deleteContentBackward', data: null,
      }));
    } catch (e) {
      el.dispatchEvent(new Event('input', { bubbles: true }));
    }

    window.dispatchEvent(new CustomEvent('crown:changed', { detail: { count: 0 } }));
    return true;
  }

  /* -------------------------------------------------------------- 외부 API */

  window.crown = {
    add,
    send,
    clear,
    count,

    /** 여러 개를 넣고 선택적으로 전송 */
    async addMany(ids, andSend) {
      const list = Array.isArray(ids) ? ids : [ids];
      for (const id of list) await add(id);
      if (andSend) return await send();
      return { count: count() };
    },

    /** 피커에 지금 보이는 이모티콘 목록 */
    async picker(filter) {
      stealthOn();
      const p = await openPicker();
      const rows = emoteButtons(p).map((b, i) => ({ i, emojiId: emojiIdOf(b) }));
      scheduleClose();
      const shown = filter
        ? rows.filter((r) => r.emojiId.toLowerCase().includes(String(filter).toLowerCase()))
        : rows;
      console.log(`${LOG} 피커에 보이는 이모티콘 ${rows.length}개`
        + (filter ? ` / '${filter}' 일치 ${shown.length}개` : ''));
      console.table(shown.slice(0, 80));
      return rows;
    },

    /*
     * 다른 방에서 이모티콘을 못 찾을 때 원인을 좁힌다.
     * 탭이 몇 개인지, 각 탭에 뭐가 들어 있는지 훑는다.
     */
    async pickerDiag(emojiId) {
      stealthOn();
      const p = await openPicker();
      const tabs = packTabs(p);
      const box = scrollBox(p);

      console.log(`${LOG} 피커 구조`);
      console.table({
        '지금 보이는 이모티콘': emoteButtons(p).length,
        '탭 후보': tabs.length,
        '스크롤 영역': box ? `${box.clientHeight}px 창 / ${box.scrollHeight}px 전체` : '없음',
      });

      const seen = new Map();
      for (let i = 0; i < tabs.length; i++) {
        try { tabs[i].click(); } catch (e) { continue; }
        await raf(); await raf();
        const cur = findPicker();
        if (!cur) { console.log(`  탭 ${i}: 피커가 닫힘 (탭이 아님)`); break; }
        const ids = emoteButtons(cur).map(emojiIdOf);
        seen.set(i, ids);
        console.log(`  탭 ${i}: ${ids.length}개` + (ids.length ? ` (예: ${ids.slice(0, 3).join(', ')})` : ''));
      }

      if (emojiId) {
        const found = [...seen].filter(([, ids]) => ids.includes(emojiId)).map(([i]) => i);
        console.log(found.length
          ? `%c'${emojiId}' 는 탭 ${found.join(', ')} 에 있습니다.`
          : `%c'${emojiId}' 를 어느 탭에서도 못 찾았습니다.`,
          found.length ? 'color:#0a0;font-weight:bold' : 'color:#c00;font-weight:bold');
      }

      scheduleClose();
      return seen;
    },

    openPicker,
    closePicker,

    /** 카탈로그 기준 사용 가능 목록 (피커에 보이는 것과 다를 수 있다) */
    list(filter) {
      const out = [];
      for (const [id] of state.emojis) {
        if (state.locked.has(id)) continue;
        if (filter && !id.toLowerCase().includes(String(filter).toLowerCase())) continue;
        out.push(id);
      }
      return out;
    },

    listLocked() {
      return [...state.locked];
    },

    diag() {
      console.table(frameDiag());
      return frameDiag();
    },

    /*
     * 모든 프레임의 상태를 한 번에 본다.
     *
     * 방송 페이지는 프레임이 여러 개라, 콘솔 컨텍스트를 어디에 두느냐에 따라
     * 전혀 다른 결과가 나온다. 어느 프레임에서 실행하든 전체 그림이 보이도록
     * 하위 프레임에 물어서 모은다.
     */
    async diagAll(waitMs = 700) {
      const rows = [{ 위치: '이 프레임', ...frameDiag() }];
      const frames = [...document.querySelectorAll('iframe')];

      const collected = [];
      const onReply = (ev) => {
        const d = ev.data;
        if (d && d.__crown === 'diag-reply') collected.push(d.info);
      };
      window.addEventListener('message', onReply);

      frames.forEach((f, i) => {
        try {
          f.contentWindow.postMessage({ __crown: 'diag-ask', i }, ORIGIN);
        } catch (e) { /* 접근 불가 프레임 */ }
      });

      await sleep(waitMs);
      window.removeEventListener('message', onReply);

      collected.forEach((info, i) => rows.push({ 위치: `하위 ${i}`, ...info }));

      console.log(`${LOG} 프레임 ${rows.length}개`);
      console.table(rows);

      const ok = rows.find((r) => r['입력창'] !== '없음');
      console.log(ok
        ? '%c입력창이 있는 프레임을 찾았습니다.'
        : '%c어느 프레임에도 채팅 입력창이 없습니다. 채팅창이 화면에 보이는지 확인하세요.',
        ok ? 'color:#0a0;font-weight:bold' : 'color:#c00;font-weight:bold');
      return rows;
    },

    setMax(n) { state.maxCount = Math.max(1, Number(n) || 1); return state.maxCount; },
    setCooldown(ms) { state.cooldownMs = Math.max(0, Number(ms) || 0); return state.cooldownMs; },
    reloadEmojis: loadEmojis,
  };

  /* ------------------------------------------- 콘텐츠 스크립트와의 통신 */

  if (window.__crownHandler) {
    window.removeEventListener('crown:cmd', window.__crownHandler);
  }
  /*
   * 명령은 탭의 모든 프레임에 뿌려진다. 채팅 입력창이 없는 프레임(최상위
   * 방송 페이지 등)은 조용히 무시한다 — 입력창이 있는 프레임이 처리한다.
   * 여기서 예외를 던지면 프레임마다 콘솔에 에러가 쌓인다.
   */
  /*
   * 명령을 한 줄로 세워 처리한다.
   *
   * add() 는 피커를 열고 버튼을 찾고 반영을 기다리느라 최대 0.5초가 걸린다.
   * 봉은 1초에 하나씩 보내지만 치지직이 굼뜬 순간에는 앞 명령이 끝나기 전에
   * 다음 명령이 들어온다. 그러면 둘 다 같은 개수를 기준으로 잡고 각자
   * 클릭해서 이모티콘이 겹쳐 들어간다.
   *
   * 앞의 것이 끝나야 다음이 시작하게 하면 그 겹침이 원천적으로 없어진다.
   */
  window.__crownQueue = Promise.resolve();
  window.__crownHandler = (ev) => {
    const d = (ev && ev.detail) || {};
    if (!findInput()) return;

    window.__crownQueue = window.__crownQueue.then(async () => {
      try {
        if (d.action === 'add') await add(d.emojiId);
        else if (d.action === 'send') await send();
        else if (d.action === 'clear') clear();
      } catch (e) {
        console.warn(LOG, e.message);
      }
    });
  };
  window.addEventListener('crown:cmd', window.__crownHandler);

  /* 상위 프레임의 diagAll() 요청에 답한다 */
  if (window.__crownDiagHandler) {
    window.removeEventListener('message', window.__crownDiagHandler);
  }
  window.__crownDiagHandler = (ev) => {
    const d = ev.data;
    if (!d || d.__crown !== 'diag-ask') return;
    try {
      ev.source.postMessage({ __crown: 'diag-reply', info: frameDiag() }, ORIGIN);
    } catch (e) { /* 무시 */ }
  };
  window.addEventListener('message', window.__crownDiagHandler);

  if (channelId() && !state.emojis.size) {
    loadEmojis().catch((e) => console.warn(LOG, '카탈로그 로드 실패:', e.message));
  }

  (function waitForInput(tries) {
    if (findInput()) {
      window.dispatchEvent(new CustomEvent('crown:ready'));
      return;
    }
    if (tries > 0) setTimeout(() => waitForInput(tries - 1), 500);
  })(60);

  console.log(
    `%c${LOG} v${VERSION} — 피커 클릭 방식\n\n` +
    "  await crown.add('redredLight')          입력창에 하나 추가\n" +
    "  await crown.picker('redred')            피커에 보이는 목록\n" +
    '  crown.send()                            전송 (엔터)\n' +
    '  crown.clear()                           입력창 비우기\n' +
    '  crown.diag()                            상태 확인',
    'color:#0a0;font-weight:bold'
  );
})();
