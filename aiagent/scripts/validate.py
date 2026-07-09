"""
aiagent/scripts/validate.py — Agent 輸出結構校驗工具

整合自 claude-risk-agent/scripts/validate.py。
用於校驗 CMA worker（子 Agent）的結構化 JSON 輸出是否符合 cookbook 中
定義的 output_schema。

用法：
  python aiagent/scripts/validate.py <output.json> <schema.json|schema.yaml>
  python aiagent/scripts/validate.py out/risk-report.json cookbooks/risk-agent/subagents/report-writer.yaml
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def load_schema(path: Path) -> dict:
    """從 YAML agent 文件或 JSON schema 文件讀取 output_schema。"""
    text = path.read_text(encoding="utf-8")
    if path.suffix in (".yaml", ".yml"):
        try:
            import yaml
            data = yaml.safe_load(text)
            return data.get("output_schema", data)
        except ImportError:
            print("pip install pyyaml")
            sys.exit(2)
    return json.loads(text)


def validate(output_path: Path, schema_path: Path) -> bool:
    try:
        import jsonschema
    except ImportError:
        print("pip install jsonschema")
        sys.exit(2)

    output = json.loads(output_path.read_text(encoding="utf-8"))
    schema = load_schema(schema_path)

    try:
        jsonschema.validate(instance=output, schema=schema)
        print(f"✓ {output_path.name} 符合 schema {schema_path.name}")
        return True
    except jsonschema.ValidationError as e:
        print(f"✗ 校驗失敗：{e.message}")
        print(f"  路徑：{' -> '.join(str(p) for p in e.path)}")
        return False


def main() -> None:
    if len(sys.argv) != 3:
        print("用法：validate.py <output.json> <schema.json|agent.yaml>")
        sys.exit(2)

    output_path = Path(sys.argv[1])
    schema_path = Path(sys.argv[2])

    if not output_path.exists():
        print(f"輸出文件不存在：{output_path}")
        sys.exit(1)
    if not schema_path.exists():
        print(f"Schema 文件不存在：{schema_path}")
        sys.exit(1)

    sys.exit(0 if validate(output_path, schema_path) else 1)


if __name__ == "__main__":
    main()
