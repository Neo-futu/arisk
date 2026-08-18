import { useTranslation } from "react-i18next"

export function Footer() {
  const { t } = useTranslation()
  const currentYear = new Date().getFullYear()

  return (
    <footer className="border-t py-3 px-6">
      <div className="flex items-center justify-between">
        <p className="text-muted-foreground text-xs">
          ARISK — Agent for Risk &amp; Investment Analysis System &copy; {currentYear}
        </p>
        <p className="text-muted-foreground text-xs">
          {t("footer.productName")}
        </p>
      </div>
    </footer>
  )
}
