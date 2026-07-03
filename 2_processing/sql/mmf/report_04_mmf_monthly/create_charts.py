"""
create_charts.py — 從 outputdata.json 生成圖表 PNG 文件
用法：python create_charts.py --data outputdata_20260625_博匯港元貨幣市場基金I.json

輸出（與 Word/PDF 同目錄）：
  pie_chart_YYYYMMDD_{fund}.png   — 資產類別分佈圓餅圖
  bar_chart_YYYYMMDD_{fund}.png   — 到期日分佈柱狀圖
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
    # 設置中文字型
    for _fp in ['C:/Windows/Fonts/msyh.ttc', 'C:/Windows/Fonts/simhei.ttf',
                'C:/Windows/Fonts/simsun.ttc']:
        if os.path.exists(_fp):
            plt.rcParams.update({
                'font.family':      [fm.FontProperties(fname=_fp).get_name(), 'sans-serif'],
                'axes.unicode_minus': False,
                'font.size':        9,
            })
            break
except ImportError:
    print('pip install matplotlib'); sys.exit(1)

# 品牌色系
PIE_COLORS = ['#2E75B6', '#70AD47', '#ED7D31', '#FFC000',
              '#5B9BD5', '#7030A0', '#FF0000', '#00B0F0']
BAR_COLOR  = '#2E75B6'


def generate_pie_chart(labels, values, out_path: Path, width_cm=9.8, height_cm=7.0, dpi=150):
    """資產配置圓餅圖（仿 ChinaAMC Factsheet 格式）"""
    fig, ax = plt.subplots(figsize=(width_cm / 2.54, height_cm / 2.54), dpi=dpi)
    colors = PIE_COLORS[:len(values)]
    wedges, _, autotexts = ax.pie(
        values, labels=None, colors=colors,
        autopct=lambda p: f'{p:.1f}%' if p >= 2.5 else '',
        startangle=90, pctdistance=0.72,
        wedgeprops={'linewidth': 0.5, 'edgecolor': 'white'})
    for at in autotexts:
        at.set_fontsize(8); at.set_fontweight('bold')
    ax.legend(
        wedges,
        [f'{l}  {v:.1f}%' for l, v in zip(labels, values)],
        loc='lower center',
        bbox_to_anchor=(0.5, -0.32),
        ncol=2,
        fontsize=7.5,
        frameon=False,
        handlelength=1.0,
        handletextpad=0.4,
        columnspacing=1.0,
    )
    ax.set_aspect('equal')
    plt.tight_layout(pad=0.2)
    plt.savefig(str(out_path), format='png', bbox_inches='tight',
                dpi=dpi, facecolor='white')
    plt.close()
    print(f'  ✅ 餅圖：{out_path.name}')
    return out_path


def generate_bar_chart(labels, values, out_path: Path, width_cm=9.8, height_cm=5.5, dpi=150):
    """到期日分佈柱狀圖（仿 ChinaAMC Factsheet 格式）"""
    fig, ax = plt.subplots(figsize=(width_cm / 2.54, height_cm / 2.54), dpi=dpi)
    x = range(len(labels))
    bars = ax.bar(x, values, color=BAR_COLOR, width=0.6, edgecolor='white')
    for bar, v in zip(bars, values):
        if v > 0.5:
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + 0.3,
                    f'{v:.1f}%', ha='center', va='bottom',
                    fontsize=7.5, fontweight='bold')
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, fontsize=8, rotation=30, ha='right')
    ax.set_ylabel('%', fontsize=8.5)
    ax.yaxis.set_tick_params(labelsize=8)
    ax.set_ylim(0, max(values) * 1.28 if values else 100)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color('#CCCCCC')
    ax.spines['bottom'].set_color('#CCCCCC')
    ax.yaxis.grid(True, linestyle='--', alpha=0.5, color='#CCCCCC')
    ax.set_axisbelow(True)
    plt.tight_layout(pad=0.3)
    plt.savefig(str(out_path), format='png', bbox_inches='tight',
                dpi=dpi, facecolor='white')
    plt.close()
    print(f'  ✅ 柱狀圖：{out_path.name}')
    return out_path


def process(json_path: Path):
    data  = json.load(open(json_path, encoding='utf-8'))
    ev_s  = data['eval_date'].replace('-', '')
    safe  = data['fund_name'].replace('/', '-').replace(' ', '_')

    alloc = data.get('asset_allocation', [])
    mat   = data.get('maturity_dist', [])

    results = {}
    if alloc:
        pie_path = OUTPUT_DIR / f'pie_chart_{ev_s}_{safe}.png'
        generate_pie_chart(
            [a['label'] for a in alloc],
            [a['pct_of_nav'] for a in alloc],
            pie_path)
        results['pie'] = pie_path
    else:
        print('  ⚠ 無資產配置數據，跳過餅圖')

    if mat:
        bar_path = OUTPUT_DIR / f'bar_chart_{ev_s}_{safe}.png'
        generate_bar_chart(
            [m['bucket'] for m in mat],
            [m['pct_of_nav'] for m in mat],
            bar_path)
        results['bar'] = bar_path
    else:
        print('  ⚠ 無到期分佈數據，跳過柱狀圖')

    return results


def main():
    ap = argparse.ArgumentParser(description='生成月報圖表 PNG')
    ap.add_argument('--data', default=None,  help='outputdata JSON 文件路徑')
    ap.add_argument('--all',  action='store_true', help='處理 output 目錄中所有 outputdata 文件')
    args = ap.parse_args()

    if args.data:
        json_files = [Path(args.data)]
    elif args.all:
        json_files = sorted(OUTPUT_DIR.glob('outputdata_*.json'))
    else:
        json_files = sorted(OUTPUT_DIR.glob('outputdata_*.json'))
        json_files = [json_files[-1]] if json_files else []

    if not json_files:
        print('✗ 找不到 outputdata 文件，請先執行 extract_data.py'); return

    print(f'[create_charts] 生成圖表 PNG')
    for jf in json_files:
        print(f'\n  基金：{jf.stem}')
        process(jf)


if __name__ == '__main__':
    main()
