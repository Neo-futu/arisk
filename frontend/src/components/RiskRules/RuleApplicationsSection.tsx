import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Pencil, Plus, Power, RotateCcw } from "lucide-react"
import { useMemo, useState } from "react"
import { toast } from "sonner"

import { FUNDS } from "@/components/FsiToolbar"
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
import { Textarea } from "@/components/ui/textarea"
import {
  fsiApi,
  type RiskRule,
  type RiskRuleType,
  type RuleApplication,
  type RuleApplicationPayload,
  type RuleApplyScope,
} from "@/fsiClient"

const today = new Date().toISOString().slice(0, 10)

const SCOPE_LABELS: Record<RuleApplyScope, string> = {
  portfolio: "组合检查",
  trade: "交易检查",
  pretrade: "交易前检查",
  posttrade: "交易后检查",
}

const TYPE_LABELS: Record<RiskRuleType, string> = {
  regulatory: "监管",
  contract: "合同",
  internal: "内部",
}

type ApplicationForm = {
  ruleRef: string
  apply_scope: RuleApplyScope
  port_id: string
  strategy_code: string
  instrument_type: string
  trade_side: "BUY" | "SELL" | "BOTH"
  priority: string
  effective_date: string
  expiry_date: string
  is_active: boolean
  note: string
}

function emptyForm(): ApplicationForm {
  return {
    ruleRef: "",
    apply_scope: "portfolio",
    port_id: FUNDS[0]?.id ?? "",
    strategy_code: "",
    instrument_type: "",
    trade_side: "BOTH",
    priority: "100",
    effective_date: today,
    expiry_date: "",
    is_active: true,
    note: "",
  }
}

function formFromApplication(application: RuleApplication): ApplicationForm {
  return {
    ruleRef: `${application.rule_type}:${application.rule_id}`,
    apply_scope: application.apply_scope,
    port_id: application.port_id ?? "",
    strategy_code: application.strategy_code ?? "",
    instrument_type: application.instrument_type ?? "",
    trade_side: application.trade_side ?? "BOTH",
    priority: String(application.priority),
    effective_date: application.effective_date,
    expiry_date: application.expiry_date ?? "",
    is_active: application.is_active,
    note: application.note ?? "",
  }
}

function ruleLabel(rule: RiskRule) {
  const name = rule.name_en && /[ÃÂâæð]/.test(rule.name) ? rule.name_en : rule.name
  return `${TYPE_LABELS[rule.rule_type]} · ${rule.code} · ${name} · ${rule.port_id}`
}

function targetLabel(application: RuleApplication) {
  const parts = [application.port_id, application.strategy_code, application.instrument_type]
    .filter(Boolean)
  if (application.trade_side) parts.push(application.trade_side)
  return parts.length ? parts.join(" / ") : "全局"
}

export function RuleApplicationsSection() {
  const queryClient = useQueryClient()
  const [scope, setScope] = useState<"all" | RuleApplyScope>("all")
  const [fundId, setFundId] = useState("all")
  const [activeOnly, setActiveOnly] = useState(false)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editing, setEditing] = useState<RuleApplication | null>(null)
  const [form, setForm] = useState<ApplicationForm>(emptyForm)

  const rulesQuery = useQuery({
    queryKey: ["risk-rules-for-applications"],
    queryFn: () => fsiApi.listRiskRules({ activeOnly: false, limit: 500 }).then((response) => response.data),
  })
  const applicationsQuery = useQuery({
    queryKey: ["rule-applications", scope, fundId, activeOnly],
    queryFn: () => fsiApi.listRuleApplications({
      applyScope: scope === "all" ? undefined : scope,
      fundId: fundId === "all" ? undefined : fundId,
      activeOnly,
      limit: 500,
    }).then((response) => response.data),
  })

  const rules = useMemo(() => rulesQuery.data?.items ?? [], [rulesQuery.data])

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["rule-applications"] })
  }

  const save = useMutation({
    mutationFn: (payload: RuleApplicationPayload) => editing
      ? fsiApi.updateRuleApplication(editing.application_id, payload)
      : fsiApi.createRuleApplication(payload),
    onSuccess: () => {
      refresh()
      setDialogOpen(false)
      toast.success(editing ? "应用配置已更新" : "应用配置已创建")
    },
    onError: () => toast.error("应用配置保存失败，请检查是否重复绑定或字段不完整"),
  })
  const deactivate = useMutation({
    mutationFn: (applicationId: number) => fsiApi.deactivateRuleApplication(applicationId),
    onSuccess: () => {
      refresh()
      toast.success("应用配置已停用")
    },
    onError: () => toast.error("停用失败"),
  })
  const reactivate = useMutation({
    mutationFn: (applicationId: number) => fsiApi.updateRuleApplication(applicationId, { is_active: true }),
    onSuccess: () => {
      refresh()
      toast.success("应用配置已启用")
    },
    onError: () => toast.error("启用失败"),
  })

  function openCreate() {
    setEditing(null)
    const next = emptyForm()
    const firstActiveRule = rules.find((rule) => rule.is_active)
    if (firstActiveRule) next.ruleRef = `${firstActiveRule.rule_type}:${firstActiveRule.id}`
    setForm(next)
    setDialogOpen(true)
  }

  function openEdit(application: RuleApplication) {
    setEditing(application)
    setForm(formFromApplication(application))
    setDialogOpen(true)
  }

  function submit() {
    const [ruleType, ruleIdText] = form.ruleRef.split(":")
    const ruleId = Number(ruleIdText)
    if (!ruleType || !ruleId || !form.effective_date) {
      toast.error("请选择规则并填写生效日期")
      return
    }
    if (form.apply_scope === "portfolio" && !form.port_id) {
      toast.error("组合检查必须选择目标组合")
      return
    }
    if (form.apply_scope !== "portfolio" && !form.port_id && !form.strategy_code && !form.instrument_type) {
      toast.error("交易场景至少填写组合、策略或工具类型之一")
      return
    }
    const priority = Number(form.priority)
    if (!Number.isFinite(priority) || priority < 1 || priority > 1000) {
      toast.error("优先级必须为 1 至 1000")
      return
    }

    save.mutate({
      rule_type: ruleType as RiskRuleType,
      rule_id: ruleId,
      apply_scope: form.apply_scope,
      port_id: form.port_id || null,
      strategy_code: form.strategy_code.trim() || null,
      instrument_type: form.instrument_type.trim() || null,
      trade_side: form.apply_scope === "portfolio" ? null : form.trade_side,
      priority,
      effective_date: form.effective_date,
      expiry_date: form.expiry_date || null,
      is_active: form.is_active,
      note: form.note.trim() || null,
    })
  }

  const set = <K extends keyof ApplicationForm>(key: K, value: ApplicationForm[K]) => {
    setForm((previous) => ({ ...previous, [key]: value }))
  }

  return (
    <>
      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-4">
          <div>
            <CardTitle className="text-base">第二部分 · 规则应用配置</CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">
              将规则库中的规则绑定到组合、交易前、交易或交易后场景；仅有效期内且启用的绑定参与实际检查。
            </p>
          </div>
          <Button onClick={openCreate} disabled={!rules.length}>
            <Plus className="mr-1 h-4 w-4" />新增应用配置
          </Button>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 md:grid-cols-[220px_220px_auto] md:items-center">
            <Select value={scope} onValueChange={(value) => setScope(value as "all" | RuleApplyScope)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部应用场景</SelectItem>
                {Object.entries(SCOPE_LABELS).map(([value, label]) => <SelectItem key={value} value={value}>{label}</SelectItem>)}
              </SelectContent>
            </Select>
            <Select value={fundId} onValueChange={setFundId}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部组合</SelectItem>
                {FUNDS.map((fund) => <SelectItem key={fund.id} value={fund.id}>{fund.name}</SelectItem>)}
              </SelectContent>
            </Select>
            <label className="flex items-center gap-2 text-sm">
              <Switch checked={activeOnly} onCheckedChange={setActiveOnly} />仅显示启用
            </label>
          </div>

          <div className="text-xs text-muted-foreground">
            当前显示 {applicationsQuery.data?.items.length ?? 0} / {applicationsQuery.data?.count ?? 0} 条应用配置
          </div>

          <div className="max-h-[36vh] min-h-[240px] overflow-auto rounded-md border">
            <Table>
              <TableHeader className="sticky top-0 z-10 bg-background">
                <TableRow>
                  <TableHead>规则</TableHead>
                  <TableHead>应用场景</TableHead>
                  <TableHead>应用目标</TableHead>
                  <TableHead>优先级</TableHead>
                  <TableHead>有效期</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(applicationsQuery.data?.items ?? []).map((application) => (
                  <TableRow key={application.application_id}>
                    <TableCell>
                      <div className="font-medium">{application.rule_name ?? application.rule_name_en ?? application.rule_code ?? `#${application.rule_id}`}</div>
                      <div className="text-xs text-muted-foreground">{TYPE_LABELS[application.rule_type]} · {application.rule_code ?? application.rule_id}</div>
                    </TableCell>
                    <TableCell><Badge variant="outline">{SCOPE_LABELS[application.apply_scope]}</Badge></TableCell>
                    <TableCell className="text-xs">{targetLabel(application)}</TableCell>
                    <TableCell>{application.priority}</TableCell>
                    <TableCell className="whitespace-nowrap text-xs">{application.effective_date}<br />{application.expiry_date ?? "∞"}</TableCell>
                    <TableCell><Badge variant={application.is_active ? "default" : "secondary"}>{application.is_active ? "启用" : "停用"}</Badge></TableCell>
                    <TableCell>
                      <div className="flex justify-end gap-1">
                        <Button variant="ghost" size="icon" onClick={() => openEdit(application)} title="编辑"><Pencil className="h-4 w-4" /></Button>
                        {application.is_active
                          ? <Button variant="ghost" size="icon" onClick={() => deactivate.mutate(application.application_id)} title="停用"><Power className="h-4 w-4" /></Button>
                          : <Button variant="ghost" size="icon" onClick={() => reactivate.mutate(application.application_id)} title="启用"><RotateCcw className="h-4 w-4" /></Button>}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
                {!applicationsQuery.isLoading && !(applicationsQuery.data?.items.length) ? (
                  <TableRow><TableCell colSpan={7} className="h-24 text-center text-muted-foreground">暂无应用配置。请点击“新增应用配置”将规则绑定到组合或交易场景。</TableCell></TableRow>
                ) : null}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle>{editing ? "编辑规则应用配置" : "新增规则应用配置"}</DialogTitle>
            <DialogDescription>选择一条规则，并指定它在哪个组合或交易条件下生效。</DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2 md:col-span-2">
              <Label>选择规则</Label>
              <Select value={form.ruleRef} disabled={Boolean(editing)} onValueChange={(value) => set("ruleRef", value)}>
                <SelectTrigger><SelectValue placeholder="请选择监管/合同/内部规则" /></SelectTrigger>
                <SelectContent>
                  {rules.map((rule) => (
                    <SelectItem key={`${rule.rule_type}:${rule.id}`} value={`${rule.rule_type}:${rule.id}`} disabled={!rule.is_active}>
                      {ruleLabel(rule)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>应用场景</Label>
              <Select value={form.apply_scope} onValueChange={(value) => set("apply_scope", value as RuleApplyScope)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {Object.entries(SCOPE_LABELS).map(([value, label]) => <SelectItem key={value} value={value}>{label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>目标组合</Label>
              <Select value={form.port_id || "none"} onValueChange={(value) => set("port_id", value === "none" ? "" : value)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {form.apply_scope !== "portfolio" ? <SelectItem value="none">不限定组合</SelectItem> : null}
                  {FUNDS.map((fund) => <SelectItem key={fund.id} value={fund.id}>{fund.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            {form.apply_scope !== "portfolio" ? (
              <>
                <div className="space-y-2"><Label>策略代码（可选）</Label><Input value={form.strategy_code} onChange={(event) => set("strategy_code", event.target.value)} /></div>
                <div className="space-y-2"><Label>工具类型（可选）</Label><Input value={form.instrument_type} onChange={(event) => set("instrument_type", event.target.value)} placeholder="例如 BOND_CORP" /></div>
                <div className="space-y-2">
                  <Label>交易方向</Label>
                  <Select value={form.trade_side} onValueChange={(value) => set("trade_side", value as "BUY" | "SELL" | "BOTH")}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent><SelectItem value="BOTH">买卖均适用</SelectItem><SelectItem value="BUY">仅买入</SelectItem><SelectItem value="SELL">仅卖出</SelectItem></SelectContent>
                  </Select>
                </div>
              </>
            ) : null}
            <div className="space-y-2"><Label>优先级（1最高）</Label><Input type="number" min={1} max={1000} value={form.priority} onChange={(event) => set("priority", event.target.value)} /></div>
            <div className="space-y-2"><Label>生效日期</Label><Input type="date" value={form.effective_date} onChange={(event) => set("effective_date", event.target.value)} /></div>
            <div className="space-y-2"><Label>失效日期</Label><Input type="date" value={form.expiry_date} onChange={(event) => set("expiry_date", event.target.value)} /></div>
            <label className="flex items-center gap-2 pt-7 text-sm"><Switch checked={form.is_active} onCheckedChange={(value) => set("is_active", value)} />启用应用配置</label>
            <div className="space-y-2 md:col-span-2"><Label>配置说明</Label><Textarea rows={3} value={form.note} onChange={(event) => set("note", event.target.value)} /></div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>取消</Button>
            <Button onClick={submit} disabled={save.isPending}>{save.isPending ? "保存中..." : "保存应用配置"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
