"""
Test running code cells from notebooks/01_initial_data_exploration.ipynb
"""
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

nb_path = Path("notebooks/01_initial_data_exploration.ipynb")
with open(nb_path, "r", encoding="utf-8") as f:
    nb = json.load(f)

# Global execution namespace
globals_dict = {}

# Mock display function if not running inside IPython
def mock_display(*args):
    for a in args:
        if hasattr(a, 'to_string'):
            print(a.to_string())
        else:
            print(a)

globals_dict['display'] = mock_display

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
plt.show = lambda *args, **kwargs: None

cells = [c for c in nb['cells'] if c['cell_type'] == 'code']
print(f"Bắt đầu kiểm thử {len(cells)} code cells...")

for idx, cell in enumerate(cells, 1):
    code_str = "".join(cell['source'])
    print(f"--- [CELL {idx}/{len(cells)}] Đang thực thi...")
    try:
        exec(code_str, globals_dict)
        print(f"--- [CELL {idx}] THÀNH CÔNG (PASS)")
    except Exception as e:
        print(f"--- [CELL {idx}] LỖI (FAIL): {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

print("\n=== TOÀN BỘ CODE CELLS ĐÃ CHẠY HOÀN TẤT VỚI 0 LỖI (ZERO EXCEPTION) ===")
