import React from "react";
import { BookOpen, Github, ChevronRight, Brain, FileText, Layers, Search, Code2, PenTool, Sparkles, Database } from "lucide-react";
import { ThemeToggle, Button } from "@writerlm/ui";
import { SignInButton, SignUpButton } from "@clerk/react";
import { motion, Variants } from "motion/react";

interface LandingPageProps {
  theme: "dark" | "light";
  onTheme: (theme: "dark" | "light") => void;
}

const fadeIn: Variants = {
  hidden: { opacity: 0, y: 20 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.5, ease: "easeOut" } }
};

const staggerContainer: Variants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { staggerChildren: 0.1 }
  }
};

export function LandingPage({ theme, onTheme }: LandingPageProps) {
  return (
    <div className="min-h-screen bg-background text-foreground transition-colors selection:bg-foreground/10 overflow-x-hidden">
      {/* Nav */}
      <motion.header 
        initial={{ y: -20, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.4 }}
        className="fixed inset-x-0 top-0 z-50 h-14 flex items-center justify-between px-6 border-b border-border bg-background/80 backdrop-blur-md"
      >
        <div className="flex items-center gap-2.5">
          <div className="w-6 h-6 rounded-md bg-foreground flex items-center justify-center shadow-sm">
            <BookOpen size={13} strokeWidth={2.5} className="text-background" />
          </div>
          <span className="text-sm font-semibold tracking-tight">WriterLM</span>
        </div>
        <div className="flex items-center gap-3">
          <ThemeToggle theme={theme} onTheme={onTheme} />
          <div className="h-4 w-px bg-border mx-1" />
          <SignInButton mode="modal">
            <Button variant="ghost" size="sm" className="font-medium">Sign in</Button>
          </SignInButton>
          <SignUpButton mode="modal">
            <Button size="sm" className="font-medium shadow-sm">Get started</Button>
          </SignUpButton>
        </div>
      </motion.header>

      {/* Hero */}
      <motion.main 
        variants={staggerContainer}
        initial="hidden"
        animate="visible"
        className="relative pt-40 pb-20 px-6 text-center max-w-5xl mx-auto"
      >
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[400px] opacity-[0.03] dark:opacity-[0.07] pointer-events-none">
          <div className="absolute inset-0 rounded-full bg-emerald-500 blur-[100px]" />
        </div>

        <motion.div variants={fadeIn} className="relative inline-flex items-center gap-2 border border-border bg-secondary/50 backdrop-blur-sm text-muted-foreground text-xs font-medium px-4 py-1.5 rounded-full mb-8 transition-colors hover:bg-secondary">
          <Sparkles size={12} className="text-emerald-500" />
          <span>Production-grade AI documentation pipeline</span>
        </motion.div>

        <motion.h1 variants={fadeIn} className="relative text-6xl md:text-[5.5rem] font-bold tracking-tighter text-foreground mb-8 leading-[0.9]">
          Ship technical
          <br />
          <span className="text-muted-foreground bg-clip-text text-transparent bg-gradient-to-r from-foreground/60 to-foreground/30">
            knowledge faster.
          </span>
        </motion.h1>

        <motion.p variants={fadeIn} className="relative text-lg md:text-xl text-muted-foreground max-w-2xl mx-auto mb-10 leading-relaxed font-light">
          WriterLM orchestrates multiple LLMs to autonomously research, draft, and typeset full-length textbooks, course companions, and technical guides.
        </motion.p>

        <motion.div variants={fadeIn} className="relative flex items-center justify-center gap-4 flex-wrap">
          <SignUpButton mode="modal">
            <Button size="lg" className="h-12 px-8 text-sm font-semibold shadow-lg shadow-emerald-500/10">
              Start building <ChevronRight size={16} className="ml-1" />
            </Button>
          </SignUpButton>
          <Button variant="outline" size="lg" className="h-12 px-8 text-sm font-semibold border-border bg-background hover:bg-secondary" onClick={() => window.open("https://github.com/anounman/writerLm", "_blank")}>
            <Github size={16} className="mr-2" /> View on GitHub
          </Button>
        </motion.div>
      </motion.main>

      {/* PDF Viewer Showcase */}
      <motion.section 
        initial={{ opacity: 0, y: 40, scale: 0.95 }}
        whileInView={{ opacity: 1, y: 0, scale: 1 }}
        viewport={{ once: true, margin: "-100px" }}
        transition={{ duration: 0.7, ease: "easeOut" }}
        className="max-w-5xl mx-auto px-6 pb-32 relative z-10"
      >
        <div className="relative rounded-2xl border border-border bg-card/40 backdrop-blur-xl shadow-2xl overflow-hidden">
          {/* macOS Mock Header */}
          <div className="h-12 border-b border-border/50 bg-background/50 flex items-center px-4 justify-between">
            <div className="flex gap-2">
              <div className="w-3 h-3 rounded-full bg-red-500/80" />
              <div className="w-3 h-3 rounded-full bg-yellow-500/80" />
              <div className="w-3 h-3 rounded-full bg-green-500/80" />
            </div>
            <div className="text-xs font-mono text-muted-foreground flex items-center gap-2 bg-secondary/50 px-3 py-1 rounded-md">
              <FileText size={12} /> generated_book.pdf
            </div>
            <div className="w-12" /> {/* Spacer */}
          </div>
          
          {/* PDF Viewer Content */}
          <div className="w-full h-[600px] bg-white">
            <iframe 
              src="/sample_book.pdf#toolbar=0&navpanes=0&scrollbar=0" 
              className="w-full h-full border-0"
              title="Sample Generated Book"
            />
          </div>
        </div>

        {/* Floating Badges */}
        <motion.div 
          initial={{ opacity: 0, x: 20 }}
          whileInView={{ opacity: 1, x: 0 }}
          viewport={{ once: true }}
          transition={{ delay: 0.5 }}
          className="absolute -right-4 top-1/4 hidden lg:flex items-center gap-2 bg-background border border-border shadow-lg rounded-full px-4 py-2"
        >
          <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          <span className="text-xs font-medium">LaTeX Compiled</span>
        </motion.div>
        
        <motion.div 
          initial={{ opacity: 0, x: -20 }}
          whileInView={{ opacity: 1, x: 0 }}
          viewport={{ once: true }}
          transition={{ delay: 0.7 }}
          className="absolute -left-4 bottom-1/4 hidden lg:flex items-center gap-2 bg-background border border-border shadow-lg rounded-full px-4 py-2"
        >
          <Brain size={14} className="text-blue-500" />
          <span className="text-xs font-medium">Multi-LLM Synthesized</span>
        </motion.div>
      </motion.section>

      {/* Bento Grid Features */}
      <section className="max-w-6xl mx-auto px-6 pb-32">
        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          className="mb-12 text-center"
        >
          <h2 className="text-3xl font-bold tracking-tight mb-4">Enterprise-ready architecture</h2>
          <p className="text-muted-foreground max-w-xl mx-auto">A fully containerized pipeline designed for deep research, factual accuracy, and beautiful typography.</p>
        </motion.div>

        <motion.div 
          variants={staggerContainer}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: "-100px" }}
          className="grid grid-cols-1 md:grid-cols-4 gap-4 md:grid-rows-2"
        >
          {/* Card 1: Multi-LLM Orchestration */}
          <motion.div variants={fadeIn} className="md:col-span-2 md:row-span-2 p-8 rounded-2xl border border-border bg-card/50 backdrop-blur-sm flex flex-col relative overflow-hidden group hover:border-border/80 transition-colors">
            <div className="absolute top-0 right-0 p-8 opacity-10 transition-opacity group-hover:opacity-20">
              <Brain size={120} />
            </div>
            <div className="w-10 h-10 rounded-lg bg-foreground/10 flex items-center justify-center mb-6">
              <Layers size={20} className="text-foreground" />
            </div>
            <h3 className="text-xl font-semibold mb-3">Multi-LLM Orchestration</h3>
            <p className="text-muted-foreground leading-relaxed mb-8 flex-grow">
              Assign the right model for the right job. Use reasoning models like Gemini Flash for curriculum planning, and high-throughput OSS models like Llama 3 for drafting.
            </p>
            <div className="grid grid-cols-2 gap-3 mt-auto">
              <div className="bg-background rounded-lg border border-border p-3 text-xs font-mono text-muted-foreground">
                <span className="text-foreground font-medium block mb-1">Planner</span>
                gemini-2.5-flash
              </div>
              <div className="bg-background rounded-lg border border-border p-3 text-xs font-mono text-muted-foreground">
                <span className="text-foreground font-medium block mb-1">Drafter</span>
                llama-3.3-70b
              </div>
            </div>
          </motion.div>

          {/* Card 2: Hybrid RAG */}
          <motion.div variants={fadeIn} className="md:col-span-2 p-8 rounded-2xl border border-border bg-card/50 backdrop-blur-sm group hover:border-border/80 transition-colors">
            <div className="flex items-start justify-between mb-6">
              <div className="w-10 h-10 rounded-lg bg-foreground/10 flex items-center justify-center">
                <Search size={20} className="text-foreground" />
              </div>
              <div className="flex gap-2">
                <span className="text-[10px] font-mono uppercase tracking-wider bg-emerald-500/10 text-emerald-500 px-2 py-1 rounded">Web</span>
                <span className="text-[10px] font-mono uppercase tracking-wider bg-blue-500/10 text-blue-500 px-2 py-1 rounded">PDF</span>
              </div>
            </div>
            <h3 className="text-xl font-semibold mb-3">Hybrid Source Ingestion</h3>
            <p className="text-muted-foreground leading-relaxed">
              Upload local PDFs to ground the AI in your proprietary documents, or enable Web Search (via Tavily/Firecrawl) to pull live data from the internet.
            </p>
          </motion.div>

          {/* Card 3: LaTeX Compilation */}
          <motion.div variants={fadeIn} className="md:col-span-1 p-8 rounded-2xl border border-border bg-card/50 backdrop-blur-sm group hover:border-border/80 transition-colors">
            <div className="w-10 h-10 rounded-lg bg-foreground/10 flex items-center justify-center mb-6">
              <FileText size={20} className="text-foreground" />
            </div>
            <h3 className="text-xl font-semibold mb-3">LaTeX Engine</h3>
            <p className="text-muted-foreground text-sm leading-relaxed">
              Native pdflatex integration compiles mathematically rigorous, publish-ready PDFs instantly.
            </p>
          </motion.div>

          {/* Card 4: Granular Control */}
          <motion.div variants={fadeIn} className="md:col-span-1 p-8 rounded-2xl border border-border bg-card/50 backdrop-blur-sm group hover:border-border/80 transition-colors">
            <div className="w-10 h-10 rounded-lg bg-foreground/10 flex items-center justify-center mb-6">
              <Code2 size={20} className="text-foreground" />
            </div>
            <h3 className="text-xl font-semibold mb-3">Granular Tone</h3>
            <p className="text-muted-foreground text-sm leading-relaxed">
              Control pedagogy style, theory/practice balance, and code density per book.
            </p>
          </motion.div>

        </motion.div>
      </section>

      {/* Pipeline Journey */}
      <section className="border-t border-border bg-secondary/20 py-32 px-6 overflow-hidden">
        <div className="max-w-4xl mx-auto">
          <motion.div 
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-100px" }}
            className="mb-16 text-center"
          >
            <h2 className="text-3xl font-bold tracking-tight mb-4">How it works</h2>
            <p className="text-muted-foreground">A multi-stage pipeline designed to beat context window limits.</p>
          </motion.div>

          <div className="space-y-12 relative">
            {/* Animated Connecting line */}
            <motion.div 
              initial={{ scaleY: 0 }}
              whileInView={{ scaleY: 1 }}
              viewport={{ once: true, margin: "-200px" }}
              transition={{ duration: 1.5, ease: "easeInOut" }}
              className="absolute left-[27px] top-6 bottom-6 w-px bg-border md:left-1/2 md:-ml-px origin-top" 
            />

            {[
              { step: 1, title: "Planning & Outline", icon: Brain, desc: "The Planner LLM parses your prompt and generates a structured JSON table of contents, determining sections, word counts, and pedagogical approach." },
              { step: 2, title: "Research Phase", icon: Database, desc: "For each section, the Researcher LLM scans your uploaded PDFs and executes targeted web searches to build factual context briefs." },
              { step: 3, title: "Parallel Drafting", icon: PenTool, desc: "The Drafter LLM processes the research briefs in parallel (chunking up to 12 concurrent workers) to write high-density content in raw LaTeX format." },
              { step: 4, title: "Compilation & Review", icon: FileText, desc: "The sections are stitched together into a master document. The backend invokes a native LaTeX compiler to generate the final PDF." }
            ].map((stage, i) => (
              <motion.div 
                key={stage.step}
                initial={{ opacity: 0, x: i % 2 === 0 ? -30 : 30 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true, margin: "-100px" }}
                transition={{ duration: 0.5, delay: i * 0.1 }}
                className="relative flex items-start gap-8 md:justify-center"
              >
                <div className={`hidden md:block w-1/2 pt-2 pr-12 text-right ${i % 2 !== 0 ? 'order-1' : 'order-3 text-left pl-12 pr-0'}`}>
                  <h3 className="text-lg font-semibold mb-2">{stage.title}</h3>
                  <p className="text-muted-foreground text-sm leading-relaxed">{stage.desc}</p>
                </div>

                <div className="z-10 flex-shrink-0 w-14 h-14 rounded-full bg-background border-2 border-border flex items-center justify-center">
                  <stage.icon size={20} className="text-foreground" />
                </div>

                <div className="md:hidden pt-2">
                  <h3 className="text-lg font-semibold mb-2">Step {stage.step}: {stage.title}</h3>
                  <p className="text-muted-foreground text-sm leading-relaxed">{stage.desc}</p>
                </div>
                
                <div className={`hidden md:block w-1/2 ${i % 2 !== 0 ? 'order-3' : 'order-1'}`} />
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <motion.section 
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-100px" }}
        className="py-32 px-6 text-center border-t border-border"
      >
        <h2 className="text-3xl md:text-4xl font-bold tracking-tight mb-6">Ready to generate your first book?</h2>
        <p className="text-muted-foreground mb-10 max-w-lg mx-auto">Create an account, bring your own API keys, and start building long-form technical content.</p>
        <SignUpButton mode="modal">
          <Button size="lg" className="h-12 px-8 font-semibold shadow-lg shadow-emerald-500/10 hover:scale-105 transition-transform">
            Get started for free
          </Button>
        </SignUpButton>
      </motion.section>

      {/* Footer */}
      <footer className="border-t border-border px-6 py-10 bg-background">
        <div className="max-w-5xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4 text-xs text-muted-foreground">
          <div className="flex items-center gap-2">
            <div className="w-5 h-5 rounded bg-muted-foreground/20 flex items-center justify-center">
              <BookOpen size={11} strokeWidth={2.5} className="text-foreground" />
            </div>
            <span className="font-semibold text-foreground">WriterLM</span>
            <span className="px-2">·</span>
            <span>Open Source AI Pipeline</span>
          </div>
          <div className="flex items-center gap-6">
            <a href="https://github.com/anounman/writerLm" target="_blank" rel="noreferrer" className="hover:text-foreground transition-colors flex items-center gap-1.5">
              <Github size={14} /> GitHub
            </a>
            <span>© 2026</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
