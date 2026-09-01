import { createFileRoute, redirect } from "@tanstack/react-router"

import { fsiApi } from "@/fsiClient"
import { SystemConfigPage } from "@/modules/system-config/SystemConfigPage"

export const Route = createFileRoute("/_layout/system-config")({
  component: SystemConfigPage,
  beforeLoad: async () => {
    const access = await fsiApi.getMyAccessContext().then((response) => response.data)
    if (!access.can_manage_system) {
      throw redirect({ to: "/" })
    }
  },
  head: () => ({ meta: [{ title: "系統配置 — ARISK" }] }),
})
