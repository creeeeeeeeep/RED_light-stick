/*
 * 치지직 채팅 입력창의 리액트 state 를 찾아 직접 쓰기 위한 조사 스크립트.
 *
 * ---------------------------------------------------------------------------
 * 왜 필요한가
 * ---------------------------------------------------------------------------
 * contenteditable 에 <img> 를 DOM 으로 직접 넣으면, 리렌더될 때 치지직이
 * 내용을 새니타이즈해서 태그가 글자 그대로("<img src=...>")로 바뀐다.
 * HTML 주입을 막는 정상적인 방어다. 피커로 고를 때는 치지직 자기 코드가
 * 리액트 state 에 직접 넣기 때문에 이 처리를 거치지 않는다.
 *
 * 따라서 우리도 DOM 이 아니라 state 를 갱신해야 한다.
 *
 * 앞선 조사(input-probe.js)에서 입력창 HTML 을 들고 있는 훅을 확인했다:
 *   3:Anonymous#hook4  ["", {get,set,sub}, {toString,init,read,write}]
 *   → 이모티콘을 넣으면 첫 원소가 "<img src='...'>" 로 바뀐다
 *
 * 이 스크립트는 그 훅을 찾아 setter 를 호출할 수 있게 해준다.
 *
 * ---------------------------------------------------------------------------
 * 사용법
 * ---------------------------------------------------------------------------
 * 1. 채팅 iframe 단독 탭 → F12 → Console → 이 파일 붙여넣기
 * 2. 채팅 입력창을 마우스로 한 번 클릭한다 (활성화 필요)
 * 3. st.scan()          입력창 HTML 을 들고 있어 보이는 훅 목록
 * 4. 피커로 이모티콘을 하나 넣고 다시 st.scan()
 *    → 값이 "<img src=..." 로 바뀐 훅이 정답이다
 * 5. st.try(i, '<img src="...">')   그 훅에 직접 써본다
 *    → 입력창에 이미지가 뜨면 성공
 */

(() => {
  'use strict';

  const LOG = '[state]';

  function findInput() {
    const eds = [...document.querySelectorAll('[contenteditable]')]
      .filter((e) => e.getAttribute('contenteditable') !== 'false');
    for (const e of eds) {
      const r = e.getBoundingClientRect();
      if (r.width > 40 && r.height > 8) return e;
    }
    return eds[0] || document.querySelector('pre[class*="_input_"]') || null;
  }

  const fiberOf = (el) => {
    const k = el && Object.keys(el).find((x) => x.startsWith('__reactFiber$')
      || x.startsWith('__reactInternalInstance$'));
    return k ? el[k] : null;
  };

  function preview(v) {
    if (typeof v === 'string') {
      return v.length > 70 ? `"${v.slice(0, 70)}…"(${v.length})` : `"${v}"`;
    }
    if (Array.isArray(v)) {
      return `[${v.map((x) => (typeof x === 'string'
        ? (x.length > 40 ? `"${x.slice(0, 40)}…"` : `"${x}"`)
        : (x && typeof x === 'object' ? `{${Object.keys(x).slice(0, 4).join(',')}}` : String(x))
      )).join(', ')}]`;
    }
    if (v && typeof v === 'object') return `{${Object.keys(v).slice(0, 6).join(', ')}}`;
    return String(v);
  }

  /** 문자열이 입력창 내용처럼 보이는가 */
  const looksLikeHtml = (s) =>
    typeof s === 'string' && (s === '' || s.includes('<img') || s.includes('<') || s.length < 200);

  /*
   * 훅 수집.
   *
   * 리액트 훅은 fiber.memoizedState 에 연결 리스트로 달려 있다.
   * useState 계열은 hook.queue.dispatch 로 값을 갱신할 수 있다.
   * 외부 스토어(atom) 를 쓰는 경우 memoizedState 안에 set/write 함수가 들어 있다.
   */
  function collect() {
    const el = findInput();
    if (!el) {
      console.warn(LOG, '입력창을 못 찾았습니다. 입력창을 클릭한 뒤 다시 실행하세요.');
      return [];
    }

    const found = [];
    let fiber = fiberOf(el);
    let depth = 0;

    while (fiber && depth < 16) {
      const name = typeof fiber.type === 'function'
        ? (fiber.type.displayName || fiber.type.name || 'Anonymous')
        : (typeof fiber.type === 'string' ? fiber.type : '?');

      let hook = fiber.memoizedState;
      let idx = 0;
      while (hook && idx < 40) {
        const ms = hook.memoizedState;

        // 문자열 자체이거나, 배열의 첫 원소가 문자열인 경우가 후보다
        const strVal = typeof ms === 'string' ? ms
          : (Array.isArray(ms) && typeof ms[0] === 'string' ? ms[0] : null);

        if (strVal !== null && looksLikeHtml(strVal)) {
          // 값을 바꿀 수 있는 경로를 모은다
          const setters = [];
          if (hook.queue && typeof hook.queue.dispatch === 'function') setters.push('queue.dispatch');
          if (Array.isArray(ms)) {
            ms.forEach((x, i) => {
              if (x && typeof x === 'object') {
                for (const k of ['set', 'write', 'update']) {
                  if (typeof x[k] === 'function') setters.push(`state[${i}].${k}`);
                }
              }
            });
          }
          found.push({
            path: `${depth}:${name}#hook${idx}`,
            hook,
            fiber,
            value: strVal,
            raw: ms,
            setters,
          });
        }
        hook = hook.next;
        idx++;
      }
      fiber = fiber.return;
      depth++;
    }
    return found;
  }

  let last = [];

  window.st = {
    /** 입력창 HTML 을 들고 있어 보이는 훅 목록 */
    scan() {
      last = collect();
      console.log(`${LOG} 후보 ${last.length}개`);
      console.table(last.map((h, i) => ({
        i,
        path: h.path,
        값: preview(h.value),
        갱신경로: h.setters.join(' / ') || '(없음)',
      })));
      console.log('원본은 st.items[i] 로 접근하세요.');
      window.st.items = last;
      return last;
    },

    /**
     * i 번 훅에 값을 써본다. 가능한 갱신 경로를 순서대로 시도한다.
     * 입력창에 반영되면 그 훅이 정답이다.
     */
    try(i, html) {
      const h = last[i];
      if (!h) return console.warn(LOG, 'st.scan() 을 먼저 실행하세요.');
      if (html === undefined) return console.warn(LOG, '쓸 HTML 을 넘기세요.');

      const attempts = [];

      // 1) useState 계열
      if (h.hook.queue && typeof h.hook.queue.dispatch === 'function') {
        try {
          h.hook.queue.dispatch(html);
          attempts.push('queue.dispatch ok');
        } catch (e) { attempts.push('queue.dispatch 실패: ' + e.message); }
      }

      // 2) 외부 스토어 형태 (set / write)
      if (Array.isArray(h.raw)) {
        h.raw.forEach((x, j) => {
          if (!x || typeof x !== 'object') return;
          for (const k of ['set', 'write', 'update']) {
            if (typeof x[k] !== 'function') continue;
            try {
              x[k](html);
              attempts.push(`state[${j}].${k} ok`);
            } catch (e) {
              attempts.push(`state[${j}].${k} 실패: ${e.message}`);
            }
          }
        });
      }

      console.log(`${LOG} 시도 결과:`, attempts);
      setTimeout(() => {
        const el = findInput();
        console.log(`${LOG} 현재 입력창 innerHTML:`);
        console.log(el ? el.innerHTML : '(입력창 없음)');
        console.log(`${LOG} <img> 개수:`, el ? el.querySelectorAll('img').length : 0);
      }, 200);
      return attempts;
    },

    /*
     * i 번 훅의 현재 값을 자르지 않고 전부 출력한다.
     * 표에서는 문자열이 잘려서 정확한 비교가 안 되므로 이걸 쓴다.
     */
    full(i) {
      last = collect();
      window.st.items = last;
      const h = last[i];
      if (!h) return console.warn(LOG, `${i}번 후보가 없습니다.`);

      console.log(`${LOG} [${i}] ${h.path}`);
      console.log('길이:', h.value.length);
      console.log('--- 값 전체 ---');
      console.log(h.value);
      console.log('--- JSON (공백/이스케이프 확인용) ---');
      console.log(JSON.stringify(h.value));
      return h.value;
    },

    /*
     * 피커로 넣은 것과 우리가 넣은 것을 비교하기 위한 기록.
     * st.mark('picker') 로 저장하고, 나중에 st.compare('picker') 로 비교한다.
     */
    marks: {},
    mark(name) {
      last = collect();
      const h = last[1] || last[0];
      if (!h) return console.warn(LOG, '후보가 없습니다.');
      this.marks[name] = h.value;
      console.log(`${LOG} '${name}' 로 기록 (길이 ${h.value.length})`);
      console.log(JSON.stringify(h.value));
      return h.value;
    },
    compare(a, b) {
      const x = this.marks[a], y = this.marks[b];
      if (x === undefined || y === undefined) {
        return console.warn(LOG, `기록이 없습니다. 있는 것: ${Object.keys(this.marks).join(', ') || '(없음)'}`);
      }
      console.log(`${LOG} '${a}' 길이 ${x.length} / '${b}' 길이 ${y.length}`);
      console.log(`동일: ${x === y}`);
      if (x !== y) {
        console.log(`--- ${a} ---`); console.log(JSON.stringify(x));
        console.log(`--- ${b} ---`); console.log(JSON.stringify(y));
        // 첫 차이 지점
        const n = Math.min(x.length, y.length);
        let i = 0;
        while (i < n && x[i] === y[i]) i++;
        console.log(`첫 차이: ${i}번째 문자`);
        console.log(`  ${a}: ${JSON.stringify(x.slice(Math.max(0, i - 20), i + 40))}`);
        console.log(`  ${b}: ${JSON.stringify(y.slice(Math.max(0, i - 20), i + 40))}`);
      }
      return x === y;
    },

    /** 현재 입력창 상태 */
    dump() {
      const el = findInput();
      if (!el) return console.warn(LOG, '입력창 없음');
      console.log(el.innerHTML);
      console.log(`${LOG} <img> ${el.querySelectorAll('img').length}개`);
      return el.innerHTML;
    },

    input: findInput,
  };

  console.log(
    `%c${LOG} 준비 완료\n\n` +
    '  1) 채팅 입력창을 마우스로 클릭 (활성화 필요)\n' +
    '  2) st.scan()                     후보 훅 목록\n' +
    '  3) 피커로 이모티콘 하나 넣고 st.scan() 다시\n' +
    '     → 값이 "<img src=..." 로 바뀐 훅이 정답\n' +
    '  4) st.dump() 로 그 HTML 을 복사해 두고 입력창을 비운 뒤\n' +
    '     st.try(i, \'<img src="...">\')  로 직접 써보기',
    'color:#0a0;font-weight:bold'
  );
})();
