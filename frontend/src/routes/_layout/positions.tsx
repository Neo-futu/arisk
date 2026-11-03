import { createFileRoute, redirect } from "@tanstack/react-router"

/** 持仓明细已并入数据管理中心；保留路由做旧书签兼容跳转。 */
export const Route = createFileRoute("/_layout/positions")({
  beforeLoad: () => {
    throw redirect({
      to: "/data-management",
      search: { section: "positions" },
    })
  },
})
