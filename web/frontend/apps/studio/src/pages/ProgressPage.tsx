import React from "react";
import { motion, AnimatePresence } from "motion/react";
import { RefreshCw, X, Check, Timer, Activity, AlertTriangle, ChevronRight } from "lucide-react";
import { Button } from "@writerlm/ui";
import { ApiClient, Job, JobStatus } from "../api";

interface ProgressPageProps {
  api: ApiClient;
  jobs: Job[];
  selectedJob: Job | null;
  onSelect: (id: number) => void;
  onJobs: React.Dispatch<React.SetStateAction<Job[]>>;
  onNotice: (message: string) => void;
}

const STAGE_ORDER = ["planner_research", "notes_synthesis", "writer", "reviewer", "quality_checker", "image_assets", "assembler", "latex_compile"];

function effectiveStatus(job: Job): JobStatus {
  const stages = Object.values(job.stages || {});
  if (stages.some((s: any) => s.status === "running")) return "running";
  if (job.status === "queued" && stages.some((s: any) => s.status === "completed")) return "running";
  return job.status;
}

function StatusBadge({ status }: { status: string }) {
  const cfg: Record<string, string> = {
    running: "bg-blue-500/10 text-blue-400 border-blue-500/20",
    completed: "bg-success/10 text-success border-success/20",
    failed: "bg-red-500/10 text-red-400 border-red-500/20",
    stopped: "bg-yellow-500/10 text-yellow-400 border-yellow-500/20",
    queued: "bg-muted text-muted-foreground border-border",
    completed_with_latex_issue: "bg-orange-500/10 text-orange-400 border-orange-500/20",
  };
  const dot: Record<string, string> = {
    running: "bg-blue-500 animate-pulse",
    completed: "bg-success",
    failed: "bg-red-500",
    stopped: "bg-yellow-500",
    queued: "bg-muted-foreground",
    completed_with_latex_issue: "bg-orange-500",
  };
  return (
    <span className={`inline-flex items-center gap-1.5 text-[11px] font-medium border rounded-full px-2 py-0.5 ${cfg[status] ?? cfg.queued}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${dot[status] ?? dot.queued}`} />
      {status.replaceAll("_", " ")}
    </span>
  );
}

function StageIcon({ status }: { status: string }) {
  if (status === "completed") return <Check size={13} className="text-success" strokeWidth={2.5} />;
  if (status === "running") return <RefreshCw size={13} className="text-blue-400 animate-spin" />;
  if (status === "failed") return <AlertTriangle size={13} className="text-red-400" />;
  if (status === "stopped") return <X size={13} className="text-yellow-400" />;
  return <Timer size={13} className="text-muted-foreground" />;
}

function formatDetails(details: Record<string, unknown>) {
  const entries = Object.entries(details || {}).filter(([, v]) => v !== null && v !== undefined && v !== "");
  if (!entries.length) return null;
  return entries.slice(0, 5).map(([k, v]) => `${k.replace(/_/g, " ")}: ${Array.isArray(v) ? v.join(", ") : String(v)}`).join("\n");
}

export function ProgressPage({ api, jobs, selectedJob, onSelect, onJobs, onNotice }: ProgressPageProps) {
  const status = selectedJob ? effectiveStatus(selectedJob) : null;
  const canStop = status === "running" || status === "queued";
  const canRetry = selectedJob && ["failed", "stopped", "completed_with_latex_issue"].includes(status ?? "");
  const hasError = selectedJob?.error_message && status !== "running" && status !== "queued";

  async function stop() {
    if (!selectedJob) return;
    try {
      const s = await api.stopJob(selectedJob.id);
      onJobs(prev => prev.map(j => j.id === s.id ? s : j));
      onNotice(`Job #${s.id} stopped.`);
    } catch (e) { onNotice(e instanceof Error ? e.message : "Could not stop job."); }
  }

  async function retry() {
    if (!selectedJob) return;
    try {
      const r = await api.retryJob(selectedJob.id);
      onJobs(prev => [r, ...prev]);
      onSelect(r.id);
      onNotice(`Retry job #${r.id} started.`);
    } catch (e) { onNotice(e instanceof Error ? e.message : "Could not retry job."); }
  }

  return (
    <div className="flex gap-0 h-full overflow-hidden px-5">
      {/* Job list */}
      <div className="w-52 flex-none border-r border-border pr-4 overflow-y-auto scrollbar-hide py-1 -ml-5 pl-5">
        {jobs.length === 0 && <p className="text-xs text-muted-foreground text-center py-12">No jobs yet</p>}
        {jobs.map(job => {
          const s = effectiveStatus(job);
          const active = selectedJob?.id === job.id;
          return (
            <button
              key={job.id}
              onClick={() => onSelect(job.id)}
              className={`w-full text-left px-3 py-3 rounded-lg mb-1 transition-colors cursor-pointer ${active ? "bg-accent" : "hover:bg-accent/50"}`}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="font-mono text-[10px] text-muted-foreground">#{job.id}</span>
                <StatusBadge status={s} />
              </div>
              <p className={`text-xs font-medium truncate ${active ? "text-foreground" : "text-muted-foreground"}`}>
                {String(job.request_payload?.topic || "Untitled")}
              </p>
            </button>
          );
        })}
      </div>

      {/* Detail pane */}
      <div className="flex-1 overflow-y-auto scrollbar-hide pl-5 py-1">
        <AnimatePresence mode="wait">
          {selectedJob ? (
            <motion.div key={selectedJob.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.1 }}>
              {/* Header */}
              <div className="flex items-start justify-between mb-5 gap-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 mb-2">
                    <StatusBadge status={status ?? ""} />
                    <span className="font-mono text-[10px] text-muted-foreground">#{selectedJob.id}</span>
                  </div>
                  <h2 className="text-lg font-semibold text-foreground tracking-tight truncate">
                    {String(selectedJob.request_payload?.topic || "Generation Task")}
                  </h2>
                </div>
                <div className="flex gap-2 flex-none">
                  {canRetry && <Button variant="secondary" size="sm" onClick={retry}><RefreshCw size={13} /> Retry</Button>}
                  {canStop && <Button variant="danger" size="sm" onClick={stop}><X size={13} /> Stop</Button>}
                </div>
              </div>

              {/* Error */}
              {hasError && (
                <div className="flex items-start gap-3 p-3 rounded-lg border border-red-500/20 bg-red-500/10 text-red-400 text-sm mb-5">
                  <AlertTriangle size={15} className="flex-none mt-0.5" />
                  <p>{selectedJob!.error_message}</p>
                </div>
              )}

              {/* Metrics */}
              <div className="grid grid-cols-3 gap-3 mb-5">
                {[
                  { label: "Quality score", value: selectedJob.summary?.evaluation?.quality_score ? `${selectedJob.summary.evaluation.quality_score}/100` : "—" },
                  { label: "Tokens used", value: selectedJob.summary?.llm_usage?.accounted_total_tokens ? `${(selectedJob.summary.llm_usage.accounted_total_tokens / 1000).toFixed(1)}k` : "—" },
                  { label: "Runtime", value: selectedJob.summary?.elapsed_seconds ? `${Math.floor(selectedJob.summary.elapsed_seconds / 60)}m ${selectedJob.summary.elapsed_seconds % 60}s` : "—" },
                ].map(m => (
                  <div key={m.label} className="rounded-lg border border-border bg-card p-4">
                    <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground mb-1">{m.label}</p>
                    <p className="text-xl font-semibold text-foreground tracking-tight">{m.value}</p>
                  </div>
                ))}
              </div>

              {/* Pipeline stages */}
              <div className="space-y-1.5">
                {STAGE_ORDER.map(key => {
                  const stage = selectedJob.stages?.[key];
                  if (!stage) return null;
                  const details = formatDetails(stage.details || {});
                  return (
                    <div key={key} className={`rounded-lg border border-border p-4 ${stage.status === "running" ? "border-blue-500/30 bg-blue-500/5" : "bg-card"}`}>
                      <div className="flex items-center gap-3">
                        <StageIcon status={stage.status} />
                        <span className="text-sm font-medium text-foreground flex-1">{stage.label}</span>
                        <span className="font-mono text-[10px] text-muted-foreground">{stage.seconds ? `${stage.seconds}s` : stage.status}</span>
                      </div>
                      {details && (
                        <pre className="mt-3 text-[11px] font-mono text-muted-foreground leading-relaxed whitespace-pre-wrap bg-secondary/50 p-3 rounded-md border border-border">
                          {details}
                        </pre>
                      )}
                    </div>
                  );
                })}
              </div>
            </motion.div>
          ) : (
            <div className="flex flex-col items-center justify-center py-32 text-center">
              <Activity size={28} className="text-muted-foreground/30 mb-4" />
              <p className="text-sm font-medium text-muted-foreground">Select a job to view progress</p>
            </div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
