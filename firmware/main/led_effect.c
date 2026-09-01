#include <math.h>
#include <string.h>

#include "led_effect.h"
#include "ws2812_matrix.h"
#include "board_config.h"

/*
 * 연출 설계
 * ---------------------------------------------------------------------------
 * 보드는 확산 돔 안에 들어간다. 돔이 죽이는 것은 '가는 것'이다 — 한 픽셀짜리
 * 스파클, 폭 1의 막대, 빠르게 지나가는 가장자리는 전부 뭉개진다.
 * 반대로 화면 전체를 가로지르는 완만한 그라데이션은 살아남고, 오히려 섞인
 * 색으로 보여서 단색보다 깊어진다.
 *
 * 그래서 두 층으로 나눈다.
 *
 *   무엇을 알리는가  →  밝기의 리듬 (모션)  +  밝기의 바닥 (쌓인 개수)
 *   어떻게 보이는가  →  화면을 가로지르는 저주파 색 그라데이션
 *
 * 리듬이 정보를 나르고 그라데이션은 정보를 나르지 않는다. 그래서 돔 너머로
 * 흘깃 봐도 모션은 구분되고, 자세히 보면 색이 오묘하게 섞여 있다.
 *
 *   IDLE      흰빛, 미색과 푸른기가 천천히 오감  5초에 한 번, 잔잔하게
 *   SWAY_LR   자홍 ~ 빨강 ~ 주황  좌우로 기운다  약 1.2초에 한 번, 숨쉬듯
 *   PUMP_UD   무지개 띠가 화면을 가로지르며 흐름  띠가 3.5초에 한 바퀴 + 박자
 *   VIGOROUS  금빛 덩어리 속 흰 중심이 부풀었다 오므라듦  쿵쿵…쿵쿵
 *
 * 넷의 리듬은 서로 배수 관계가 아니다. 겹쳐 보이지 않게 하려는 것이다.
 *
 * 색은 목표로 곧장 갈아끼우지 않고 시상수를 두고 다가간다. 모드가 바뀌는
 * 순간 한 프레임 만에 잘려 바뀌면 돔 안에서 특히 사납게 보인다.
 * 자세한 것은 follow_tau_ms 참고.
 */

static uint32_t s_phase_ms;         /* 현재 제스처 시작 시각 */
static uint32_t s_rng = 0x2545F491; /* 명멸용 xorshift */
static uint32_t s_add_ms;           /* 마지막으로 하나 쌓인 시각 */
static uint32_t s_flush_ms;         /* 전송 연출 시작 시각. 0이면 비활성 */

#define ADD_FLASH_MS    200
#define FLUSH_ANIM_MS   700

/* 하나도 안 쌓였을 때의 밝기 바닥. 가득 차면 FILL_MAX 까지 올라온다. */
#define FILL_MIN        0.16f
#define FILL_MAX        0.78f

static inline uint32_t rnd(void)
{
    s_rng ^= s_rng << 13;
    s_rng ^= s_rng >> 17;
    s_rng ^= s_rng << 5;
    return s_rng;
}

static inline float clampf(float v, float lo, float hi)
{
    return v < lo ? lo : (v > hi ? hi : v);
}

/* 0~1 을 오가는 부드러운 왕복. p 를 키우면 어두운 쪽에 오래 머문다. */
static inline float breathe(float t, float period, float p)
{
    const float x = 0.5f - 0.5f * cosf(6.2831853f * t / period);
    return p == 1.0f ? x : powf(x, p);
}

void led_effect_on_gesture_change(gesture_t g, uint32_t now_ms)
{
    (void)g;
    s_phase_ms = now_ms;
}

void led_effect_on_queue_add(uint32_t now_ms)
{
    s_add_ms = now_ms ? now_ms : 1;
}

void led_effect_on_flush(uint32_t now_ms)
{
    s_flush_ms = now_ms ? now_ms : 1;
}

bool led_effect_flush_active(uint32_t now_ms)
{
    return s_flush_ms != 0 && (now_ms - s_flush_ms) < FLUSH_ANIM_MS;
}

/* --------------------------------------------------------------------------
 * 그라데이션 필드
 * ------------------------------------------------------------------------ */

/*
 * 한 프레임의 색을 여기에 먼저 짓는다. 곧바로 프레임버퍼에 쓰지 않는 이유는,
 * 다 그려놓고 나서야 이 프레임이 전력 예산 안에 들어오는지 알 수 있기
 * 때문이다. 미리 알아야 밝기를 예산 안으로 접어 넣을 수 있다.
 */
static rgb_t s_field[MATRIX_PIXELS];

/*
 * 모션마다 "이 픽셀은 무슨 색인가" 만 답한다. 밝기는 나중에 한꺼번에 곱하므로
 * 여기서는 항상 최대 채도·최대 명도로 낸다.
 *
 *   u, v : 0~1 로 정규화한 좌표
 *   t    : 모션이 시작된 뒤 흐른 초
 */
typedef rgb_t (*tint_fn)(float u, float v, float t, float intensity);

/* 색상환을 넘나들 때 8비트로 자연스럽게 감기도록 */
static inline uint8_t hue_wrap(float h)
{
    float x = fmodf(h, 256.0f);
    if (x < 0.0f) x += 256.0f;
    return (uint8_t)x;
}

/*
 * 한 번의 타격. 순간 솟았다가 천천히 식는다.
 *   x : 타격이 시작된 뒤 흐른 정규화 시간
 *   w : 타격이 이어지는 길이
 */
static inline float hit(float x, float w)
{
    if (x < 0.0f || x >= w) return 0.0f;
    const float a = 1.0f - x / w;
    return a * a;
}

/*
 * VIGOROUS 의 박자 — 쿵쿵 … 쿵쿵.
 *
 * 같은 간격으로 균일하게 깜빡이면 금세 기계처럼 보인다. 두 번 치고 쉬는
 * 구조를 주면 밝기 변화의 크기는 그대로인데 훨씬 격정적으로 읽힌다.
 * 세게 흔들수록 박자가 빨라진다.
 *
 * 초당 타격 수를 5~7회 선에서 잡는다. 더 올리면 눈에 부담이 커지는 구간으로
 * 들어가는데, 격렬한 느낌은 속도보다 구조와 대비에서 나오므로 그럴 이유가 없다.
 */
static float vigor_beat(float t, float intensity)
{
    const float period = 0.42f - 0.12f * intensity;     /* 0.42s -> 0.30s */
    const float p = fmodf(t, period) / period;
    const float e = hit(p, 0.30f) + 0.80f * hit(p - 0.34f, 0.30f);
    return clampf(e, 0.0f, 1.0f);
}

/*
 * IDLE — 흰빛. 화면을 가로지르는 축이 아주 느리게 돌면서 한쪽은 따뜻하게,
 * 반대쪽은 차갑게 기운다.
 *
 * 완전한 백색이 아니라 채도를 조금 남긴다. 순백은 평평해 보이는데, 미색과
 * 푸른기가 천천히 오가면 같은 흰색이라도 살아 있는 느낌이 난다. 돔을 지나면
 * 이 정도 차이만 남고 나머지는 섞여 흰빛으로 읽힌다.
 *
 * 대기 상태는 "켜져 있다" 를 알리는 게 일이므로 모션들보다 얌전하되
 * 확실히 보여야 한다. 밝기는 envelope() 쪽에서 정한다.
 */
static rgb_t tint_idle(float u, float v, float t, float intensity)
{
    (void)intensity;
    const float a = 6.2831853f * t / 21.0f;          /* 21초에 한 바퀴 */
    const float d = u * cosf(a) + v * sinf(a);       /* -1 ~ 1 */

    /* 미색(h=32) 과 옅은 푸른빛(h=150) 사이를 오간다. 채도는 낮게. */
    const float hue = (d >= 0.0f) ? 32.0f : 150.0f;
    const uint8_t sat = (uint8_t)(10.0f + 26.0f * fabsf(d));
    return hsv2rgb(hue_wrap(hue), sat, 255);
}

/*
 * SWAY_LR — 자홍에서 빨강을 지나 주황으로.
 *
 * 그라데이션 축이 숨쉬기와 같은 박자로 좌우로 기운다. 흔드는 방향과 색이
 * 같이 움직이는 셈이라, 뭉개져 보여도 "빨간 무언가가 좌우로 일렁인다" 는
 * 인상이 남는다. 색 폭은 좁게 둔다 — 넓히면 빨강이 아니게 된다.
 */
static rgb_t tint_sway(float u, float v, float t, float intensity)
{
    const float period = 1.35f - 0.35f * intensity;
    const float lean = sinf(6.2831853f * t / period);          /* -1 ~ 1 */
    const float d = (u - 0.5f) * lean + (v - 0.5f) * 0.35f;
    return hsv2rgb(hue_wrap(2.0f + 22.0f * d), 255, 255);      /* 대략 -20 ~ 24 */
}

/*
 * PUMP_UD — 무지개 띠가 화면을 대각선으로 가로지르며 흐른다.
 *
 * 색상환을 통째로 깔지 않고 170도 남짓만 깐다. 한 바퀴를 다 깔면 돔 안에서
 * 전부 섞여 허연 색이 되어 버린다. 좁은 띠를 흘려보내면 항상 이웃한 색끼리
 * 섞이므로 채도가 살아 있고, 시간이 지나면 띠 자체가 색상환을 돌아 결국
 * 모든 색을 보여준다.
 */
static rgb_t tint_pump(float u, float v, float t, float intensity)
{
    (void)intensity;
    const float scroll = t / 3.5f * 256.0f;                    /* 3.5초에 한 바퀴 */
    const float across = (u + v) * 0.5f;                       /* 0 ~ 1 대각선 */
    return hsv2rgb(hue_wrap(scroll + across * 120.0f), 255, 255);
}

/*
 * VIGOROUS — 가운데는 흰빛, 가장자리는 금빛.
 *
 * 반지름 방향 그라데이션은 돔 안에서 "속이 뜨거운 덩어리" 로 읽힌다.
 * 명멸이 빠를 때 가운데가 더 희어져서 터지는 느낌이 강해진다.
 */
static rgb_t tint_vigorous(float u, float v, float t, float intensity)
{
    const float dx = u - 0.5f, dy = v - 0.5f;
    const float r = clampf(sqrtf(dx * dx + dy * dy) * 2.4f, 0.0f, 1.0f);
    const float b = vigor_beat(t, intensity);

    /*
     * 흰 중심이 타격마다 부풀어 올랐다 다시 오므라든다.
     *
     * 쉴 때는 작은 금빛 덩어리였다가 칠 때 화면을 삼키는데, 돔 안에서
     * 이 팽창은 살아남는다 — 가장자리가 흐려질 뿐 "커졌다" 는 읽힌다.
     * 밝기만 흔드는 것보다 훨씬 터지는 느낌이 난다.
     *
     * 채도를 명멸에 맞춰 무작위로 흔들지는 않는다. 초당 여러 번 색이 튀면
     * 격정적이 아니라 그냥 눈이 아프다. 여기서 변하는 것은 중심의 크기다.
     */
    const float core = 0.22f + 0.60f * b;
    const float k = clampf(r / core, 0.0f, 1.0f);      /* 0 = 중심, 1 = 바깥 */

    const uint8_t sat = (uint8_t)(35.0f + 200.0f * k);
    return hsv2rgb(hue_wrap(44.0f - 10.0f * k), sat, 255);
}

/* 모션별 밝기 포락선 (0~1). 정보를 나르는 쪽은 이것이다. */
static float envelope(gesture_t g, float t, float intensity)
{
    switch (g) {
    case GESTURE_SWAY_LR:
        return breathe(t, 1.35f - 0.35f * intensity, 1.5f);

    case GESTURE_PUMP_UD:
        /* 높게 유지한다 — 어두워지면 색이 도는 게 안 보인다 */
        return 0.78f + 0.22f * breathe(t, 0.30f - 0.08f * intensity, 1.0f);

    case GESTURE_VIGOROUS: {
        /*
         * 바닥을 낮게 둬서 타격 사이가 확실히 어두워지게 한다. 대비가 깊어야
         * 친다는 느낌이 난다. 흔들림을 조금 섞어 기계적인 반복을 흐트러뜨린다.
         */
        const float b = vigor_beat(t, intensity);
        const float jitter = 0.90f + 0.10f * ((rnd() & 0xFF) / 255.0f);
        return clampf(0.12f + 0.88f * b * jitter, 0.0f, 1.0f);
    }

    case GESTURE_IDLE:
    default:
        /*
         * 예전에는 0.05~0.17 이라 켜져 있는지 아닌지 헷갈렸다. 대기 상태도
         * 기본적으로 켜져 있는 편이 낫다는 판단이라 확실히 올렸다.
         *
         * 흰색은 세 채널을 다 쓰므로 같은 숫자라도 전류를 가장 많이 먹는다.
         * matrix_headroom() 이 그만큼 상한을 낮춰 잡으니 예산은 그대로
         * 지켜지고, 대신 모션들보다는 자연히 얌전해진다.
         */
        return 0.30f + 0.25f * breathe(t, 5.0f, 1.4f);
    }
}

/* --------------------------------------------------------------------------
 * 그리기
 * ------------------------------------------------------------------------ */

/*
 * 실제로 화면에 나가는 색. 목표 색으로 곧장 갈아끼우지 않고 여기서 천천히
 * 다가간다.
 *
 * 이게 없으면 모드가 바뀌는 순간 호박색이 빨강으로 한 프레임 만에 잘려서
 * 바뀐다. 돔 안에서는 그 전환이 특히 사납게 보인다. 사람이 색이 변했다고
 * 느끼는 데는 100ms 남짓이면 충분하므로, 그 시간에 걸쳐 건너가면 "변했다"는
 * 정보는 그대로 두고 거슬리는 것만 없앤다.
 */
static rgb_t s_shown[MATRIX_PIXELS];
static bool  s_shown_valid;
static uint32_t s_last_render_ms;

/*
 * 모드마다 따라붙는 속도가 달라야 한다.
 *
 * VIGOROUS 는 초당 11번 떠는 게 핵심이라 느리게 따라가면 그 떨림이 뭉개져
 * 사라진다. 반대로 IDLE 은 느긋할수록 좋다.
 *
 * 반환값은 시상수(ms). 목표까지 63% 다가가는 데 걸리는 시간이다.
 */
#define ENTER_TAU_MS    380.0f   /* 막 들어온 모션이 물드는 속도 */
#define ENTER_RAMP_S    0.5f     /* 이만큼 지나면 제 속도로 */

static float follow_tau_ms(gesture_t g, float t)
{
    float base;
    switch (g) {
    case GESTURE_VIGOROUS: base = 16.0f;  break;   /* 타격이 뭉개지면 안 된다 */
    case GESTURE_PUMP_UD:  base = 90.0f;  break;
    case GESTURE_SWAY_LR:  base = 110.0f; break;
    case GESTURE_IDLE:
    default:               base = 200.0f; break;
    }

    /*
     * 막 들어온 모션은 천천히 물든다.
     *
     * 손이 살짝 스치기만 해도 판정이 잠깐 튀는데, 그때마다 화면이 통째로
     * 그 색으로 덮이면 대기 중에 자꾸 깜빡거린다. 들어오는 속도를 늦추면
     * 0.2초쯤 스친 오인식은 30% 남짓만 물들었다 사라지고, 진짜로 흔들면
     * 0.6초 안에 제 색이 다 오른다.
     *
     * 임계값을 올려 덜 예민하게 만드는 방법도 있지만, 그건 봉을 조립한 뒤
     * 실제 데이터로 맞출 일이다. 여기서 손대면 그때 두 번 일하게 된다.
     *
     * VIGOROUS 는 빼둔다. 격하게 흔드는 건 애초에 스치듯 일어나지 않고,
     * 여기서 늦추면 첫 타격의 힘이 죽는다.
     */
    if (g != GESTURE_IDLE && g != GESTURE_VIGOROUS && t < ENTER_RAMP_S) {
        const float k = t / ENTER_RAMP_S;           /* 0 -> 1 */
        return ENTER_TAU_MS + (base - ENTER_TAU_MS) * k;
    }
    return base;
}

/*
 * 색 필드를 짓고, 전력 예산 안에서 쓸 수 있는 배율을 구한 뒤, 그 결과로
 * 천천히 다가가며 프레임버퍼에 쓴다.
 *
 * 보간된 프레임이 예산을 넘지 않는 것은 보장된다 — 예산 안의 두 프레임을
 * 섞은 것이고, 감마가 볼록함수라 섞은 쪽의 전류가 항상 더 작거나 같다.
 */
static void paint_field(tint_fn tint, float t, float intensity, float level,
                        uint32_t now_ms, float tau_ms, float white_mix)
{
    for (int y = 0; y < MATRIX_H; y++) {
        const float v = (MATRIX_H > 1) ? (float)y / (MATRIX_H - 1) : 0.0f;
        for (int x = 0; x < MATRIX_W; x++) {
            const float u = (MATRIX_W > 1) ? (float)x / (MATRIX_W - 1) : 0.0f;
            s_field[y * MATRIX_W + x] = tint(u, v, t, intensity);
        }
    }

    /*
     * 하나 쌓였을 때의 섬광. 위에 흰색을 덧그리지 않고 색을 흰 쪽으로 당긴다.
     *
     * 덧그리면 전력 예산 계산 뒤에 얹히게 돼서 그 순간만 눌리고, 보간도
     * 거치지 않아 매초 흰 점이 툭툭 튄다. 색을 당기면 예산 계산과 보간을
     * 둘 다 통과해서 부드럽게 번진다.
     */
    if (white_mix > 0.001f) {
        const float w = clampf(white_mix, 0.0f, 1.0f);
        for (int i = 0; i < MATRIX_PIXELS; i++) {
            s_field[i].r = (uint8_t)(s_field[i].r + (255 - s_field[i].r) * w);
            s_field[i].g = (uint8_t)(s_field[i].g + (255 - s_field[i].g) * w);
            s_field[i].b = (uint8_t)(s_field[i].b + (255 - s_field[i].b) * w);
        }
    }

    const float k = clampf(level, 0.0f, 1.0f) * matrix_headroom(s_field, MATRIX_PIXELS);
    for (int i = 0; i < MATRIX_PIXELS; i++) {
        s_field[i] = rgb_scale(s_field[i], k);
    }

    /*
     * 프레임 간격으로 보간 계수를 정한다. 고정 계수를 쓰면 프레임이 한 번
     * 밀릴 때마다 전환 속도가 달라진다.
     */
    uint32_t dt = now_ms - s_last_render_ms;
    s_last_render_ms = now_ms;
    if (!s_shown_valid || dt > 500) {          /* 첫 프레임이거나 오래 쉬었으면 그냥 맞춘다 */
        memcpy(s_shown, s_field, sizeof(s_shown));
        s_shown_valid = true;
    } else {
        const float a = clampf(1.0f - expf(-(float)dt / tau_ms), 0.0f, 1.0f);
        for (int i = 0; i < MATRIX_PIXELS; i++) {
            s_shown[i].r = (uint8_t)(s_shown[i].r + (s_field[i].r - s_shown[i].r) * a);
            s_shown[i].g = (uint8_t)(s_shown[i].g + (s_field[i].g - s_shown[i].g) * a);
            s_shown[i].b = (uint8_t)(s_shown[i].b + (s_field[i].b - s_shown[i].b) * a);
        }
    }

    for (int y = 0; y < MATRIX_H; y++) {
        for (int x = 0; x < MATRIX_W; x++) {
            matrix_set(x, y, s_shown[y * MATRIX_W + x]);
        }
    }
}

/* 단색으로 화면 전체 (전송 연출용) */
static rgb_t tint_flat_white(float u, float v, float t, float i)
{
    (void)u; (void)v; (void)t; (void)i;
    return (rgb_t){ 255, 255, 255 };
}

static rgb_t tint_flat_gold(float u, float v, float t, float i)
{
    (void)t; (void)i;
    const float d = (u + v) * 0.5f;
    return hsv2rgb(hue_wrap(30.0f + 16.0f * d), 200, 255);
}

/* --------------------------------------------------------------------------
 * 전송 연출 — 흰 섬광 뒤 금빛으로 식고 잠깐 어두워진다.
 * ------------------------------------------------------------------------ */
/*
 * 예전에는 아래로 쓸려나가는 연출이었는데, 돔 안에서는 방향이 보이지 않는다.
 * "번쩍 → 식음 → 암전" 은 밝기만으로 읽히므로 확실히 전달된다.
 */
static void render_flush(uint32_t now_ms)
{
    const float p = (float)(now_ms - s_flush_ms) / FLUSH_ANIM_MS;

    if (p < 0.18f) {
        paint_field(tint_flat_white, 0.0f, 0.0f, 1.0f, now_ms, 12.0f, 0.0f);
    } else if (p < 0.45f) {
        const float k = 1.0f - (p - 0.18f) / 0.27f;
        paint_field(tint_flat_gold, 0.0f, 0.0f, k * k, now_ms, 40.0f, 0.0f);
    } else {
        /* 잠깐의 암전. 보간 상태도 같이 내려야 다음 프레임에서 튀지 않는다. */
        paint_field(tint_flat_gold, 0.0f, 0.0f, 0.0f, now_ms, 40.0f, 0.0f);
    }
}

/* --------------------------------------------------------------------------
 * 쌓인 개수 → 밝기 바닥
 * ------------------------------------------------------------------------ */

/*
 * 0개면 바닥이 낮아 깊게 숨쉬고, 가득 차면 바닥이 높아 거의 계속 밝다.
 * 개수를 세지 않아도 "어두워지는 정도" 로 얼마나 찼는지 읽힌다.
 */
static float fill_floor(const led_queue_view_t *q)
{
    if (!q || q->capacity <= 0) return FILL_MIN;
    const float ratio = clampf((float)q->count / (float)q->capacity, 0.0f, 1.0f);
    return FILL_MIN + (FILL_MAX - FILL_MIN) * ratio;
}

void led_effect_render(gesture_t g, float intensity, uint32_t now_ms,
                       const led_queue_view_t *q)
{
    if (led_effect_flush_active(now_ms)) {
        render_flush(now_ms);
        return;
    }
    if (s_flush_ms) {
        s_flush_ms = 0;
        matrix_clear();     /* 연출 잔상이 다음 프레임으로 새지 않게 */
    }

    const float t = (now_ms - s_phase_ms) / 1000.0f;
    intensity = clampf(intensity, 0.0f, 1.0f);

    tint_fn tint;
    switch (g) {
    case GESTURE_SWAY_LR:  tint = tint_sway;     break;
    case GESTURE_PUMP_UD:  tint = tint_pump;     break;
    case GESTURE_VIGOROUS: tint = tint_vigorous; break;
    case GESTURE_IDLE:
    default:               tint = tint_idle;     break;
    }

    /*
     * 개수는 바닥을 올리는 방식으로 얹는다. 전체에 곱하면 개수가 적을 때
     * 리듬까지 같이 어두워져서 무슨 모션인지 안 보인다.
     * IDLE 은 대기 화면이라 개수와 무관하다.
     */
    float level = envelope(g, t, intensity);
    if (g != GESTURE_IDLE) {
        const float floor = fill_floor(q);
        level = floor + (1.0f - floor) * level;

        /* 가득 차면 얕고 빠르게 떨어 "보낼 수 있다"고 알린다 */
        if (q && q->capacity > 0 && q->count >= q->capacity) {
            level *= 0.88f + 0.12f * sinf(t * 14.0f);
        }
    }

    /*
     * 하나 쌓인 순간 색이 잠깐 흰 쪽으로 밀린다.
     * 개수를 세지 않아도 들어갔다는 게 손에 잡힌다.
     */
    float white = 0.0f;
    if (s_add_ms && (now_ms - s_add_ms) < ADD_FLASH_MS) {
        const float f = 1.0f - (float)(now_ms - s_add_ms) / ADD_FLASH_MS;
        white = f * f * 0.55f;
    }

    paint_field(tint, t, intensity, level, now_ms, follow_tau_ms(g, t), white);
}
