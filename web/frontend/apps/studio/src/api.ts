/// <reference types="vite/client" />
export type ApiKeyProvider = "google" | "groq" | "tavily" | "firecrawl";
export type JobStatus =
  | "queued"
  | "running"
  | "validating"
  | "repairing"
  | "completed"
  | "completed_with_latex_issue"
  | "completed_with_warnings"
  | "completed_with_major_issues"
  | "qa_failed"
  | "needs_user_review"
  | "failed"
  | "stopped";

export interface User {
  id: number;
  email: string;
  created_at: string;
}

export interface ApiKeyRecord {
  id: number;
  provider: ApiKeyProvider;
  key_hint: string;
  created_at: string;
  updated_at: string;
}

export interface PipelineConfig {
  llm_provider: "google" | "groq";
  planner_google_model: string;
  researcher_google_model: string;
  notes_google_model: string;
  writer_google_model: string;
  reviewer_google_model: string;
  planner_groq_model: string;
  researcher_groq_model: string;
  notes_groq_model: string;
  writer_groq_model: string;
  reviewer_groq_model: string;
  parallel_section_pipeline: boolean;
  section_pipeline_concurrency: number;
  compile_latex: boolean;
  strict_latex_compile: boolean;
  latex_engine: "pdflatex" | "xelatex" | "lualatex";
  research_execution_profile: "budget" | "debug" | "full";
  token_budget: number | null;
  max_completion_tokens: number | null;
  image_assets_enabled: boolean;
  web_image_search_enabled: boolean;
  generated_images_enabled: boolean;
  image_generation_model: string;
  max_image_assets: number;
}

export interface ProviderModel {
  id: string;
  label: string;
}

export type BookType =
  | "auto"
  | "textbook"
  | "practice_workbook"
  | "course_companion"
  | "implementation_guide"
  | "reference_handbook"
  | "conceptual_guide"
  | "exam_prep";

export type TheoryPracticeBalance = "auto" | "theory_heavy" | "balanced" | "practice_heavy" | "implementation_heavy";
export type PedagogyStyle = "auto" | "german_theoretical" | "indian_theory_then_examples" | "socratic" | "exam_oriented" | "project_based";
export type SourceUsage = "auto" | "primary_curriculum" | "supplemental" | "example_inspiration";
export type ExerciseStrategy = "auto" | "none" | "extract_patterns" | "worked_examples" | "practice_sets";
export type CodeDensity = "none" | "low" | "medium" | "high";
export type ContentDensity = "low" | "medium" | "high";

export type DepthLevel = "surface" | "intermediate" | "deep" | "exhaustive";
export type ImplementationStyle =
  | "conceptual_only" | "pseudocode" | "recipe_steps" | "file_by_file" | "project_progressive"
  | "argument_driven" | "case_study_playbook" | "workbook" | "visual_textbook" | "reference";
export type SectionStyle =
  | "academic" | "conversational" | "handbook" | "tutorial" | "reference"
  | "file_by_file_implementation" | "academic_argument" | "case_study_playbook" | "visual_textbook" | "workbook";
export type CodeArtifactPolicy = "no_code" | "pseudocode_only" | "minimal_runnable" | "file_labeled_code_required";
export type DiagramStyle =
  | "none" | "conceptual" | "architecture" | "data_flow" | "comparison_matrix"
  | "architecture_sequence_schema_deployment" | "concept_maps_decision_trees_checklists"
  | "argument_maps_comparison_matrices" | "timelines_cause_effect_maps" | "frameworks_matrices_funnels";
export type SourceStrictness = "low" | "medium" | "high" | "primary_sources_required";
export type EvidenceStandard = "anecdotal" | "curated" | "primary_source" | "peer_reviewed";

export interface GenerationContract {
  depth_level?: DepthLevel | null;
  implementation_style?: ImplementationStyle | null;
  section_style?: SectionStyle | null;
  code_artifact_policy?: CodeArtifactPolicy | null;
  diagram_style?: DiagramStyle | null;
  source_strictness?: SourceStrictness | null;
  evidence_standard?: EvidenceStandard | null;
  showcase_candidate?: boolean;
  required_stack?: string[];
  forbidden_content?: string[];
  project_artifacts?: string[];
  required_outputs?: string[];
  success_criteria?: string[];
  running_examples?: string[];
  style_references?: string[];
  target_reader_outcome?: string | null;
  citation_policy?: string | null;
  visual_policy?: string | null;
  notation_system?: string | null;
}

export interface BookRequest {
  topic: string;
  audience: string;
  tone: string;
  book_type: BookType;
  theory_practice_balance: TheoryPracticeBalance;
  pedagogy_style: PedagogyStyle;
  source_usage: SourceUsage;
  exercise_strategy: ExerciseStrategy;
  goals: string[];
  project_based: boolean;
  running_project_description: string | null;
  code_density: CodeDensity;
  example_density: ContentDensity;
  diagram_density: ContentDensity;
  generation_contract?: GenerationContract | null;
  max_section_words: number | null;
  force_web_research: boolean;
  urls: string[];
  /** Free-form language instruction, e.g. "Explain theory in English, write exam examples in German." */
  language_request?: string | null;
  target_quality_score: number;
  max_repair_passes: number;
  hard_fail_threshold: number;
  auto_repair: boolean;
  sample_first: boolean;
  quality_mode: "fast_draft" | "full_generation" | "full_auto_repair" | "sample_first";
}

export interface JobStage {
  label: string;
  status: "queued" | "running" | "completed" | "failed" | "stopped";
  started_at: string | null;
  completed_at: string | null;
  seconds: number | null;
  details: Record<string, unknown>;
}

export interface Job {
  id: number;
  status: JobStatus;
  current_stage: string;
  request_payload: Record<string, unknown>;
  config_snapshot: Record<string, unknown>;
  stages: Record<string, JobStage>;
  summary: {
    evaluation?: {
      quality_score?: number;
    };
    quality?: {
      score?: number;
      label?: string;
      status?: string;
      target_quality_score?: number;
      hard_fail_threshold?: number;
      breakdown?: Record<string, { label: string; score: number }>;
      top_issues?: string[];
      expected_final_quality_range?: string;
      repair_passes?: number;
      weak_section_count?: number;
      showcase_ready?: boolean;
      pre_run_risk?: {
        risk?: string;
        recommended?: string;
        expected_runtime?: string;
        recommended_quality_mode?: string;
        factors?: string[];
      };
    };
    llm_usage?: {
      accounted_total_tokens?: number;
    };
    elapsed_seconds?: number;
  };
  warnings: Record<string, unknown>;
  error_message: string | null;
  run_dir: string | null;
  process_id: number | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface JobArtifact {
  key: string;
  filename: string;
  size_bytes: number;
  updated_at: string;
}

export interface GeneratedBook {
  id: number;
  job_id: number;
  title: string;
  topic: string;
  status: string;
  run_dir: string;
  latex_path: string | null;
  pdf_path: string | null;
  summary_metrics: Record<string, unknown>;
  artifact_paths: Record<string, string | null>;
  created_at: string;
}

const configuredApiBase = (import.meta.env.VITE_API_URL || "").trim().replace(/\/$/, "");
const API_BASE = configuredApiBase || (import.meta.env.PROD ? "" : "/api");
type TokenProvider = () => Promise<string | null>;

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(message: string, status: number, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export function friendlyApiErrorMessage(error: unknown, fallback = "Something went wrong.") {
  if (error instanceof ApiError) {
    if (error.status === 429) return "Rate limit reached. Please wait a while before trying again.";
    if (error.status === 401) return "Your session has expired. Please sign in again.";
    if (error.status === 403) return "You do not have permission to perform this action.";
    if (error.status === 404) return "That item is no longer available.";
    if (error.status >= 500) return "The server hit a problem. Please try again in a moment.";
  }
  if (error instanceof Error) {
    const text = error.message.toLowerCase();
    if (text.includes("rate limit") || text.includes("429") || text.includes("quota")) return "Rate limit reached. Please wait a while before trying again.";
    if (text.includes("api key") || text.includes("unauthorized") || text.includes("permission")) return "Provider access problem. Check your API keys and selected models.";
    if (text.includes("network") || text.includes("timeout") || text.includes("failed to fetch")) return "Network problem. Please check the connection and try again.";
  }
  return fallback;
}

function errorMessageFromPayload(payload: any, fallback: string) {
  if (typeof payload?.detail === "string") return payload.detail;
  if (Array.isArray(payload?.detail)) return payload.detail.map((item: any) => item?.msg || String(item)).join("\n");
  return fallback;
}

function filenameFromContentDisposition(contentDisposition: string, fallback: string) {
  const encodedMatch = contentDisposition.match(/filename\*=([^;]+)/i);
  if (encodedMatch?.[1]) {
    const encoded = encodedMatch[1].trim().replace(/^UTF-8''/i, "").replace(/^"|"$/g, "");
    try {
      return decodeURIComponent(encoded);
    } catch {
      return encoded;
    }
  }
  const filenameMatch = contentDisposition.match(/(?:^|;\s*)filename="?([^";]+)"?/i);
  return filenameMatch?.[1] || fallback;
}

export class ApiClient {
  token: string | null;
  private tokenProvider?: TokenProvider;

  constructor(token: string | null, tokenProvider?: TokenProvider) {
    this.token = token;
    this.tokenProvider = tokenProvider;
  }

  private async authToken() {
    if (!this.tokenProvider) return this.token;
    const nextToken = await this.tokenProvider();
    this.token = nextToken;
    return nextToken;
  }

  async request<T>(path: string, options: RequestInit = {}): Promise<T> {
    if (!API_BASE) {
      throw new Error("Backend API is not configured. Set VITE_API_URL to your deployed FastAPI backend URL in Vercel.");
    }
    const headers = new Headers(options.headers);
    headers.set("Content-Type", "application/json");
    const token = await this.authToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);

    const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({ detail: response.statusText }));
      throw new ApiError(errorMessageFromPayload(payload, response.statusText), response.status, payload.detail);
    }
    if (response.status === 204) return undefined as T;
    return response.json() as Promise<T>;
  }

  signup(email: string, password: string) {
    return this.request<{ access_token: string }>("/auth/signup", {
      method: "POST",
      body: JSON.stringify({ email, password })
    });
  }

  login(email: string, password: string) {
    return this.request<{ access_token: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password })
    });
  }

  me() {
    return this.request<User>("/me");
  }

  apiKeys() {
    return this.request<ApiKeyRecord[]>("/api-keys");
  }

  saveApiKey(provider: ApiKeyProvider, value: string) {
    return this.request<ApiKeyRecord>(`/api-keys/${provider}`, {
      method: "PUT",
      body: JSON.stringify({ provider, value })
    });
  }

  deleteApiKey(provider: ApiKeyProvider) {
    return this.request<void>(`/api-keys/${provider}`, { method: "DELETE" });
  }

  config() {
    return this.request<PipelineConfig>("/config");
  }

  providerModels(provider: "google" | "groq") {
    return this.request<ProviderModel[]>(`/models/${provider}`);
  }

  saveConfig(config: PipelineConfig) {
    return this.request<PipelineConfig>("/config", {
      method: "PUT",
      body: JSON.stringify(config)
    });
  }

  parsePrompt(prompt: string) {
    return this.request<Partial<BookRequest>>("/jobs/parse-prompt", {
      method: "POST",
      body: JSON.stringify({ prompt })
    });
  }

  qualityEstimate(payload: BookRequest) {
    return this.request<{
      risk: string;
      score: number;
      factors: string[];
      recommended: string;
      expected_runtime: string;
      recommended_quality_mode: string;
    }>("/jobs/quality-estimate", {
      method: "POST",
      body: JSON.stringify({ request: payload })
    });
  }

  createJob(payload: BookRequest) {
    return this.request<Job>("/jobs", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  }

  /** Create a job and attach PDF source files via multipart upload. */
  async createJobWithPdfs(payload: BookRequest, pdfFiles: File[]) {
    if (!API_BASE) {
      return Promise.reject(new Error("Backend API is not configured. Set VITE_API_URL to your deployed FastAPI backend URL in Vercel."));
    }
    const form = new FormData();
    form.append("request_json", JSON.stringify(payload));
    for (const file of pdfFiles) {
      form.append("pdf_files", file, file.name);
    }
    // Use fetch directly — request() forces Content-Type: application/json
    const headers = new Headers();
    const token = await this.authToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
    return fetch(`${API_BASE}/jobs/upload`, { method: "POST", headers, body: form })
      .then(async (response) => {
        if (!response.ok) {
          const payload = await response.json().catch(() => ({ detail: response.statusText }));
          throw new ApiError(errorMessageFromPayload(payload, response.statusText), response.status, payload.detail);
        }
        return response.json() as Promise<Job>;
      });
  }

  jobs() {
    return this.request<Job[]>("/jobs");
  }

  job(id: number) {
    return this.request<Job>(`/jobs/${id}`);
  }

  stopJob(id: number) {
    return this.request<Job>(`/jobs/${id}/stop`, { method: "POST" });
  }

  retryJob(id: number) {
    return this.request<Job>(`/jobs/${id}/retry`, { method: "POST" });
  }

  repairJob(id: number, action: "repair" | "code" | "diagrams" | "sources" | "showcase" = "repair") {
    const suffix = action === "repair" ? "" : `/${action}`;
    return this.request<Job>(`/jobs/${id}/repair${suffix}`, { method: "POST", body: JSON.stringify({}) });
  }

  jobArtifacts(id: number) {
    return this.request<JobArtifact[]>(`/jobs/${id}/artifacts`);
  }

  async downloadJobArtifact(jobId: number, artifactKey: string) {
    if (!API_BASE) {
      throw new Error("Backend API is not configured. Set VITE_API_URL to your deployed FastAPI backend URL in Vercel.");
    }
    const headers = new Headers();
    const token = await this.authToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
    const response = await fetch(`${API_BASE}/jobs/${jobId}/artifacts/${artifactKey}`, { headers });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({ detail: response.statusText }));
      throw new ApiError(errorMessageFromPayload(payload, response.statusText), response.status, payload.detail);
    }
    const blob = await response.blob();
    const contentDisposition = response.headers.get("content-disposition") || "";
    return {
      blob,
      filename: filenameFromContentDisposition(contentDisposition, `${artifactKey}-${jobId}`),
    };
  }

  books() {
    return this.request<GeneratedBook[]>("/books");
  }

  async downloadArtifact(bookId: number, artifactName: string) {
    if (!API_BASE) {
      throw new Error("Backend API is not configured. Set VITE_API_URL to your deployed FastAPI backend URL in Vercel.");
    }
    const headers = new Headers();
    const token = await this.authToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
    const response = await fetch(this.artifactUrl(bookId, artifactName), { headers });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({ detail: response.statusText }));
      throw new ApiError(errorMessageFromPayload(payload, response.statusText), response.status, payload.detail);
    }
    const blob = await response.blob();
    const contentDisposition = response.headers.get("content-disposition") || "";
    return {
      blob,
      filename: filenameFromContentDisposition(contentDisposition, `${artifactName}-${bookId}`),
    };
  }

  artifactUrl(bookId: number, artifactName: string) {
    return `${API_BASE}/books/${bookId}/artifacts/${artifactName}`;
  }
}
