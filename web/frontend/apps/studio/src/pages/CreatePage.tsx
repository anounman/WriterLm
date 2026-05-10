import React, { useState, useRef } from "react";
import { FileText, X, ArrowRight, RefreshCw, Upload, Play, Plus, Globe, Check, ChevronDown } from "lucide-react";
import { Button, Card, Input } from "@writerlm/ui";
import { ApiClient, BookRequest, CodeDensity, Job, friendlyApiErrorMessage, GenerationContract, DepthLevel, ImplementationStyle, SectionStyle, CodeArtifactPolicy } from "../api";

interface CreatePageProps {
  api: ApiClient;
  onCreated: (job: Job) => void;
  onNotice: (message: string) => void;
}

const defaultBookRequest: BookRequest = {
  topic: "", audience: "Professionals and students", tone: "Technical and clear",
  book_type: "auto", theory_practice_balance: "balanced", pedagogy_style: "auto",
  source_usage: "auto", exercise_strategy: "extract_patterns", goals: [],
  project_based: false, running_project_description: null, code_density: "none",
  example_density: "high", diagram_density: "medium", max_section_words: 900,
  force_web_research: true, language_request: null, urls: [],
  target_quality_score: 75, max_repair_passes: 2, hard_fail_threshold: 45,
  auto_repair: true, sample_first: false, quality_mode: "full_auto_repair",
};

const CODE_DENSITY_OPTIONS = [
  { value: "none", label: "None — no code examples" },
  { value: "low", label: "Low — rare code only when clearly useful" },
  { value: "medium", label: "Medium — balanced technical examples" },
  { value: "high", label: "High — code-heavy implementation" },
] as const;

export function CreatePage({ api, onCreated, onNotice }: CreatePageProps) {
  const [promptMode, setPromptMode] = useState(true);
  const [promptText, setPromptText] = useState("");
  const [parsing, setParsing] = useState(false);
  const [request, setRequest] = useState<BookRequest>(defaultBookRequest);
  const [goalText, setGoalText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [pdfFiles, setPdfFiles] = useState<File[]>([]);
  const [showAttachMenu, setShowAttachMenu] = useState(false);
  const [qualityEstimate, setQualityEstimate] = useState<any>(null);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const promptFileRef = useRef<HTMLInputElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const hasPdfs = pdfFiles.length > 0;
  // Web research is always on when no PDFs; user can toggle when PDFs present
  const webResearchActive = request.force_web_research || !hasPdfs;

  async function handlePromptSubmit(e?: React.SyntheticEvent) {
    e?.preventDefault();
    if (!promptText.trim()) return;
    setParsing(true);
    try {
      const parsed = await api.parsePrompt(promptText);
      setRequest(r => ({ ...r, ...parsed, force_web_research: webResearchActive }));
      if (parsed.goals?.length) setGoalText(parsed.goals.join("\n"));
      setPromptMode(false);
    } catch {
      onNotice("Could not parse prompt — switching to manual mode.");
      setPromptMode(false);
    } finally { setParsing(false); }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    const finalReq = { ...request, force_web_research: webResearchActive, goals: goalText.split("\n").map(s => s.trim()).filter(Boolean) };
    try {
      const job = hasPdfs ? await api.createJobWithPdfs(finalReq, pdfFiles) : await api.createJob(finalReq);
      onCreated(job);
      onNotice(`Job #${job.id} started. Book generation can take several hours, so it is okay to come back later.`);
    } catch (err) {
      onNotice(friendlyApiErrorMessage(err, "Could not start job."));
    } finally { setSubmitting(false); }
  }

  async function refreshQualityEstimate(nextRequest = request) {
    try {
      const finalReq = { ...nextRequest, force_web_research: webResearchActive, goals: goalText.split("\n").map(s => s.trim()).filter(Boolean) };
      if (!finalReq.topic.trim() || !finalReq.audience.trim()) return;
      setQualityEstimate(await api.qualityEstimate(finalReq));
    } catch {
      setQualityEstimate(null);
    }
  }

  const addFiles = (fl: FileList | File[]) => {
    const valid = Array.from(fl).filter(f => f.name.toLowerCase().endsWith(".pdf"));
    if (!valid.length) { onNotice("Only PDF files are accepted."); return; }
    setPdfFiles(prev => {
      const existing = new Set(prev.map(f => f.name));
      const next = [...prev, ...valid.filter(f => !existing.has(f.name))];
      if (prev.length === 0 && next.length > 0) setRequest(r => ({ ...r, force_web_research: false }));
      return next;
    });
  };

  const removeFile = (name: string) => setPdfFiles(prev => {
    const next = prev.filter(f => f.name !== name);
    if (next.length === 0) setRequest(r => ({ ...r, force_web_research: true }));
    return next;
  });

  // ── Prompt mode ──────────────────────────────────────────
  if (promptMode) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[calc(100vh-200px)] px-4">
        <div className="w-full max-w-2xl">
          <div className="mb-8 text-center">
            <h1 className="text-2xl font-semibold tracking-tight text-foreground mb-2">What do you want to build?</h1>
            <p className="text-sm text-muted-foreground">Describe your book or technical document and we'll configure the pipeline.</p>
          </div>

          {/* Chat-style input */}
          <div className="rounded-xl border border-border bg-card overflow-hidden shadow-lg">
            <textarea
              className="w-full min-h-[120px] bg-transparent border-none outline-none p-4 text-sm text-foreground placeholder:text-muted-foreground resize-none leading-relaxed"
              placeholder="e.g. Write a comprehensive guide on Kubernetes architecture for senior DevOps engineers with hands-on labs…"
              value={promptText}
              onChange={e => setPromptText(e.target.value)}
              onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handlePromptSubmit(); } }}
            />

            {/* Attachments pills */}
            {(hasPdfs || webResearchActive) && (
              <div className="flex items-center gap-2 px-4 py-2 border-t border-border bg-secondary/30">
                {webResearchActive && (
                  <span className="inline-flex items-center gap-1 text-[11px] font-medium text-success bg-success/10 border border-success/20 px-2 py-0.5 rounded-full">
                    <Globe size={10} /> Web
                    {hasPdfs && <button onClick={() => setRequest(r => ({ ...r, force_web_research: false }))} className="ml-1 hover:text-success/70"><X size={10}/></button>}
                  </span>
                )}
                {hasPdfs && (
                  <span className="inline-flex items-center gap-1 text-[11px] font-medium text-muted-foreground border border-border px-2 py-0.5 rounded-full">
                    <FileText size={10} /> {pdfFiles.length} PDF{pdfFiles.length > 1 ? "s" : ""}
                    <button onClick={() => { setPdfFiles([]); setRequest(r => ({ ...r, force_web_research: true })); }} className="ml-1 hover:text-foreground"><X size={10}/></button>
                  </span>
                )}
              </div>
            )}

            {/* Toolbar */}
            <div className="flex items-center justify-between p-3 border-t border-border">
              <div className="relative">
                <Button variant="ghost" size="icon" onClick={() => setShowAttachMenu(!showAttachMenu)}>
                  <Plus size={15} />
                </Button>
                {showAttachMenu && (
                  <>
                    <div className="fixed inset-0 z-10" onClick={() => setShowAttachMenu(false)} />
                    <div className="absolute bottom-10 left-0 z-20 w-48 bg-popover border border-border rounded-lg shadow-xl py-1 overflow-hidden">
                      <button
                        className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-foreground hover:bg-accent transition-colors text-left"
                        onClick={() => { promptFileRef.current?.click(); setShowAttachMenu(false); }}
                      >
                        <FileText size={13} className="text-muted-foreground" /> Attach PDF
                      </button>
                      <button
                        disabled={!hasPdfs}
                        className={`w-full flex items-center justify-between px-3 py-2 text-sm transition-colors text-left ${hasPdfs ? "text-foreground hover:bg-accent" : "text-muted-foreground/50 cursor-not-allowed"}`}
                        onClick={() => { if (!hasPdfs) return; setRequest(r => ({ ...r, force_web_research: !r.force_web_research })); setShowAttachMenu(false); }}
                      >
                        <span className="flex items-center gap-2.5"><Globe size={13} className="text-muted-foreground" /> Web search</span>
                        {webResearchActive && <Check size={13} className="text-success" />}
                      </button>
                    </div>
                  </>
                )}
                <input ref={promptFileRef} type="file" accept=".pdf" multiple className="hidden" onChange={e => e.target.files && addFiles(e.target.files)} />
              </div>

              <Button size="sm" disabled={parsing || !promptText.trim()} onClick={handlePromptSubmit}>
                {parsing ? <RefreshCw size={13} className="animate-spin" /> : <><span>Continue</span><ArrowRight size={13} /></>}
              </Button>
            </div>
          </div>

          <p className="text-center mt-4">
            <button className="text-xs text-muted-foreground hover:text-foreground transition-colors underline-offset-4 hover:underline" onClick={() => setPromptMode(false)}>
              Switch to manual setup
            </button>
          </p>
        </div>
      </div>
    );
  }

  // ── Manual mode ──────────────────────────────────────────
  return (
    <div className="px-5 max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-6 pb-4 border-b border-border">
        <h2 className="text-base font-semibold text-foreground">Configuration</h2>
        <Button variant="ghost" size="sm" onClick={() => setPromptMode(true)}>← Back to prompt</Button>
      </div>

      <form onSubmit={handleSubmit} className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Left 2/3 */}
        <div className="lg:col-span-2 space-y-5">
          <Card>
            <div className="p-5">
              <h3 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-4">Subject</h3>
              <div className="space-y-4">
                <div>
                  <label className="text-xs font-medium text-muted-foreground block mb-1.5">Topic *</label>
                  <textarea
                    className="w-full bg-input border border-input rounded-md p-3 text-sm text-foreground focus:ring-1 focus:ring-ring outline-none min-h-[72px] resize-none"
                    value={request.topic} onChange={e => setRequest(r => ({ ...r, topic: e.target.value }))}
                    placeholder="e.g. Kubernetes architecture for DevOps engineers"
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-muted-foreground block mb-1.5">Learning Goals & Constraints</label>
                  <textarea
                    className="w-full bg-input border border-input rounded-md p-3 text-sm text-foreground focus:ring-1 focus:ring-ring outline-none min-h-[80px] resize-none"
                    value={goalText} onChange={e => setGoalText(e.target.value)}
                    placeholder="e.g. Explain habits&#10;Avoid diagnosis or clinical claims&#10;Focus on practical study schedules"
                  />
                  <p className="text-[10px] text-muted-foreground mt-1.5">One goal or constraint per line. These drive the automated quality validators.</p>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-1.5">Audience</label>
                    <Input value={request.audience} onChange={e => setRequest(r => ({ ...r, audience: e.target.value }))} />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-1.5">Tone</label>
                    <Input value={request.tone} onChange={e => setRequest(r => ({ ...r, tone: e.target.value }))} />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-1.5">Language</label>
                    <Input value={request.language_request || ""} placeholder="e.g. Spanish" onChange={e => setRequest(r => ({ ...r, language_request: e.target.value || null }))} />
                  </div>
                </div>
              </div>
            </div>
          </Card>

          <Card>
            <div className="p-5">
              <h3 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-4">Pedagogy & Style</h3>
              <div className="space-y-4">
                <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-1.5">Book Type</label>
                    <select className="w-full h-8 bg-input border border-input text-foreground rounded-md px-3 text-xs focus:ring-1 focus:ring-ring outline-none" value={request.book_type} onChange={e => setRequest(r => ({ ...r, book_type: e.target.value as any }))}>
                      <option value="auto">Auto</option><option value="textbook">Textbook</option><option value="practice_workbook">Practice Workbook</option><option value="course_companion">Course Companion</option><option value="implementation_guide">Implementation Guide</option><option value="reference_handbook">Reference Handbook</option><option value="conceptual_guide">Conceptual Guide</option><option value="exam_prep">Exam Prep</option>
                    </select>
                  </div>
                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-1.5">Theory/Practice</label>
                    <select className="w-full h-8 bg-input border border-input text-foreground rounded-md px-3 text-xs focus:ring-1 focus:ring-ring outline-none" value={request.theory_practice_balance} onChange={e => setRequest(r => ({ ...r, theory_practice_balance: e.target.value as any }))}>
                      <option value="auto">Auto</option><option value="theory_heavy">Theory Heavy</option><option value="balanced">Balanced</option><option value="practice_heavy">Practice Heavy</option><option value="implementation_heavy">Implementation Heavy</option>
                    </select>
                  </div>
                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-1.5">Pedagogy Style</label>
                    <select className="w-full h-8 bg-input border border-input text-foreground rounded-md px-3 text-xs focus:ring-1 focus:ring-ring outline-none" value={request.pedagogy_style} onChange={e => setRequest(r => ({ ...r, pedagogy_style: e.target.value as any }))}>
                      <option value="auto">Auto</option><option value="german_theoretical">German Theoretical</option><option value="indian_theory_then_examples">Indian (Theory then Examples)</option><option value="socratic">Socratic</option><option value="exam_oriented">Exam Oriented</option><option value="project_based">Project Based</option>
                    </select>
                  </div>
                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-1.5">Source Usage</label>
                    <select className="w-full h-8 bg-input border border-input text-foreground rounded-md px-3 text-xs focus:ring-1 focus:ring-ring outline-none" value={request.source_usage} onChange={e => setRequest(r => ({ ...r, source_usage: e.target.value as any }))}>
                      <option value="auto">Auto</option><option value="primary_curriculum">Primary Curriculum</option><option value="supplemental">Supplemental</option><option value="example_inspiration">Example Inspiration</option>
                    </select>
                  </div>
                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-1.5">Exercises</label>
                    <select className="w-full h-8 bg-input border border-input text-foreground rounded-md px-3 text-xs focus:ring-1 focus:ring-ring outline-none" value={request.exercise_strategy} onChange={e => setRequest(r => ({ ...r, exercise_strategy: e.target.value as any }))}>
                      <option value="auto">Auto</option><option value="none">None</option><option value="extract_patterns">Extract Patterns</option><option value="worked_examples">Worked Examples</option><option value="practice_sets">Practice Sets</option>
                    </select>
                  </div>
                </div>
                
                <div className="pt-2 border-t border-border">
                  <label className="flex items-center gap-2 cursor-pointer mb-3 mt-2">
                    <input type="checkbox" checked={request.project_based} onChange={e => setRequest(r => ({ ...r, project_based: e.target.checked }))} className="accent-foreground" />
                    <span className="text-sm font-medium text-foreground">Project-based running example</span>
                  </label>
                  {request.project_based && (
                    <div>
                      <label className="text-xs font-medium text-muted-foreground block mb-1.5">Project Description</label>
                      <Input value={request.running_project_description || ""} onChange={e => setRequest(r => ({ ...r, running_project_description: e.target.value || null }))} placeholder="e.g. Build a task management API..." />
                    </div>
                  )}
                </div>
              </div>
            </div>
          </Card>

          <Card>
            <div className="p-5">
              <h3 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-4">Source Material</h3>
              <div
                className="border-2 border-dashed border-border rounded-lg p-8 text-center hover:border-muted-foreground transition-colors cursor-pointer"
                onClick={() => fileRef.current?.click()}
              >
                <input ref={fileRef} type="file" accept=".pdf" multiple className="hidden" onChange={e => e.target.files && addFiles(e.target.files)} />
                <Upload size={20} className="mx-auto text-muted-foreground mb-2" />
                <p className="text-sm text-muted-foreground">
                  {hasPdfs ? <span className="text-foreground font-medium">{pdfFiles.length} file{pdfFiles.length > 1 ? "s" : ""} selected</span> : "Drop PDFs here or click to browse"}
                </p>
                {!hasPdfs && <p className="text-xs text-muted-foreground mt-1">Supports .pdf files up to 50MB</p>}
              </div>
              {hasPdfs && (
                <div className="mt-3 space-y-1.5">
                  {pdfFiles.map(f => (
                    <div key={f.name} className="flex items-center gap-2 px-3 py-2 rounded-md bg-secondary text-sm">
                      <FileText size={13} className="text-muted-foreground flex-none" />
                      <span className="flex-1 truncate text-foreground">{f.name}</span>
                      <button type="button" onClick={() => removeFile(f.name)} className="text-muted-foreground hover:text-foreground flex-none"><X size={13} /></button>
                    </div>
                  ))}
                </div>
              )}
              
              {/* URL Input */}
              <div className="mt-6 border-t border-border pt-5">
                <label className="text-xs font-medium text-muted-foreground block mb-1.5 flex items-center gap-2">
                  <Globe size={13} /> Additional Web Sources
                </label>
                <textarea
                  className="w-full bg-input border border-input rounded-md p-3 text-sm text-foreground focus:ring-1 focus:ring-ring outline-none min-h-[80px] resize-none"
                  value={(request.urls || []).join("\n")}
                  onChange={e => setRequest(r => ({ ...r, urls: e.target.value.split("\n").map(u => u.trim()).filter(Boolean) }))}
                  placeholder="https://example.com/article&#10;https://arxiv.org/abs/1234"
                />
                <p className="text-[10px] text-muted-foreground mt-1.5">Enter exactly one URL per line. These will be scraped directly.</p>
              </div>
            </div>
          </Card>
        </div>

        {/* Right sidebar */}
        <div className="space-y-5">
          <Card>
            <div className="p-5">
              <h3 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-4">Settings</h3>
              <div className="space-y-4">
                {/* Web research toggle */}
                <label className="flex items-center justify-between cursor-pointer group">
                  <div>
                    <p className="text-sm font-medium text-foreground">Web research</p>
                    <p className="text-[11px] text-muted-foreground mt-0.5">{!hasPdfs ? "Required (no PDFs)" : "Optional"}</p>
                  </div>
                  <div className={`relative w-8 h-4.5 rounded-full transition-colors flex-none ${webResearchActive ? "bg-success" : "bg-muted"} ${!hasPdfs ? "opacity-60" : ""}`}
                    onClick={() => hasPdfs && setRequest(r => ({ ...r, force_web_research: !r.force_web_research }))}>
                    <div className={`absolute top-0.5 w-3.5 h-3.5 rounded-full bg-white shadow-sm transition-transform ${webResearchActive ? "translate-x-4" : "translate-x-0.5"}`} />
                  </div>
                </label>

                <div className="h-px bg-border" />

                <div>
                  <label className="text-xs font-medium text-muted-foreground block mb-1.5">Code Density</label>
                  <select
                    className="w-full h-8 bg-input border border-input text-foreground rounded-md px-3 text-xs focus:ring-1 focus:ring-ring outline-none"
                    value={request.code_density}
                    onChange={e => setRequest(r => ({ ...r, code_density: e.target.value as CodeDensity }))}
                  >
                    {CODE_DENSITY_OPTIONS.map(option => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-xs font-medium text-muted-foreground block mb-1.5">Example density</label>
                  <select
                    className="w-full h-8 bg-input border border-input text-foreground rounded-md px-3 text-xs focus:ring-1 focus:ring-ring outline-none"
                    value={request.example_density}
                    onChange={e => setRequest(r => ({ ...r, example_density: e.target.value as any }))}
                  >
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs font-medium text-muted-foreground block mb-1.5">Diagram density</label>
                  <select
                    className="w-full h-8 bg-input border border-input text-foreground rounded-md px-3 text-xs focus:ring-1 focus:ring-ring outline-none"
                    value={request.diagram_density}
                    onChange={e => setRequest(r => ({ ...r, diagram_density: e.target.value as any }))}
                  >
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                  </select>
                </div>
                
                <div className="h-px bg-border" />
                
                <div>
                  <label className="text-xs font-medium text-muted-foreground block mb-1.5">Max section words</label>
                  <Input type="number" min={100} max={3000} step={100} value={request.max_section_words ?? ""} onChange={e => setRequest(r => ({ ...r, max_section_words: parseInt(e.target.value) || 900 }))} className="text-xs" />
                </div>
              </div>
            </div>
          </Card>

          {/* Advanced Generation Settings — collapsed by default */}
          <Card>
            <div className="p-5">
              <button
                type="button"
                className="flex items-center justify-between w-full text-left"
                onClick={() => setAdvancedOpen(o => !o)}
              >
                <h3 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">Advanced Generation</h3>
                <ChevronDown size={14} className={`text-muted-foreground transition-transform ${advancedOpen ? 'rotate-180' : ''}`} />
              </button>
              {advancedOpen && (
                <div className="space-y-4 mt-4">
                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-1.5">Depth level</label>
                    <select
                      className="w-full h-8 bg-input border border-input text-foreground rounded-md px-3 text-xs focus:ring-1 focus:ring-ring outline-none"
                      value={request.generation_contract?.depth_level ?? ""}
                      onChange={e => setRequest(r => ({ ...r, generation_contract: { ...r.generation_contract, depth_level: (e.target.value || null) as DepthLevel | null } }))}
                    >
                      <option value="">Auto (inferred)</option>
                      <option value="surface">Surface — overview</option>
                      <option value="intermediate">Intermediate — working knowledge</option>
                      <option value="deep">Deep — expert level</option>
                      <option value="exhaustive">Exhaustive — reference grade</option>
                    </select>
                  </div>
                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-1.5">Implementation style</label>
                    <select
                      className="w-full h-8 bg-input border border-input text-foreground rounded-md px-3 text-xs focus:ring-1 focus:ring-ring outline-none"
                      value={request.generation_contract?.implementation_style ?? ""}
                      onChange={e => setRequest(r => ({ ...r, generation_contract: { ...r.generation_contract, implementation_style: (e.target.value || null) as ImplementationStyle | null } }))}
                    >
                      <option value="">Auto (inferred)</option>
                      <option value="conceptual_only">Conceptual only</option>
                      <option value="pseudocode">Pseudocode</option>
                      <option value="recipe_steps">Recipe steps</option>
                      <option value="file_by_file">File-by-file implementation</option>
                      <option value="project_progressive">Progressive project</option>
                      <option value="argument_driven">Argument driven</option>
                      <option value="case_study_playbook">Case study playbook</option>
                      <option value="workbook">Workbook</option>
                      <option value="visual_textbook">Visual textbook</option>
                      <option value="reference">Reference</option>
                    </select>
                  </div>
                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-1.5">Section style</label>
                    <select
                      className="w-full h-8 bg-input border border-input text-foreground rounded-md px-3 text-xs focus:ring-1 focus:ring-ring outline-none"
                      value={request.generation_contract?.section_style ?? ""}
                      onChange={e => setRequest(r => ({ ...r, generation_contract: { ...r.generation_contract, section_style: (e.target.value || null) as SectionStyle | null } }))}
                    >
                      <option value="">Auto (inferred)</option>
                      <option value="academic">Academic</option>
                      <option value="conversational">Conversational</option>
                      <option value="handbook">Handbook</option>
                      <option value="tutorial">Tutorial</option>
                      <option value="reference">Reference</option>
                      <option value="file_by_file_implementation">File-by-file implementation</option>
                      <option value="academic_argument">Academic argument</option>
                      <option value="case_study_playbook">Case study playbook</option>
                      <option value="visual_textbook">Visual textbook</option>
                      <option value="workbook">Workbook</option>
                    </select>
                  </div>
                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-1.5">Code artifact policy</label>
                    <select
                      className="w-full h-8 bg-input border border-input text-foreground rounded-md px-3 text-xs focus:ring-1 focus:ring-ring outline-none"
                      value={request.generation_contract?.code_artifact_policy ?? ""}
                      onChange={e => setRequest(r => ({ ...r, generation_contract: { ...r.generation_contract, code_artifact_policy: (e.target.value || null) as CodeArtifactPolicy | null } }))}
                    >
                      <option value="">Auto (inferred)</option>
                      <option value="no_code">No code</option>
                      <option value="pseudocode_only">Pseudocode only</option>
                      <option value="minimal_runnable">Minimal runnable</option>
                      <option value="file_labeled_code_required">File-labeled code required</option>
                    </select>
                  </div>
                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-1.5">Target reader outcome</label>
                    <Input
                      type="text"
                      value={request.generation_contract?.target_reader_outcome ?? ""}
                      onChange={e => setRequest(r => ({ ...r, generation_contract: { ...r.generation_contract, target_reader_outcome: e.target.value || null } }))}
                      placeholder="What should the reader achieve?"
                      className="text-xs"
                    />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-1.5">Forbidden content</label>
                    <textarea
                      className="w-full bg-input border border-input rounded-md p-3 text-sm text-foreground focus:ring-1 focus:ring-ring outline-none min-h-[60px] resize-none"
                      value={(request.generation_contract?.forbidden_content ?? []).join("\n")}
                      onChange={e => setRequest(r => ({ ...r, generation_contract: { ...r.generation_contract, forbidden_content: e.target.value.split("\n").map(s => s.trim()).filter(Boolean) } }))}
                      placeholder={"fake quotes\nclinical diagnosis\nplaceholder code"}
                    />
                    <p className="text-[10px] text-muted-foreground mt-1">One item per line. These will be enforced during generation.</p>
                  </div>
                </div>
              )}
            </div>
          </Card>

          <Card>
            <div className="p-5">
              <h3 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-4">Quality Control</h3>
              <div className="space-y-4">
                <div>
                  <label className="text-xs font-medium text-muted-foreground block mb-1.5">Quality mode</label>
                  <select
                    className="w-full h-8 bg-input border border-input text-foreground rounded-md px-3 text-xs focus:ring-1 focus:ring-ring outline-none"
                    value={request.quality_mode}
                    onChange={e => {
                      const mode = e.target.value as BookRequest["quality_mode"];
                      setRequest(r => ({
                        ...r,
                        quality_mode: mode,
                        sample_first: mode === "sample_first",
                        auto_repair: mode === "full_auto_repair" || mode === "sample_first",
                      }));
                    }}
                  >
                    <option value="fast_draft">Fast draft</option>
                    <option value="full_generation">Full generation</option>
                    <option value="full_auto_repair">Full generation + auto-repair</option>
                    <option value="sample_first">Generate sample first</option>
                  </select>
                </div>
                <label className="flex items-center justify-between cursor-pointer group">
                  <div>
                    <p className="text-sm font-medium text-foreground">Auto-repair</p>
                    <p className="text-[11px] text-muted-foreground mt-0.5">Repair low scores before final assembly.</p>
                  </div>
                  <input type="checkbox" checked={request.auto_repair} onChange={e => setRequest(r => ({ ...r, auto_repair: e.target.checked }))} className="accent-foreground" />
                </label>
                <label className="flex items-center justify-between cursor-pointer group">
                  <div>
                    <p className="text-sm font-medium text-foreground">Sample first</p>
                    <p className="text-[11px] text-muted-foreground mt-0.5">Validate direction before committing to the full book.</p>
                  </div>
                  <input type="checkbox" checked={request.sample_first} onChange={e => setRequest(r => ({ ...r, sample_first: e.target.checked, quality_mode: e.target.checked ? "sample_first" : r.quality_mode }))} className="accent-foreground" />
                </label>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-1.5">Target score</label>
                    <Input type="number" min={0} max={100} value={request.target_quality_score} onChange={e => setRequest(r => ({ ...r, target_quality_score: parseInt(e.target.value) || 75 }))} className="text-xs" />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-1.5">Repair passes</label>
                    <Input type="number" min={0} max={5} value={request.max_repair_passes} onChange={e => setRequest(r => ({ ...r, max_repair_passes: parseInt(e.target.value) || 2 }))} className="text-xs" />
                  </div>
                </div>
                <Button type="button" variant="secondary" size="sm" className="w-full" onClick={() => refreshQualityEstimate()}>
                  Estimate quality risk
                </Button>
                {qualityEstimate && (
                  <div className="rounded-md border border-border bg-secondary/40 p-3">
                    <p className="text-xs font-semibold text-foreground">Estimated risk: {qualityEstimate.risk}</p>
                    <p className="text-[11px] text-muted-foreground mt-1">Recommended: {qualityEstimate.recommended}</p>
                    <p className="text-[11px] text-muted-foreground">Expected runtime: {qualityEstimate.expected_runtime}</p>
                  </div>
                )}
              </div>
            </div>
          </Card>

          <Button type="submit" size="lg" disabled={submitting} className="w-full">
            {submitting ? <RefreshCw size={14} className="animate-spin" /> : <Play size={14} />}
            {submitting ? "Starting…" : "Start pipeline"}
          </Button>
        </div>
      </form>
    </div>
  );
}
