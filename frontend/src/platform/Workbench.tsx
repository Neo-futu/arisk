import type { ReactNode } from "react"
import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button"

export function Workbench({
  parameter,
  data,
  charts,
  loading = false,
  error,
  empty = false,
  onExport,
}: {
  parameter?: ReactNode
  data?: ReactNode
  charts?: ReactNode
  loading?: boolean
  error?: string | null
  empty?: boolean
  onExport?: () => void
}) {
  const { t } = useTranslation()
  return (
    <div className="grid min-w-0 gap-6" data-testid="platform-workbench">
      {parameter ? (
        <section className="min-w-0" data-testid="platform-parameter">
          {parameter}
        </section>
      ) : null}
      {loading ? (
        <p className="animate-pulse text-sm text-muted-foreground" data-testid="platform-loading">
          {t("platform.loading")}
        </p>
      ) : null}
      {error ? (
        <p className="text-sm text-destructive" data-testid="platform-error">
          {error}
        </p>
      ) : null}
      {!loading && !error && empty ? (
        <p className="text-sm text-muted-foreground" data-testid="platform-empty">
          {t("platform.empty")}
        </p>
      ) : null}
      {data ? (
        <section className="min-w-0 overflow-x-auto" data-testid="platform-data">
          {data}
        </section>
      ) : null}
      {charts ? (
        <section className="min-w-0" data-testid="platform-charts">
          {charts}
        </section>
      ) : null}
      {onExport ? (
        <div>
          <Button type="button" variant="outline" size="sm" data-testid="platform-export" onClick={onExport}>
            {t("platform.export")}
          </Button>
        </div>
      ) : null}
      <p className="text-xs text-muted-foreground" data-testid="platform-engine-note">
        {t("platform.engineNote")}
      </p>
    </div>
  )
}
