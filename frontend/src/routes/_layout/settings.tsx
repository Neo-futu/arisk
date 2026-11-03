import { createFileRoute } from "@tanstack/react-router"
import { Monitor, Moon, Settings2, Sun } from "lucide-react"
import { useTranslation } from "react-i18next"

import { Appearance } from "@/components/Common/Appearance"
import ChangePassword from "@/components/UserSettings/ChangePassword"
import DeleteAccount from "@/components/UserSettings/DeleteAccount"
import UserInformation from "@/components/UserSettings/UserInformation"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { type Theme, useTheme } from "@/components/theme-provider"
import useAuth from "@/hooks/useAuth"
import i18n from "@/i18n"

export const Route = createFileRoute("/_layout/settings")({
  component: UserSettings,
  head: () => ({
    meta: [{ title: "设置 — ARISK" }],
  }),
})

function PreferencesPanel() {
  const { t } = useTranslation()
  const { theme, setTheme } = useTheme()
  const language = (i18n.language || "zh-CN").startsWith("zh-TW")
    ? "zh-TW"
    : (i18n.language || "").startsWith("en")
      ? "en"
      : "zh-CN"

  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("settings.appearanceTitle")}</CardTitle>
          <p className="text-sm text-muted-foreground">{t("settings.appearanceHint")}</p>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between gap-4">
            <div className="space-y-1">
              <Label>{t("settings.themeLabel")}</Label>
              <p className="text-xs text-muted-foreground">{t("settings.themeHint")}</p>
            </div>
            <Appearance />
          </div>
          <Select value={theme} onValueChange={(value) => setTheme(value as Theme)}>
            <SelectTrigger className="w-full max-w-xs"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="light"><span className="inline-flex items-center gap-2"><Sun className="h-4 w-4" />{t("settings.themeLight")}</span></SelectItem>
              <SelectItem value="dark"><span className="inline-flex items-center gap-2"><Moon className="h-4 w-4" />{t("settings.themeDark")}</span></SelectItem>
              <SelectItem value="system"><span className="inline-flex items-center gap-2"><Monitor className="h-4 w-4" />{t("settings.themeSystem")}</span></SelectItem>
            </SelectContent>
          </Select>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("settings.languageTitle")}</CardTitle>
          <p className="text-sm text-muted-foreground">{t("settings.languageHint")}</p>
        </CardHeader>
        <CardContent>
          <Select
            value={language}
            onValueChange={(value) => {
              void i18n.changeLanguage(value)
            }}
          >
            <SelectTrigger className="w-full max-w-xs"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="zh-CN">{t("settings.langZhCN")}</SelectItem>
              <SelectItem value="zh-TW">{t("settings.langZhTW")}</SelectItem>
              <SelectItem value="en">{t("settings.langEn")}</SelectItem>
            </SelectContent>
          </Select>
        </CardContent>
      </Card>
    </div>
  )
}

function UserSettings() {
  const { t } = useTranslation()
  const { user: currentUser } = useAuth()

  if (!currentUser) return null

  return (
    <div className="space-y-5" data-testid="platform-workbench">
      <div>
        <div className="mb-2 flex items-center gap-2">
          <Badge className="gap-1">
            <Settings2 className="h-3.5 w-3.5" />
            {t("nav.systemManagement")}
          </Badge>
        </div>
        <h1 className="text-2xl font-bold tracking-tight">{t("settings.title")}</h1>
        <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{t("settings.subtitle")}</p>
      </div>

      <Tabs defaultValue="profile" className="space-y-4">
        <TabsList className="grid w-full max-w-2xl grid-cols-4">
          <TabsTrigger value="profile">{t("settings.tabProfile")}</TabsTrigger>
          <TabsTrigger value="password">{t("settings.tabPassword")}</TabsTrigger>
          <TabsTrigger value="preferences">{t("settings.tabPreferences")}</TabsTrigger>
          <TabsTrigger value="danger">{t("settings.tabDanger")}</TabsTrigger>
        </TabsList>

        <TabsContent value="profile" className="mt-0">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t("settings.tabProfile")}</CardTitle>
            </CardHeader>
            <CardContent>
              <UserInformation />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="password" className="mt-0">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t("settings.tabPassword")}</CardTitle>
            </CardHeader>
            <CardContent>
              <ChangePassword />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="preferences" className="mt-0">
          <PreferencesPanel />
        </TabsContent>

        <TabsContent value="danger" className="mt-0">
          <Card className="border-destructive/30">
            <CardHeader>
              <CardTitle className="text-base text-destructive">{t("settings.tabDanger")}</CardTitle>
              <p className="text-sm text-muted-foreground">{t("settings.dangerHint")}</p>
            </CardHeader>
            <CardContent>
              <DeleteAccount />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
