/*
 * 치지직 채팅 입력창에 이모티콘을 삽입하는 실험 스크립트.
 *
 * input-probe.js 로 알아낸 것:
 *   - 입력창은 <pre contenteditable="true" class="_input_...">
 *   - 내용을 HTML 문자열로 다루며, 이모티콘은 <img> 태그로 들어간다
 *   - 컴포넌트가 html/innerRef/tagName/disabled prop 을 받는 걸로 보아
 *     react-contenteditable 이다 → DOM 을 고치고 input 이벤트를 쏘면 동기화된다
 *
 * 이 스크립트는 **아무것도 전송하지 않는다.** 입력창에 넣기만 한다.
 * 전송은 사람이 엔터를 치거나 전송 버튼을 눌러야 일어난다.
 *
 * ---------------------------------------------------------------------------
 * 사용법
 * ---------------------------------------------------------------------------
 * 1. 채팅 iframe 단독 탭 → F12 → Console → 이 파일 붙여넣기
 *
 * 2. 이모티콘 피커로 이모티콘을 하나 골라 입력창에 넣는다 (전송 금지)
 *
 * 3. ins.dump()
 *    → 치지직이 실제로 넣은 <img> 의 전체 HTML 이 출력된다. 이게 정답 형식이다.
 *
 * 4. 입력창을 비운 뒤, ins.copyLast()
 *    → 방금 본 그 <img> 를 우리가 직접 넣어본다. 똑같이 보이면 성공.
 *
 * 5. ins.emoji('redredLight')
 *    → 카탈로그의 URL 로 <img> 를 만들어 넣는다. 이게 되면 끝난 것이다.
 *
 * 6. 엔터를 쳐서 정상적으로 이모티콘이 나가는지 확인한다.
 */

(() => {
  'use strict';

  const LOG = '[ins]';
  let lastSeen = null;     // 치지직이 넣은 <img> 원본 HTML
  let sendButton = null;   // 탐지/지정된 전송 버튼

  function findInput() {
    const cands = [...document.querySelectorAll('[contenteditable="true"]')];
    const visible = cands.filter((el) => {
      const r = el.getBoundingClientRect();
      return r.width > 40 && r.height > 10;
    });
    return (visible[0] || cands[0]) || null;
  }

  /* ------------------------------------------------------------- 삽입 방식 */

  /*
   * 방법 A — execCommand('insertHTML')
   * 낡았지만 contenteditable 에서 가장 잘 먹고, 브라우저가 네이티브 input
   * 이벤트를 알아서 발생시켜 준다. 커서 위치에 삽입되는 것도 장점.
   */
  function insertViaExec(html) {
    const el = findInput();
    if (!el) throw new Error('입력창을 찾지 못했습니다');
    el.focus();

    // 커서가 입력창 안에 없으면 맨 끝으로 옮긴다
    const sel = window.getSelection();
    if (!sel.rangeCount || !el.contains(sel.anchorNode)) {
      const r = document.createRange();
      r.selectNodeContents(el);
      r.collapse(false);
      sel.removeAllRanges();
      sel.addRange(r);
    }

    const ok = document.execCommand('insertHTML', false, html);
    if (!ok) throw new Error('execCommand 가 거부되었습니다');
    return el;
  }

  /*
   * 방법 B — innerHTML 직접 수정 후 input 이벤트 수동 발생
   * execCommand 가 막혔을 때의 대안. 커서 위치는 무시하고 항상 끝에 붙는다.
   */
  function insertViaDom(html) {
    const el = findInput();
    if (!el) throw new Error('입력창을 찾지 못했습니다');
    el.focus();
    el.innerHTML += html;
    el.dispatchEvent(new InputEvent('input', { bubbles: true, cancelable: false }));
    return el;
  }

  /* ---------------------------------------------------- 이모티콘 카탈로그 */

  const emojiUrls = new Map();

  async function loadCatalog() {
    const m = location.pathname.match(/\/live\/([0-9a-f]{32})/i);
    if (!m) throw new Error('채널 ID를 URL에서 찾지 못했습니다');
    const res = await fetch(
      `https://api.chzzk.naver.com/service/v1/channels/${m[1]}/emoji-packs`,
      {
        credentials: 'include',
        headers: {
          'Front-Client-Platform-Type': 'PC',
          'Front-Client-Product-Type': 'web',
        },
      }
    );
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const c = (await res.json()).content;
    emojiUrls.clear();
    for (const p of [...(c.emojiPacks || []), ...(c.subscriptionEmojiPacks || [])]) {
      for (const e of [...(p.emojis || []), ...(p.tier1Emojis || []), ...(p.tier2Emojis || [])]) {
        emojiUrls.set(e.emojiId, e.imageUrl);
      }
    }
    console.log(`${LOG} 이모티콘 ${emojiUrls.size}개 로드`);
    return emojiUrls.size;
  }

  /* -------------------------------------------------------------- 외부 API */

  window.ins = {
    /** 입력창 요소 */
    el: findInput,

    /**
     * 지금 입력창에 든 내용을 그대로 출력한다.
     * 이모티콘을 피커로 넣은 직후에 실행해서 '정답 형식'을 확인하는 용도.
     */
    dump() {
      const el = findInput();
      if (!el) return console.warn(LOG, '입력창 없음');

      console.log(`${LOG} innerHTML 전체:`);
      console.log(el.innerHTML);

      const imgs = [...el.querySelectorAll('img')];
      console.log(`${LOG} <img> ${imgs.length}개`);
      imgs.forEach((img, i) => {
        console.log(`  [${i}] outerHTML:`);
        console.log('      ' + img.outerHTML);
        const attrs = {};
        for (const a of img.attributes) attrs[a.name] = a.value;
        console.table(attrs);
      });

      if (imgs.length) {
        lastSeen = imgs[imgs.length - 1].outerHTML;
        console.log(`%c${LOG} 마지막 <img> 를 기억했습니다. ins.copyLast() 로 재현해볼 수 있습니다.`,
          'color:#0a0;font-weight:bold');
      }
      return el.innerHTML;
    },

    /** dump() 로 기억해 둔 <img> 를 우리가 직접 삽입해본다 */
    copyLast(method) {
      if (!lastSeen) return console.warn(LOG, '먼저 ins.dump() 를 실행하세요.');
      return this.raw(lastSeen, method);
    },

    /** 임의 HTML 삽입. method: 'exec'(기본) 또는 'dom' */
    raw(html, method) {
      const fn = method === 'dom' ? insertViaDom : insertViaExec;
      const el = fn(html);
      console.log(`${LOG} 삽입 (${method === 'dom' ? 'dom' : 'exec'}). 현재 내용:`);
      console.log(el.innerHTML);
      return el.innerHTML;
    },

    /**
     * 카탈로그의 URL 로 <img> 를 만들어 삽입한다.
     * 치지직이 넣는 형식과 정확히 같아야 하므로, dump() 로 확인한 뒤
     * 필요하면 buildImg() 를 고칠 것.
     */
    async emoji(emojiId, method) {
      if (!emojiUrls.size) await loadCatalog();
      const url = emojiUrls.get(emojiId);
      if (!url) throw new Error(`이모티콘을 찾을 수 없습니다: ${emojiId}`);
      return this.raw(this.buildImg(emojiId, url), method);
    },

    /**
     * <img> 태그 조립. 치지직이 실제로 쓰는 형식에 맞춰 고쳐야 한다.
     * dump() 결과의 outerHTML 과 비교해서 속성을 맞출 것.
     */
    buildImg(emojiId, url) {
      const src = url + (url.includes('?') ? '' : '?type=f60_60');
      return `<img src='${src}' title='${emojiId}' alt='${emojiId}'>`;
    },

    /** 입력창 비우기 */
    clear() {
      const el = findInput();
      if (!el) return;
      el.focus();
      const sel = window.getSelection();
      const r = document.createRange();
      r.selectNodeContents(el);
      sel.removeAllRanges();
      sel.addRange(r);
      document.execCommand('delete');
      console.log(`${LOG} 비움`);
    },

    /** 전송 버튼 후보 찾기 (누르지는 않는다) */
    findSend() {
      const btns = [...document.querySelectorAll('button')];
      const rows = btns.map((b, i) => ({
        i,
        text: (b.textContent || '').trim().slice(0, 16),
        aria: b.getAttribute('aria-label') || '',
        cls: (b.className || '').toString().slice(0, 44),
        disabled: b.disabled,
      }));
      console.table(rows);
      window.ins.buttons = btns;
      console.log(`${LOG} ins.buttons[i] 로 요소 접근. 아직 아무것도 누르지 않았습니다.`);
      return btns;
    },

    /*
     * 전송 버튼 자동 탐지.
     *
     * 클래스명이나 텍스트로 찾으면 치지직이 UI를 바꿀 때마다 깨진다. 대신
     * "입력창이 비었을 때는 비활성, 내용이 있으면 활성"이라는 동작 특성을
     * 이용한다. 이건 UI가 바뀌어도 잘 유지되는 성질이다.
     *
     * 전송하지 않는다. 찾기만 한다.
     */
    detectSend() {
      const el = findInput();
      if (!el) return console.warn(LOG, '입력창 없음');

      const before = new Map();
      document.querySelectorAll('button').forEach((b) => before.set(b, b.disabled));

      const hadContent = el.innerHTML.trim().length > 0;
      if (!hadContent) {
        insertViaExec('탐지');   // 임시 텍스트. 전송하지 않으므로 채팅엔 안 나간다
      }

      const enabled = [];
      document.querySelectorAll('button').forEach((b) => {
        if (before.get(b) === true && b.disabled === false) enabled.push(b);
      });

      if (!hadContent) this.clear();

      if (!enabled.length) {
        console.warn(LOG, '입력에 따라 활성화되는 버튼을 못 찾았습니다.');
        console.warn('    엔터 방식(ins.send("enter"))을 쓰거나,');
        console.warn('    ins.findSend() 로 목록을 보고 ins.setSend(i) 로 직접 지정하세요.');
        return null;
      }

      sendButton = enabled[0];
      console.log(`%c${LOG} 전송 버튼 탐지됨:`, 'color:#0a0;font-weight:bold', sendButton);
      if (enabled.length > 1) {
        console.log(LOG, `후보가 ${enabled.length}개입니다. 틀렸으면 ins.setSend(i) 로 지정하세요.`);
        window.ins.buttons = enabled;
      }
      return sendButton;
    },

    /** findSend()/detectSend() 목록에서 전송 버튼을 직접 지정 */
    setSend(i) {
      const b = (window.ins.buttons || [])[i];
      if (!b) return console.warn(LOG, '해당 인덱스의 버튼이 없습니다.');
      sendButton = b;
      console.log(LOG, '전송 버튼 지정됨:', b);
      return b;
    },

    /*
     * ⚠ 여기서부터는 실제로 채팅이 전송된다.
     *
     * 기본은 엔터 키 이벤트다. 치지직 채팅창에는 별도 전송 버튼이 없고
     * 엔터로만 보내는 구조로 확인됐다(detectSend 가 아무것도 못 찾음).
     * 버튼이 있는 환경을 대비해 how='button' 경로는 남겨 둔다.
     */
    send(how) {
      const el = findInput();
      if (!el) throw new Error('입력창을 찾지 못했습니다');
      if (!el.innerHTML.trim()) throw new Error('입력창이 비어 있습니다');

      if (how === 'button') {
        if (!sendButton) this.detectSend();
        if (sendButton && !sendButton.disabled) {
          sendButton.click();
          console.log(`${LOG} 전송 버튼 클릭`);
          return 'button';
        }
        console.warn(LOG, '전송 버튼이 없어 엔터 방식으로 진행합니다.');
      }

      el.focus();
      for (const type of ['keydown', 'keypress', 'keyup']) {
        el.dispatchEvent(new KeyboardEvent(type, {
          key: 'Enter', code: 'Enter', keyCode: 13, which: 13,
          bubbles: true, cancelable: true,
        }));
      }
      console.log(`${LOG} 엔터 키 이벤트 발생`);
      return 'enter';
    },

    loadCatalog,
    catalog: emojiUrls,
  };

  console.log(
    `%c${LOG} 준비 완료\n\n` +
    '[전송하지 않는 것들]\n' +
    '  ins.dump()                    치지직이 넣은 <img> 원본 형식 확인\n' +
    '  ins.clear()                   입력창 비우기\n' +
    '  ins.copyLast()                같은 <img> 직접 넣어보기\n' +
    "  ins.emoji('redredLight')      카탈로그 URL 로 만들어 넣기\n" +
    '  ins.detectSend()              전송 버튼 찾기 (누르진 않음)\n' +
    '  ins.findSend()                버튼 목록 보기\n\n' +
    '%c[실제로 채팅이 전송되는 것]\n' +
    "  ins.send()                    전송 버튼 클릭\n" +
    "  ins.send('enter')             엔터 키 이벤트\n\n" +
    '%c한 번에 여러 개 넣어보려면:\n' +
    "  ins.emoji('redredLight'); ins.emoji('redredLight'); ins.emoji('redredCrownlight')",
    'color:#0a0;font-weight:bold',
    'color:#c00;font-weight:bold',
    'color:#666'
  );
})();
