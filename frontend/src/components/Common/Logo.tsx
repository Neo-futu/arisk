import { Link } from "@tanstack/react-router"

import { useTheme } from "@/components/theme-provider"
import { cn } from "@/lib/utils"

interface LogoProps {
  variant?: "full" | "icon" | "responsive"
  className?: string
  asLink?: boolean
}

export function Logo({
  variant = "full",
  className,
  asLink = true,
}: LogoProps) {
  const { resolvedTheme } = useTheme()
  const isDark = resolvedTheme === "dark"

  const content =
    variant === "responsive" ? (
      <>
        <div
          aria-label="ARISK"
          className={cn(
            "group-data-[collapsible=icon]:hidden",
            className,
          )}
        >
          <div className="leading-tight">
            <div className="text-sm font-bold tracking-wide text-foreground">
              ARISK
            </div>
            <div className="text-[10px] text-muted-foreground leading-tight">
              Agent for Risk &amp; Investment Analysis System
            </div>
          </div>
        </div>
        <div
          aria-label="ARISK"
          className={cn(
            "size-6 hidden group-data-[collapsible=icon]:flex items-center justify-center rounded-md bg-primary text-primary-foreground text-xs font-bold",
            className,
          )}
        >
          A
        </div>
      </>
    ) : (
      <>
        {variant === "full" ? (
          <div aria-label="ARISK" className={cn("leading-tight", className)}>
            <div className="text-sm font-bold tracking-wide text-foreground">
              ARISK
            </div>
            <div className="text-[10px] text-muted-foreground leading-tight">
              Agent for Risk &amp; Investment Analysis System
            </div>
          </div>
        ) : (
          <div
            aria-label="ARISK"
            className={cn(
              "size-6 flex items-center justify-center rounded-md bg-primary text-primary-foreground text-xs font-bold",
              className,
            )}
          >
            A
          </div>
        )}
      </>
    )

  if (!asLink) {
    return content
  }

  return <Link to="/">{content}</Link>
}
