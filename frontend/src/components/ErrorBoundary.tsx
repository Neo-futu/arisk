/**
 * ErrorBoundary — React 組件錯誤邊界
 * 捕獲子組件樹中的未處理渲染錯誤，上報日誌並顯示友好界面。
 */
import { AlertTriangle, RefreshCw } from "lucide-react"
import React from "react"
import { Button } from "@/components/ui/button"
import { logger } from "@/lib/logger"

interface Props {
  children:  React.ReactNode
  module?:   string        // 標識哪個模塊崩潰，默認 "unknown"
  fallback?: React.ReactNode
}

interface State { hasError: boolean; errorMessage: string }

export class ErrorBoundary extends React.Component<Props, State> {
  state: State = { hasError: false, errorMessage: "" }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, errorMessage: error.message }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    logger.error(this.props.module ?? "component", "render_crash", {
      error:           error.message,
      stack:           error.stack?.slice(0, 1000),
      component_stack: info.componentStack?.slice(0, 1000),
    })
  }

  reset = () => this.setState({ hasError: false, errorMessage: "" })

  render() {
    if (!this.state.hasError) return this.props.children

    if (this.props.fallback) return this.props.fallback

    return (
      <div className="flex flex-col items-center justify-center gap-4 rounded-xl border border-destructive/30 bg-destructive/5 p-10 text-center">
        <AlertTriangle className="h-10 w-10 text-destructive opacity-70" />
        <div>
          <p className="font-semibold text-destructive">頁面組件發生錯誤</p>
          <p className="mt-1 max-w-sm text-sm text-muted-foreground">{this.state.errorMessage}</p>
        </div>
        <Button variant="outline" size="sm" className="gap-1.5" onClick={this.reset}>
          <RefreshCw className="h-3.5 w-3.5" />重試
        </Button>
      </div>
    )
  }
}
