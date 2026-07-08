import React, { useState, useEffect } from "react";
import { KeyRound, Eye, EyeOff, RefreshCw, Upload, AlertCircle } from "lucide-react";
import { Button, Input } from "@writerlm/ui";
import { ApiClient, ApiKeyProvider } from "../api";

interface KeysPageProps {
  api: ApiClient;
  onNotice: (message: string) => void;
}

const PROVIDERS: { id: ApiKeyProvider; label: string; hint: string }[] = [
  { id: "google",    label: "Google AI",  hint: "Used for Gemini models (planner, writer, researcher)" },
  { id: "groq",      label: "Groq",       hint: "Used for fast LLM inference (Llama, Mixtral)" },
  { id: "ollama",    label: "Ollama",     hint: "Ollama cloud API key (ollama.com) for cloud models" },
  { id: "tavily",    label: "Tavily",     hint: "Used for web research search results" },
  { id: "firecrawl", label: "Firecrawl", hint: "Used for web scraping and content extraction" },
];

export function KeysPage({ api, onNotice }: KeysPageProps) {
  const [hints, setHints] = useState<Record<string, string>>({});
  const [values, setValues] = useState<Record<string, string>>({});
  const [visible, setVisible] = useState<Record<string, boolean>>({});
  const [saving, setSaving] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    try {
      const data = await api.apiKeys();
      const h: Record<string, string> = {};
      data.forEach(r => { h[r.provider] = r.key_hint; });
      setHints(h);
    } catch { onNotice("Failed to load key metadata."); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  async function save(provider: ApiKeyProvider) {
    if (!values[provider]) return;
    setSaving(provider);
    try {
      await api.saveApiKey(provider, values[provider]);
      setValues(v => { const n = { ...v }; delete n[provider]; return n; });
      onNotice(`${provider} API key updated.`);
      load();
    } catch { onNotice(`Failed to save ${provider} key.`); }
    finally { setSaving(null); }
  }

  const importEnv = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = evt => {
      const lines = (evt.target?.result as string).split("\n");
      const next = { ...values };
      lines.forEach(line => {
        const [k, v] = line.split("=");
        if (!k || !v) return;
        const pid = k.trim().toLowerCase().replace("_api_key", "") as ApiKeyProvider;
        if (PROVIDERS.some(p => p.id === pid)) next[pid] = v.trim().replace(/^["']|["']$/g, "");
      });
      setValues(next);
      onNotice("Keys imported from file — review and save each one.");
    };
    reader.readAsText(file);
  };

  if (loading) return (
    <div className="flex items-center justify-center py-40">
      <RefreshCw size={18} className="animate-spin text-muted-foreground/30" />
    </div>
  );

  return (
    <div className="px-5 max-w-2xl mx-auto">
      <div className="flex items-center justify-between mb-6 pb-4 border-b border-border">
        <h2 className="text-base font-semibold text-foreground">API Credentials</h2>
        <label>
          <input type="file" accept=".env,.txt" className="hidden" onChange={importEnv} />
          <Button variant="outline" size="sm" className="cursor-pointer" onClick={() => {}}>
            <Upload size={13} /> Import .env
          </Button>
        </label>
      </div>

      <div className="space-y-3">
        {PROVIDERS.map(({ id, label, hint }) => (
          <div key={id} className="rounded-xl border border-border bg-card p-5">
            <div className="flex items-center gap-3 mb-1">
              <div className="w-7 h-7 rounded-md bg-secondary flex items-center justify-center flex-none">
                <KeyRound size={13} className="text-muted-foreground" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-foreground">{label}</span>
                  {hints[id] && (
                    <span className="font-mono text-[10px] text-muted-foreground bg-secondary border border-border px-1.5 py-0.5 rounded">
                      ••• {hints[id]}
                    </span>
                  )}
                </div>
                <p className="text-[11px] text-muted-foreground mt-0.5">{hint}</p>
              </div>
            </div>

            <div className="flex gap-2 mt-3">
              <div className="relative flex-1">
                <Input
                  type={visible[id] ? "text" : "password"}
                  value={values[id] ?? ""}
                  onChange={e => setValues(v => ({ ...v, [id]: e.target.value }))}
                  placeholder={hints[id] ? "Enter new key to update…" : "Enter API key…"}
                  className="font-mono text-xs pr-9"
                />
                <button
                  type="button"
                  onClick={() => setVisible(v => ({ ...v, [id]: !v[id] }))}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                >
                  {visible[id] ? <EyeOff size={13} /> : <Eye size={13} />}
                </button>
              </div>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => save(id)}
                disabled={saving === id || !values[id]}
                className="min-w-[60px]"
              >
                {saving === id ? <RefreshCw size={12} className="animate-spin" /> : "Save"}
              </Button>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-5 flex items-start gap-2.5 text-xs text-muted-foreground p-4 rounded-xl border border-border bg-card">
        <AlertCircle size={14} className="flex-none mt-0.5" />
        <p>Keys are encrypted at rest and used exclusively during background pipeline execution. They are never logged.</p>
      </div>
    </div>
  );
}
