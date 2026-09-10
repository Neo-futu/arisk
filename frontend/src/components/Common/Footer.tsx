import { useTranslation } from "react-i18next"

import { cn } from "@/lib/utils"

export function Footer({ className }: { className?: string }) {
  const { t } = useTranslation()
  const currentYear = new Date().getFullYear()

  return (
    <footer className={cn("border-t py-3 px-6", className)}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-muted-foreground text-xs">
          {t("footer.company")} &copy; {currentYear}
        </p>
        <p className="text-muted-foreground text-xs">
          {t("footer.productName")}
        </p>
      </div>
    </footer>
  )
}
