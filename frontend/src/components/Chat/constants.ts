export const FALLBACK_MODELS = [
  { id: "claude-sonnet-4-6",         label: "Claude Sonnet 4.6（推薦）",   provider: "anthropic"  as const, default: true  },
  { id: "claude-opus-4-5",           label: "Claude Opus 4.5（最強）",     provider: "anthropic"  as const, default: false },
  { id: "claude-haiku-4-5-20251001", label: "Claude Haiku 4.5（最快）",    provider: "anthropic"  as const, default: false },
  { id: "gemini-2.0-flash",          label: "Gemini 2.0 Flash",           provider: "gemini"     as const, default: false },
  { id: "gemini-1.5-pro",            label: "Gemini 1.5 Pro",             provider: "gemini"     as const, default: false },
  { id: "gpt-4o",                    label: "GPT-4o",                     provider: "openai"     as const, default: false },
  { id: "gpt-4o-mini",               label: "GPT-4o Mini",                provider: "openai"     as const, default: false },
  { id: "moonshot-v1-32k",           label: "Kimi moonshot-v1-32k（推薦）",provider: "moonshot"   as const, default: false },
  { id: "moonshot-v1-128k",          label: "Kimi moonshot-v1-128k（長文）",provider: "moonshot"  as const, default: false },
  { id: "deepseek-chat",             label: "DeepSeek Chat V3（推薦）",    provider: "deepseek"   as const, default: false },
  { id: "deepseek-reasoner",         label: "DeepSeek R1（推理增強）",     provider: "deepseek"   as const, default: false },
  { id: "x-ai/grok-4.20",           label: "xAI Grok 4.20（最新旗艦）",  provider: "openrouter" as const, default: false },
  { id: "x-ai/grok-4.3",            label: "xAI Grok 4.3",              provider: "openrouter" as const, default: false },
]

export const MODEL_GROUPS = [
  { key: "anthropic",  label: "Anthropic Claude",   icon: "◆", color: "text-blue-600"   },
  { key: "gemini",     label: "Google Gemini",       icon: "▲", color: "text-orange-500" },
  { key: "openai",     label: "OpenAI GPT",          icon: "●", color: "text-green-600"  },
  { key: "moonshot",   label: "Kimi 月之暗面",       icon: "★", color: "text-purple-500" },
  { key: "deepseek",   label: "DeepSeek 深度求索",   icon: "■", color: "text-cyan-600"   },
  { key: "openrouter", label: "xAI Grok",            icon: "✦", color: "text-rose-500"   },
] as const

export const FALLBACK_AGENTS = [
  { id: "general",            name: "通用助理" },
  { id: "risk-analyst",       name: "ARISK 風控分析師" },
  { id: "compliance-officer", name: "SFC 合規審查員" },
  { id: "fund-reporter",      name: "基金報表助理" },
  { id: "market-researcher",  name: "市場研究員" },
]
