// NOTE: `label` fields are the original Chinese display strings, retained for
// backward compatibility with non-i18n consumers (e.g. expert.tsx). The Chat UI
// resolves display text via the `labelKey` / `tagKey` i18n keys instead.
export const FALLBACK_MODELS = [
  { id: "claude-sonnet-4-6",         label: "Claude Sonnet 4.6（推薦）",   baseLabel: "Claude Sonnet 4.6",  tagKey: "chat.tagRecommended",    provider: "anthropic"  as const, default: true  },
  { id: "claude-opus-4-5",           label: "Claude Opus 4.5（最強）",     baseLabel: "Claude Opus 4.5",    tagKey: "chat.tagStrongest",      provider: "anthropic"  as const, default: false },
  { id: "claude-haiku-4-5-20251001", label: "Claude Haiku 4.5（最快）",    baseLabel: "Claude Haiku 4.5",   tagKey: "chat.tagFastest",        provider: "anthropic"  as const, default: false },
  { id: "gemini-2.0-flash",          label: "Gemini 2.0 Flash",           baseLabel: "Gemini 2.0 Flash",   tagKey: null,                     provider: "gemini"     as const, default: false },
  { id: "gemini-1.5-pro",            label: "Gemini 1.5 Pro",             baseLabel: "Gemini 1.5 Pro",     tagKey: null,                     provider: "gemini"     as const, default: false },
  { id: "gpt-4o",                    label: "GPT-4o",                     baseLabel: "GPT-4o",             tagKey: null,                     provider: "openai"     as const, default: false },
  { id: "gpt-4o-mini",               label: "GPT-4o Mini",                baseLabel: "GPT-4o Mini",        tagKey: null,                     provider: "openai"     as const, default: false },
  { id: "moonshot-v1-32k",           label: "Kimi moonshot-v1-32k（推薦）",baseLabel: "Kimi moonshot-v1-32k",  tagKey: "chat.tagRecommended", provider: "moonshot"   as const, default: false },
  { id: "moonshot-v1-128k",          label: "Kimi moonshot-v1-128k（長文）",baseLabel: "Kimi moonshot-v1-128k", tagKey: "chat.tagLongContext", provider: "moonshot"  as const, default: false },
  { id: "deepseek-chat",             label: "DeepSeek Chat V3（推薦）",    baseLabel: "DeepSeek Chat V3",   tagKey: "chat.tagRecommended",    provider: "deepseek"   as const, default: false },
  { id: "deepseek-reasoner",         label: "DeepSeek R1（推理增強）",     baseLabel: "DeepSeek R1",        tagKey: "chat.tagReasoning",      provider: "deepseek"   as const, default: false },
  { id: "x-ai/grok-4.20",           label: "xAI Grok 4.20（最新旗艦）",  baseLabel: "xAI Grok 4.20",       tagKey: "chat.tagLatestFlagship", provider: "openrouter" as const, default: false },
  { id: "x-ai/grok-4.3",            label: "xAI Grok 4.3",              baseLabel: "xAI Grok 4.3",         tagKey: null,                     provider: "openrouter" as const, default: false },
]

export const MODEL_GROUPS = [
  { key: "anthropic",  label: "Anthropic Claude",   labelKey: "chat.groupAnthropic",  icon: "◆", color: "text-blue-600"   },
  { key: "gemini",     label: "Google Gemini",       labelKey: "chat.groupGemini",     icon: "▲", color: "text-orange-500" },
  { key: "openai",     label: "OpenAI GPT",          labelKey: "chat.groupOpenai",     icon: "●", color: "text-green-600"  },
  { key: "moonshot",   label: "Kimi 月之暗面",       labelKey: "chat.groupMoonshot",   icon: "★", color: "text-purple-500" },
  { key: "deepseek",   label: "DeepSeek 深度求索",   labelKey: "chat.groupDeepseek",   icon: "■", color: "text-cyan-600"   },
  { key: "openrouter", label: "xAI Grok",            labelKey: "chat.groupOpenrouter", icon: "✦", color: "text-rose-500"   },
] as const

export const FALLBACK_AGENTS = [
  { id: "general",            name: "通用助理",           nameKey: "chat.agentGeneral" },
  { id: "risk-analyst",       name: "ARISK 風控分析師",   nameKey: "chat.agentRiskAnalyst" },
  { id: "compliance-officer", name: "SFC 合規審查員",     nameKey: "chat.agentComplianceOfficer" },
  { id: "fund-reporter",      name: "基金報表助理",       nameKey: "chat.agentFundReporter" },
  { id: "market-researcher",  name: "市場研究員",         nameKey: "chat.agentMarketResearcher" },
]
