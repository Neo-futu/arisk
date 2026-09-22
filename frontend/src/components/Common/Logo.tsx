import { Link } from "@tanstack/react-router"

import { cn } from "@/lib/utils"

const LOGO_SRC = "/assets/images/balance_logo.png"

interface LogoProps {
  variant?: "full" | "icon" | "responsive"
  className?: string
  asLink?: boolean
}

/**
 * Platform brand: balance_logo.png (百仁思 · Asset Management).
 * Full lockup for expanded UI; left mark crop for collapsed sidebar icon.
 */
function BrandImage({
  mode,
  className,
}: {
  mode: "full" | "icon"
  className?: string
}) {
  return (
    <img
      src={LOGO_SRC}
      alt="百仁思 Asset Management"
      className={cn(
        "shrink-0 object-contain",
        mode === "full" && "h-10 w-auto max-w-[220px]",
        mode === "icon" && "size-8 object-cover object-left",
        className,
      )}
      draggable={false}
    />
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
            "flex items-center group-data-[collapsible=icon]:hidden",
            className,
          )}
        >
          <BrandImage mode="full" className="h-9 max-w-[200px]" />
        </div>
        <BrandImage
          mode="icon"
          className={cn(
            "hidden size-7 group-data-[collapsible=icon]:block",
            className,
          )}
        />
      </>
    ) : variant === "full" ? (
      <BrandImage mode="full" className={cn("h-12 max-w-[260px]", className)} />
    ) : (
      <BrandImage mode="icon" className={className} />
    )

  if (!asLink) {
    return content
  }

  return <Link to="/">{content}</Link>
}
