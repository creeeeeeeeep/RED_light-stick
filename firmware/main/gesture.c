#include <string.h>
#include <stdlib.h>
#include <math.h>

#include "gesture.h"
#include "esp_log.h"

#define WIN_SEC         0.8f    /* RMS/피크 윈도우 */
#define STROKE_WIN_MS   1200    /* 스트로크 집계 윈도우 — 1Hz 모션도 2회를 채우도록 */
#define MAX_WIN         256
#define DECIDE_HZ       20      /* 50ms마다 재분류 */
#define STROKE_RING     24
#define DEG2RAD         0.017453292f

struct gesture_engine_t {
    gesture_config_t cfg;
    float dt;
    int   win;                  /* 윈도우 길이 (샘플 수) */
    int   decide_every;         /* 몇 샘플마다 분류할지 */

    /* 중력 추정 (상보필터) */
    float gvec[3];
    bool  gvec_init;
    float a_slow[3];        /* 저역통과 가속도 — 느린 보정의 기준 */
    float w_slow;           /* 저역통과 |각속도| (dps) — 원심 편향의 지표 */
    float dyn_slow;         /* 저역통과 |a - a_slow| (g) — 흔들림의 정도 */
    int   diverge_n;        /* 발산이 지속된 샘플 수 */
    int   diverge_need;
    float init_sum[3];      /* 초기 평균용 누산기 */
    int   init_n;
    int   init_need;

    /* 슬라이딩 윈도우: 제곱합만 필요하므로 제곱값을 저장해 누적 갱신 */
    float sq_v[MAX_WIN];
    float sq_h[MAX_WIN];
    float sq_g[MAX_WIN];
    float mag_lin[MAX_WIN];
    double sum_v, sum_h, sum_g;
    int  idx;
    int  count;

    /*
     * 스트로크 검출. 수직축(부호 반전)과 수평면(벡터 방향 반전)을 따로 세고
     * 분류 시점에 둘 중 큰 값을 쓴다. 상하 찍기는 수평 성분이 거의 없고,
     * 좌우 흔들기는 원심력 탓에 수직 성분이 부호를 잘 안 바꾸기 때문이다.
     */
    int      sign_v;                    /* -1 / 0 / +1 */
    float    href[3];                   /* 마지막 수평 스트로크의 방향 (단위벡터) */
    bool     href_valid;
    uint32_t stroke_v_ms[STROKE_RING];
    uint32_t stroke_h_ms[STROKE_RING];
    int      stroke_v_head;
    int      stroke_h_head;

    /* 분류 상태 */
    int       tick;
    gesture_t committed;
    gesture_t candidate;
    int       candidate_ticks;
    uint32_t  committed_ms;
    float     intensity;
    gesture_features_t feat;
};

void gesture_default_config(gesture_config_t *cfg)
{
    cfg->idle_rms_g       = 0.12f;
    cfg->axis_ratio       = 1.35f;
    /*
     * 격한 흔들기 임계. 사람이 봉을 정말 격하게 흔들면 센서 위치(손잡이에서
     * 20cm 위)에서 4~15g가 나온다. 반면 빠른 좌우/상하는 1~2g 수준이라
     * 밴드를 넉넉히 벌려 둔다. 너무 낮추면 신나는 좌우 흔들기가 전부
     * VIGOROUS로 빨려 들어간다.
     */
    cfg->vig_peak_g       = 3.20f;
    /*
     * 실기 로그(113초, 2360샘플) 기준으로 1.65 가 최적점이다.
     * 이 값에서 좌우/상하 오탐이 0 이고, 격하게의 63%를 tot 만으로 잡는다.
     * 2.00 은 너무 보수적이어서 tot 조건이 사실상 죽어 있었다
     * (VIGOROUS 전환 4회가 전부 peak 로만 발동했다).
     * 참고: 실측 최대값 — 좌우 1.56 / 상하 1.29 / 격하게 3.73
     */
    cfg->vig_rms_g        = 1.65f;
    cfg->vig_gyro_dps     = 500.0f;
    cfg->vig_gyro_min_rms = 0.45f;
    cfg->vig_hysteresis   = 0.72f;
    cfg->stroke_dead_g    = 0.10f;
    cfg->stroke_flip_dot  = -0.30f;
    cfg->max_crest        = 4.5f;
    cfg->min_strokes      = 2;
    cfg->confirm_ticks    = 3;
    /*
     * 실기 로그에서 구간의 22%가 0.6초 이하로 끊겼다 (짧은 IDLE 7회,
     * 짧은 PUMP_UD 4회). 400ms 는 최소 유지 시간이라 그 값에 딱 맞춰
     * 깜빡이고 있었다. 700ms 로 올려 흔드는 도중의 순간적인 흔들림에
     * 상태가 따라가지 않게 한다.
     */
    cfg->hold_ms          = 700;
    /*
     * IDLE 로 되돌아갈 때만 임계를 낮춘다.
     * 흔드는 도중 에너지가 잠깐 꺼져도 IDLE 로 떨어지지 않게 하는 장치다.
     * 들어갈 때 0.12, 나올 때 0.12*0.6 = 0.072 가 된다.
     */
    cfg->idle_exit_ratio  = 0.60f;
}

gesture_engine_t *gesture_create(const gesture_config_t *cfg, float sample_hz)
{
    gesture_engine_t *eng = calloc(1, sizeof(gesture_engine_t));
    if (!eng) {
        return NULL;
    }

    if (cfg) {
        eng->cfg = *cfg;
    } else {
        gesture_default_config(&eng->cfg);
    }

    eng->dt  = 1.0f / sample_hz;
    eng->win = (int)(sample_hz * WIN_SEC);
    if (eng->win > MAX_WIN) {
        eng->win = MAX_WIN;
    }
    if (eng->win < 8) {
        eng->win = 8;
    }
    eng->decide_every = (int)(sample_hz / DECIDE_HZ);
    if (eng->decide_every < 1) {
        eng->decide_every = 1;
    }
    eng->init_need = (int)(sample_hz * 0.4f);   /* 초기 중력 평균 구간 0.4초 */
    if (eng->init_need < 4) {
        eng->init_need = 4;
    }
    eng->diverge_need = (int)(sample_hz * 1.5f); /* 1.5초 연속 어긋나면 강제 정렬 */
    if (eng->diverge_need < 8) {
        eng->diverge_need = 8;
    }

    eng->committed = GESTURE_IDLE;
    eng->candidate = GESTURE_IDLE;
    return eng;
}

void gesture_destroy(gesture_engine_t *eng)
{
    free(eng);
}

/* --------------------------------------------------------------------------
 * 중력 추정: 자이로로 회전 예측 + 가속도로 보정
 *
 * 보정은 두 갈래다.
 *   빠른 보정 : |a|가 1g에 가까울 때(= 거의 정지)만 크게 작동. 빠른 수렴 담당.
 *   느린 보정 : 항상 작동. 저역통과된 가속도를 향해 조금씩 끌어당긴다.
 *
 * 느린 보정이 반드시 있어야 한다. 빠른 보정만 두면 격하게 흔드는 동안
 * |a|가 1g 근처로 오지 않아 신뢰 게이트가 계속 닫혀 있고, 그 사이 자이로
 * 적분 오차로 한번 틀어진 중력 추정이 영원히 복구되지 않는다 (시뮬레이션에서
 * 6초 뒤에도 120도 오차가 남았다). 그러면 수직/수평 분해가 뒤집혀서
 * 좌우 흔들기와 상하 찍기가 조용히 서로 바뀐다.
 *
 * 흔드는 동작은 진동이므로 선형가속도의 한 주기 평균은 0이고, 따라서
 * 저역통과된 가속도는 흔드는 도중에도 중력 방향을 가리킨다.
 * ------------------------------------------------------------------------ */
#define GRAV_SLOW_TAU_S     1.0f    /* 가속도 저역통과 시정수 */
#define GRAV_ALPHA_FAST     0.020f  /* 준정지 시 보정 계수 */
#define GRAV_ALPHA_SLOW     0.010f  /* 상시 보정 계수 (≈0.5초 시정수 @200Hz) */
#define GRAV_SPIN_GATE_DPS  400.0f  /* 이 이상 회전하면 느린 보정을 닫는다 */
#define GRAV_QUIET_GATE_G   0.30f   /* 이 이상 진동하면 빠른 보정을 닫는다 */

static void update_gravity(gesture_engine_t *eng, const qmi8658_data_t *s)
{
    const float a[3] = { s->ax, s->ay, s->az };
    const float amag = sqrtf(a[0] * a[0] + a[1] * a[1] + a[2] * a[2]);

    if (!eng->gvec_init) {
        /*
         * 초기 방향은 한 샘플이 아니라 짧은 평균으로 잡는다. 부팅 직후
         * 이미 움직이고 있어도 한 주기 이상 평균되면 중력에 수렴한다.
         */
        eng->init_sum[0] += a[0];
        eng->init_sum[1] += a[1];
        eng->init_sum[2] += a[2];
        if (++eng->init_n >= eng->init_need) {
            const float m[3] = {
                eng->init_sum[0] / eng->init_n,
                eng->init_sum[1] / eng->init_n,
                eng->init_sum[2] / eng->init_n,
            };
            const float mn = sqrtf(m[0] * m[0] + m[1] * m[1] + m[2] * m[2]);
            if (mn > 0.3f) {
                for (int i = 0; i < 3; i++) {
                    eng->gvec[i]   = m[i] / mn;
                    eng->a_slow[i] = m[i];
                }
                eng->gvec_init = true;
            }
            /* 자유낙하 등으로 평균이 무의미하면 다시 모은다 */
            eng->init_n = 0;
            eng->init_sum[0] = eng->init_sum[1] = eng->init_sum[2] = 0.0f;
        }
        return;
    }

    /* 저역통과 가속도 / 각속도 갱신 */
    const float beta = eng->dt / GRAV_SLOW_TAU_S;
    for (int i = 0; i < 3; i++) {
        eng->a_slow[i] += beta * (a[i] - eng->a_slow[i]);
    }
    const float wnow = sqrtf(s->gx * s->gx + s->gy * s->gy + s->gz * s->gz);
    eng->w_slow += beta * (wnow - eng->w_slow);

    const float ac[3] = {
        a[0] - eng->a_slow[0], a[1] - eng->a_slow[1], a[2] - eng->a_slow[2],
    };
    const float dyn = sqrtf(ac[0] * ac[0] + ac[1] * ac[1] + ac[2] * ac[2]);
    eng->dyn_slow += beta * (dyn - eng->dyn_slow);

    /*
     * 바디 프레임에서 본 중력은 dg/dt = -w x g 로 회전한다.
     *
     * 오일러 1차(g -= (w x g)dt) 대신 로드리게스 회전을 쓴다. 격하게 흔들면
     * 각속도가 1000dps에 달해 한 스텝(5ms)에 5도씩 도는데, 그 영역에서
     * 1차 근사는 오차가 무시할 수준이 아니다. 스텝 내 각속도가 일정하다고
     * 보면 로드리게스는 정확해이고, 비용은 샘플당 sin/cos 한 번뿐이다.
     */
    const float wx = s->gx * DEG2RAD;
    const float wy = s->gy * DEG2RAD;
    const float wz = s->gz * DEG2RAD;
    const float *g = eng->gvec;

    float p[3];
    const float wmag = sqrtf(wx * wx + wy * wy + wz * wz);
    const float theta = wmag * eng->dt;

    if (theta > 1e-6f) {
        const float n[3] = { wx / wmag, wy / wmag, wz / wmag };
        const float ct = cosf(theta);
        const float st = sinf(theta);
        const float ndg = n[0] * g[0] + n[1] * g[1] + n[2] * g[2];
        /* g 를 축 n 둘레로 -theta 만큼 회전 */
        const float ncg[3] = {
            n[1] * g[2] - n[2] * g[1],
            n[2] * g[0] - n[0] * g[2],
            n[0] * g[1] - n[1] * g[0],
        };
        for (int i = 0; i < 3; i++) {
            p[i] = g[i] * ct - ncg[i] * st + n[i] * ndg * (1.0f - ct);
        }
    } else {
        p[0] = g[0];
        p[1] = g[1];
        p[2] = g[2];
    }

    /*
     * (1) 빠른 보정 — 사실상 정지 상태일 때만 크게 작동.
     *
     * "정지"의 판정에 순간 |a|만 쓰면 안 된다. 격하게 흔드는 동안 |a|는
     * 0~4g를 오가며 매 주기 1g를 스쳐 지나가는데, 그 순간의 가속도 방향은
     * 중력과 아무 상관이 없다. 게이트가 매 주기 잠깐씩 열려 엉뚱한 방향으로
     * 조금씩 끌려가고, 그게 누적되면 수십 도까지 벌어진다 (계측에서 평균
     * fast_trust 0.05만으로 8초에 36도).
     *
     * 그래서 저역통과된 진동 크기(dyn_slow)로 한 번 더 막는다. 이 값은
     * 정지 상태에서만 0에 가깝고, 흔드는 동안에는 |a|가 어디를 지나든 크다.
     */
    if (amag > 0.3f) {
        const float dev   = fabsf(amag - 1.0f) / 0.5f;
        const float trust = 1.0f - (dev > 1.0f ? 1.0f : dev);
        const float qdev  = eng->dyn_slow / GRAV_QUIET_GATE_G;
        const float quiet = 1.0f - (qdev > 1.0f ? 1.0f : qdev);
        const float alpha = GRAV_ALPHA_FAST * trust * quiet;
        if (alpha > 0.0f) {
            for (int i = 0; i < 3; i++) {
                p[i] = p[i] * (1.0f - alpha) + (a[i] / amag) * alpha;
            }
        }
    }

    /*
     * (2) 느린 보정.
     *
     * 저역통과 가속도의 크기가 1g 근처일 때만 적용한다. 봉을 격하게 휘두르면
     * 원심가속도(호 반경 20cm, 4Hz면 4g가 넘는다)가 항상 회전축 쪽을 향해
     * 걸리기 때문에 a_slow가 1g를 크게 벗어나고, 그걸 중력으로 믿으면
     * 추정이 정반대로 뒤집힌다 (시뮬레이션에서 169도까지 갔다).
     *
     * 게이트는 두 개다.
     *   크기 게이트 : |a_slow|가 1g에서 멀면 그건 중력이 아니다.
     *   회전 게이트 : 원심 편향은 "지속적인 회전"이 있을 때만 생기므로
     *                저역통과 각속도가 크면 느린 보정을 닫는다.
     *
     * 크기 게이트만으로는 부족하다. 중간 세기의 회전(3Hz 부근)에서는
     * |a_slow|가 1.2g 정도라 게이트가 반쯤 열린 채 편향된 방향을 그대로
     * 따라가서, 게이트가 완전히 닫히는 더 격한 경우보다 오히려 오차가
     * 커진다 (시뮬레이션에서 10도 vs 54도).
     *
     * 두 게이트가 닫혀 있는 동안에는 자이로 적분만으로 버티는데, 부팅 시
     * 바이어스를 보정해 두면 수 초 정도는 10도 이내로 유지된다.
     */
    const float sm = sqrtf(eng->a_slow[0] * eng->a_slow[0] +
                           eng->a_slow[1] * eng->a_slow[1] +
                           eng->a_slow[2] * eng->a_slow[2]);
    if (sm > 0.3f) {
        const float sdev  = fabsf(sm - 1.0f) / 0.6f;
        const float strut = 1.0f - (sdev > 1.0f ? 1.0f : sdev);
        const float wdev  = eng->w_slow / GRAV_SPIN_GATE_DPS;
        const float wtrut = 1.0f - (wdev > 1.0f ? 1.0f : wdev);
        const float alpha = GRAV_ALPHA_SLOW * strut * wtrut;
        if (alpha > 0.0f) {
            for (int i = 0; i < 3; i++) {
                p[i] = p[i] * (1.0f - alpha) + (eng->a_slow[i] / sm) * alpha;
            }
        }
    }

    const float n = sqrtf(p[0] * p[0] + p[1] * p[1] + p[2] * p[2]);
    if (n > 1e-6f) {
        eng->gvec[0] = p[0] / n;
        eng->gvec[1] = p[1] / n;
        eng->gvec[2] = p[2] / n;
    }

    /*
     * 발산 감지 및 강제 정렬.
     *
     * 위 게이트들은 흔드는 동안 잘못된 보정이 들어오는 걸 막지만, 반대로
     * 이미 크게 틀어진 추정을 되돌리는 경로까지 같이 막는다. 봉을 흔드는
     * 도중에 전원이 들어온 경우가 그렇다 (초기 평균이 오염되고, 그 뒤로
     * 게이트가 닫혀 있어 영영 회복되지 않는다).
     *
     * 그래서 a_slow의 크기가 정말로 중력처럼 보이는 구간(0.7~1.3g)에서
     * 방향이 45도 이상 계속 어긋나면 그쪽으로 한 번에 맞춘다. 정상 동작
     * 중에는 추정이 잘 따라가므로 이 조건이 성립하지 않는다.
     */
    if (sm > 0.7f && sm < 1.3f) {
        const float d = (eng->a_slow[0] * eng->gvec[0] +
                         eng->a_slow[1] * eng->gvec[1] +
                         eng->a_slow[2] * eng->gvec[2]) / sm;
        if (d < 0.7f) {
            if (++eng->diverge_n >= eng->diverge_need) {
                for (int i = 0; i < 3; i++) {
                    eng->gvec[i] = eng->a_slow[i] / sm;
                }
                eng->diverge_n = 0;
            }
        } else {
            eng->diverge_n = 0;
        }
    } else {
        eng->diverge_n = 0;
    }
}

/* --------------------------------------------------------------------------
 * 분류
 * ------------------------------------------------------------------------ */
static gesture_t classify(gesture_engine_t *eng, uint32_t now_ms)
{
    const gesture_config_t *c = &eng->cfg;
    const int n = eng->count < eng->win ? eng->count : eng->win;
    if (n < eng->win / 2) {
        return GESTURE_IDLE;    /* 아직 윈도우가 덜 찼다 */
    }

    const float rms_v = sqrtf((float)(eng->sum_v / n));
    const float rms_h = sqrtf((float)(eng->sum_h / n));
    const float rms_g = sqrtf((float)(eng->sum_g / n));
    const float rms_t = sqrtf(rms_v * rms_v + rms_h * rms_h);

    float peak = 0.0f;
    for (int i = 0; i < n; i++) {
        if (eng->mag_lin[i] > peak) {
            peak = eng->mag_lin[i];
        }
    }

    /* 최근 STROKE_WIN_MS 안에 들어오는 스트로크만 센다 */
    int strokes_v = 0, strokes_h = 0;
    for (int i = 0; i < STROKE_RING; i++) {
        uint32_t tv = eng->stroke_v_ms[i];
        if (tv != 0 && (now_ms - tv) <= STROKE_WIN_MS) {
            strokes_v++;
        }
        uint32_t th = eng->stroke_h_ms[i];
        if (th != 0 && (now_ms - th) <= STROKE_WIN_MS) {
            strokes_h++;
        }
    }
    const int strokes = (strokes_v > strokes_h) ? strokes_v : strokes_h;

    eng->feat.rms_vertical   = rms_v;
    eng->feat.rms_horizontal = rms_h;
    eng->feat.rms_total      = rms_t;
    eng->feat.peak_linear    = peak;
    eng->feat.rms_gyro       = rms_g;
    eng->feat.strokes        = strokes;
    eng->feat.stroke_rate    = strokes / (STROKE_WIN_MS / 1000.0f);
    eng->feat.tilt_deg       = acosf(fmaxf(-1.0f, fminf(1.0f, eng->gvec[2]))) / DEG2RAD;

    /* 이펙트 강도: 0.35g ~ 1.6g를 0~1로 매핑 */
    float inten = (rms_t - 0.10f) / 1.50f;
    eng->intensity = inten < 0.0f ? 0.0f : (inten > 1.0f ? 1.0f : inten);

    /*
     * 진동이 아니면(= 단발 충격, 손에 쥐고 걷기 등) IDLE.
     *
     * 들어갈 때와 나올 때의 임계를 다르게 둔다. 이미 모션 상태라면 더 낮은
     * 값까지 버틴다. 흔드는 동작은 매 스트로크 사이에 에너지가 순간적으로
     * 꺼지는데, 대칭 임계를 쓰면 그때마다 IDLE 로 떨어졌다 돌아온다
     * (실기 로그에서 짧은 IDLE 구간이 7번 나왔다).
     */
    const float idle_th = (eng->committed == GESTURE_IDLE)
        ? c->idle_rms_g
        : c->idle_rms_g * c->idle_exit_ratio;

    if (strokes < c->min_strokes || rms_t < idle_th) {
        return GESTURE_IDLE;
    }
    /*
     * 파고율이 높다 = 에너지가 한순간에 몰려 있다 = 봉을 내려놓거나 부딪힌 것.
     * 지속적인 흔들기는 정현파에 가까워 peak/rms가 1.3~2.5 수준이다.
     */
    if (peak > c->max_crest * rms_t) {
        return GESTURE_IDLE;
    }

    /* 이미 VIGOROUS면 임계를 낮춰서 경계에서 깜빡이지 않게 한다 */
    const float s = (eng->committed == GESTURE_VIGOROUS) ? c->vig_hysteresis : 1.0f;

    if (peak  >= c->vig_peak_g   * s ||
        rms_t >= c->vig_rms_g    * s ||
        (rms_g >= c->vig_gyro_dps * s && rms_t >= c->vig_gyro_min_rms * s)) {
        return GESTURE_VIGOROUS;
    }

    /*
     * 축 비교는 "축 하나당 에너지" 로 해야 공평하다.
     *
     * rms_v 는 중력축 하나의 크기지만 rms_h 는 그에 수직인 평면 두 축의
     * 합이다. 그래서 등방 잡음만 있어도 rms_h 가 rms_v 의 약 1.41배(=√2)로
     * 나온다. axis_ratio 가 1.35 였으니, 아무것도 안 하고 있어도 수평이
     * 이기는 구조였다. 흔들기 시작한 직후처럼 신호가 아직 잡음에 묻혀 있는
     * 구간에서 거의 언제나 SWAY 로 판정되던 원인이 이것이다.
     *
     * √2 로 나눠 두 값을 같은 기준에 올려놓는다. 잡음만 있을 때 비가 1.0이
     * 되므로 어느 쪽도 이기지 못하고, IDLE 에서는 그대로 IDLE 로 남는다.
     *
     * feat.rms_horizontal 은 실제 수평 크기 그대로 둔다 — 로그와 임계값이
     * 그 정의를 쓰고 있다. 여기서만 축 기준으로 환산한다.
     */
    const float rms_h_axis = rms_h * 0.70710678f;

    if (rms_v >= rms_h_axis * c->axis_ratio) {
        return GESTURE_PUMP_UD;
    }
    if (rms_h_axis >= rms_v * c->axis_ratio) {
        return GESTURE_SWAY_LR;
    }

    /* 축이 모호한 구간 — 이전 모션을 유지해서 팔랑거림을 막는다 */
    return (eng->committed == GESTURE_IDLE) ? GESTURE_IDLE : eng->committed;
}

gesture_t gesture_update(gesture_engine_t *eng, const qmi8658_data_t *s,
                         uint32_t now_ms, bool *changed)
{
    if (changed) {
        *changed = false;
    }
    if (!eng || !s) {
        return GESTURE_IDLE;
    }

    update_gravity(eng, s);
    if (!eng->gvec_init) {
        return eng->committed;
    }

    /* 선형가속도 = 측정값 - 중력 (gvec은 단위벡터, 크기 1g) */
    const float lin[3] = {
        s->ax - eng->gvec[0],
        s->ay - eng->gvec[1],
        s->az - eng->gvec[2],
    };

    /* 수직 성분 / 수평 성분 분해 */
    const float a_v = lin[0] * eng->gvec[0] + lin[1] * eng->gvec[1] + lin[2] * eng->gvec[2];
    const float h[3] = {
        lin[0] - a_v * eng->gvec[0],
        lin[1] - a_v * eng->gvec[1],
        lin[2] - a_v * eng->gvec[2],
    };
    const float a_h  = sqrtf(h[0] * h[0] + h[1] * h[1] + h[2] * h[2]);
    const float mag  = sqrtf(lin[0] * lin[0] + lin[1] * lin[1] + lin[2] * lin[2]);
    const float gmag = sqrtf(s->gx * s->gx + s->gy * s->gy + s->gz * s->gz);

    /* 링버퍼 갱신 — 나가는 값을 빼고 들어오는 값을 더한다 */
    const int i = eng->idx;
    if (eng->count >= eng->win) {
        eng->sum_v -= eng->sq_v[i];
        eng->sum_h -= eng->sq_h[i];
        eng->sum_g -= eng->sq_g[i];
    }
    eng->sq_v[i]    = a_v * a_v;
    eng->sq_h[i]    = a_h * a_h;
    eng->sq_g[i]    = gmag * gmag;
    eng->mag_lin[i] = mag;
    eng->sum_v += eng->sq_v[i];
    eng->sum_h += eng->sq_h[i];
    eng->sum_g += eng->sq_g[i];

    eng->idx = (i + 1) % eng->win;
    if (eng->count < eng->win) {
        eng->count++;
    }

    /* ---- 스트로크 검출 ---- */
    const uint32_t stamp = now_ms ? now_ms : 1;   /* 0은 "빈 칸" 표식이라 피한다 */
    const float dead = eng->cfg.stroke_dead_g;

    /* 수직: 데드밴드 밖에서 부호가 뒤집힐 때마다 1회 */
    if (a_v > dead) {
        if (eng->sign_v <= 0) {
            eng->sign_v = 1;
            eng->stroke_v_ms[eng->stroke_v_head] = stamp;
            eng->stroke_v_head = (eng->stroke_v_head + 1) % STROKE_RING;
        }
    } else if (a_v < -dead) {
        if (eng->sign_v >= 0) {
            eng->sign_v = -1;
            eng->stroke_v_ms[eng->stroke_v_head] = stamp;
            eng->stroke_v_head = (eng->stroke_v_head + 1) % STROKE_RING;
        }
    }

    /* 수평: 가속도 벡터가 직전 스트로크 방향의 반대편으로 넘어갈 때마다 1회 */
    if (a_h > dead) {
        const float hu[3] = { h[0] / a_h, h[1] / a_h, h[2] / a_h };
        if (!eng->href_valid) {
            eng->href_valid = true;
            memcpy(eng->href, hu, sizeof(hu));
            eng->stroke_h_ms[eng->stroke_h_head] = stamp;
            eng->stroke_h_head = (eng->stroke_h_head + 1) % STROKE_RING;
        } else {
            const float d = hu[0] * eng->href[0] + hu[1] * eng->href[1] + hu[2] * eng->href[2];
            if (d < eng->cfg.stroke_flip_dot) {
                memcpy(eng->href, hu, sizeof(hu));
                eng->stroke_h_ms[eng->stroke_h_head] = stamp;
                eng->stroke_h_head = (eng->stroke_h_head + 1) % STROKE_RING;
            }
        }
    }

    /* 50ms마다만 분류 */
    if (++eng->tick < eng->decide_every) {
        return eng->committed;
    }
    eng->tick = 0;

    gesture_t cand = classify(eng, now_ms);

    if (cand == eng->candidate) {
        eng->candidate_ticks++;
    } else {
        eng->candidate = cand;
        eng->candidate_ticks = 1;
    }

    if (cand == eng->committed) {
        return eng->committed;
    }

    /*
     * 격한 흔들기는 즉시 반응해야 응원봉답다 → 확정 틱 1회.
     * 나머지는 confirm_ticks만큼 연속으로 같아야 전환한다.
     */
    const int need = (cand == GESTURE_VIGOROUS) ? 1 : eng->cfg.confirm_ticks;
    const bool held_long_enough = (now_ms - eng->committed_ms) >= (uint32_t)eng->cfg.hold_ms;

    if (eng->candidate_ticks >= need && held_long_enough) {
        eng->committed    = cand;
        eng->committed_ms = now_ms;
        if (changed) {
            *changed = true;
        }
    }

    return eng->committed;
}

gesture_t gesture_current(const gesture_engine_t *eng)
{
    return eng ? eng->committed : GESTURE_IDLE;
}

float gesture_intensity(const gesture_engine_t *eng)
{
    return eng ? eng->intensity : 0.0f;
}

void gesture_get_features(const gesture_engine_t *eng, gesture_features_t *out)
{
    if (eng && out) {
        *out = eng->feat;
    }
}

const char *gesture_name(gesture_t g)
{
    switch (g) {
    case GESTURE_IDLE:     return "IDLE";
    case GESTURE_SWAY_LR:  return "SWAY_LR";
    case GESTURE_PUMP_UD:  return "PUMP_UD";
    case GESTURE_VIGOROUS: return "VIGOROUS";
    default:               return "?";
    }
}
