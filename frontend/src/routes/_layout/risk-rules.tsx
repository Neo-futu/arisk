import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute, redirect } from "@tanstack/react-router"
import { Download, Paperclip, Pencil, Plus, Power, RotateCcw, Search, ShieldCheck, Trash2, Upload } from "lucide-react"
import { useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"

import { FUNDS } from "@/components/FsiToolbar"
import { RuleApplicationsSection } from "@/components/RiskRules/RuleApplicationsSection"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import {
  fsiApi,
  type RiskRuleAttachment,
  type RiskRule,
  type RiskRulePayload,
  type RiskRuleType,
} from "@/fsiClient"

export const Route = createFileRoute("/_layout/risk-rules")({
  component: RiskRulesPage,
  beforeLoad: async () => {
    const access = await fsiApi.getMyAccessContext().then((response) => response.data)
    if (!access.is_superuser && !access.permission_codes.includes("risk_rules.manage")) {
      throw redirect({ to: "/" })
    }
  },
  head: () => ({ meta: [{ title: "Risk Rules — ARISK" }] }),
})

type RuleFilter = "all" | RiskRuleType

type FormState = {
  rule_type: RiskRuleType
  port_id: string
  code: string
  name: string
  name_en: string
  category: string
  source: string
  dimension: string
  dimension_key: string
  lower_limit: string
  upper_limit: string
  limit_unit: string
  limit_direction: "MIN" | "MAX"
  clause_ref: string
  mandate_ref: string
  client_name: string
  breach_action: string
  alert_pct: string
  is_hard: boolean
  effective_date: string
  expiry_date: string
  is_active: boolean
  description: string
}

const today = new Date().toISOString().slice(0, 10)

function emptyForm(ruleType: RiskRuleType): FormState {
  return {
    rule_type: ruleType,
    port_id: FUNDS[0]?.id ?? "",
    code: "",
    name: "",
    name_en: "",
    category: ruleType === "internal" ? "CONCENTRATION" : "",
    source: ruleType === "regulatory" ? "SFC_MMF_CODE" : "",
    dimension: "PORTFOLIO",
    dimension_key: "",
    lower_limit: "",
    upper_limit: "",
    limit_unit: "PCT",
    limit_direction: "MAX",
    clause_ref: "",
    mandate_ref: "",
    client_name: "",
    breach_action: "",
    alert_pct: "90",
    is_hard: true,
    effective_date: today,
    expiry_date: "",
    is_active: true,
    description: "",
  }
}

function formFromRule(rule: RiskRule): FormState {
  return {
    rule_type: rule.rule_type,
    port_id: rule.port_id,
    code: rule.code,
    name: rule.name,
    name_en: rule.name_en ?? "",
    category: rule.category ?? "",
    source: rule.rule_type === "regulatory" ? (rule.source ?? "") : "",
    dimension: rule.dimension,
    dimension_key: rule.dimension_key ?? "",
    lower_limit: rule.lower_limit?.toString() ?? "",
    upper_limit: rule.upper_limit?.toString() ?? "",
    limit_unit: rule.limit_unit,
    limit_direction: rule.limit_direction ?? (rule.lower_limit !== null ? "MIN" : "MAX"),
    clause_ref: rule.clause_ref ?? "",
    mandate_ref: rule.mandate_ref ?? "",
    client_name: rule.client_name ?? "",
    breach_action: rule.breach_action ?? "",
    alert_pct: rule.alert_pct?.toString() ?? "90",
    is_hard: rule.is_hard,
    effective_date: rule.effective_date,
    expiry_date: rule.expiry_date ?? "",
    is_active: rule.is_active,
    description: rule.description ?? "",
  }
}

function nullableNumber(value: string) {
  return value.trim() === "" ? null : Number(value)
}

function isLikelyMojibake(text: string) {
  return /[ÃÂâæð]/.test(text)
}

function displayRuleName(rule: RiskRule) {
  if (rule.name_en && isLikelyMojibake(rule.name)) return rule.name_en
  return rule.name
}

function normalizeRuleListPayload(payload: unknown): { items: RiskRule[]; count: number } {
  if (Array.isArray(payload)) {
    return { items: payload as RiskRule[], count: payload.length }
  }
  if (!payload || typeof payload !== "object") {
    return { items: [], count: 0 }
  }
  const record = payload as Record<string, unknown>
  const nested = (record.data && typeof record.data === "object" ? record.data : null) as Record<string, unknown> | null
  const itemsCandidate =
    (Array.isArray(record.items) ? record.items : null)
    ?? (Array.isArray(record.results) ? record.results : null)
    ?? (nested && Array.isArray(nested.items) ? nested.items : null)
    ?? (nested && Array.isArray(nested.results) ? nested.results : null)
    ?? []
  const countCandidate =
    (typeof record.count === "number" ? record.count : null)
    ?? (typeof record.total === "number" ? record.total : null)
    ?? (nested && typeof nested.count === "number" ? nested.count : null)
    ?? itemsCandidate.length
  return { items: itemsCandidate as RiskRule[], count: countCandidate }
}

function toPayload(form: FormState): RiskRulePayload {
  const lower = nullableNumber(form.lower_limit)
  const upper = nullableNumber(form.upper_limit)
  return {
    rule_type: form.rule_type,
    port_id: form.port_id,
    code: form.code.trim().toUpperCase(),
    name: form.name.trim(),
    name_en: form.name_en.trim() || null,
    category: form.category.trim() || null,
    source: form.source.trim() || null,
    dimension: form.dimension,
    dimension_key: form.dimension_key.trim() || null,
    lower_limit: form.rule_type === "regulatory" && form.limit_direction === "MAX" ? null : lower,
    upper_limit: form.rule_type === "regulatory" && form.limit_direction === "MIN" ? null : upper,
    limit_unit: form.limit_unit,
    limit_direction: form.rule_type === "regulatory" ? form.limit_direction : null,
    clause_ref: form.clause_ref.trim() || null,
    mandate_ref: form.mandate_ref.trim() || null,
    client_name: form.client_name.trim() || null,
    breach_action: form.breach_action.trim() || null,
    alert_pct: form.rule_type === "internal" ? nullableNumber(form.alert_pct) : null,
    is_hard: form.rule_type === "internal" ? form.is_hard : true,
    effective_date: form.effective_date,
    expiry_date: form.expiry_date || null,
    is_active: form.is_active,
    description: form.description.trim() || null,
  }
}

function RiskRulesPage() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [ruleType, setRuleType] = useState<RuleFilter>("all")
  const [fundId, setFundId] = useState("all")
  const [search, setSearch] = useState("")
  const [activeOnly, setActiveOnly] = useState(false)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editing, setEditing] = useState<RiskRule | null>(null)
  const [form, setForm] = useState<FormState>(() => emptyForm("regulatory"))
  const [pendingFile, setPendingFile] = useState<File | null>(null)
  const [pendingFileNote, setPendingFileNote] = useState("")
  const [attachmentRule, setAttachmentRule] = useState<RiskRule | null>(null)
  const [attachmentNote, setAttachmentNote] = useState("")
  const [attachmentFile, setAttachmentFile] = useState<File | null>(null)

  const rules = useQuery({
    queryKey: ["risk-rules", ruleType, fundId, activeOnly, search],
    queryFn: () => fsiApi.listRiskRules({
      ruleType: ruleType === "all" ? undefined : ruleType,
      fundId: fundId === "all" ? undefined : fundId,
      activeOnly,
      search: search.trim() || undefined,
    }).then((response) => normalizeRuleListPayload(response.data)),
  })
  const summary = useQuery({
    queryKey: ["risk-rules-summary"],
    queryFn: () => fsiApi.getRiskRuleSummary().then((response) => response.data),
  })
  const attachments = useQuery({
    queryKey: ["risk-rule-attachments", attachmentRule?.rule_type, attachmentRule?.id],
    enabled: Boolean(attachmentRule),
    queryFn: () => fsiApi.listRiskRuleAttachments(attachmentRule!.rule_type, attachmentRule!.id).then((response) => response.data),
  })

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["risk-rules"] })
    void queryClient.invalidateQueries({ queryKey: ["risk-rules-summary"] })
  }

  const saveRule = useMutation({
    mutationFn: (payload: RiskRulePayload) => editing
      ? fsiApi.updateRiskRule(editing.rule_type, editing.id, payload)
      : fsiApi.createRiskRule(payload),
    onError: () => toast.error(t("riskRules.saveFailed")),
  })
  const deactivate = useMutation({
    mutationFn: (rule: RiskRule) => fsiApi.deactivateRiskRule(rule.rule_type, rule.id),
    onSuccess: refresh,
    onError: () => toast.error(t("riskRules.saveFailed")),
  })
  const reactivate = useMutation({
    mutationFn: (rule: RiskRule) => fsiApi.updateRiskRule(rule.rule_type, rule.id, { is_active: true }),
    onSuccess: refresh,
    onError: () => toast.error(t("riskRules.saveFailed")),
  })
  const uploadAttachment = useMutation({
    mutationFn: ({ rule, file, note }: { rule: RiskRule; file: File; note?: string }) =>
      fsiApi.uploadRiskRuleAttachment(rule.rule_type, rule.id, file, note),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["risk-rule-attachments"] })
      refresh()
      toast.success("附件上传成功")
    },
    onError: () => toast.error("附件上传失败"),
  })
  const deleteAttachment = useMutation({
    mutationFn: (attachmentId: number) => fsiApi.deleteRiskRuleAttachment(attachmentId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["risk-rule-attachments"] })
      refresh()
      toast.success("附件已删除")
    },
    onError: () => toast.error("附件删除失败"),
  })

  const cards = useMemo(() => (["regulatory", "contract", "internal"] as RiskRuleType[]).map((type) => ({
    type,
    total: summary.data?.by_type[type]?.total ?? 0,
    active: summary.data?.by_type[type]?.active ?? 0,
  })), [summary.data])

  function openCreate() {
    const type = ruleType === "all" ? "regulatory" : ruleType
    setEditing(null)
    setForm(emptyForm(type))
    setPendingFile(null)
    setPendingFileNote("")
    setDialogOpen(true)
  }

  function openEdit(rule: RiskRule) {
    setEditing(rule)
    setForm(formFromRule(rule))
    setPendingFile(null)
    setPendingFileNote("")
    setDialogOpen(true)
  }

  function openAttachmentDialog(rule: RiskRule) {
    setAttachmentRule(rule)
    setAttachmentNote("")
    setAttachmentFile(null)
  }

  async function downloadAttachment(attachment: RiskRuleAttachment) {
    const response = await fsiApi.downloadRiskRuleAttachment(attachment.id)
    const url = URL.createObjectURL(response.data)
    const a = document.createElement("a")
    a.href = url
    a.download = attachment.file_name
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  }

  async function submit() {
    const payload = toPayload(form)
    if (!payload.port_id || !payload.code || !payload.name || !payload.dimension || !payload.effective_date) {
      toast.error(t("riskRules.required"))
      return
    }
    if (form.rule_type === "regulatory") {
      const selectedLimit = form.limit_direction === "MAX" ? payload.upper_limit : payload.lower_limit
      if (!payload.source || selectedLimit === null) {
        toast.error(t("riskRules.required"))
        return
      }
    }
    if (form.rule_type === "contract" && !payload.mandate_ref) {
      toast.error(t("riskRules.required"))
      return
    }
    if (form.rule_type !== "regulatory" && payload.lower_limit === null && payload.upper_limit === null) {
      toast.error(t("riskRules.required"))
      return
    }
    const saved = await saveRule.mutateAsync(payload)
    const savedRule = saved.data
    if (pendingFile) {
      await uploadAttachment.mutateAsync({
        rule: savedRule,
        file: pendingFile,
        note: pendingFileNote.trim() || undefined,
      })
    }
    refresh()
    setDialogOpen(false)
    toast.success(editing ? t("riskRules.updated") : t("riskRules.created"))
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="mb-1 flex items-center gap-2 text-sm text-muted-foreground">
            <ShieldCheck className="h-5 w-5 text-primary" />
            {t("nav.systemManagement")}
          </div>
          <h1 className="text-2xl font-bold tracking-tight">{t("riskRules.title")}</h1>
          <p className="text-sm text-muted-foreground">{t("riskRules.description")}</p>
        </div>
        <Button onClick={openCreate}><Plus className="h-4 w-4" />{t("riskRules.create")}</Button>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        {cards.map((card) => (
          <Card key={card.type}>
            <CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground">{t(`riskRules.types.${card.type}`)}</CardTitle></CardHeader>
            <CardContent><div className="text-2xl font-bold">{card.active}</div><p className="text-xs text-muted-foreground">{t("riskRules.activeOfTotal", { active: card.active, total: card.total })}</p></CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">第一部分 · 规则库</CardTitle>
          <p className="text-sm text-muted-foreground">添加和维护监管规则、合同规则、内部规则；规则保存后需在第二部分绑定应用场景才会生效。</p>
        </CardHeader>
        <CardContent className="space-y-4 pt-6">
          <Tabs value={ruleType} onValueChange={(value) => setRuleType(value as RuleFilter)}>
            <TabsList className="grid w-full grid-cols-4 md:w-[560px]">
              <TabsTrigger value="all">{t("riskRules.all")}</TabsTrigger>
              <TabsTrigger value="regulatory">{t("riskRules.types.regulatory")}</TabsTrigger>
              <TabsTrigger value="contract">{t("riskRules.types.contract")}</TabsTrigger>
              <TabsTrigger value="internal">{t("riskRules.types.internal")}</TabsTrigger>
            </TabsList>
          </Tabs>
          <div className="grid gap-3 md:grid-cols-[220px_1fr_auto] md:items-center">
            <Select value={fundId} onValueChange={setFundId}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t("riskRules.allFunds")}</SelectItem>
                {FUNDS.map((fund) => <SelectItem key={fund.id} value={fund.id}>{fund.name}</SelectItem>)}
              </SelectContent>
            </Select>
            <div className="relative">
              <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input className="pl-9" value={search} onChange={(event) => setSearch(event.target.value)} placeholder={t("riskRules.search")} />
            </div>
            <label className="flex items-center gap-2 text-sm"><Switch checked={activeOnly} onCheckedChange={setActiveOnly} />{t("riskRules.activeOnly")}</label>
          </div>

          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>{t("riskRules.activeOfTotal", { active: rules.data?.items.length ?? 0, total: rules.data?.count ?? 0 })}</span>
            {rules.isError ? <span className="text-destructive">规则列表加载失败，请检查后端服务</span> : null}
          </div>

          <div className="max-h-[36vh] min-h-[240px] overflow-auto rounded-md border">
            <Table>
              <TableHeader className="sticky top-0 z-10 bg-background"><TableRow><TableHead>{t("riskRules.type")}</TableHead><TableHead>{t("riskRules.codeName")}</TableHead><TableHead>{t("riskRules.fund")}</TableHead><TableHead>{t("riskRules.dimension")}</TableHead><TableHead>{t("riskRules.limit")}</TableHead><TableHead>附件</TableHead><TableHead>{t("riskRules.period")}</TableHead><TableHead>{t("riskRules.status")}</TableHead><TableHead className="text-right">{t("riskRules.actions")}</TableHead></TableRow></TableHeader>
              <TableBody>
                {(rules.data?.items ?? []).map((rule) => (
                  <TableRow key={`${rule.rule_type}-${rule.id}`}>
                    <TableCell><RuleTypeBadge type={rule.rule_type} /></TableCell>
                    <TableCell>
                      <div className="font-medium">{displayRuleName(rule)}</div>
                      {rule.name_en && !isLikelyMojibake(rule.name) ? <div className="text-xs text-muted-foreground">{rule.name_en}</div> : null}
                      <code className="text-xs text-muted-foreground">{rule.code}</code>
                      {rule.description ? <div className="mt-1 max-w-[320px] truncate text-xs text-muted-foreground">{rule.description}</div> : null}
                    </TableCell>
                    <TableCell>{rule.port_id}</TableCell>
                    <TableCell>{rule.dimension}{rule.dimension_key ? ` / ${rule.dimension_key}` : ""}</TableCell>
                    <TableCell className="font-mono text-xs">{formatLimit(rule)}</TableCell>
                    <TableCell>
                      <Button variant="ghost" size="sm" onClick={() => openAttachmentDialog(rule)}>
                        <Paperclip className="mr-1 h-4 w-4" />
                        {rule.attachment_count ?? 0}
                      </Button>
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-xs">{rule.effective_date}<br />{rule.expiry_date ?? "∞"}</TableCell>
                    <TableCell><Badge variant={rule.is_active ? "default" : "secondary"}>{rule.is_active ? t("riskRules.active") : t("riskRules.inactive")}</Badge></TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-1">
                        <Button variant="ghost" size="icon" onClick={() => openEdit(rule)} title={t("riskRules.edit")}><Pencil className="h-4 w-4" /></Button>
                        {rule.is_active ? (
                          <Button variant="ghost" size="icon" onClick={() => deactivate.mutate(rule)} title={t("riskRules.deactivate")}><Power className="h-4 w-4" /></Button>
                        ) : (
                          <Button variant="ghost" size="icon" onClick={() => reactivate.mutate(rule)} title={t("riskRules.activate")}><RotateCcw className="h-4 w-4" /></Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
                {!rules.isLoading && !rules.data?.items.length && <TableRow><TableCell colSpan={9} className="h-24 text-center text-muted-foreground">{t("riskRules.empty")}</TableCell></TableRow>}
              </TableBody>
            </Table>
          </div>

        </CardContent>
      </Card>

      <RuleApplicationsSection />

      <RuleDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        editing={editing}
        form={form}
        setForm={setForm}
        saving={saveRule.isPending || uploadAttachment.isPending}
        onSubmit={() => { void submit() }}
        pendingFile={pendingFile}
        pendingFileNote={pendingFileNote}
        onFileChange={setPendingFile}
        onFileNoteChange={setPendingFileNote}
      />

      <AttachmentDialog
        open={Boolean(attachmentRule)}
        onOpenChange={(open) => {
          if (!open) setAttachmentRule(null)
        }}
        rule={attachmentRule}
        items={attachments.data?.items ?? []}
        loading={attachments.isLoading}
        uploadPending={uploadAttachment.isPending}
        deletePending={deleteAttachment.isPending}
        file={attachmentFile}
        note={attachmentNote}
        onFileChange={setAttachmentFile}
        onNoteChange={setAttachmentNote}
        onUpload={() => {
          if (!attachmentRule || !attachmentFile) return
          void uploadAttachment.mutateAsync({ rule: attachmentRule, file: attachmentFile, note: attachmentNote }).then(() => {
            setAttachmentFile(null)
            setAttachmentNote("")
          })
        }}
        onDownload={(attachment) => { void downloadAttachment(attachment) }}
        onDelete={(attachment) => { void deleteAttachment.mutateAsync(attachment.id) }}
      />
    </div>
  )
}

function RuleTypeBadge({ type }: { type: RiskRuleType }) {
  const { t } = useTranslation()
  return <Badge variant={type === "regulatory" ? "destructive" : type === "contract" ? "default" : "secondary"}>{t(`riskRules.types.${type}`)}</Badge>
}

function formatLimit(rule: RiskRule) {
  if (rule.lower_limit !== null && rule.upper_limit !== null) return `${rule.lower_limit} ≤ x ≤ ${rule.upper_limit} ${rule.limit_unit}`
  if (rule.upper_limit !== null) return `≤ ${rule.upper_limit} ${rule.limit_unit}`
  if (rule.lower_limit !== null) return `≥ ${rule.lower_limit} ${rule.limit_unit}`
  return "—"
}

function RuleDialog({
  open,
  onOpenChange,
  editing,
  form,
  setForm,
  saving,
  onSubmit,
  pendingFile,
  pendingFileNote,
  onFileChange,
  onFileNoteChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  editing: RiskRule | null
  form: FormState
  setForm: React.Dispatch<React.SetStateAction<FormState>>
  saving: boolean
  onSubmit: () => void
  pendingFile: File | null
  pendingFileNote: string
  onFileChange: (file: File | null) => void
  onFileNoteChange: (note: string) => void
}) {
  const { t } = useTranslation()
  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => setForm((previous) => ({ ...previous, [key]: value }))

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader><DialogTitle>{editing ? t("riskRules.edit") : t("riskRules.create")}</DialogTitle><DialogDescription>{t("riskRules.formHint")}</DialogDescription></DialogHeader>
        <div className="grid gap-4 md:grid-cols-2">
          <Field label={t("riskRules.type")}><Select value={form.rule_type} disabled={Boolean(editing)} onValueChange={(value) => setForm(emptyForm(value as RiskRuleType))}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="regulatory">{t("riskRules.types.regulatory")}</SelectItem><SelectItem value="contract">{t("riskRules.types.contract")}</SelectItem><SelectItem value="internal">{t("riskRules.types.internal")}</SelectItem></SelectContent></Select></Field>
          <Field label={t("riskRules.fund")}><Select value={form.port_id} onValueChange={(value) => set("port_id", value)}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{FUNDS.map((fund) => <SelectItem key={fund.id} value={fund.id}>{fund.name}</SelectItem>)}</SelectContent></Select></Field>
          <Field label={t("riskRules.code")}><Input value={form.code} onChange={(event) => set("code", event.target.value)} /></Field>
          <Field label={t("riskRules.name")}><Input value={form.name} onChange={(event) => set("name", event.target.value)} /></Field>
          <Field label={t("riskRules.nameEn")}><Input value={form.name_en} onChange={(event) => set("name_en", event.target.value)} /></Field>
          <Field label={t("riskRules.dimension")}><Select value={form.dimension} onValueChange={(value) => set("dimension", value)}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{["PORTFOLIO", "ASSET_CLASS", "ISSUER", "ISSUER_GROUP", "CURRENCY", "MATURITY", "WAM", "WAL", "LIQUIDITY", "VAR", "DRAWDOWN", "LEVERAGE"].map((value) => <SelectItem key={value} value={value}>{value}</SelectItem>)}</SelectContent></Select></Field>
          <Field label={t("riskRules.dimensionKey")}><Input value={form.dimension_key} onChange={(event) => set("dimension_key", event.target.value)} /></Field>
          <Field label={t("riskRules.unit")}><Select value={form.limit_unit} onValueChange={(value) => set("limit_unit", value)}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{["PCT", "DAYS", "ABS", "HKD", "RATIO"].map((value) => <SelectItem key={value} value={value}>{value}</SelectItem>)}</SelectContent></Select></Field>

          {form.rule_type === "regulatory" && <>
            <Field label={t("riskRules.source")}><Input value={form.source} onChange={(event) => set("source", event.target.value)} /></Field>
            <Field label={t("riskRules.direction")}><Select value={form.limit_direction} onValueChange={(value) => set("limit_direction", value as "MIN" | "MAX")}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="MAX">MAX</SelectItem><SelectItem value="MIN">MIN</SelectItem></SelectContent></Select></Field>
            <Field label={t("riskRules.value")}><Input type="number" value={form.limit_direction === "MAX" ? form.upper_limit : form.lower_limit} onChange={(event) => set(form.limit_direction === "MAX" ? "upper_limit" : "lower_limit", event.target.value)} /></Field>
          </>}

          {form.rule_type === "internal" && <>
            <Field label={t("riskRules.category")}><Select value={form.category} onValueChange={(value) => set("category", value)}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{["CONCENTRATION", "LIQUIDITY", "DURATION", "VAR", "DRAWDOWN", "LEVERAGE"].map((value) => <SelectItem key={value} value={value}>{value}</SelectItem>)}</SelectContent></Select></Field>
            <Field label={t("riskRules.alertPct")}><Input type="number" value={form.alert_pct} onChange={(event) => set("alert_pct", event.target.value)} /></Field>
          </>}

          {form.rule_type === "contract" && <>
            <Field label={t("riskRules.mandateRef")}><Input value={form.mandate_ref} onChange={(event) => set("mandate_ref", event.target.value)} /></Field>
            <Field label={t("riskRules.clientName")}><Input value={form.client_name} onChange={(event) => set("client_name", event.target.value)} /></Field>
            <Field label={t("riskRules.breachAction")}><Input value={form.breach_action} onChange={(event) => set("breach_action", event.target.value)} /></Field>
          </>}

          {form.rule_type !== "regulatory" && <>
            <Field label={t("riskRules.lowerLimit")}><Input type="number" value={form.lower_limit} onChange={(event) => set("lower_limit", event.target.value)} /></Field>
            <Field label={t("riskRules.upperLimit")}><Input type="number" value={form.upper_limit} onChange={(event) => set("upper_limit", event.target.value)} /></Field>
          </>}

          <Field label={t("riskRules.clauseRef")}><Input value={form.clause_ref} onChange={(event) => set("clause_ref", event.target.value)} /></Field>
          <Field label={t("riskRules.effectiveDate")}><Input type="date" value={form.effective_date} onChange={(event) => set("effective_date", event.target.value)} /></Field>
          <Field label={t("riskRules.expiryDate")}><Input type="date" value={form.expiry_date} onChange={(event) => set("expiry_date", event.target.value)} /></Field>
          <div className="flex flex-wrap items-center gap-6 pt-6">
            <label className="flex items-center gap-2 text-sm"><Switch checked={form.is_active} onCheckedChange={(value) => set("is_active", value)} />{t("riskRules.active")}</label>
            {form.rule_type === "internal" && <label className="flex items-center gap-2 text-sm"><Switch checked={form.is_hard} onCheckedChange={(value) => set("is_hard", value)} />{t("riskRules.hardLimit")}</label>}
          </div>
          <div className="space-y-2 md:col-span-2"><Label>{t("riskRules.descriptionField")}</Label><Textarea value={form.description} onChange={(event) => set("description", event.target.value)} rows={3} /></div>
          <div className="space-y-2 md:col-span-2">
            <Label>附件（可选，PDF/DOC/DOCX/TXT）</Label>
            <Input
              type="file"
              accept=".pdf,.doc,.docx,.txt,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain"
              onChange={(event) => onFileChange(event.target.files?.[0] ?? null)}
            />
            {pendingFile ? <p className="text-xs text-muted-foreground">已选择: {pendingFile.name}</p> : null}
            <Input placeholder="附件说明（可选）" value={pendingFileNote} onChange={(event) => onFileNoteChange(event.target.value)} />
          </div>
        </div>
        <DialogFooter><Button variant="outline" onClick={() => onOpenChange(false)}>{t("riskRules.cancel")}</Button><Button onClick={onSubmit} disabled={saving}>{saving ? t("riskRules.saving") : t("riskRules.save")}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function AttachmentDialog({
  open,
  onOpenChange,
  rule,
  items,
  loading,
  uploadPending,
  deletePending,
  file,
  note,
  onFileChange,
  onNoteChange,
  onUpload,
  onDownload,
  onDelete,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  rule: RiskRule | null
  items: RiskRuleAttachment[]
  loading: boolean
  uploadPending: boolean
  deletePending: boolean
  file: File | null
  note: string
  onFileChange: (file: File | null) => void
  onNoteChange: (value: string) => void
  onUpload: () => void
  onDownload: (attachment: RiskRuleAttachment) => void
  onDelete: (attachment: RiskRuleAttachment) => void
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>规则附件</DialogTitle>
          <DialogDescription>{rule ? `${displayRuleName(rule)} (${rule.code})` : ""}</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="rounded-md border p-3">
            <div className="grid gap-3 md:grid-cols-[1fr_220px_auto] md:items-end">
              <div className="space-y-2">
                <Label>上传文件</Label>
                <Input
                  type="file"
                  accept=".pdf,.doc,.docx,.txt,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain"
                  onChange={(event) => onFileChange(event.target.files?.[0] ?? null)}
                />
              </div>
              <div className="space-y-2">
                <Label>说明</Label>
                <Input value={note} onChange={(event) => onNoteChange(event.target.value)} placeholder="可选" />
              </div>
              <Button onClick={onUpload} disabled={!file || uploadPending}><Upload className="mr-1 h-4 w-4" />上传</Button>
            </div>
          </div>

          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>文件名</TableHead>
                  <TableHead>大小</TableHead>
                  <TableHead>说明</TableHead>
                  <TableHead>上传时间</TableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((attachment) => (
                  <TableRow key={attachment.id}>
                    <TableCell className="font-medium">{attachment.file_name}</TableCell>
                    <TableCell>{(attachment.file_size / 1024).toFixed(1)} KB</TableCell>
                    <TableCell>{attachment.note ?? "-"}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">{String(attachment.created_at).slice(0, 19).replace("T", " ")}</TableCell>
                    <TableCell>
                      <div className="flex justify-end gap-1">
                        <Button variant="ghost" size="icon" onClick={() => onDownload(attachment)} title="下载"><Download className="h-4 w-4" /></Button>
                        <Button variant="ghost" size="icon" onClick={() => onDelete(attachment)} disabled={deletePending} title="删除"><Trash2 className="h-4 w-4" /></Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
                {!loading && items.length === 0 ? <TableRow><TableCell colSpan={5} className="h-20 text-center text-muted-foreground">暂无附件</TableCell></TableRow> : null}
              </TableBody>
            </Table>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="space-y-2"><Label>{label}</Label>{children}</div>
}
