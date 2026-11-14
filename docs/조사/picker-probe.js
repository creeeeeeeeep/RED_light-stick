/*
 * 치지직 이모티콘 피커를 UI 그대로 조작하기 위한 조사 스크립트.
 *
 * ---------------------------------------------------------------------------
 * 왜 이 방식인가
 * ---------------------------------------------------------------------------
 * 그동안 시도한 것들과 결과:
 *   1) 입력창에 {:id:} 텍스트 입력      → 글자 그대로 전송됨
 *   2) DOM 에 <img> 직접 삽입           → 리렌더 시 새니타이즈되어 텍스트로
 *   3) 리액트 state 에 HTML 직접 주입    → 이미지는 보이는데 전송이 안 됨
 *
 * 3번이 실패한다는 건 입력창 HTML 말고도 치지직이 전송 시 참조하는 상태가
 * 더 있다는 뜻이다. 그게 어디 있는지 계속 추적하는 대신, 피커를 실제로
 * 클릭해서 치지직 자기 코드가 전부 채우게 한다.
 *
 * 참고로 기존 확장("치지직 이모티콘 단축키")이 "한 번 이상 사용한 이모티콘"만
 * 등록 가능하다고 안내하는데, 이는 피커의 '최근 사용' 영역을 클릭하기 때문으로
 * 보인다. 스크롤 없이 바로 접근할 수 있는 위치이기 때문이다.
 *
 * ---------------------------------------------------------------------------
 * 사용법
 * ---------------------------------------------------------------------------
 * 1. 채팅 iframe 단독 탭 → F12 → Console → 이 파일 붙여넣기
 * 2. pk.button()      이모티콘 버튼을 찾았는지 확인
 * 3. pk.open()        피커 열기
 * 4. pk.list()        피커 안에 보이는 이모티콘 목록
 * 5. pk.click(0)      0번 이모티콘 클릭 → 입력창에 들어가는지 확인
 * 6. 엔터로 전송되는지 확인
 */

(() => {
  'use strict';

  const LOG = '[pk]';

  function findInput() {
    const eds = [...document.querySelectorAll('[contenteditable]')]
      .filter((e) => e.getAttribute('contenteditable') !== 'false');
    for (const e of eds) {
      const r = e.getBoundingClientRect();
      if (r.width > 40 && r.height > 8) return e;
    }
    return eds[0] || null;
  }

  /*
   * 이모티콘 버튼 찾기.
   * 클래스명은 빌드마다 바뀌므로 위치로 찾는다 — 입력창과 같은 높이대에 있는
   * 작은 정사각형 클릭 요소가 후보다.
   */
  function buttonCandidates() {
    const input = findInput();
    if (!input) return [];
    const ir = input.getBoundingClientRect();

    const all = [...document.querySelectorAll('button, [role="button"], svg, img')];
    const out = [];
    const seen = new Set();

    for (const el of all) {
      const clickable = el.closest('button, [role="button"]') || el;
      if (seen.has(clickable)) continue;
      const r = clickable.getBoundingClientRect();
      if (r.width < 8 || r.width > 60 || r.height < 8 || r.height > 60) continue;
      // 입력창과 세로로 겹치는 범위에 있는 것만
      if (r.bottom < ir.top - 40 || r.top > ir.bottom + 40) continue;
      seen.add(clickable);
      out.push({
        el: clickable,
        x: Math.round(r.left), y: Math.round(r.top),
        w: Math.round(r.width), h: Math.round(r.height),
        cls: (clickable.className || '').toString().slice(0, 40),
        aria: clickable.getAttribute('aria-label') || '',
      });
    }
    return out.sort((a, b) => b.x - a.x);   // 보통 입력창 오른쪽 끝에 있다
  }

  /** 피커로 보이는 컨테이너 (이모티콘 이미지가 여러 개 든 요소) */
  function findPicker() {
    let best = null;
    let bestCount = 0;
    for (const el of document.querySelectorAll('div, section, ul')) {
      const imgs = el.querySelectorAll('img');
      if (imgs.length < 5) continue;
      const r = el.getBoundingClientRect();
      if (r.width < 100 || r.height < 60) continue;
      // 가장 안쪽(작은) 컨테이너를 고른다
      if (!best || imgs.length < bestCount || el.contains(best) === false && imgs.length >= 5) {
        if (!best || (best.contains(el) && imgs.length >= 5)) {
          best = el; bestCount = imgs.length;
        }
      }
    }
    return best;
  }

  let pickerBtn = null;

  window.pk = {
    /** 이모티콘 버튼 후보 목록 */
    button() {
      const c = buttonCandidates();
      console.log(`${LOG} 버튼 후보 ${c.length}개 (오른쪽부터)`);
      console.table(c.map((x, i) => ({
        i, 위치: `${x.x},${x.y}`, 크기: `${x.w}x${x.h}`, aria: x.aria, class: x.cls,
      })));
      window.pk.buttons = c.map((x) => x.el);
      console.log('요소는 pk.buttons[i], 클릭은 pk.open(i)');
      return c;
    },

    /** 피커 열기. i 를 주면 그 후보를 클릭한다 */
    open(i) {
      const btns = window.pk.buttons || buttonCandidates().map((x) => x.el);
      window.pk.buttons = btns;
      const el = (i === undefined) ? btns[0] : btns[i];
      if (!el) return console.warn(LOG, '버튼을 못 찾았습니다. pk.button() 으로 목록을 보세요.');
      pickerBtn = el;
      el.click();
      console.log(`${LOG} 클릭:`, el);
      setTimeout(() => {
        const p = findPicker();
        console.log(`${LOG} 피커로 보이는 요소:`, p);
        if (p) console.log(`${LOG} 안에 이미지 ${p.querySelectorAll('img').length}개`);
        else console.log(`${LOG} 피커를 못 찾았습니다. 다른 버튼을 시도해 보세요: pk.open(1), pk.open(2) ...`);
      }, 300);
      return el;
    },

    /** 피커 안 이모티콘 목록 */
    list(filter) {
      const p = findPicker();
      if (!p) return console.warn(LOG, '피커가 안 열렸습니다. pk.open() 먼저.');

      const imgs = [...p.querySelectorAll('img')].filter((im) => {
        const r = im.getBoundingClientRect();
        return r.width > 8 && r.height > 8;
      });

      const rows = imgs.map((im, i) => {
        const src = im.getAttribute('src') || '';
        // 파일명에서 emojiId 를 뽑는다 (<id>_<타임스탬프>.<확장자>)
        const m = src.match(/\/([^/]+?)_\d+\.(?:gif|png|jpe?g|webp)/i);
        return { i, emojiId: m ? m[1] : '(불명)', src: src.slice(-60) };
      });

      const shown = filter
        ? rows.filter((r) => r.emojiId.toLowerCase().includes(String(filter).toLowerCase()))
        : rows;

      console.log(`${LOG} 이모티콘 ${rows.length}개` + (filter ? ` (필터 '${filter}': ${shown.length}개)` : ''));
      console.table(shown.slice(0, 60));
      window.pk.images = imgs;
      return rows;
    },

    /** i 번 이모티콘 클릭 */
    click(i) {
      const imgs = window.pk.images;
      if (!imgs || !imgs[i]) return console.warn(LOG, 'pk.list() 를 먼저 실행하세요.');
      const im = imgs[i];
      const target = im.closest('button, [role="button"], li, a') || im;
      target.click();
      console.log(`${LOG} 클릭:`, target);
      setTimeout(() => {
        const input = findInput();
        console.log(`${LOG} 입력창 <img> 개수:`, input ? input.querySelectorAll('img').length : 0);
        console.log(input ? input.innerHTML : '(입력창 없음)');
      }, 250);
      return target;
    },

    /** emojiId 로 찾아 클릭 */
    pick(emojiId) {
      const rows = this.list();
      if (!rows) return;
      const hit = rows.find((r) => r.emojiId === emojiId);
      if (!hit) {
        console.warn(`${LOG} 피커에서 '${emojiId}' 를 못 찾았습니다.`);
        console.warn('    다른 탭/카테고리에 있거나 스크롤이 필요할 수 있습니다.');
        return null;
      }
      return this.click(hit.i);
    },

    /** 피커 닫기 (버튼 다시 클릭) */
    close() {
      if (pickerBtn) pickerBtn.click();
    },

    input: findInput,
    picker: findPicker,
  };

  console.log(
    `%c${LOG} 준비 완료\n\n` +
    '  pk.button()        이모티콘 버튼 후보 확인\n' +
    '  pk.open()          피커 열기 (안 열리면 pk.open(1), pk.open(2) ...)\n' +
    '  pk.list()          피커 안 이모티콘 목록\n' +
    "  pk.list('redred')  필터링\n" +
    '  pk.click(0)        0번 클릭\n' +
    "  pk.pick('redredLight')   emojiId 로 클릭\n" +
    '  pk.close()         닫기',
    'color:#0a0;font-weight:bold'
  );
})();
