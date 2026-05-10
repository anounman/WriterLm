import { SignInButton, SignUpButton } from "@clerk/react";
import { Button, ThemeToggle } from "@writerlm/ui";
import {
  BookOpen,
  Brain,
  ChevronRight,
  Code2,
  Database,
  FileCheck2,
  FileText,
  Github,
  Layers,
  PenTool,
  Search,
  ShieldCheck,
  Sparkles,
  TerminalSquare,
} from "lucide-react";
import { motion, Variants } from "motion/react";

interface LandingPageProps {
  theme: "dark" | "light";
  onTheme: (theme: "dark" | "light") => void;
}

const fadeUp: Variants = {
  hidden: { opacity: 0, y: 18 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.45, ease: "easeOut" } },
};

const stagger: Variants = {
  hidden: { opacity: 1 },
  visible: { opacity: 1, transition: { staggerChildren: 0.08 } },
};

const pipeline = [
  { label: "Planner", detail: "Book plan, audience, scope", icon: Brain },
  { label: "Researcher", detail: "PDF + web evidence bundles", icon: Search },
  { label: "Notes", detail: "Section-ready briefs", icon: Database },
  { label: "Writer", detail: "Long-form manuscript drafts", icon: PenTool },
  { label: "Reviewer", detail: "Quality checks and repairs", icon: ShieldCheck },
  { label: "Compiler", detail: "Typeset PDF output", icon: FileCheck2 },
];

const featureCards = [
  {
    title: "Bring real source material",
    body: "Upload PDFs, attach URLs, or enable web research. Every section is grounded before drafting begins.",
    icon: Database,
    meta: "PDF · URL · Web",
  },
  {
    title: "Control the book shape",
    body: "Tune book type, audience, theory/practice balance, language, diagrams, examples, and exercise strategy.",
    icon: Layers,
    meta: "Genre aware",
  },
  {
    title: "Keep model routing flexible",
    body: "Use Google or Groq per layer, with separate planner, researcher, notes, writer, and reviewer models.",
    icon: Code2,
    meta: "BYO keys",
  },
  {
    title: "Recover failed runs",
    body: "Track stages, retry jobs, and download troubleshooting artifacts when a generation needs inspection.",
    icon: TerminalSquare,
    meta: "Operational UI",
  },
];

export function LandingPage({ theme, onTheme }: LandingPageProps) {
  return (
    <div className="min-h-screen bg-background text-foreground transition-colors selection:bg-foreground/10 overflow-x-hidden">
      <motion.header
        initial={{ y: -18, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.35 }}
        className="relative z-10 mx-3 mt-3 sm:mx-4 sm:mt-4 h-14 rounded-lg border border-border bg-background/90 backdrop-blur-md shadow-sm"
      >
        <div className="h-full max-w-7xl mx-auto flex items-center justify-between px-4 sm:px-5">
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 rounded-md bg-foreground flex items-center justify-center shadow-sm">
              <BookOpen size={14} strokeWidth={2.5} className="text-background" />
            </div>
            <span className="text-sm font-semibold tracking-tight">WriterLM</span>
          </div>
          <div className="flex items-center gap-2 sm:gap-3">
            <ThemeToggle theme={theme} onTheme={onTheme} />
            <SignInButton mode="modal">
              <Button variant="ghost" size="sm" className="font-medium hidden sm:inline-flex">Sign in</Button>
            </SignInButton>
            <SignUpButton mode="modal">
              <Button size="sm" className="font-medium shadow-sm">Get started</Button>
            </SignUpButton>
          </div>
        </div>
      </motion.header>

      <main>
        <section className="relative min-h-[calc(92vh-4.5rem)] px-4 sm:px-6 pt-14 sm:pt-16 pb-12 sm:pb-16 flex items-center overflow-hidden border-b border-border">
          <div className="absolute inset-0 pointer-events-none">
            <div className="absolute inset-0 bg-background" />
            <div className="absolute left-1/2 top-24 sm:top-20 w-[760px] sm:w-[980px] xl:w-[1180px] max-w-[170vw] sm:max-w-[130vw] -translate-x-1/2 opacity-[0.10] sm:opacity-[0.14] dark:opacity-[0.18]">
              <div className="rounded-lg border border-border bg-card shadow-2xl overflow-hidden rotate-[-2deg]">
                <div className="h-9 border-b border-border bg-secondary/80 flex items-center justify-between px-4">
                  <div className="flex items-center gap-1.5">
                    <span className="w-2.5 h-2.5 rounded-full bg-red-400" />
                    <span className="w-2.5 h-2.5 rounded-full bg-yellow-400" />
                    <span className="w-2.5 h-2.5 rounded-full bg-emerald-400" />
                  </div>
                  <span className="text-[10px] font-mono text-muted-foreground">sample_book.pdf</span>
                </div>
                <iframe
                  src="/sample_book.pdf#toolbar=0&navpanes=0&scrollbar=0"
                  className="w-full h-[460px] sm:h-[620px] xl:h-[720px] bg-white border-0"
                  title="Sample generated WriterLM book preview"
                />
              </div>
            </div>
            <div className="absolute inset-0 bg-gradient-to-b from-background via-background/90 to-background" />
          </div>

          <motion.div
            variants={stagger}
            initial="hidden"
            animate="visible"
            className="relative z-10 w-full max-w-6xl mx-auto text-center"
          >
            <motion.div variants={fadeUp} className="inline-flex max-w-full items-center gap-2 border border-border bg-background/85 text-muted-foreground text-xs font-medium px-3 py-1.5 rounded-full mb-6">
              <Sparkles size={12} className="text-emerald-500" />
              <span className="truncate sm:whitespace-normal">AI book generation with research, review, and PDF compilation</span>
            </motion.div>

            <motion.h1 variants={fadeUp} className="text-5xl sm:text-6xl md:text-[5.75rem] xl:text-[7rem] font-bold tracking-tight leading-[0.92] mb-7">
              WriterLM
            </motion.h1>

            <motion.p variants={fadeUp} className="text-xl sm:text-2xl md:text-3xl xl:text-4xl font-semibold tracking-tight max-w-4xl mx-auto mb-5 leading-tight">
              Turn prompts, PDFs, and web sources into publish-ready books of any kind.
            </motion.p>

            <motion.p variants={fadeUp} className="text-sm sm:text-base xl:text-lg text-muted-foreground max-w-3xl mx-auto mb-8 leading-relaxed">
              A local-first studio for long-form AI publishing: plan the structure, research every section, draft with controllable models, review quality, and compile the finished book to LaTeX/PDF.
            </motion.p>

            <motion.div variants={fadeUp} className="flex flex-col sm:flex-row items-stretch sm:items-center justify-center gap-3 mb-9">
              <SignUpButton mode="modal">
                <Button size="lg" className="h-11 px-6 text-sm font-semibold shadow-lg shadow-emerald-500/10 w-full sm:w-auto">
                  Start a book <ChevronRight size={15} className="ml-1" />
                </Button>
              </SignUpButton>
              <Button
                variant="outline"
                size="lg"
                className="h-11 px-6 text-sm font-semibold border-border bg-background/80 hover:bg-secondary w-full sm:w-auto"
                onClick={() => window.open("https://github.com/anounman/writerLm", "_blank")}
              >
                <Github size={15} className="mr-2" /> View source
              </Button>
            </motion.div>

            <motion.div variants={fadeUp} className="grid grid-cols-2 md:grid-cols-4 gap-2 max-w-4xl mx-auto">
              {[
                ["Any", "book category"],
                ["PDF", "final export"],
                ["11", "LLM stages"],
                ["Local", "Docker stack"],
              ].map(([value, label]) => (
                <div key={label} className="rounded-lg border border-border bg-background/75 px-4 py-3">
                  <p className="text-lg font-semibold text-foreground">{value}</p>
                  <p className="text-[10px] uppercase tracking-widest text-muted-foreground">{label}</p>
                </div>
              ))}
            </motion.div>
          </motion.div>
        </section>

        <section className="px-4 sm:px-6 py-14 lg:py-18 border-b border-border bg-secondary/20">
          <div className="max-w-7xl mx-auto">
            <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4 mb-8">
              <div>
                <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-2">Pipeline</p>
                <h2 className="text-2xl sm:text-3xl font-bold tracking-tight">Built for long documents, not chat snippets.</h2>
              </div>
              <p className="text-sm text-muted-foreground max-w-xl leading-relaxed">
                WriterLM breaks a book into inspectable stages so you can see where time, tokens, sources, and failures are happening.
              </p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3">
              {pipeline.map((stage, index) => (
                <motion.div
                  key={stage.label}
                  initial={{ opacity: 0, y: 12 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true, margin: "-80px" }}
                  transition={{ duration: 0.35, delay: index * 0.04 }}
                  className="rounded-lg border border-border bg-card p-4 min-h-[138px]"
                >
                  <div className="flex items-center justify-between gap-3 mb-5">
                    <div className="w-8 h-8 rounded-md bg-secondary flex items-center justify-center">
                      <stage.icon size={15} className="text-foreground" />
                    </div>
                    <span className="font-mono text-[10px] text-muted-foreground">{String(index + 1).padStart(2, "0")}</span>
                  </div>
                  <h3 className="text-sm font-semibold mb-1">{stage.label}</h3>
                  <p className="text-xs text-muted-foreground leading-relaxed">{stage.detail}</p>
                </motion.div>
              ))}
            </div>
          </div>
        </section>

        <section className="max-w-7xl mx-auto px-4 sm:px-6 py-14 sm:py-20">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-100px" }}
              className="lg:col-span-5 rounded-lg border border-border bg-card p-6 sm:p-8"
            >
              <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-3">Output Preview</p>
              <h2 className="text-2xl sm:text-3xl font-bold tracking-tight mb-4">Books that look finished, not dumped.</h2>
              <p className="text-sm text-muted-foreground leading-relaxed mb-6">
                The pipeline assembles sections into a structured manuscript and compiles a typeset PDF with a generated title, citations, diagrams, examples, exercises, and stage artifacts.
              </p>
              <div className="grid grid-cols-2 gap-3">
                {["LaTeX manuscript", "PDF artifact", "Research bundle", "Review bundle"].map(item => (
                  <div key={item} className="rounded-md border border-border bg-secondary/35 p-3 text-xs font-medium text-foreground">
                    {item}
                  </div>
                ))}
              </div>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-100px" }}
              transition={{ delay: 0.08 }}
              className="lg:col-span-7 rounded-lg border border-border bg-card overflow-hidden"
            >
              <div className="h-11 border-b border-border bg-secondary/50 flex items-center justify-between px-4">
                <div className="flex items-center gap-2 text-xs font-mono text-muted-foreground">
                  <FileText size={13} />
                  generated_book.pdf
                </div>
                <span className="text-[10px] font-medium uppercase tracking-widest text-emerald-500">Compiled</span>
              </div>
              <div className="h-[320px] sm:h-[440px] lg:h-[520px] bg-white">
                <iframe
                  src="/sample_book.pdf#toolbar=0&navpanes=0&scrollbar=0"
                  className="w-full h-full border-0"
                  title="Sample Generated Book"
                />
              </div>
            </motion.div>
          </div>
        </section>

        <section className="max-w-7xl mx-auto px-4 sm:px-6 pb-14 sm:pb-20">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {featureCards.map((feature, index) => (
              <motion.div
                key={feature.title}
                initial={{ opacity: 0, y: 16 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-80px" }}
                transition={{ duration: 0.35, delay: index * 0.05 }}
                className="rounded-lg border border-border bg-card p-5 transition-colors hover:border-muted-foreground/40"
              >
                <div className="flex items-center justify-between mb-6">
                  <div className="w-9 h-9 rounded-md bg-secondary flex items-center justify-center">
                    <feature.icon size={17} className="text-foreground" />
                  </div>
                  <span className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">{feature.meta}</span>
                </div>
                <h3 className="text-base font-semibold mb-2">{feature.title}</h3>
                <p className="text-sm text-muted-foreground leading-relaxed">{feature.body}</p>
              </motion.div>
            ))}
          </div>
        </section>

        <section className="border-y border-border bg-secondary/20 px-4 sm:px-6 py-20">
          <div className="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-3 gap-4">
            <div className="lg:col-span-1">
              <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-3">Operator View</p>
              <h2 className="text-2xl sm:text-3xl font-bold tracking-tight mb-4">A studio for running the work, not just launching it.</h2>
              <p className="text-sm text-muted-foreground leading-relaxed">
                Every run has statuses, logs, allowed troubleshooting downloads, retry paths, model settings, and user-owned API keys.
              </p>
            </div>
            <div className="lg:col-span-2 grid grid-cols-1 sm:grid-cols-3 gap-3">
              {[
                ["Progress", "Stage timings, failure categories, downloadable logs."],
                ["Config", "Provider routing, model selection, LaTeX, images."],
                ["Library", "Generated books with title-safe PDF downloads."],
              ].map(([title, body]) => (
                <div key={title} className="rounded-lg border border-border bg-card p-5">
                  <h3 className="text-sm font-semibold mb-2">{title}</h3>
                  <p className="text-xs text-muted-foreground leading-relaxed">{body}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <motion.section
          initial={{ opacity: 0, y: 18 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          className="py-16 sm:py-20 px-4 sm:px-6 text-center"
        >
          <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-3">Start</p>
          <h2 className="text-3xl md:text-4xl xl:text-5xl font-bold tracking-tight mb-5">Generate your first book.</h2>
          <p className="text-muted-foreground mb-8 max-w-2xl mx-auto leading-relaxed">
            Sign in, save your provider keys, and run the book pipeline for textbooks, workbooks, guides, handbooks, or any structured long-form project.
          </p>
          <SignUpButton mode="modal">
            <Button size="lg" className="h-12 px-8 font-semibold shadow-lg shadow-emerald-500/10">
              Open WriterLM <ChevronRight size={16} className="ml-1" />
            </Button>
          </SignUpButton>
        </motion.section>
      </main>

      <footer className="border-t border-border px-4 sm:px-6 py-8 bg-background">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4 text-xs text-muted-foreground">
          <div className="flex items-center gap-2">
            <div className="w-5 h-5 rounded bg-muted-foreground/20 flex items-center justify-center">
              <BookOpen size={11} strokeWidth={2.5} className="text-foreground" />
            </div>
            <span className="font-semibold text-foreground">WriterLM</span>
            <span className="px-1">·</span>
            <span>Open source AI publishing pipeline</span>
          </div>
          <a href="https://github.com/anounman/writerLm" target="_blank" rel="noreferrer" className="hover:text-foreground transition-colors flex items-center gap-1.5">
            <Github size={14} /> GitHub
          </a>
        </div>
      </footer>
    </div>
  );
}
