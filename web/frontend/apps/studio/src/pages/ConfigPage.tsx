import React, { useState, useEffect } from "react";
import { Save, RefreshCw, SlidersHorizontal, Settings2, Image as ImageIcon, AlertTriangle } from "lucide-react";
import { Button, Input } from "@writerlm/ui";
import { ApiClient, PipelineConfig, ProviderModel, friendlyApiErrorMessage } from "../api";

interface ConfigPageProps {
  api: ApiClient;
  onNotice: (message: string) => void;
}

function Toggle({ checked, onChange, disabled }: { checked: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative w-8 h-4 rounded-full transition-colors flex-none ${checked ? "bg-success" : "bg-muted-foreground/30"} ${disabled ? "opacity-40 cursor-not-allowed" : "cursor-pointer"}`}
    >
      <span className={`absolute top-0.5 w-3 h-3 rounded-full bg-white shadow-sm transition-transform ${checked ? "translate-x-4" : "translate-x-0.5"}`} />
    </button>
  );
}

function ModelSelect({
  label,
  value,
  models,
  loading,
  onChange,
}: {
  label: string;
  value: string;
  models: ProviderModel[];
  loading: boolean;
  onChange: (v: string) => void;
}) {
  const hasCurrent = models.some(model => model.id === value);
  return (
    <div>
      <label className="block text-[10px] font-medium text-muted-foreground mb-1">{label}</label>
      {models.length ? (
        <select
          value={value}
          onChange={e => onChange(e.target.value)}
          className="w-full h-8 bg-input border border-input text-foreground rounded-md px-2 text-xs font-mono outline-none focus:ring-1 focus:ring-ring"
        >
          {!hasCurrent && value && <option value={value}>{value}</option>}
          {models.map(model => (
            <option key={model.id} value={model.id}>{model.label === model.id ? model.id : `${model.label} - ${model.id}`}</option>
          ))}
        </select>
      ) : (
        <Input
          value={value}
          onChange={e => onChange(e.target.value)}
          placeholder={loading ? "Loading models..." : "Enter model id..."}
          className="h-8 text-xs font-mono"
        />
      )}
    </div>
  );
}

function Section({ icon: Icon, title, subtitle, children }: { icon: any; title: string; subtitle: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-border bg-card">
      <div className="flex items-center gap-3 px-5 py-4 border-b border-border">
        <div className="w-7 h-7 rounded-md bg-secondary flex items-center justify-center flex-none">
          <Icon size={14} className="text-muted-foreground" />
        </div>
        <div>
          <p className="text-sm font-semibold text-foreground">{title}</p>
          <p className="text-[11px] text-muted-foreground">{subtitle}</p>
        </div>
      </div>
      <div className="p-5 space-y-5">{children}</div>
    </div>
  );
}

function Row({ label, description, children }: { label: string; description?: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <div className="min-w-0">
        <p className="text-sm font-medium text-foreground">{label}</p>
        {description && <p className="text-[11px] text-muted-foreground mt-0.5">{description}</p>}
      </div>
      <div className="flex-none">{children}</div>
    </div>
  );
}

export function ConfigPage({ api, onNotice }: ConfigPageProps) {
  const [config, setConfig] = useState<PipelineConfig | null>(null);
  const [saving, setSaving] = useState(false);
  const [models, setModels] = useState<{ google: ProviderModel[]; groq: ProviderModel[]; ollama: ProviderModel[] }>({ google: [], groq: [], ollama: [] });
  const [loadingModels, setLoadingModels] = useState<{ google: boolean; groq: boolean; ollama: boolean }>({ google: false, groq: false, ollama: false });
  const [modelErrors, setModelErrors] = useState<{ google: string | null; groq: string | null; ollama: string | null }>({ google: null, groq: null, ollama: null });

  useEffect(() => { api.config().then(setConfig).catch(e => onNotice(friendlyApiErrorMessage(e, "Failed to load config."))); }, []);

  async function loadModels(provider: "google" | "groq" | "ollama") {
    setLoadingModels(prev => ({ ...prev, [provider]: true }));
    setModelErrors(prev => ({ ...prev, [provider]: null }));
    try {
      const data = await api.providerModels(provider);
      setModels(prev => ({ ...prev, [provider]: data }));
    } catch (e) {
      const message = friendlyApiErrorMessage(e, `Could not load ${provider} models.`);
      setModelErrors(prev => ({ ...prev, [provider]: message }));
    } finally {
      setLoadingModels(prev => ({ ...prev, [provider]: false }));
    }
  }

  useEffect(() => {
    loadModels("google");
    loadModels("groq");
    loadModels("ollama");
  }, [api]);

  async function save() {
    if (!config) return;
    setSaving(true);
    try {
      const s = await api.saveConfig(config);
      setConfig(s);
      onNotice("Configuration saved.");
    } catch (e) { onNotice(friendlyApiErrorMessage(e, "Failed to save.")); }
    finally { setSaving(false); }
  }

  const upd = (patch: Partial<PipelineConfig>) => setConfig(c => c ? { ...c, ...patch } : c);

  if (!config) return (
    <div className="flex items-center justify-center py-40">
      <RefreshCw size={18} className="animate-spin text-muted-foreground/30" />
    </div>
  );

  return (
    <div className="px-5 max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-6 pb-4 border-b border-border">
        <h2 className="text-base font-semibold text-foreground">Pipeline Settings</h2>
        <Button size="sm" onClick={save} disabled={saving}>
          {saving ? <RefreshCw size={13} className="animate-spin" /> : <Save size={13} />}
          {saving ? "Saving…" : "Save changes"}
        </Button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <div className="lg:col-span-2 space-y-5">
          {/* LLM routing */}
          <Section icon={SlidersHorizontal} title="Provider Routing" subtitle="Configure LLM inference and research strategy">
            <Row label="Default LLM provider">
              <div className="flex bg-secondary border border-border rounded-md p-0.5 gap-0.5">
                {["google", "groq", "ollama"].map(opt => (
                  <button key={opt} onClick={() => upd({ llm_provider: opt as any })}
                    className={`px-4 py-1 text-xs font-medium rounded-sm transition-colors capitalize cursor-pointer ${config.llm_provider === opt ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"}`}
                  >{opt}</button>
                ))}
              </div>
            </Row>

            <Row label="Automatic model routing" description="Let an LLM pick the best model per stage for your book's domain">
              <Toggle checked={config.auto_model_routing} onChange={v => upd({ auto_model_routing: v })} />
            </Row>

            <Row label="Research profile" description="Controls how much research effort is applied">
              <select
                className="h-7 bg-input border border-input text-foreground rounded-md px-2 text-xs outline-none focus:ring-1 focus:ring-ring"
                value={config.research_execution_profile}
                onChange={e => upd({ research_execution_profile: e.target.value as any })}
              >
                <option value="budget">Budget — fast, low cost</option>
                <option value="full">Full — deep research</option>
                <option value="debug">Debug — minimal</option>
              </select>
            </Row>
          </Section>

          {/* Runtime */}
          <Section icon={Settings2} title="Runtime Pipeline" subtitle="Execution and compilation controls">
            <Row label="Parallel section writing" description="Write multiple sections simultaneously">
              <Toggle checked={config.parallel_section_pipeline} onChange={v => upd({ parallel_section_pipeline: v })} />
            </Row>
            {config.parallel_section_pipeline && (
              <Row label="Concurrency" description="Max concurrent writing workers">
                <Input type="number" className="w-20 h-7 text-xs text-center" min={1} max={10}
                  value={config.section_pipeline_concurrency}
                  onChange={e => upd({ section_pipeline_concurrency: parseInt(e.target.value) || 1 })} />
              </Row>
            )}
            <div className="h-px bg-border" />
            <Row label="Compile LaTeX to PDF">
              <Toggle checked={config.compile_latex} onChange={v => upd({ compile_latex: v })} />
            </Row>
            {config.compile_latex && (
              <>
                <Row label="Strict LaTeX compile" description="Fail if any LaTeX errors occur">
                  <Toggle checked={config.strict_latex_compile} onChange={v => upd({ strict_latex_compile: v })} />
                </Row>
                <Row label="LaTeX engine">
                  <select className="h-7 bg-input border border-input text-foreground rounded-md px-2 text-xs outline-none focus:ring-1 focus:ring-ring"
                    value={config.latex_engine} onChange={e => upd({ latex_engine: e.target.value as any })}>
                    <option value="pdflatex">pdfLaTeX</option>
                    <option value="xelatex">XeLaTeX</option>
                    <option value="lualatex">LuaLaTeX</option>
                  </select>
                </Row>
              </>
            )}
          </Section>

          {/* Images */}
          <Section icon={ImageIcon} title="Visual Assets" subtitle="Image generation and sourcing options">
            <Row label="Enable image assets">
              <Toggle checked={config.image_assets_enabled} onChange={v => upd({ image_assets_enabled: v })} />
            </Row>
            {config.image_assets_enabled && (
              <>
                <Row label="Web image search"><Toggle checked={config.web_image_search_enabled} onChange={v => upd({ web_image_search_enabled: v })} /></Row>
                <Row label="AI image generation"><Toggle checked={config.generated_images_enabled} onChange={v => upd({ generated_images_enabled: v })} /></Row>
                {config.generated_images_enabled && (
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="text-[10px] font-medium text-muted-foreground block mb-1">Generation model</label>
                      <Input className="h-7 text-xs" value={config.image_generation_model} onChange={e => upd({ image_generation_model: e.target.value })} />
                    </div>
                    <div>
                      <label className="text-[10px] font-medium text-muted-foreground block mb-1">Max per book</label>
                      <Input type="number" className="h-7 text-xs" value={config.max_image_assets} onChange={e => upd({ max_image_assets: parseInt(e.target.value) || 0 })} />
                    </div>
                  </div>
                )}
              </>
            )}
          </Section>
        </div>

        {/* Model overrides */}
        <div>
          <div className="rounded-xl border border-red-500/20 bg-red-500/5">
            <div className="flex items-center gap-2 px-5 py-4 border-b border-red-500/20">
              <AlertTriangle size={14} className="text-red-400 flex-none" />
              <p className="text-sm font-semibold text-foreground">Model Overrides</p>
            </div>
            <div className="p-5 space-y-5">
              <p className="text-[11px] text-muted-foreground leading-relaxed">Override default models for each pipeline stage. Use with caution.</p>
              <div className="space-y-3">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Google</p>
                  <button type="button" onClick={() => loadModels("google")} className="text-[10px] text-muted-foreground hover:text-foreground transition-colors cursor-pointer">
                    {loadingModels.google ? "Loading..." : "Refresh"}
                  </button>
                </div>
                {modelErrors.google && <p className="text-[11px] text-red-300 leading-relaxed">{modelErrors.google}</p>}
                <ModelSelect label="Planner" value={config.planner_google_model} models={models.google} loading={loadingModels.google} onChange={v => upd({ planner_google_model: v })} />
                <ModelSelect label="Researcher" value={config.researcher_google_model} models={models.google} loading={loadingModels.google} onChange={v => upd({ researcher_google_model: v })} />
                <ModelSelect label="Notes" value={config.notes_google_model} models={models.google} loading={loadingModels.google} onChange={v => upd({ notes_google_model: v })} />
                <ModelSelect label="Writer" value={config.writer_google_model} models={models.google} loading={loadingModels.google} onChange={v => upd({ writer_google_model: v })} />
                <ModelSelect label="Reviewer" value={config.reviewer_google_model} models={models.google} loading={loadingModels.google} onChange={v => upd({ reviewer_google_model: v })} />
              </div>
              <div className="space-y-3">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Groq</p>
                  <button type="button" onClick={() => loadModels("groq")} className="text-[10px] text-muted-foreground hover:text-foreground transition-colors cursor-pointer">
                    {loadingModels.groq ? "Loading..." : "Refresh"}
                  </button>
                </div>
                {modelErrors.groq && <p className="text-[11px] text-red-300 leading-relaxed">{modelErrors.groq}</p>}
                <ModelSelect label="Planner" value={config.planner_groq_model} models={models.groq} loading={loadingModels.groq} onChange={v => upd({ planner_groq_model: v })} />
                <ModelSelect label="Researcher" value={config.researcher_groq_model} models={models.groq} loading={loadingModels.groq} onChange={v => upd({ researcher_groq_model: v })} />
                <ModelSelect label="Notes" value={config.notes_groq_model} models={models.groq} loading={loadingModels.groq} onChange={v => upd({ notes_groq_model: v })} />
                <ModelSelect label="Writer" value={config.writer_groq_model} models={models.groq} loading={loadingModels.groq} onChange={v => upd({ writer_groq_model: v })} />
                <ModelSelect label="Reviewer" value={config.reviewer_groq_model} models={models.groq} loading={loadingModels.groq} onChange={v => upd({ reviewer_groq_model: v })} />
              </div>
              <div className="space-y-3">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Ollama</p>
                  <button type="button" onClick={() => loadModels("ollama")} className="text-[10px] text-muted-foreground hover:text-foreground transition-colors cursor-pointer">
                    {loadingModels.ollama ? "Loading..." : "Refresh"}
                  </button>
                </div>
                {modelErrors.ollama && <p className="text-[11px] text-red-300 leading-relaxed">{modelErrors.ollama}</p>}
                <ModelSelect label="Planner" value={config.planner_ollama_model} models={models.ollama} loading={loadingModels.ollama} onChange={v => upd({ planner_ollama_model: v })} />
                <ModelSelect label="Researcher" value={config.researcher_ollama_model} models={models.ollama} loading={loadingModels.ollama} onChange={v => upd({ researcher_ollama_model: v })} />
                <ModelSelect label="Notes" value={config.notes_ollama_model} models={models.ollama} loading={loadingModels.ollama} onChange={v => upd({ notes_ollama_model: v })} />
                <ModelSelect label="Writer" value={config.writer_ollama_model} models={models.ollama} loading={loadingModels.ollama} onChange={v => upd({ writer_ollama_model: v })} />
                <ModelSelect label="Reviewer" value={config.reviewer_ollama_model} models={models.ollama} loading={loadingModels.ollama} onChange={v => upd({ reviewer_ollama_model: v })} />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
