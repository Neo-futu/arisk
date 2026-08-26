# tests

应用自带测试，CI 在 PR 阶段运行作为合入门槛（见 `.github/workflows/ci.yml`）。

- `test_handler.py` — 对 `app/handler.py` 的 pytest 单测。
- `conftest.py` — 把 `app/` 加入 `sys.path`（无需安装即可 import），固定 `APP_NAME`/`ENV`。
- `data/events.json` — 测试事件 fixtures（Function URL / REST API / 直接 invoke）。
- `requirements-dev.txt` — 测试依赖（pytest）。

本地运行：

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r tests/requirements-dev.txt
pytest tests/ -q
```
