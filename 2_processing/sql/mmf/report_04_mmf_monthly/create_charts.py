"""
create_charts.py — 生成月報圖表 PNG（仿 PDF Page 2 格式）
用法：python create_charts.py --all

輸出：
  pie_chart_{date}_{fund}.png  — 資產類別分佈（寬幅橫向，仿 PDF）
  bar_chart_{date}_{fund}.png  — 到期日分佈（寬幅橫向，仿 PDF）
"""
import sys, os, json, argparse
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path

BASE_DIR   = Path(__file__).parent
OUTPUT_DIR = BASE_DIR.parent / 'output' / 'report_04_mmf_monthly'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

try:
    import matplotlib; matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.font_manager as fm
    import matplotlib.patches as mpatches
    import numpy as np
    for _fp in ['C:/Windows/Fonts/msyh.ttc', 'C:/Windows/Fonts/simhei.ttf']:
        if os.path.exists(_fp):
            plt.rcParams.update({
                'font.family':      [fm.FontProperties(fname=_fp).get_name(), 'sans-serif'],
                'axes.unicode_minus': False,
            }); break
except ImportError:
    print('pip install matplotlib numpy'); sys.exit(1)

# 品牌色系（與 PDF 一致）
COLORS = ['#2E75B6','#70AD47','#ED7D31','#FFC000',
          '#5B9BD5','#7030A0','#FF0000','#00B0F0']


def generate_pie_chart(labels, values, out_path: Path, dpi=180):
    """
    資產類別分佈圓餅圖
    仿 PDF Page 2 格式：餅圖居中，圖例在右側兩列，寬幅橫向
    圖片尺寸：W≈9.7cm（275pt）× H≈7cm，對應 PDF 嵌入比例
    """
    fig, (ax, ax_leg) = plt.subplots(1, 2, figsize=(6.8, 3.5),
                                      gridspec_kw={'width_ratios': [1.2, 1]})
    colors = COLORS[:len(values)]

    # 餅圖（僅顯示 ≥3% 的百分比標籤）
    wedges, _, autotexts = ax.pie(
        values,
        labels=None,
        colors=colors,
        autopct=lambda p: f'{p:.1f}%' if p >= 3 else '',
        startangle=90,
        pctdistance=0.70,
        wedgeprops={'linewidth': 0.5, 'edgecolor': 'white'},
    )
    for at in autotexts:
        at.set_fontsize(8.5)
        at.set_fontweight('bold')
        at.set_color('white')
    ax.set_aspect('equal')
    ax.axis('off')

    # 圖例（右側，仿 PDF 格式）
    ax_leg.axis('off')
    handles = [mpatches.Patch(color=c, label=f'{l}  {v:.1f}%')
               for c, l, v in zip(colors, labels, values)]
    ax_leg.legend(
        handles=handles,
        loc='center left',
        fontsize=8,
        frameon=False,
        handlelength=1.2,
        handletextpad=0.5,
        borderpad=0,
        labelspacing=0.5,
    )

    plt.tight_layout(pad=0.3)
    fig.savefig(str(out_path), format='png', bbox_inches='tight',
                dpi=dpi, facecolor='white')
    plt.close(fig)
    print(f'  ✅ 餅圖：{out_path.name}')
    return out_path


def generate_bar_chart(labels, values, out_path: Path, dpi=180):
    """
    到期日分佈柱狀圖
    仿 PDF Page 2 格式：垂直柱狀，X軸標籤傾斜，寬幅橫向
    """
    fig, ax = plt.subplots(figsize=(6.8, 2.8))

    colors = ['#2E75B6' if v > 0 else '#CCCCCC' for v in values]
    bars = ax.bar(range(len(labels)), values, color=colors,
                  width=0.6, edgecolor='white', linewidth=0.5)

    # 數值標籤
    for bar, v in zip(bars, values):
        if v >= 0.5:
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + 0.4,
                    f'{v:.1f}%',
                    ha='center', va='bottom',
                    fontsize=8, fontweight='bold', color='#333333')

    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=8.5, rotation=25, ha='right')
    ax.set_ylabel('%', fontsize=9, color='#555555')
    ax.yaxis.set_tick_params(labelsize=8.5, colors='#555555')
    ax.set_ylim(0, max(values) * 1.3 if values else 100)

    # 樣式（仿 PDF 簡潔風格）
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color('#CCCCCC')
    ax.spines['bottom'].set_color('#CCCCCC')
    ax.yaxis.grid(True, linestyle='--', alpha=0.4, color='#CCCCCC')
    ax.set_axisbelow(True)
    ax.tick_params(left=False)

    plt.tight_layout(pad=0.4)
    fig.savefig(str(out_path), format='png', bbox_inches='tight',
                dpi=dpi, facecolor='white')
    plt.close(fig)
    print(f'  ✅ 柱狀圖：{out_path.name}')
    return out_path


def process(json_path: Path):
    data = json.load(open(json_path, encoding='utf-8'))
    ev_s = data['eval_date'].replace('-', '')
    safe = data['fund_name'].replace('/', '-').replace(' ', '_')

    alloc = data.get('asset_allocation', [])
    mat   = data.get('maturity_dist', [])
    results = {}

    if alloc:
        pie_path = OUTPUT_DIR / f'pie_chart_{ev_s}_{safe}.png'
        generate_pie_chart([a['label'] for a in alloc],
                           [a['pct_of_nav'] for a in alloc], pie_path)
        results['pie'] = pie_path

    if mat:
        bar_path = OUTPUT_DIR / f'bar_chart_{ev_s}_{safe}.png'
        generate_bar_chart([m['bucket'] for m in mat],
                           [m['pct_of_nav'] for m in mat], bar_path)
        results['bar'] = bar_path

    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', default=None)
    ap.add_argument('--all',  action='store_true')
    args = ap.parse_args()

    if args.data:
        json_files = [Path(args.data)]
    elif args.all:
        json_files = sorted(OUTPUT_DIR.glob('outputdata_*.json'))
    else:
        json_files = sorted(OUTPUT_DIR.glob('outputdata_*.json'))
        json_files = [json_files[-1]] if json_files else []

    if not json_files:
        print('✗ 找不到 outputdata 文件'); return
    print('[create_charts] 生成圖表')
    for jf in json_files:
        print(f'\n  基金：{jf.stem}')
        process(jf)

if __name__ == '__main__':
    main()
