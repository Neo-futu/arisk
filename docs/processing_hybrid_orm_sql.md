# Processing: Hybrid ORM + SQL Pattern

目的：在保留現有高性能 SQL 聚合能力的前提下，引入 Python 面向對象的 DB 實體模型，提升可維護性與專業性。

## 為什麼不是全 ORM

風控場景中很多查詢是：

- 大量聚合
- 跨多表 UNION
- 時間窗口條件（T+1/T+5）
- 複雜口徑和風控規則

這些 SQL 直接寫通常更清晰、更穩定、也更容易做性能優化。

## 建議架構（已落地在 exposure）

在 exposure 模塊中採用三引擎並行，並做了模塊拆分：

- ORM 實體： [2_processing/tools/risk/exposure_models.py](2_processing/tools/risk/exposure_models.py)
- ORM 查詢倉儲： [2_processing/tools/risk/exposure_repository.py](2_processing/tools/risk/exposure_repository.py)
- SQL 引擎： [2_processing/tools/risk/exposure_engine_sql.py](2_processing/tools/risk/exposure_engine_sql.py)
- Hybrid 引擎（py+sql）： [2_processing/tools/risk/exposure_engine_hybrid.py](2_processing/tools/risk/exposure_engine_hybrid.py)
- ORM 引擎： [2_processing/tools/risk/exposure_engine_orm.py](2_processing/tools/risk/exposure_engine_orm.py)
- 門面與切換： [2_processing/tools/risk/exposure_engine.py](2_processing/tools/risk/exposure_engine.py)

具體模式：

1. SQL 模式
- 全部採用 raw SQL text。
- 優點：最接近 DB 執行計劃，易於精細優化。

2. Hybrid（py+sql）模式
- ORM/repository 讀取基礎快照。
- 複雜聚合與 UNION 使用 SQL text。
- 優點：工程可讀性與性能平衡。

3. ORM 模式
- 使用 SQLAlchemy ORM/Core expression API（無 text SQL）。
- 優點：面向對象一致性最好，易做跨模塊抽象。

4. ORM 實體（面向對象）
- `BalancePortfolioNav`
- `BalancePortfolioMmf`
- `BalancePortfolioAsset`
- `BalanceCash`
- `BalanceBond`
- `BalanceCd`
- `BalanceDeposit`
- `BalanceRepo`

用途：
- 基礎快照讀取（NAV、WAM/WAL、資產配置）
- 清晰的欄位語義與類型

5. SQL text（保留於 SQL/Hybrid 模式）
- DLA/WLA 複雜聚合
- 發行人/集團集中度 UNION 聚合

用途：
- 保留既有口徑
- 保留複雜查詢可控性與性能

## 數據流位置

業務鏈路仍為：

frontend -> backend -> processing(router) -> tools -> db

其中 tools 層可按引擎模式選擇執行路徑。

## 模式切換

`exposure_engine.py` 提供統一入口 `compute_exposure` / `find_latest_exposure_date`。

可通過環境變量切換：

- `EXPOSURE_ENGINE_MODE=sql`
- `EXPOSURE_ENGINE_MODE=hybrid`（默認）
- `EXPOSURE_ENGINE_MODE=orm`

也可在函數調用時傳 `mode` 參數覆蓋。

## 推薦擴展方式

針對每個指標模塊：

1. 先建最小 ORM 實體（只映射該模塊實際使用欄位）
2. 把簡單讀取改成 ORM（單表查詢、快照查詢）
3. 保留複雜聚合 SQL（UNION、窗口、大 GROUP BY）
4. 用同一個 `AsyncSession`，避免額外連接管理
5. 保持返回 DTO（dataclass / pydantic）不變，對上層 API 無破壞

## 設計原則

- 三種模式長期並行存在，避免一次性替換風險
- ORM 用於「可讀性與可維護性」
- SQL 用於「複雜度與性能關鍵路徑」
- 不做一次性全量重寫，按模塊漸進演進

## 本次已完成

- 在 exposure 模塊中引入最小 ORM 實體（獨立文件）
- 引入 repository 查詢封裝（獨立文件）
- 新增 SQL/Hybrid/ORM 三個並行引擎文件
- 用 facade 統一對外 API，不破壞 router 調用
