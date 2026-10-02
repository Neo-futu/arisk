import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import matplotlib
from pathlib import Path

# --- 0. 环境配置：解决中文与负号 ---
matplotlib.rcParams['font.family'] = ['sans-serif']
matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans', 'Microsoft YaHei', 'STHeiti', 'Arial']
matplotlib.rcParams['axes.unicode_minus'] = False

# --- 数据截止 ---
AS_OF_DATE = '2026-09-24'
AS_OF_LABEL = '2026-09-24 美股/美债/外汇收盘'

# --- 1. 核心数据库 (1920-2026.09.24｜百年变局：前看约百年) ---
# 节点为同期代表性水平；EURUSD 在 1999 前为 DEM/ECU 合成近似
# 2026-09-24：SPX 7704.13；WTI ≈94.50；Fed 3.75–4.00%；美债10Y 5.160%；EURUSD 1.1379
macro_data = {
    'DATE': [
        # —— 1920-1969：大萧条 / 二战 / 战后秩序 ——
        '1920-01-01', '1929-09-03', '1932-06-01', '1939-09-01', '1945-08-15',
        '1950-06-01', '1960-01-01', '1966-02-01',
        # —— 1970 以降（原序列） ——
        '1970-01-01', '1973-10-15', '1974-07-01', '1979-01-01', '1981-06-01',
        '1982-12-01', '1987-10-19', '1992-09-01', '1997-07-01', '1998-08-31',
        '2000-03-10', '2003-06-01', '2007-10-01', '2008-09-15', '2008-12-31',
        '2011-12-31', '2013-05-22', '2015-12-31', '2019-12-31', '2020-04-01',
        '2022-03-16', '2022-12-31', '2023-12-31', '2024-01-01', '2024-12-31',
        '2025-12-31', '2026-03-31', '2026-09-24'
    ],
    'SP500': [
        9.0, 31.3, 4.4, 12.0, 15.5,
        18.0, 58.0, 93.0,
        92, 107, 70, 105, 132, 140, 330, 410, 950, 950,
        1527, 980, 1565, 900, 903.25, 1257.60, 1650, 2043.94, 3230.78, 2800,
        4400, 3839.50, 4769.83, 5000, 5881.63, 6845.50, 6343.00, 7704.13
    ],
    'OIL': [
        3.07, 1.27, 0.65, 1.02, 1.22,
        2.51, 2.88, 2.97,
        3.35, 3.56, 11.58, 15.00, 37.00, 30.00, 20.00, 20.00, 19.00, 12.00,
        30.00, 30.00, 95.00, 40.00, 44.60, 98.83, 95.00, 37.04, 55.17, 20.00,
        105.0, 80.26, 71.65, 75.0, 68.00, 57.42, 102.81, 94.50
    ],
    'FED_RATE': [
        7.0, 5.0, 2.5, 1.0, 0.5,
        1.5, 3.0, 4.5,
        8.9, 10.7, 12.9, 10.0, 19.1, 8.5, 7.2, 3.0, 5.5, 5.5,
        6.5, 1.0, 5.25, 0.15, 0.12, 0.00, 0.15, 0.15, 1.50, 0.05,
        0.25, 4.26, 5.18, 5.33, 5.24, 4.25, 3.75, 4.00
    ],
    'US10Y': [
        5.40, 3.60, 3.70, 2.40, 2.00,
        2.30, 4.10, 4.60,
        7.80, 7.00, 8.00, 9.10, 14.00, 10.50, 9.50, 6.40, 6.30, 5.30,
        6.20, 3.30, 4.50, 3.50, 2.25, 1.89, 2.02, 2.27, 1.92, 0.62,
        2.19, 3.88, 3.88, 3.95, 4.58, 4.20, 3.95, 5.160
    ],
    # EURUSD：1999 前为 DEM/ECU 合成近似（1920s 德马克紊乱期为示意衔接）
    'EURUSD': [
        0.55, 0.70, 0.85, 0.88, 0.90,
        0.95, 1.05, 1.00,
        0.95, 1.20, 1.25, 1.35, 0.90, 0.95, 1.15, 1.30, 1.10, 1.15,
        0.96, 1.17, 1.42, 1.40, 1.40, 1.30, 1.30, 1.09, 1.12, 1.09,
        1.10, 1.07, 1.10, 1.10, 1.035, 1.08, 1.09, 1.1379
    ]
}

ASSET_COLS = ['SP500', 'OIL', 'FED_RATE', 'US10Y', 'EURUSD']

df = pd.DataFrame(macro_data)
df['DATE'] = pd.to_datetime(df['DATE'])
df = df.sort_values('DATE').set_index('DATE')

AS_OF = pd.Timestamp(AS_OF_DATE)
# 后100年 = 以 AS_OF 为镜面，将前史路径时间对称映射（取值不变，时间轴对折）
hist = df.loc[:AS_OF]
mirror_idx = AS_OF + (AS_OF - hist.index)
df_mirror = hist.copy()
df_mirror.index = mirror_idx
df_mirror = df_mirror.sort_index()
df_mirror = df_mirror.loc[df_mirror.index > AS_OF]

returns = df[ASSET_COLS].pct_change().dropna()

# --- 2. 绘图：5 纵轴（左 1 + 右 4），五项大类同区对照 ---
fig, ax_sp = plt.subplots(figsize=(24, 12))
plt.subplots_adjust(right=0.72, top=0.90, left=0.08)

ax_oil = ax_sp.twinx()
ax_fed = ax_sp.twinx()
ax_10y = ax_sp.twinx()
ax_fx = ax_sp.twinx()

ax_fed.spines['right'].set_position(('outward', 55))
ax_10y.spines['right'].set_position(('outward', 110))
ax_fx.spines['right'].set_position(('outward', 165))

c_sp, c_oil, c_fed, c_10y, c_fx = '#1f77b4', '#8c564b', '#d62728', '#9467bd', '#2ca02c'

l1, = ax_sp.plot(df.index, df['SP500'], color=c_sp, lw=2.8, marker='o', markersize=4, label='标普500', zorder=3, alpha=1.0)
l2, = ax_oil.plot(df.index, df['OIL'], color=c_oil, lw=1.6, marker='s', markersize=3, alpha=0.32, label='WTI原油 ($/bbl)', zorder=2)
l3, = ax_fed.plot(df.index, df['FED_RATE'], color=c_fed, lw=1.6, marker='^', markersize=3, alpha=0.32, label='联邦基金利率 (%)', zorder=2)
l4, = ax_10y.plot(df.index, df['US10Y'], color=c_10y, lw=1.7, marker='D', markersize=3, alpha=0.32, label='美债10年收益率 (%)', zorder=2)
l5, = ax_fx.plot(df.index, df['EURUSD'], color=c_fx, lw=1.7, marker='v', markersize=3, alpha=0.32, label='EURUSD', zorder=2)

# 镜像未来（虚线）：衔接到 AS_OF 实点，再沿对折路径延伸
mirror_bridge = pd.concat([hist.iloc[[-1]], df_mirror])
ax_sp.plot(mirror_bridge.index, mirror_bridge['SP500'], color=c_sp, lw=2.2, ls='--', marker='o', markersize=3, alpha=0.85, zorder=3)
ax_oil.plot(mirror_bridge.index, mirror_bridge['OIL'], color=c_oil, lw=1.4, ls='--', marker='s', markersize=2, alpha=0.22, zorder=2)
ax_fed.plot(mirror_bridge.index, mirror_bridge['FED_RATE'], color=c_fed, lw=1.4, ls='--', marker='^', markersize=2, alpha=0.22, zorder=2)
ax_10y.plot(mirror_bridge.index, mirror_bridge['US10Y'], color=c_10y, lw=1.5, ls='--', marker='D', markersize=2, alpha=0.22, zorder=2)
ax_fx.plot(mirror_bridge.index, mirror_bridge['EURUSD'], color=c_fx, lw=1.5, ls='--', marker='v', markersize=2, alpha=0.22, zorder=2)
l_mirror = matplotlib.lines.Line2D([0], [0], color='#555555', lw=2.0, ls='--', label='虚拟现实(虚线)')

# 双轴默认白底会盖住下层内容：各轴背景透明，曲线可透视；文字框半透明置顶
for ax in (ax_sp, ax_oil, ax_fed, ax_10y, ax_fx):
    ax.patch.set_visible(False)
fig.patch.set_facecolor('white')

ax_sp.axvline(AS_OF, color='#888888', ls=':', lw=1.5, alpha=0.7, zorder=3)
ax_sp.text(
    AS_OF, 0.02, '今天', transform=ax_sp.get_xaxis_transform(),
    ha='center', va='bottom', fontsize=10, color='#444',
    bbox=dict(boxstyle='round,pad=0.2', fc='white', ec='#888', alpha=0.55),
    zorder=100,
)

ax_sp.set_ylabel('标普500', color=c_sp, fontsize=11)
ax_oil.set_ylabel('WTI ($/bbl)', color=c_oil, fontsize=11)
ax_fed.set_ylabel('Fed (%)', color=c_fed, fontsize=11)
ax_10y.set_ylabel('美债10Y (%)', color=c_10y, fontsize=11)
ax_fx.set_ylabel('EURUSD', color=c_fx, fontsize=11)

for ax, color in (
    (ax_sp, c_sp), (ax_oil, c_oil), (ax_fed, c_fed), (ax_10y, c_10y), (ax_fx, c_fx)
):
    ax.tick_params(axis='y', labelcolor=color)
    if ax is ax_sp:
        ax.spines['left'].set_color(color)
    else:
        ax.spines['right'].set_color(color)

# --- 2b. 以美债10Y 当前分位（向上取整）对齐标注另外 4 项；分位样本自 2000 年起 ---
fmt = {
    'SP500': lambda v: f'{v:.0f}',
    'OIL': lambda v: f'{v:.2f}',
    'FED_RATE': lambda v: f'{v:.2f}',
    'US10Y': lambda v: f'{v:.3f}',
    'EURUSD': lambda v: f'{v:.4f}',
}
df_pct = df.loc['2000-01-01':]
us10y_now = float(df['US10Y'].iloc[-1])
# 经验分位：≤ 当前值的样本占比 × 100（仅 2000+）
us10y_pct_raw = float((df_pct['US10Y'] <= us10y_now).mean() * 100)
us10y_pct = int(np.ceil(us10y_pct_raw))
us10y_pct = min(max(us10y_pct, 1), 100)
q_level = us10y_pct / 100.0

# 美债10Y 轴：标注当前值与分位
ax_10y.annotate(
    f'美债10Y 当前\n{fmt["US10Y"](us10y_now)}\n第{us10y_pct}分位(2000+)',
    xy=(1, us10y_now),
    xycoords=('axes fraction', 'data'),
    xytext=(125, 0),
    textcoords='offset points',
    ha='left', va='center',
    fontsize=8, fontweight='bold', color=c_10y, clip_on=False, zorder=100,
    arrowprops=dict(arrowstyle='-', color=c_10y, lw=1.0),
    bbox=dict(boxstyle='round,pad=0.25', fc='white', ec=c_10y, alpha=0.55),
)
ticks_10y = list(ax_10y.get_yticks()) + [us10y_now]
ax_10y.set_yticks(sorted({round(t, 6) for t in ticks_10y if np.isfinite(t)}))

# 另外 4 项：取同一整数分位上的数值（2000+ 样本）
aligned = {
    col: float(df_pct[col].quantile(q_level))
    for col in ('SP500', 'OIL', 'FED_RATE', 'EURUSD')
}
align_axes = [
    (ax_sp, 'SP500', '标普500', c_sp, -14),
    (ax_oil, 'OIL', 'WTI', c_oil, 14),
    (ax_fed, 'FED_RATE', 'Fed', c_fed, 70),
    (ax_fx, 'EURUSD', 'EURUSD', c_fx, 180),
]
for ax, col, name, color, x_offset in align_axes:
    q = aligned[col]
    ax.annotate(
        f'{name} 第{us10y_pct}分位\n{fmt[col](q)}',
        xy=(0 if x_offset < 0 else 1, q),
        xycoords=('axes fraction', 'data'),
        xytext=(x_offset, 0),
        textcoords='offset points',
        ha='right' if x_offset < 0 else 'left',
        va='center',
        fontsize=8, fontweight='bold', color=color, clip_on=False, zorder=100,
        arrowprops=dict(arrowstyle='-', color=color, lw=1.0),
        bbox=dict(boxstyle='round,pad=0.25', fc='white', ec=color, alpha=0.55),
    )
    ticks = list(ax.get_yticks()) + [q]
    ax.set_yticks(sorted({round(t, 6) for t in ticks if np.isfinite(t)}))

# --- 3. 左上研判 ---
analysis_text = (
    f"【风险研判｜百年变局｜数据截止 {AS_OF_LABEL}】\n"
    "■ 视窗：前看约百年（1920—）· 后看约百年（—2126，虚拟未来/虚线）。\n"
    "■ 数据锚点：SPX 7704 / WTI $94.5 / Fed 3.75–4.00% /\n"
    f"  美债10Y 5.160%（2000+第{us10y_pct}分位，原始{us10y_pct_raw:.1f}%↑取整） / EURUSD 1.1379。\n"
    "■ 美元：10Y 收于 5.160%（2007.07 以来收盘新高）+ Fed 重启加息，\n"
    "  压制欧元；地缘溢价与长端重定价并行。\n"
    "■ 研判：对照大萧条→滞胀→金融危机→再通胀链条，当前更近\n"
    "  “能源冲击 + 股指韧性 + 长端重定价”；若油价站稳 $100 且 10Y 维持 5%+，\n"
    "  风险溢价更易二次重估。虚线仅为情景，非预测。"
)
ax_sp.text(0.02, 0.97, analysis_text, transform=ax_sp.transAxes, verticalalignment='top',
           bbox=dict(boxstyle='round,pad=0.5', fc='white', ec='navy', alpha=0.62),
           fontsize=11, fontweight='bold', color='navy', zorder=100)

# --- 4. 全部事件标注画在 SPX 轴（最前），半透明底，其他四条曲线可透视 ---
events = [
    ('1929-09-03', '大萧条', 'SP500', 8, 1200, 'black'),
    ('1945-08-15', '二战结束', 'SP500', 12, 0, c_sp),
    ('1973-10-15', '石油禁运', 'OIL', 15, 0, c_oil),
    ('1981-06-01', '沃尔克巅峰', 'FED_RATE', 2.2, 2200, c_fed),
    ('1997-07-01', '亚洲金融危机', 'OIL', -12, 0, c_oil),
    ('2000-03-10', '科网泡沫', 'SP500', 300, 0, c_sp),
    ('2008-09-15', '雷曼倒闭/08危机', 'SP500', -800, 0, 'black'),
    ('2013-05-22', '削减恐慌(Taper)', 'FED_RATE', 1.2, 0, c_fed),
    ('2022-03-16', '乌克兰危机/加息开启', 'OIL', 15, 0, c_oil),
    ('2024-01-01', 'AI 科技狂涨', 'SP500', 600, 0, c_sp),
]

future_event_map = {
    '1929-09-03': '人类移居火星',
    '1945-08-15': 'AI统治地球',
    '1973-10-15': '伊朗核武器成功',
    '1981-06-01': '访问火星',
    '1997-07-01': '韩国金融危机',
    '2000-03-10': '人脑连接网络',
    '2008-09-15': '英特尔倒闭',
    '2013-05-22': '美债危机',
    '2022-03-16': ('台海统一', 0, 3200),
    '2024-01-01': ('AI开启灭亡人类', -900, 2800),
}

axis_for = {
    'SP500': ax_sp,
    'OIL': ax_oil,
    'FED_RATE': ax_fed,
    'US10Y': ax_10y,
    'EURUSD': ax_fx,
}

Z_FRONT = 100
# 先定横轴，再映射坐标，保证标注落在 SPX 图层最前
x_right = max(pd.Timestamp('2126-12-31'), df_mirror.index.max() + pd.Timedelta(days=400))
ax_sp.set_xlim(pd.Timestamp('1920-01-01'), x_right)
for ax in (ax_oil, ax_fed, ax_10y, ax_fx):
    ax.set_zorder(1)
ax_sp.set_zorder(5)
fig.canvas.draw()


def to_sp_xy(src_ax, x, y):
    """把其他轴上的 (时间, 数值) 映射到 SPX 轴数据坐标，箭头仍对准原曲线。"""
    xnum = matplotlib.dates.date2num(pd.Timestamp(x))
    disp = src_ax.transData.transform((xnum, float(y)))
    return ax_sp.transData.inverted().transform(disp)


# --- 3b. Gemini 中秋图（略下移）+ 右上淡黄色弯月 ---
_midautumn_img = Path(__file__).resolve().parent / 'Gemini_Generated_Image_1fu6eb1fu6eb1fu6.jpg'
if _midautumn_img.is_file():
    _img = plt.imread(_midautumn_img)
    _ih, _iw = _img.shape[0], _img.shape[1]
    _box_w = 0.34
    _pos = ax_sp.get_position()
    _axes_disp_aspect = (_pos.width * fig.get_figwidth()) / (_pos.height * fig.get_figheight())
    _box_h = _box_w * (_ih / _iw) * _axes_disp_aspect
    # 以 WTI≈80 为基准再略下移
    _x_ref = matplotlib.dates.date2num(pd.Timestamp('2090-01-01'))
    _disp = ax_oil.transData.transform((_x_ref, 80.0))
    _, _y_frac = ax_sp.transAxes.inverted().transform(_disp)
    _y_frac = float(_y_frac) - 0.07
    _left = 0.64
    _bottom = float(np.clip(_y_frac - _box_h / 2, 0.02, 0.98 - _box_h))
    moon_ax = ax_sp.inset_axes([_left, _bottom, _box_w, _box_h])
    moon_ax.imshow(_img, aspect='equal', zorder=1)
    moon_ax.axis('off')
    moon_ax.set_zorder(110)
    for spine in moon_ax.spines.values():
        spine.set_visible(True)
        spine.set_color('#E8C547')
        spine.set_linewidth(1.2)
else:
    moon_ax = ax_sp.inset_axes([0.70, 0.40, 0.24, 0.20])
    moon_ax.axis('off')
    moon_ax.text(0.5, 0.5, '中秋快乐', ha='center', va='center', fontsize=14,
                 fontweight='bold', color='#8B6914', transform=moon_ax.transAxes)

# 右上角淡黄色弯月（天涯明月刀意象）
crescent_ax = ax_sp.inset_axes([0.86, 0.78, 0.12, 0.18])
crescent_ax.set_xlim(0, 1)
crescent_ax.set_ylim(0, 1)
crescent_ax.axis('off')
crescent_ax.set_zorder(112)
crescent_ax.add_patch(plt.Circle((0.48, 0.52), 0.32, color='#F6E27A', ec='#E8C547', lw=1.5, zorder=1))
crescent_ax.add_patch(plt.Circle((0.64, 0.58), 0.28, color='white', ec='none', zorder=2, alpha=0.95))


for date_str, label, col, y_offset, x_days, bg_color in events:
    dt = pd.to_datetime(date_str)
    idx_pos = df.index.get_indexer([dt], method='nearest')[0]
    y_val = float(df.iloc[idx_pos][col])
    src_ax = axis_for[col]
    text_dt = dt + pd.Timedelta(days=int(x_days))
    xy = to_sp_xy(src_ax, dt, y_val)
    xy_text = to_sp_xy(src_ax, text_dt, y_val + y_offset)
    ax_sp.annotate(
        label, xy=xy, xytext=xy_text,
        arrowprops=dict(arrowstyle='->', color=bg_color, lw=1.6, alpha=0.95),
        fontsize=12, fontweight='bold', color='white', ha='center',
        bbox=dict(boxstyle="round,pad=0.35", fc=bg_color, ec="none", alpha=0.88),
        zorder=Z_FRONT, clip_on=False,
    )
    f_entry = future_event_map.get(date_str)
    if not f_entry:
        continue
    if isinstance(f_entry, tuple):
        f_label, f_y_extra, f_x_extra = f_entry
    else:
        f_label, f_y_extra, f_x_extra = f_entry, 0, 0
    f_dt = AS_OF + (AS_OF - dt)
    if f_dt <= AS_OF:
        continue
    f_text_dt = f_dt + pd.Timedelta(days=int(x_days + f_x_extra))
    f_xy = to_sp_xy(src_ax, f_dt, y_val)
    f_xy_text = to_sp_xy(src_ax, f_text_dt, y_val + y_offset + f_y_extra)
    ax_sp.annotate(
        f_label, xy=f_xy, xytext=f_xy_text,
        arrowprops=dict(arrowstyle='->', color=bg_color, lw=1.3, ls='--', alpha=0.9),
        fontsize=11, fontweight='bold', color=bg_color, ha='center',
        bbox=dict(boxstyle="round,pad=0.35", fc='white', ec=bg_color, ls='--', alpha=0.82),
        zorder=Z_FRONT, clip_on=False,
    )

ax_sp.set_title(
    '全球宏观资产跨周期图谱 (1920 - 2126)\n前看一百年 · 后看一百年',
    fontsize=22, pad=18
)
leg = ax_sp.legend(
    [l1, l2, l3, l4, l5, l_mirror],
    [l.get_label() for l in [l1, l2, l3, l4, l5, l_mirror]],
    loc='upper left', bbox_to_anchor=(0.02, 0.48), framealpha=0.45
)
leg.set_zorder(100)
ax_sp.grid(True, axis='both', alpha=0.2)
plt.show()

# --- 5. 分段相关性矩阵分析 (Regime Analysis) ---
def print_regime_corr(title, start_date, end_date):
    subset = returns.loc[start_date:end_date]
    print(f"\n>>> {title} ({start_date} 至 {end_date})")
    print("-" * 50)
    print(subset.corr().round(4))

print("\n" + "=" * 60)
print("资产变化率分段相关性矩阵分析")
print(f"数据截止：{AS_OF_LABEL}｜样本视窗 1920—（展望至 2126）")
print("=" * 60)

print_regime_corr("大萧条模式 (需求崩塌)", '1929-01-01', '1939-12-31')
print_regime_corr("1970s 滞胀模式 (供给冲击)", '1970-01-01', '1982-12-31')
print_regime_corr("2008 金融危机模式 (需求崩塌)", '2007-01-01', '2009-12-31')
print_regime_corr("当前再通胀/地缘溢价模式", '2022-01-01', AS_OF_DATE)

print("\n[研判提示]: ")
print(f"数据截止 {AS_OF_DATE}｜前看百年自 1920，后看百年至 2126")
print("股指自 3 月低点大幅修复并逼近高位；WTI 自 $102+ 回落至约 $94.5，地缘溢价仍高波动；")
print("Fed 目标区间 3.75–4.00%；美债10Y 5.160%（2007.07 以来收盘新高）；EURUSD 1.1379（美元偏强承压）。")
print("观察窗口：油价再站稳 $100 + 10Y 维持 5%+ + EURUSD 失守关键支撑 + OIL/SP500 转负相关时，")
print("风险溢价更易二次重估。")
