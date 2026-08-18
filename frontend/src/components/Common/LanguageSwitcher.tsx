import { Languages } from "lucide-react"
import { useTranslation } from "react-i18next"

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

const normalizeLanguage = (language: string) => {
  if (language.startsWith("zh-CN")) return "zh-CN"
  if (language.startsWith("zh-TW") || language.startsWith("zh-HK")) return "zh-TW"
  return "en"
}

export function LanguageSwitcher() {
  const { i18n } = useTranslation()
  const value = normalizeLanguage(i18n.resolvedLanguage ?? i18n.language)

  return (
    <div className="flex items-center gap-2">
      <Languages className="h-4 w-4 text-muted-foreground" />
      <Select
        value={value}
        onValueChange={(nextLanguage) => {
          void i18n.changeLanguage(nextLanguage)
        }}
      >
        <SelectTrigger className="w-40" aria-label="Language">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="zh-TW">繁體中文</SelectItem>
          <SelectItem value="zh-CN">简体中文</SelectItem>
          <SelectItem value="en">EN</SelectItem>
        </SelectContent>
      </Select>
    </div>
  )
}
