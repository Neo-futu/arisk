import { useTranslation } from "react-i18next"

import { Appearance } from "@/components/Common/Appearance"
import { Logo } from "@/components/Common/Logo"
import { Footer } from "./Footer"

interface AuthLayoutProps {
  children: React.ReactNode
}

export function AuthLayout({ children }: AuthLayoutProps) {
  const { t } = useTranslation()

  return (
    <div
      className="relative flex min-h-svh flex-col items-center justify-center px-4 py-8"
      style={{
        background:
          "linear-gradient(135deg, #e8f0fe 0%, #f4f6f9 50%, #fef3e2 100%)",
      }}
    >
      <div className="absolute right-6 top-6">
        <Appearance />
      </div>
      <div className="w-full max-w-[400px] rounded-2xl border border-[#e8eaf6] bg-white px-9 py-10 shadow-[0_8px_32px_rgba(21,101,192,0.12)]">
        <div className="mb-8 flex flex-col items-center gap-4 text-center">
          <Logo variant="full" asLink={false} />
          <div className="rounded-md bg-[#f0f4ff] px-3.5 py-1 text-[13px] tracking-wider text-primary">
            {t("login.productChip")}
          </div>
        </div>
        {children}
      </div>
      <div className="mt-6 w-full max-w-[400px] text-center">
        <Footer className="border-0 py-0 px-0" />
      </div>
    </div>
  )
}
