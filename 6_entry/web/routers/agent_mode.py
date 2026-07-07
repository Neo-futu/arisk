"""Agent Mode Router — 觸發 Claude Managed Agent 執行複雜任務。"""
from __future__ import annotations

import os
import uuid
from datetime import datetime

import anthropic
import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
PROCESSING_API_URL = os.environ.get("PROCESSING_API_URL", "http://localhost:8001")
PROCESSING_API_KEY = os.environ.get("PROCESSING_API_KEY", "internal_key_change_me")

router = APIRouter()
_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
_headers = {"X-API-Key": PROCESSING_API_KEY}

# 任務狀態存儲（生產環境應用 Redis）
_tasks: dict[str, dict] = {}


class AgentTaskRequest(BaseModel):
    task: str
    fund_id: str | None = None
    date: str | None = None
    mode: str = "agent"  # agent | chat


class AgentTaskResponse(BaseModel):
    task_id: str
    status: str
    message: str


class VarSkillRequest(BaseModel):
    fund_id: str
    as_of_date: str
    confidence: float = 0.99
    horizon_days: int = 1
    simulations: int = 10000


@router.post("/run", response_model=AgentTaskResponse)
async def run_agent_task(
    request: AgentTaskRequest,
    background_tasks: BackgroundTasks,
):
    """
    觸發 Agent 執行複雜分析任務（非同步）。
    返回 task_id，用 GET /agent/status/{task_id} 輪詢結果。
    """
    task_id = str(uuid.uuid4())
    _tasks[task_id] = {
        "status": "queued",
        "created_at": datetime.utcnow().isoformat(),
        "request": request.model_dump(),
    }

    background_tasks.add_task(_run_agent_background, task_id, request)
    return AgentTaskResponse(task_id=task_id, status="queued", message="任務已加入隊列")


@router.get("/status/{task_id}")
async def get_task_status(task_id: str):
    """查詢 Agent 任務狀態和結果。"""
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("/chat")
async def chat_with_agent(request: AgentTaskRequest):
    """
    同步 Chat 模式：直接與 Claude 對話（短查詢，不走 Agent 框架）。
    適合 ≤30s 的簡單問答。
    """
    context = _build_context(request)
    response = _client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=4096,
        system=(
            "你是 ARISK 的助手，幫助分析基金風控數據。"
            "回答要簡潔、結構化。如需詳細計算，建議使用 /agent/run 觸發完整 Agent 分析。"
        ),
        messages=[{"role": "user", "content": context}],
    )
    return {"reply": response.content[0].text, "model": ANTHROPIC_MODEL}


@router.post("/skills/var-analysis")
async def run_var_skill(request: VarSkillRequest):
    """VaR skill（入口層聚合）：輸出三方法結果和技能格式摘要。"""
    async with httpx.AsyncClient(base_url=PROCESSING_API_URL, headers=_headers, timeout=30) as client:
        results = []
        for method in ("historical", "monte_carlo", "distribution"):
            params = {
                "as_of_date": request.as_of_date,
                "confidence": request.confidence,
                "horizon_days": request.horizon_days,
                "method": method,
            }
            if method == "monte_carlo":
                params["simulations"] = request.simulations

            resp = await client.get(f"/risk/var/{request.fund_id}", params=params)
            if resp.status_code != 200:
                raise HTTPException(status_code=resp.status_code, detail=resp.text)

            payload = resp.json()
            payload["method_requested"] = method
            results.append(payload)

    max_var_pct_nav = max((float(r.get("var_pct_nav", 0.0) or 0.0) for r in results), default=0.0)
    summary = _format_var_skill_summary(
        fund_id=request.fund_id,
        as_of_date=request.as_of_date,
        confidence=request.confidence,
        horizon_days=request.horizon_days,
        results=results,
    )

    return {
        "fund_id": request.fund_id,
        "as_of_date": request.as_of_date,
        "confidence": request.confidence,
        "horizon_days": request.horizon_days,
        "max_var_pct_nav": max_var_pct_nav,
        "results": results,
        "summary": summary,
    }


@router.get("/skills/var-analysis", response_class=HTMLResponse)
async def var_skill_page() -> str:
        """Browser page for Agent VaR skill testing and demo."""
        return """
<!doctype html>
<html lang="zh-HK">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>FSI Agent VaR Skill</title>
    <style>
        body{font-family:Segoe UI,Arial,sans-serif;background:#f4f7fb;margin:0;padding:24px;color:#1f2937}
        .wrap{max-width:980px;margin:0 auto}
        .card{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:18px;margin-bottom:14px}
        .title{font-size:22px;font-weight:700;margin:0 0 6px}
        .sub{font-size:13px;color:#6b7280;margin:0 0 16px}
        .row{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px}
        label{display:block;font-size:12px;color:#374151;margin-bottom:4px}
        input{width:100%;padding:8px;border:1px solid #d1d5db;border-radius:6px}
        button{margin-top:12px;padding:8px 14px;border:none;background:#2563eb;color:#fff;border-radius:6px;cursor:pointer}
        button:hover{background:#1d4ed8}
        table{width:100%;border-collapse:collapse;margin-top:10px;font-size:13px}
        th,td{border:1px solid #e5e7eb;padding:8px;text-align:right}
        th:first-child,td:first-child{text-align:left}
        .muted{font-size:12px;color:#6b7280;margin-top:8px}
        pre{background:#0b1020;color:#dbeafe;padding:12px;border-radius:8px;overflow:auto;max-height:260px}
        .ok{color:#065f46;font-weight:600}
        .err{color:#991b1b;font-weight:600}
    </style>
</head>
<body>
    <div class="wrap">
        <div class="card">
            <h1 class="title">Agent 模式 VaR 技能頁</h1>
            <p class="sub">此頁面直接調用 POST /agent/skills/var-analysis，展示三方法 VaR 結果與 summary。</p>
            <div class="row">
                <div><label>Fund ID</label><input id="fund" value="BHMMF001"></div>
                <div><label>As Of Date</label><input id="dt" value="2026-06-25"></div>
                <div><label>Confidence</label><input id="conf" value="0.99"></div>
                <div><label>Horizon Days</label><input id="hday" value="1"></div>
                <div><label>Simulations</label><input id="sim" value="10000"></div>
            </div>
            <button onclick="runSkill()">執行 Agent VaR Skill</button>
            <div id="status" class="muted">等待執行...</div>
        </div>

        <div class="card" id="tableCard" style="display:none">
            <h3>三方法結果</h3>
            <table>
                <thead><tr><th>方法</th><th>VaR(HKD)</th><th>VaR(%NAV)</th><th>CVaR(HKD)</th><th>樣本數</th></tr></thead>
                <tbody id="tbody"></tbody>
            </table>
            <div class="muted" id="maxVar"></div>
        </div>

        <div class="card" id="summaryCard" style="display:none">
            <h3>Skill Summary</h3>
            <pre id="summary"></pre>
        </div>
    </div>

    <script>
        async function runSkill(){
            const body={
                fund_id:document.getElementById('fund').value,
                as_of_date:document.getElementById('dt').value,
                confidence:parseFloat(document.getElementById('conf').value),
                horizon_days:parseInt(document.getElementById('hday').value),
                simulations:parseInt(document.getElementById('sim').value)
            };
            const status=document.getElementById('status');
            status.textContent='執行中...';
            status.className='muted';
            try{
                const resp=await fetch('/agent/skills/var-analysis',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
                const data=await resp.json();
                if(!resp.ok){ throw new Error(data.detail || JSON.stringify(data)); }

                const tbody=document.getElementById('tbody');
                tbody.innerHTML='';
                for(const r of (data.results||[])){
                    const tr=document.createElement('tr');
                    tr.innerHTML=`<td>${r.method||r.method_requested||'UNKNOWN'}</td><td>${Number(r.var_hkd||0).toLocaleString(undefined,{maximumFractionDigits:2})}</td><td>${Number(r.var_pct_nav||0).toFixed(6)}%</td><td>${Number(r.cvar_hkd||0).toLocaleString(undefined,{maximumFractionDigits:2})}</td><td>${r.sample_size||0}</td>`;
                    tbody.appendChild(tr);
                }

                document.getElementById('tableCard').style.display='block';
                document.getElementById('summaryCard').style.display='block';
                document.getElementById('summary').textContent=data.summary||'';
                document.getElementById('maxVar').textContent=`max_var_pct_nav = ${Number(data.max_var_pct_nav||0).toFixed(6)}%`;
                status.textContent='執行成功';
                status.className='ok';
            }catch(err){
                status.textContent='執行失敗: '+err.message;
                status.className='err';
            }
        }
    </script>
</body>
</html>
        """


async def _run_agent_background(task_id: str, request: AgentTaskRequest) -> None:
    """後台執行 Agent 任務（實際生產應用 Celery 或 Managed Agent API）。"""
    try:
        _tasks[task_id]["status"] = "running"
        context = _build_context(request)

        response = _client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=8192,
            system=(
                "你是 ARISK 的 Risk Agent。執行用戶指定的風控分析任務。"
                "可調用的 API: Processing API (http://localhost:8001)，需要 X-API-Key 頭。"
                "按 risk-analysis 和 mmf-compliance SKILL 格式輸出報告。"
            ),
            messages=[{"role": "user", "content": context}],
        )

        _tasks[task_id].update({
            "status": "completed",
            "result": response.content[0].text,
            "completed_at": datetime.utcnow().isoformat(),
        })
    except Exception as e:
        _tasks[task_id].update({
            "status": "failed",
            "error": str(e),
            "completed_at": datetime.utcnow().isoformat(),
        })


def _build_context(request: AgentTaskRequest) -> str:
    parts = [request.task]
    if request.fund_id:
        parts.append(f"基金 ID: {request.fund_id}")
    if request.date:
        parts.append(f"日期: {request.date}")
    return "\n".join(parts)


def _format_var_skill_summary(
    fund_id: str,
    as_of_date: str,
    confidence: float,
    horizon_days: int,
    results: list[dict],
) -> str:
    lines = [
        f"## VaR 專項分析 - {fund_id} · {as_of_date}",
        "",
        "| 方法 | VaR(HKD) | VaR(%NAV) | CVaR(HKD) | 樣本數 |",
        "|------|----------|-----------|-----------|--------|",
    ]
    for r in results:
        method_name = r.get("method", r.get("method_requested", "UNKNOWN"))
        lines.append(
            f"| {method_name} | {float(r.get('var_hkd', 0.0) or 0.0):,.2f} | "
            f"{float(r.get('var_pct_nav', 0.0) or 0.0):.4f}% | {float(r.get('cvar_hkd', 0.0) or 0.0):,.2f} | "
            f"{int(r.get('sample_size', 0) or 0)} |"
        )

    lines.extend(
        [
            "",
            "### 口徑說明",
            f"- 置信度: {confidence:.2%}",
            f"- 持有期: {horizon_days} 天",
            "- VaR(%NAV) 以 as_of_date 當日 NAV 為分母",
        ]
    )
    return "\n".join(lines)
