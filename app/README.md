# app

应用运行时代码。lambda-deploy 形态下这里是 Lambda 的部署包内容。

- `handler.py` — 入口，导出 `handler(event, context)`。两个路由：
  - `GET /health` → `{"status":"ok", ...}`
  - 其它路径 → `{"message":"hello from <app>", ...}`
  - 兼容 API Gateway / Lambda Function URL（payload v2.0）与直接 invoke。
  - 仅用 Python 标准库；从环境变量 `APP_NAME` / `ENV` 取上下文（由 `iac/` 注入）。

打包：`iac/main.tf` 用 `archive_file` 把整个 `app/` 打成 zip（排除 `README.md`）。若引入第三方依赖，新建 `app/requirements.txt`，CI 打包前 `pip install -t app/`。
