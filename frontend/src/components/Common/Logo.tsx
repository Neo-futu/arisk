import { Link } from "@tanstack/react-router"

import { cn } from "@/lib/utils"

interface LogoProps {
  variant?: "full" | "icon" | "responsive"
  className?: string
  asLink?: boolean
}

function BrandMark({ className }: { className?: string }) {
  return (
    <div
      aria-hidden
      className={cn(
        "flex size-8 shrink-0 items-center justify-center rounded-md bg-primary text-sm font-bold text-primary-foreground",
        className,
      )}
    >
      百
    </div>
  )
}

function BrandWordmark({ compact = false }: { compact?: boolean }) {
  return (
    <div className="leading-tight">
      <span className="sr-only">百仁思 ARISK</span>
      <div className="text-[15px] font-bold tracking-wide text-primary">
        百仁思
      </div>
      <div
        className={cn(
          "text-[10px] leading-tight text-muted-foreground",
          compact && "hidden sm:block",
        )}
      >
        ARISK · 智能风控和投资分析系统
      </div>
    </div>
  )
}

export function Logo({
  variant = "full",
  className,
  asLink = true,
}: LogoProps) {
  const content =
    variant === "responsive" ? (
      <>
        <div
          className={cn(
            "flex items-center gap-2.5 group-data-[collapsible=icon]:hidden",
            className,
          )}
        >
          <BrandMark />
          <BrandWordmark />
        </div>
        <BrandMark
          className={cn(
            "hidden size-6 text-xs group-data-[collapsible=icon]:flex",
            className,
          )}
        />
      </>
    ) : variant === "full" ? (
      <div className={cn("flex items-center gap-3", className)}>
        <BrandMark className="size-10 text-base" />
        <BrandWordmark />
      </div>
    ) : (
      <BrandMark className={className} />
    )

  if (!asLink) {
    return content
  }

  return <Link to="/">{content}</Link>
}
