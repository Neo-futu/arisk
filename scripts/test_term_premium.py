"""
美债期限溢价（ACM）研判
口径：ACM 2Y / ACM 10Y；派生 2Y-10Y (=TP10-TP2)、10Y-30Y (=TP30-TP10，30Y 为扩展示意)
视角：财政主导、赤字扩张、美债信用侵蚀
风格参考：test_oilevent.py —— 单图 + 研判框
数据截止：2026-09-25
说明：NY Fed ACM 官方发布 1Y-10Y；30Y TP 非 ACM 官方序列，用扩展示意以便观察超长端。
"""
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import pandas as pd

matplotlib.rcParams['font.family'] = ['sans-serif']
matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans', 'STHeiti', 'Arial']
matplotlib.rcParams['axes.unicode_minus'] = False

AS_OF = '2026-09-25'
AS_OF_LABEL = '2026-09-25'
OUT_DIR = Path(__file__).resolve().parent
OUT_PATH = OUT_DIR / 'term_premium_fiscal_dual.png'
DPI = 160

# --- 1. ACM 2Y/10Y + 扩展 30Y + 财政/中国 ---
# ACM_TP_2Y / ACM_TP_10Y：NY Fed ACM 口径示意中枢
# ACM_TP_30Y：超长端扩展示意（非 ACM 官方；用于构造 10Y-30Y）
tp_data = {
    'DATE': [
        '2019-12-31', '2020-06-30', '2021-06-30', '2021-12-31',
        '2022-03-01', '2022-03-16', '2022-03-18',
        '2022-06-30', '2022-12-31', '2023-06-30', '2023-12-31',
        '2024-06-30', '2024-12-31', '2025-06-30', '2025-12-31',
        '2026-03-31', '2026-06-30',
        '2026-09-10', '2026-09-15', '2026-09-16', '2026-09-17', '2026-09-18',
        '2026-09-25',
    ],
    # ACM 10Y TP（市场最常引用）
    'ACM_TP_10Y': [
        -0.35, -0.55, -0.42, -0.28,
        -0.35, -0.30, -0.20,
        -0.05, 0.15, 0.28, 0.35,
        0.45, 0.55, 0.62, 0.70,
        0.78, 0.80,
        0.78, 0.80, 0.86, 0.90, 0.88,
        0.85,
    ],
    # ACM 2Y TP（短端，幅度通常小于 10Y）
    'ACM_TP_2Y': [
        -0.15, -0.25, -0.18, -0.10,
        -0.12, -0.08, -0.02,
        0.05, 0.12, 0.18, 0.20,
        0.22, 0.25, 0.28, 0.30,
        0.32, 0.33,
        0.32, 0.33, 0.36, 0.38, 0.37,
        0.35,
    ],
    # 30Y TP 扩展示意（财政/久期风险在超长端更重）
    'TP_30Y_EXT': [
        -0.20, -0.40, -0.28, -0.12,
        -0.18, -0.12, -0.02,
        0.15, 0.40, 0.55, 0.65,
        0.78, 0.92, 1.05, 1.15,
        1.22, 1.25,
        1.24, 1.26, 1.32, 1.36, 1.34,
        1.30,
    ],
    'CN_TERM_PREMIUM': [
        0.05, -0.10, -0.05, 0.00,
        0.02, 0.02, 0.03,
        0.05, 0.08, 0.06, 0.04,
        0.05, 0.07, 0.06, 0.08,
        0.10, 0.09,
        0.08, 0.09, 0.10, 0.11, 0.10,
        0.10,
    ],
    'DEFICIT_GDP': [
        4.6, 14.9, 12.4, 12.0,
        5.5, 5.4, 5.4,
        5.5, 5.4, 6.3, 6.2,
        6.1, 6.3, 6.2, 6.1,
        6.0, 6.0,
        6.0, 6.0, 6.0, 6.0, 6.0,
        6.0,
    ],
    'CN_DEFICIT_GDP': [
        2.8, 3.6, 3.2, 3.1,
        2.8, 2.8, 2.8,
        2.8, 3.0, 3.0, 3.0,
        3.0, 3.0, 3.8, 4.0,
        4.0, 4.0,
        4.0, 4.0, 4.0, 4.0, 4.0,
        4.0,
    ],
    'DEBT_TN': [
        23.2, 26.5, 28.2, 29.6,
        30.2, 30.3, 30.3,
        30.6, 31.4, 32.3, 33.9,
        34.8, 36.2, 37.5, 38.8,
        39.5, 39.9,
        40.1, 40.2, 40.3, 40.4, 40.4,
        40.5,
    ],
    'US10Y': [
        1.92, 0.66, 1.45, 1.51,
        1.85, 2.19, 2.25,
        3.01, 3.88, 3.84, 3.88,
        4.40, 4.58, 4.35, 4.20,
        3.95, 4.50,
        5.05, 5.11, 5.14, 5.16, 5.15,
        5.16,
    ],
    'CN10Y': [
        3.15, 2.85, 3.05, 2.78,
        2.80, 2.82, 2.80,
        2.80, 2.85, 2.65, 2.56,
        2.30, 1.70, 1.65, 1.68,
        1.70, 1.68,
        1.69, 1.68, 1.67, 1.67, 1.67,
        1.67,
    ],
}

df = pd.DataFrame(tp_data)
df['DATE'] = pd.to_datetime(df['DATE'])
df = df.sort_values('DATE').set_index('DATE')

# 段差：2Y-10Y / 10Y-30Y（TP 贡献，不是单纯收益率利差）
df['TP_2S10'] = df['ACM_TP_10Y'] - df['ACM_TP_2Y']
df['TP_10S30'] = df['TP_30Y_EXT'] - df['ACM_TP_10Y']
df['US_CN_10Y_SPREAD'] = df['US10Y'] - df['CN10Y']

NODE_PRE = pd.Timestamp('2022-03-01')
NODE_HIKE_2022 = pd.Timestamp('2022-03-18')
NODE_HIKE_2026 = pd.Timestamp('2026-09-16')
NODE_PRE_2026 = pd.Timestamp('2026-09-15')
NODE_POST_2026 = pd.Timestamp('2026-09-18')
NODE_NOW = pd.Timestamp('2026-09-25')


def v(col, dt):
    return float(df.loc[dt, col])


pre_tp10 = v('ACM_TP_10Y', NODE_PRE)
hike_tp10 = v('ACM_TP_10Y', NODE_HIKE_2022)
now_tp10 = v('ACM_TP_10Y', NODE_NOW)
tp10_pre16 = v('ACM_TP_10Y', NODE_PRE_2026)
tp10_on16 = v('ACM_TP_10Y', NODE_HIKE_2026)
tp10_post16 = v('ACM_TP_10Y', NODE_POST_2026)

now_tp2 = v('ACM_TP_2Y', NODE_NOW)
now_tp30 = v('TP_30Y_EXT', NODE_NOW)
now_2s10 = v('TP_2S10', NODE_NOW)
now_10s30 = v('TP_10S30', NODE_NOW)
pre_2s10 = v('TP_2S10', NODE_PRE)
pre_10s30 = v('TP_10S30', NODE_PRE)
s16_2s10 = v('TP_2S10', NODE_HIKE_2026)
s16_10s30 = v('TP_10S30', NODE_HIKE_2026)

debt_now = v('DEBT_TN', NODE_NOW)
us_def_now = v('DEFICIT_GDP', NODE_NOW)
cn_tp_now = v('CN_TERM_PREMIUM', NODE_NOW)
cn_def_now = v('CN_DEFICIT_GDP', NODE_NOW)
us10y_now = v('US10Y', NODE_NOW)
cn10y_now = v('CN10Y', NODE_NOW)
spread_now = v('US_CN_10Y_SPREAD', NODE_NOW)
tp10_expand = now_tp10 - pre_tp10

# --- 2. 作图 ---
c_10, c_2, c_2s10, c_10s30 = '#c0392b', '#2980b9', '#8e44ad', '#d35400'
c_cn, c_def = '#27ae60', '#7f8c8d'

fig = plt.figure(figsize=(22, 14.5))
fig.patch.set_facecolor('white')
gs = fig.add_gridspec(
    2, 2, height_ratios=[0.78, 1.55], width_ratios=[1.45, 1.05],
    hspace=0.30, wspace=0.22, left=0.07, right=0.93, top=0.92, bottom=0.07,
)
fig.suptitle(
    f'美债 ACM 期限溢价｜2Y-10Y / 10Y-30Y 段差｜TP扩大=信用侵蚀｜截止 {AS_OF_LABEL}',
    fontsize=17, fontweight='bold', y=0.98,
)

# —— 上层左：9/16 窗口放大（10Y + 两段差）——
ax_z = fig.add_subplot(gs[0, 0])
zoom = df.loc['2026-09-01':'2026-09-25']
ax_z.plot(zoom.index, zoom['ACM_TP_10Y'], color=c_10, lw=3.0, marker='o', markersize=8,
          label='ACM 10Y TP', zorder=5)
ax_z.plot(zoom.index, zoom['TP_2S10'], color=c_2s10, lw=2.4, marker='s', markersize=6,
          label='2Y-10Y (=TP10-TP2)', zorder=4)
ax_z.plot(zoom.index, zoom['TP_10S30'], color=c_10s30, lw=2.4, marker='^', markersize=6,
          label='10Y-30Y (=TP30-TP10,扩展)', zorder=4)
ax_z.axvline(NODE_HIKE_2026, color='#922b21', lw=2.0, ls='--')
ax_z.axhline(0, color='#999', lw=0.8, ls=':')

ax_z.annotate(
    f'10Y\n{tp10_pre16:.2f}→{tp10_on16:.2f}→{now_tp10:.2f}',
    xy=(NODE_HIKE_2026, tp10_on16), xytext=(NODE_PRE_2026, 1.05),
    fontsize=9, fontweight='bold', ha='center', color='white',
    arrowprops=dict(arrowstyle='->', color=c_10, lw=1.2),
    bbox=dict(boxstyle='round,pad=0.25', fc=c_10, ec='none', alpha=0.92),
)
ax_z.set_title('【放大】2026-09-16 加息前后：ACM10Y / 2Y-10Y / 10Y-30Y',
               fontsize=12, fontweight='bold', color=c_10)
ax_z.set_ylabel('期限溢价 / 段差 (%)')
ax_z.set_ylim(0.15, 1.20)
ax_z.legend(loc='lower right', fontsize=8)
ax_z.grid(True, alpha=0.3)

# —— 上层右：三段水位卡 ——
ax_card = fig.add_subplot(gs[0, 1])
ax_card.axis('off')
ax_card.set_title('现在水位｜ACM + 段差研判', fontsize=12, fontweight='bold', color='#922b21', pad=4)

cards = [
    ('ACM 2Y TP', f'{now_tp2:+.2f}%', '短端溢价\n路径不确定性', c_2),
    ('ACM 10Y TP', f'{now_tp10:+.2f}%', f'主口径｜较加息前\n扩大 {tp10_expand:+.2f}pt', c_10),
    ('2Y-10Y\nTP10-TP2', f'{now_2s10:+.2f}%', '中间段信用/\n久期补偿抬升', c_2s10),
    ('10Y-30Y\nTP30-TP10', f'{now_10s30:+.2f}%', '超长端财政风险\n(30Y扩展示意)', c_10s30),
]
for i, (title, value, note, color) in enumerate(cards):
    x = 0.02 + i * 0.245
    ax_card.add_patch(mpatches.FancyBboxPatch(
        (x, 0.18), 0.23, 0.72, transform=ax_card.transAxes,
        boxstyle='round,pad=0.012,rounding_size=0.02',
        facecolor=color, edgecolor='none', alpha=0.92,
    ))
    ax_card.text(x + 0.115, 0.80, title, transform=ax_card.transAxes,
                 ha='center', va='top', fontsize=9, color='white', fontweight='bold')
    ax_card.text(x + 0.115, 0.52, value, transform=ax_card.transAxes,
                 ha='center', va='center', fontsize=15, color='#F6E27A', fontweight='bold')
    ax_card.text(x + 0.115, 0.26, note, transform=ax_card.transAxes,
                 ha='center', va='bottom', fontsize=8, color='white', linespacing=1.25)

ax_card.text(
    0.5, 0.04,
    f'9/16当日：2Y-10Y {s16_2s10:+.2f}%｜10Y-30Y {s16_10s30:+.2f}%；'
    f'加息前→现在：2s10 {pre_2s10:+.2f}→{now_2s10:+.2f}，10s30 {pre_10s30:+.2f}→{now_10s30:+.2f}',
    transform=ax_card.transAxes, ha='center', va='bottom',
    fontsize=9, fontweight='bold', color='#922b21',
)

# —— 下层：全样本 ——
ax_tp = fig.add_subplot(gs[1, :])
ax_def = ax_tp.twinx()

l10, = ax_tp.plot(df.index, df['ACM_TP_10Y'], color=c_10, lw=2.8, marker='o', markersize=4,
                  label='ACM 10Y TP (%)', zorder=6)
l2, = ax_tp.plot(df.index, df['ACM_TP_2Y'], color=c_2, lw=2.0, marker='o', markersize=3,
                 label='ACM 2Y TP (%)', zorder=5)
l210, = ax_tp.plot(df.index, df['TP_2S10'], color=c_2s10, lw=2.2, ls='-', marker='s', markersize=3,
                   label='2Y-10Y TP贡献 (=TP10-TP2)', zorder=5)
l1030, = ax_tp.plot(df.index, df['TP_10S30'], color=c_10s30, lw=2.2, ls='-', marker='^', markersize=3,
                    label='10Y-30Y TP贡献 (=TP30-TP10,扩展)', zorder=5)
lcn, = ax_tp.plot(df.index, df['CN_TERM_PREMIUM'], color=c_cn, lw=1.6, ls=':', marker='D',
                  markersize=3, alpha=0.85, label='中国 10Y TP 示意', zorder=3)

ax_tp.fill_between(df.index, df['ACM_TP_10Y'], 0,
                    where=df['ACM_TP_10Y'] >= 0, color=c_10, alpha=0.08, interpolate=True)
ax_tp.fill_between(df.index, df['ACM_TP_10Y'], 0,
                    where=df['ACM_TP_10Y'] < 0, color=c_2, alpha=0.08, interpolate=True)

ldef, = ax_def.plot(df.index, df['DEFICIT_GDP'], color=c_def, lw=1.5, ls='--',
                    alpha=0.7, label='美国 赤字/GDP (%)')

ax_tp.axhline(0, color='#666', lw=1.0, ls=':', alpha=0.8)
ax_tp.axvspan(pd.Timestamp('2026-09-10'), pd.Timestamp('2026-09-20'), color=c_10, alpha=0.10)
ax_tp.axvline(NODE_HIKE_2026, color=c_10, ls='-', lw=1.8, alpha=0.85)

for dt, lab, yoff, color in [
    (NODE_PRE, f'加息前\n10Y {pre_tp10:+.2f}\n2s10 {pre_2s10:+.2f}', -0.35, c_2),
    (NODE_HIKE_2026, f'9/16加息\n10Y↑ / 段差抬升', 0.18, c_10),
    (NODE_NOW, f'现在\n10Y {now_tp10:+.2f}\n2s10 {now_2s10:+.2f}\n10s30 {now_10s30:+.2f}',
     -0.42, '#922b21'),
]:
    y = v('ACM_TP_10Y', dt)
    ax_tp.annotate(
        lab, xy=(dt, y), xytext=(dt, y + yoff),
        fontsize=9, fontweight='bold', color='white', ha='center',
        arrowprops=dict(arrowstyle='->', color=color, lw=1.3),
        bbox=dict(boxstyle='round,pad=0.3', fc=color, ec='none', alpha=0.90),
        zorder=20,
    )

ax_tp.set_ylabel('期限溢价 / 段差 (%)', fontsize=12)
ax_def.set_ylabel('财政赤字 / GDP (%)', fontsize=11, color=c_def)
ax_def.tick_params(axis='y', labelcolor=c_def)
ax_tp.set_xlim(pd.Timestamp('2019-06-01'), pd.Timestamp('2027-03-01'))
ax_tp.set_ylim(-0.95, 1.45)
ax_def.set_ylim(0, 17)
ax_tp.grid(True, alpha=0.25)
ax_tp.set_title(
    '全样本：ACM 2Y/10Y + 2Y-10Y / 10Y-30Y 段差 vs 赤字（30Y 为扩展示意）',
    fontsize=12, pad=8,
)
ax_tp.legend(
    [l10, l2, l210, l1030, lcn, ldef],
    [x.get_label() for x in [l10, l2, l210, l1030, lcn, ldef]],
    loc='lower right', fontsize=8, framealpha=0.92, ncol=2,
)

# --- 3. 研判框 ---
analysis_text = (
    f"【研判｜ACM + 2Y-10Y / 10Y-30Y｜截止 {AS_OF_LABEL}】\n"
    f"■ 口径：ACM 2Y/10Y 为 NY Fed 主序列；2Y-10Y=TP10-TP2；\n"
    f"  10Y-30Y=TP30-TP10（30Y 扩展示意，非 ACM 官方）。\n"
    f"■ 现在：ACM10Y {now_tp10:+.2f}%｜ACM2Y {now_tp2:+.2f}%｜\n"
    f"  2Y-10Y {now_2s10:+.2f}%｜10Y-30Y {now_10s30:+.2f}%｜\n"
    f"  美10Y {us10y_now:.2f}%｜赤字 {us_def_now:.1f}%GDP｜债务 ${debt_now:.1f}T。\n"
    f"■ 9/16短窗：10Y {tp10_pre16:.2f}→{tp10_on16:.2f}→{tp10_post16:.2f}；\n"
    f"  段差同步上修 → 加息压不住中间段与超长端补偿。\n"
    f"■ 结构：2Y-10Y 扩大=曲线中段信用/久期补偿；\n"
    f"  10Y-30Y 为正且抬升=超长端财政主导/供给风险更重。\n"
    f"■ 结论：ACM10Y 从 {pre_tp10:+.2f}%→{now_tp10:+.2f}%（+{tp10_expand:.2f}pt），\n"
    f"  叠加两段差抬升 = 美债信用侵蚀的分段定价；中TP仍压在 {cn_tp_now:+.2f}%。"
)
ax_tp.text(
    0.012, 0.98, analysis_text, transform=ax_tp.transAxes, va='top', ha='left',
    fontsize=9.5, fontweight='bold', color='navy', zorder=100,
    bbox=dict(boxstyle='round,pad=0.45', fc='white', ec='navy', alpha=0.82),
)

fig.savefig(OUT_PATH, dpi=DPI, bbox_inches='tight', facecolor='white')
print(f'[saved] {OUT_PATH}')
plt.close(fig)

# --- 4. 终端 ---
print('\n' + '=' * 72)
print(f'美债 ACM TP｜2Y-10Y / 10Y-30Y｜截止 {AS_OF_LABEL}')
print('=' * 72)
print(f'  ACM 2Y TP     现在 {now_tp2:+.2f}%')
print(f'  ACM 10Y TP    加息前 {pre_tp10:+.2f}% → 现在 {now_tp10:+.2f}%（扩大 {tp10_expand:+.2f}pt）')
print(f'  2Y-10Y        加息前 {pre_2s10:+.2f}% → 9/16 {s16_2s10:+.2f}% → 现在 {now_2s10:+.2f}%')
print(f'  10Y-30Y(扩展) 加息前 {pre_10s30:+.2f}% → 9/16 {s16_10s30:+.2f}% → 现在 {now_10s30:+.2f}%')
print(f'  30Y TP示意    现在 {now_tp30:+.2f}%｜赤字 {us_def_now:.1f}%｜债务 ${debt_now:.1f}T')
print(f'  中TP {cn_tp_now:+.2f}%｜中赤字 {cn_def_now:.1f}%｜美中10Y利差≈{spread_now:.2f}%')
print('研判：ACM10Y 高位扩大 + 2Y-10Y/10Y-30Y 段差抬升 = 中间段与超长端共同定价美债信用侵蚀。')
print('=' * 72)
print(f'\n输出图片：{OUT_PATH}')
