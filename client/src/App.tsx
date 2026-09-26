import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowLeft,
  ArrowRight,
  BarChart3,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleDot,
  ClipboardCheck,
  CloudUpload,
  Code2,
  Database,
  FileCode2,
  FileSearch,
  FolderGit2,
  Github,
  GitBranch,
  GitCommitHorizontal,
  Info,
  LayoutDashboard,
  ListChecks,
  Loader2,
  LockKeyhole,
  Menu,
  Network,
  Play,
  Plus,
  RotateCcw,
  ScanSearch,
  Search,
  Server,
  Settings2,
  ShieldCheck,
  ShieldHalf,
  Sparkles,
  TerminalSquare,
  TestTube2,
  Upload,
  X,
  Zap,
} from "lucide-react";
import {
  behavioralContract,
  driftResult,
  impactAnalysis,
  maintenanceRequest,
  proofOfDone,
  repositoryAnalysis,
  verificationResult,
  type EvidenceSource,
} from "./services/devguardApi";

type ViewKey =
  | "overview"
  | "repositories"
  | "connect"
  | "understanding"
  | "maintenance"
  | "contract"
  | "impact"
  | "bob"
  | "review"
  | "drift"
  | "verify"
  | "proof";

type Notice = { tone: "neutral" | "success" | "warning"; text: string } | null;

const navItems: { key: ViewKey; label: string; icon: typeof LayoutDashboard; group?: string }[] = [
  { key: "overview", label: "Overview", icon: LayoutDashboard },
  { key: "repositories", label: "Repositories", icon: FolderGit2 },
  { key: "maintenance", label: "Maintenance", icon: Settings2 },
  { key: "contract", label: "Behavioral Contracts", icon: ClipboardCheck },
  { key: "impact", label: "Impact Analysis", icon: Network },
  { key: "bob", label: "Bob Execution", icon: TerminalSquare },
  { key: "drift", label: "Drift Detection", icon: AlertTriangle },
  { key: "verify", label: "Verification", icon: TestTube2 },
  { key: "proof", label: "Proof of Done", icon: ShieldCheck },
];

const workflow = [
  { key: "understanding" as ViewKey, label: "Understand", short: "01" },
  { key: "contract" as ViewKey, label: "Contract", short: "02" },
  { key: "impact" as ViewKey, label: "Impact", short: "03" },
  { key: "bob" as ViewKey, label: "Bob", short: "04" },
  { key: "drift" as ViewKey, label: "Drift", short: "05" },
  { key: "verify" as ViewKey, label: "Verify", short: "06" },
  { key: "proof" as ViewKey, label: "Proof", short: "07" },
];

const analysisSteps = [
  "Reading source files",
  "Analyzing dependencies",
  "Reading tests",
  "Reconstructing behavior",
  "Building evidence",
  "Establishing baseline",
];

const verificationSteps = [
  "Creating isolated working copy",
  "Applying candidate change",
  "Running tests",
  "Comparing baseline failures",
  "Checking protected behavior",
  "Evaluating contract",
];

function StatusBadge({ tone = "neutral", children }: { tone?: "neutral" | "green" | "amber" | "red"; children: ReactNode }) {
  const styles = {
    neutral: "border-white/10 bg-white/[0.04] text-muted",
    green: "border-emerald-400/25 bg-emerald-400/10 text-emerald-300",
    amber: "border-amber-400/25 bg-amber-400/10 text-amber-200",
    red: "border-red-400/25 bg-red-400/10 text-red-300",
  }[tone];
  return <span className={`status-badge ${styles}`}><span className="status-dot" />{children}</span>;
}

function Panel({ children, className = "", accent = false }: { children: ReactNode; className?: string; accent?: boolean }) {
  return <section className={`panel ${accent ? "panel-accent" : ""} ${className}`}>{children}</section>;
}

function SectionHeader({ eyebrow, title, description, action }: { eyebrow?: string; title: string; description?: string; action?: ReactNode }) {
  return (
    <div className="section-header">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {action}
    </div>
  );
}

function Button({ children, onClick, variant = "primary", icon: Icon, disabled = false, className = "" }: { children: ReactNode; onClick?: () => void; variant?: "primary" | "secondary" | "ghost" | "danger"; icon?: typeof ArrowRight; disabled?: boolean; className?: string }) {
  return (
    <button disabled={disabled} className={`button button-${variant} ${className}`} onClick={onClick}>
      {Icon && <Icon size={15} strokeWidth={1.8} />}
      <span>{children}</span>
    </button>
  );
}

function WorkflowStepper({ active, onSelect }: { active: ViewKey; onSelect: (key: ViewKey) => void }) {
  return (
    <div className="workflow-strip">
      <div className="workflow-label"><span className="pulse-mark" /> INVESTIGATION WORKFLOW</div>
      <div className="workflow-items">
        {workflow.map((item, index) => {
          const isCurrent = active === item.key;
          const isPast = workflow.findIndex((entry) => entry.key === active) > index;
          return (
            <div className="workflow-node-wrap" key={item.key}>
              <button className={`workflow-node ${isCurrent ? "current" : ""} ${isPast ? "past" : ""}`} onClick={() => onSelect(item.key)}>
                <span className="workflow-number">{isPast ? <Check size={12} /> : item.short}</span>
                <span>{item.label}</span>
              </button>
              {index < workflow.length - 1 && <span className={`workflow-line ${isPast ? "filled" : ""}`} />}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function EvidencePanel({ source, text }: { source: EvidenceSource; text: string }) {
  return (
    <div className="evidence-row">
      <span className={`evidence-tag evidence-${source.toLowerCase()}`}>{source}</span>
      <span>{text}</span>
    </div>
  );
}

function ProtectedBehaviorList({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`protected-list ${compact ? "compact" : ""}`}>
      {behavioralContract.protectedBehaviors.map((behavior) => (
        <div className="protected-item" key={behavior.id}>
          <div className="protected-icon"><LockKeyhole size={14} /></div>
          <div className="protected-copy"><strong>{behavior.title}</strong>{!compact && <span>{behavior.description}</span>}</div>
          <span className="mono muted">{behavior.id}</span>
        </div>
      ))}
    </div>
  );
}

function CodeDiff({ corrected = false }: { corrected?: boolean }) {
  return (
    <div className="code-diff">
      <div className="code-toolbar"><span className="file-chip"><FileCode2 size={13} /> customers.py</span><span className="mono muted">working tree</span></div>
      <div className="code-line context"><span className="line-number">18</span><span className="line-mark"> </span><code>def discount_for(customer_type):</code></div>
      <div className="code-line removed"><span className="line-number">19</span><span className="line-mark">−</span><code>    ENTERPRISE_DISCOUNT = 0.10</code></div>
      <div className="code-line added"><span className="line-number">19</span><span className="line-mark">+</span><code>    ENTERPRISE_DISCOUNT = 0.15</code></div>
      {!corrected && <>
        <div className="code-line removed"><span className="line-number">20</span><span className="line-mark">−</span><code>    LOYALTY_DISCOUNT = 0.10</code></div>
        <div className="code-line added bad"><span className="line-number">20</span><span className="line-mark">+</span><code>    LOYALTY_DISCOUNT = 0.15</code></div>
      </>}
      {corrected && <div className="code-line context"><span className="line-number">20</span><span className="line-mark"> </span><code>    LOYALTY_DISCOUNT = 0.10</code></div>}
      <div className="code-line context"><span className="line-number">21</span><span className="line-mark"> </span><code>    return resolve_discount(customer_type)</code></div>
    </div>
  );
}

function Metric({ label, value, detail, icon: Icon }: { label: string; value: string | number; detail: string; icon: typeof Database }) {
  return <div className="metric"><div className="metric-top"><span>{label}</span><Icon size={14} /></div><strong>{value}</strong><small>{detail}</small></div>;
}

function EmptyState({ title, copy, onClick }: { title: string; copy: string; onClick: () => void }) {
  return <div className="empty-state"><div className="empty-icon"><FolderGit2 size={20} /></div><h3>{title}</h3><p>{copy}</p><Button onClick={onClick} variant="secondary" icon={Plus}>Connect Repository</Button></div>;
}

function App() {
  const [active, setActive] = useState<ViewKey>("overview");
  const [mobileOpen, setMobileOpen] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);
  const [source, setSource] = useState("GitHub Repository");
  const [analysisState, setAnalysisState] = useState<"idle" | "running" | "complete">("idle");
  const [analysisStep, setAnalysisStep] = useState(0);
  const [verificationState, setVerificationState] = useState<"idle" | "running" | "complete">("idle");
  const [verificationStep, setVerificationStep] = useState(0);
  const [demoExecuted, setDemoExecuted] = useState(false);
  const [proofOpen, setProofOpen] = useState<string | null>("Behavioral Evidence");

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "smooth" });
    setMobileOpen(false);
  }, [active]);

  useEffect(() => {
    if (analysisState !== "running") return;
    const timer = window.setInterval(() => setAnalysisStep((step) => step + 1), 720);
    return () => window.clearInterval(timer);
  }, [analysisState]);

  useEffect(() => {
    if (analysisState === "running" && analysisStep >= analysisSteps.length) {
      setAnalysisState("complete");
      setNotice({ tone: "success", text: "Behavioral baseline established for the sample repository." });
      setActive("understanding");
    }
  }, [analysisState, analysisStep]);

  useEffect(() => {
    if (verificationState !== "running") return;
    const timer = window.setInterval(() => setVerificationStep((step) => step + 1), 720);
    return () => window.clearInterval(timer);
  }, [verificationState]);

  useEffect(() => {
    if (verificationState === "running" && verificationStep >= verificationSteps.length) {
      setVerificationState("complete");
      setNotice({ tone: "success", text: "Deterministic verification passed. Protected behaviors were preserved." });
      setActive("proof");
    }
  }, [verificationState, verificationStep]);

  const go = (view: ViewKey) => setActive(view);
  const triggerNotice = (next: Notice) => {
    setNotice(next);
    window.setTimeout(() => setNotice(null), 4200);
  };
  const startAnalysis = () => {
    setAnalysisStep(0);
    setAnalysisState("running");
    triggerNotice({ tone: "neutral", text: "Analyzing the sample repository. This is a simulated demo flow." });
  };
  const startVerification = () => {
    setVerificationStep(0);
    setVerificationState("running");
  };

  const page = useMemo(() => {
    switch (active) {
      case "repositories": return <RepositoriesPage go={go} triggerNotice={triggerNotice} />;
      case "connect": return <ConnectPage source={source} setSource={setSource} analysisState={analysisState} analysisStep={analysisStep} startAnalysis={startAnalysis} />;
      case "understanding": return <UnderstandingPage go={go} />;
      case "maintenance": return <MaintenancePage go={go} />;
      case "contract": return <ContractPage go={go} />;
      case "impact": return <ImpactPage go={go} />;
      case "bob": return <BobPage go={go} demoExecuted={demoExecuted} setDemoExecuted={setDemoExecuted} triggerNotice={triggerNotice} />;
      case "review": return <ReviewPage go={go} />;
      case "drift": return <DriftPage go={go} />;
      case "verify": return <VerifyPage go={go} verificationState={verificationState} verificationStep={verificationStep} startVerification={startVerification} />;
      case "proof": return <ProofPage proofOpen={proofOpen} setProofOpen={setProofOpen} triggerNotice={triggerNotice} />;
      default: return <OverviewPage go={go} />;
    }
  }, [active, analysisState, analysisStep, demoExecuted, proofOpen, source, verificationState, verificationStep]);

  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobileOpen ? "open" : ""}`}>
        <div className="brand-block">
          <div className="brand-mark"><ShieldHalf size={18} /></div>
          <div><strong>DEVGUARD</strong><span>2.0 / CONTROL PLANE</span></div>
          <button className="mobile-close" onClick={() => setMobileOpen(false)}><X size={18} /></button>
        </div>
        <div className="workspace-label">WORKSPACE <span>DEMO</span></div>
        <nav className="side-nav">
          {navItems.map(({ key, label, icon: Icon }) => (
            <button key={key} className={`nav-item ${active === key ? "selected" : ""}`} onClick={() => go(key)}>
              <Icon size={16} strokeWidth={1.7} /><span>{label}</span>{active === key && <span className="nav-active-line" />}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="sidebar-rule" />
          <button className="nav-item" onClick={() => triggerNotice({ tone: "neutral", text: "Settings are scoped to this demo workspace." })}><Settings2 size={16} /><span>Settings</span></button>
          <div className="user-row"><div className="avatar">MC</div><div><strong>mira.chen</strong><span>Developer</span></div><ChevronRight size={14} className="muted" /></div>
        </div>
      </aside>

      {mobileOpen && <button className="mobile-scrim" onClick={() => setMobileOpen(false)} aria-label="Close navigation" />}

      <main className="main-shell">
        <header className="topbar">
          <button className="mobile-menu" onClick={() => setMobileOpen(true)}><Menu size={18} /></button>
          <div className="crumbs"><span>DEVGUARD</span><ChevronRight size={13} /><span className="crumb-repo"><span className="repo-dot" /> LegacyShop</span><StatusBadge tone="amber">SAMPLE LEGACY REPOSITORY</StatusBadge></div>
          <div className="topbar-meta"><span><span className="green-dot" /> Baseline established</span><span className="top-divider" /><span>Environment: <strong>Demo</strong></span></div>
        </header>

        {notice && <div className={`notice notice-${notice.tone}`}><span className="notice-icon">{notice.tone === "success" ? <CheckCircle2 size={15} /> : notice.tone === "warning" ? <AlertTriangle size={15} /> : <Info size={15} />}</span>{notice.text}<button onClick={() => setNotice(null)}><X size={14} /></button></div>}

        <div className="content-wrap">
          <WorkflowStepper active={active} onSelect={go} />
          <div className="view-enter" key={active}>{page}</div>
        </div>
      </main>
    </div>
  );
}

function OverviewPage({ go }: { go: (view: ViewKey) => void }) {
  return <div className="page-stack">
    <div className="hero-grid">
      <div className="hero-copy">
        <div className="eyebrow"><span className="pulse-mark" /> BEHAVIORAL SAFETY / AI-ASSISTED MAINTENANCE</div>
        <h1>Know what changed.<br /><em>Prove what stayed.</em></h1>
        <p>DEVGUARD sits around your existing codebase to understand behavior, constrain the maintenance task, and verify what IBM Bob actually changed.</p>
        <div className="hero-actions"><Button onClick={() => go("connect")} icon={ArrowRight}>Connect Repository</Button><Button onClick={() => go("understanding")} variant="secondary" icon={Play}>View Demo</Button></div>
        <div className="hero-footnote"><span className="mono">NO REWRITE REQUIRED</span><span className="tiny-divider" /><span className="mono">PYTHON ENGINE READY</span></div>
      </div>
      <div className="hero-visual">
        <div className="orbit orbit-one" /><div className="orbit orbit-two" /><div className="orbit orbit-three" />
        <div className="visual-core"><ShieldCheck size={36} strokeWidth={1.2} /><span>BEHAVIORAL<br />BASELINE</span><strong>ESTABLISHED</strong></div>
        <div className="orbit-tag tag-top"><span className="green-dot" /> EVIDENCE <b>18</b></div>
        <div className="orbit-tag tag-bottom"><span className="amber-dot" /> DRIFT GATE <b>ARMED</b></div>
      </div>
    </div>

    <Panel className="repository-banner" accent>
      <div className="panel-overline"><span className="amber-bar" /> ACTIVE REPOSITORY</div>
      <div className="repo-banner-main"><div><div className="repo-title"><FolderGit2 size={18} /> LegacyShop</div><div className="repo-sub"><span className="mono">main</span><span>·</span><span className="mono">4f9c1a2</span><span>·</span><span>Python / pytest</span></div></div><StatusBadge tone="green">BASELINE ESTABLISHED</StatusBadge></div>
      <div className="repo-banner-footer"><span>SAMPLE LEGACY REPOSITORY</span><span className="mono">SIMULATED DEMO DATA</span><button onClick={() => go("understanding")}>Open repository <ArrowRight size={14} /></button></div>
    </Panel>

    <div className="overview-grid">
      <Panel className="workflow-panel"><div className="panel-heading"><div><div className="eyebrow">THE INVESTIGATION</div><h2>From existing code to proof.</h2></div><span className="mono muted">REQ-2026-041</span></div><div className="vertical-flow">{[
        ["UNDERSTAND", "Reconstruct behavior from code, tests, and evidence.", "complete"], ["CONTRACT", "Define the allowed change and protected behaviors.", "complete"], ["IMPACT", "Map the requested symbol to its behavioral dependencies.", "complete"], ["IBM BOB", "Hand off a constrained task to the maintenance agent.", "active"], ["DRIFT → VERIFY → PROOF", "Inspect actual changes, then create durable evidence.", "blocked"],
      ].map(([label, text, state], index) => <div className={`flow-row ${state}`} key={label}><div className="flow-index">{state === "complete" ? <Check size={13} /> : state === "active" ? <CircleDot size={13} /> : index + 1}</div><div><strong>{label}</strong><span>{text}</span></div><div className="flow-status">{state === "complete" ? "DONE" : state === "active" ? "CURRENT" : "NEXT"}</div></div>)}</div></Panel>
      <Panel className="current-panel" accent><div className="panel-overline"><span className="red-bar" /> CURRENT INVESTIGATION</div><div className="current-icon"><AlertTriangle size={20} /></div><h2>Intent drift detected</h2><p>IBM Bob changed the requested Enterprise behavior — and a protected Loyalty behavior along with it.</p><div className="current-change"><div><span>REQUESTED</span><strong>ENTERPRISE_DISCOUNT</strong><b>10% → 15%</b></div><ArrowDownRight size={20} /><div className="bad-change"><span>UNEXPECTED</span><strong>LOYALTY_DISCOUNT</strong><b>10% → 15%</b></div></div><StatusBadge tone="red">BLOCKED / FAILED</StatusBadge><button className="text-button" onClick={() => go("drift")}>Review drift analysis <ArrowRight size={14} /></button></Panel>
    </div>
  </div>;
}

function RepositoriesPage({ go, triggerNotice }: { go: (view: ViewKey) => void; triggerNotice: (notice: Notice) => void }) {
  return <div className="page-stack"><SectionHeader eyebrow="WORKSPACE / REPOSITORIES" title="Repositories" description="Existing codebases connected to this DEVGUARD workspace." action={<Button onClick={() => go("connect")} icon={Plus}>Connect Repository</Button>} /><Panel className="repo-table-panel"><div className="table-toolbar"><div className="search-field"><Search size={15} /><input placeholder="Filter repositories" /></div><span className="mono muted">1 repository</span></div><div className="repo-table"><div className="repo-row repo-head"><span>REPOSITORY</span><span>BASELINE</span><span>LAST ANALYSIS</span><span>ACTIONS</span></div><div className="repo-row"><div className="repo-cell-main"><div className="repo-icon"><FolderGit2 size={17} /></div><div><strong>LegacyShop</strong><span><StatusBadge tone="amber">SAMPLE LEGACY REPOSITORY</StatusBadge></span></div></div><div><StatusBadge tone="green">ESTABLISHED</StatusBadge></div><div className="mono muted">Today, 14:42</div><div className="row-actions"><button onClick={() => go("understanding")}>View</button><button onClick={() => go("connect")}>Analyze</button><button onClick={() => go("maintenance")}>Maintenance Request</button></div></div></div><div className="repo-table-foot"><span><span className="green-dot" /> Demo repository is isolated from your source code.</span><button className="text-button" onClick={() => triggerNotice({ tone: "neutral", text: "Production repository connectors are intentionally not active in this prototype." })}>About repository connections <Info size={14} /></button></div></Panel><div className="empty-hint"><CloudUpload size={17} /><span>Connect an existing repository to establish a behavioral baseline. No repository is uploaded from this demo.</span></div></div>;
}

function ConnectPage({ source, setSource, analysisState, analysisStep, startAnalysis }: { source: string; setSource: (source: string) => void; analysisState: "idle" | "running" | "complete"; analysisStep: number; startAnalysis: () => void }) {
  return <div className="page-stack"><SectionHeader eyebrow="GET STARTED / EXISTING CODE" title="Connect a Repository" description="DEVGUARD works around your existing application. You do not need to rewrite your codebase to use it." /><div className="connect-grid"><Panel className="connect-options"><div className="panel-heading"><div><div className="eyebrow">CONNECTION METHOD</div><h2>Choose your source</h2></div><span className="mono muted">DEMO ONLY</span></div>{[
    ["GitHub Repository", Github, "Connect a repository URL or organization."], ["Local Repository", FolderGit2, "Point DEVGUARD at an existing local checkout."], ["Upload Repository", Upload, "Upload an archive for a one-time analysis."],
  ].map(([label, Icon, copy]) => <button key={label as string} className={`source-option ${source === label ? "active" : ""}`} onClick={() => setSource(label as string)}><span className="source-icon"><Icon size={17} /></span><span><strong>{label as string}</strong><small>{copy as string}</small></span>{source === label ? <CheckCircle2 size={17} className="source-check" /> : <ChevronRight size={17} className="muted" />}</button>)}<div className="form-grid"><label>Repository<input value="LegacyShop" readOnly /></label><label>Branch<input value="main" readOnly /></label><label>Commit<input className="mono" value="4f9c1a2" readOnly /></label><label>Language<input value="Python" readOnly /></label><label>Test framework<input value="pytest" readOnly /></label></div><div className="connect-foot"><div><span className="green-dot" /> SAMPLE LEGACY REPOSITORY</div><Button onClick={startAnalysis} disabled={analysisState === "running"} icon={analysisState === "running" ? Loader2 : ScanSearch}>{analysisState === "running" ? "Analyzing…" : "Analyze Repository"}</Button></div></Panel><Panel className="analysis-panel"><div className="panel-overline"><span className="green-bar" /> ANALYSIS PIPELINE</div><h2>{analysisState === "complete" ? "Baseline established" : "Understand before you change."}</h2><p>{analysisState === "running" ? "The demo engine is reconstructing the repository's behavioral evidence." : "Repository understanding turns code, tests, and existing behavior into an evidence-backed baseline."}</p><div className="analysis-list">{analysisSteps.map((step, index) => <div className={`analysis-step ${analysisState === "running" && index === analysisStep ? "current" : ""} ${analysisState === "complete" || index < analysisStep ? "done" : ""}`} key={step}><span className="analysis-marker">{analysisState === "running" && index === analysisStep ? <Loader2 size={13} className="spin" /> : analysisState === "complete" || index < analysisStep ? <Check size={13} /> : <span>{String(index + 1).padStart(2, "0")}</span>}</span><span>{step}</span>{analysisState === "complete" || index < analysisStep ? <span className="mono success-text">DONE</span> : null}</div>)}</div><div className="analysis-note"><Info size={14} />This is simulated demo data. A real REST boundary will replace the local service implementation.</div></Panel></div></div>;
}

function UnderstandingPage({ go }: { go: (view: ViewKey) => void }) {
  const files = ["catalog.py", "customers.py", "discount.py", "tax.py", "cart.py", "checkout.py", "refunds.py", "tests/"];
  return <div className="page-stack"><SectionHeader eyebrow="REPOSITORY / LEGACYSHOP" title="Repository Understanding" description="A behavioral map reconstructed from the sample repository's source, tests, and documentation." action={<StatusBadge tone="green">BASELINE ESTABLISHED</StatusBadge>} /><div className="understanding-metrics"><Metric label="Files analyzed" value={repositoryAnalysis.filesAnalyzed} detail="source files" icon={FileSearch} /><Metric label="Tests discovered" value={repositoryAnalysis.testsDiscovered} detail="pytest cases" icon={TestTube2} /><Metric label="Behavioral rules" value={repositoryAnalysis.behavioralRules} detail="mapped relationships" icon={Network} /><Metric label="Protected behaviors" value={repositoryAnalysis.protectedBehaviors} detail="contract candidates" icon={LockKeyhole} /><Metric label="Evidence sources" value={repositoryAnalysis.evidenceSources} detail="observed / tested" icon={Database} /></div><div className="understanding-grid"><Panel><div className="panel-heading"><div><div className="eyebrow">SOURCE MAP</div><h2>Repository files</h2></div><span className="mono muted">sample_app/</span></div><div className="file-tree"><div className="tree-root"><ChevronDown size={14} /><FolderGit2 size={15} /> <strong>sample_app/</strong></div>{files.map((file) => <div className={`tree-file ${file === "discount.py" ? "selected" : ""}`} key={file}><span className="tree-indent" />{file.endsWith("/") ? <FolderGit2 size={14} /> : <FileCode2 size={14} />}<span>{file}</span>{file === "discount.py" && <span className="tree-selected">TARGET</span>}</div>)}</div><div className="tree-footer"><span>8 files in baseline</span><span className="mono">4f9c1a2</span></div></Panel><Panel><div className="panel-heading"><div><div className="eyebrow">BEHAVIOR MAP</div><h2>Relationships with provenance</h2></div><Info size={16} className="muted" /></div><div className="relationship-map"><div className="relationship-node main"><span>Customer type</span><b>OBSERVED</b></div><ArrowRight className="relationship-arrow" size={16} /><div className="relationship-node"><span>Discount</span><b>TESTED</b></div><ArrowRight className="relationship-arrow" size={16} /><div className="relationship-node"><span>Coupon</span><b>DOCUMENTED</b></div><ArrowDownRight className="relationship-turn" size={16} /><div className="relationship-node"><span>Tax</span><b>OBSERVED</b></div><ArrowRight className="relationship-arrow" size={16} /><div className="relationship-node"><span>Checkout</span><b>TESTED</b></div><ArrowRight className="relationship-arrow" size={16} /><div className="relationship-node"><span>Refund</span><b>INFERRED</b></div></div><div className="evidence-stack"><EvidencePanel source="OBSERVED" text="Customer type routes to the discount resolver." /><EvidencePanel source="TESTED" text="Discount behavior is covered by checkout tests." /><EvidencePanel source="DOCUMENTED" text="Coupon order is defined in checkout notes." /><EvidencePanel source="INFERRED" text="Refund mirrors the final checkout amount." /></div></Panel></div><div className="page-actions"><Button onClick={() => go("maintenance")} icon={ArrowRight}>Create Maintenance Request</Button></div></div>;
}

function MaintenancePage({ go }: { go: (view: ViewKey) => void }) {
  return <div className="page-stack"><SectionHeader eyebrow="MAINTENANCE / NEW REQUEST" title="Create Maintenance Request" description="Describe the behavior you want to change. DEVGUARD will turn it into an explicit behavioral boundary." /><div className="maintenance-grid"><Panel className="request-editor"><label className="large-label">What do you want to change?<textarea defaultValue={maintenanceRequest.requestedChange} rows={6} /></label><div className="editor-foot"><span className="mono muted">Natural language request</span><span className="mono muted">0 / 500</span></div><div className="request-actions"><Button variant="secondary" icon={RotateCcw}>Reset</Button><Button onClick={() => go("contract")} icon={ArrowRight}>Create Behavioral Contract</Button></div></Panel><Panel className="request-summary"><div className="panel-overline"><span className="amber-bar" /> REQUEST PREVIEW</div><div className="request-id"><span className="mono muted">REQUEST ID</span><strong>{maintenanceRequest.id}</strong></div><div className="detail-list"><div><span>Requestor</span><strong>{maintenanceRequest.requestor}</strong></div><div><span>Target behavior</span><strong>{maintenanceRequest.targetBehavior}</strong></div><div><span>Requested change</span><strong>{maintenanceRequest.requestedChange}</strong></div></div><div className="summary-note"><Sparkles size={15} /><span>DEVGUARD will inspect the baseline before allowing any code change.</span></div></Panel></div></div>;
}

function ContractPage({ go }: { go: (view: ViewKey) => void }) {
  return <div className="page-stack"><SectionHeader eyebrow="MAINTENANCE REQUEST / REQ-2026-041" title="Behavioral Contract" description="The boundary IBM Bob must operate inside — before any maintenance work begins." action={<StatusBadge tone="green">{behavioralContract.status}</StatusBadge>} /><div className="contract-grid"><Panel className="allowed-panel" accent><div className="contract-label green-label"><CheckCircle2 size={15} /> ALLOWED CHANGE</div><h2>{behavioralContract.allowedBehavior}</h2><div className="change-arrow"><strong>{behavioralContract.from}</strong><ArrowRight size={18} /><strong>{behavioralContract.to}</strong></div><p>Only the Enterprise discount behavior may change in this task.</p></Panel><Panel className="protected-panel"><div className="contract-label"><LockKeyhole size={15} /> PROTECTED BEHAVIOR</div><h2>Must not change</h2><ProtectedBehaviorList /></Panel></div><Panel className="contract-explanation"><div className="explanation-icon"><ShieldCheck size={20} /></div><div><strong>Why this contract exists</strong><p>DEVGUARD converts the maintenance request into an explicit behavioral boundary before AI-assisted changes are made. This is the source of truth for drift detection.</p></div><Button onClick={() => go("impact")} icon={ArrowRight}>Run Impact Analysis</Button></Panel></div>;
}

function ImpactPage({ go }: { go: (view: ViewKey) => void }) {
  return <div className="page-stack"><SectionHeader eyebrow="CONTRACT / SCOPE MAPPING" title="Impact Analysis" description="Where the requested symbol lives, what it touches, and what DEVGUARD will protect." action={<StatusBadge tone="amber">SCOPE REVIEW</StatusBadge>} /><Panel className="symbol-banner"><div><span className="eyebrow">REQUESTED SYMBOL</span><strong className="symbol-name">{impactAnalysis.requestedSymbol}</strong></div><div className="symbol-detail"><span>Allowed change</span><strong>Enterprise discount · 10% → 15%</strong></div><ArrowRight size={18} className="muted" /><div className="symbol-detail"><span>Protected boundary</span><strong>4 behaviors</strong></div></Panel><div className="impact-grid"><Panel><div className="panel-heading"><div><div className="eyebrow">EXPECTED IMPACT</div><h2>Files in scope</h2></div><FileSearch size={16} className="muted" /></div><div className="impact-files">{impactAnalysis.expectedImpact.map((file, index) => <div className="impact-file" key={file}><span className="file-index">0{index + 1}</span><FileCode2 size={15} /><span>{file}</span><StatusBadge tone="green">IN SCOPE</StatusBadge></div>)}</div><div className="impact-note"><Info size={14} />No risk score is fabricated. The boundary is defined by the behavioral contract.</div></Panel><Panel><div className="panel-heading"><div><div className="eyebrow">PROTECTED DEPENDENCIES</div><h2>Must remain stable</h2></div><LockKeyhole size={16} className="muted" /></div><div className="dependency-list">{impactAnalysis.protectedDependencies.map((dependency, index) => <div key={dependency}><span className="dependency-id">B{String(index + 2).padStart(3, "0")}</span><strong>{dependency}</strong><span className="dependency-lock"><LockKeyhole size={13} /></span></div>)}</div></Panel></div><div className="page-actions"><Button onClick={() => go("bob")} icon={ArrowRight}>Prepare IBM Bob Task</Button></div></div>;
}

function BobPage({ go, demoExecuted, setDemoExecuted, triggerNotice }: { go: (view: ViewKey) => void; demoExecuted: boolean; setDemoExecuted: (value: boolean) => void; triggerNotice: (notice: Notice) => void }) {
  return <div className="page-stack"><SectionHeader eyebrow="IMPACT ANALYSIS / HANDOFF" title="IBM Bob Execution" description="DEVGUARD prepares and constrains the maintenance task. IBM Bob performs the code change." /><div className="honesty-banner"><Info size={17} /><div><strong>Important distinction</strong><span>DEVGUARD is the behavioral safety layer. IBM Bob remains the coding and maintenance agent.</span></div></div><div className="bob-grid"><Panel className="task-packet"><div className="panel-heading"><div><div className="eyebrow">PREPARED TASK PACKET</div><h2>Maintenance request</h2></div><span className="mono muted">BOB-TASK-041</span></div><div className="task-block"><span>REQUEST</span><strong>{maintenanceRequest.requestedChange}</strong></div><div className="task-columns"><div><span>ALLOWED SCOPE</span><strong>ENTERPRISE_DISCOUNT</strong></div><div><span>PROTECTED</span><strong>LOYALTY · TAX · COUPON · REFUND</strong></div><div><span>RELEVANT FILES</span><strong>customers.py<br />discount.py<br />related tests</strong></div><div><span>TESTS</span><strong>pytest baseline<br />26 discovered</strong></div></div><div className="instruction-box"><TerminalSquare size={15} /><div><span>BOB TASK INSTRUCTIONS</span><code>Change only the Enterprise discount from 0.10 to 0.15. Preserve all protected behaviors. Run the existing test suite.</code></div></div></Panel><div className="execution-paths"><Panel className="path-card"><div className="path-kicker">PATH A</div><h3>IBM Bob</h3><p>Open the prepared task in IBM Bob and perform the maintenance.</p><Button variant="secondary" onClick={() => triggerNotice({ tone: "neutral", text: "No live programmatic IBM Bob API integration is active in this prototype." })} icon={ArrowRight}>Open IBM Bob Task</Button></Panel><Panel className="path-card demo-path"><div className="path-kicker"><span className="amber-bar" /> PATH B</div><h3>Demo execution</h3><p>Run the controlled demonstration scenario with simulated data.</p><StatusBadge tone="amber">SIMULATED DEMO</StatusBadge><Button onClick={() => { setDemoExecuted(true); go("review"); }} icon={Play}>{demoExecuted ? "Review Demo Changes" : "Run Demo Scenario"}</Button></Panel></div></div></div>;
}

function ReviewPage({ go }: { go: (view: ViewKey) => void }) {
  return <div className="page-stack"><SectionHeader eyebrow="BOB EXECUTION / ACTUAL OUTPUT" title="Change Review" description="Inspect what the maintenance agent actually changed — not just what it was asked to change." action={<StatusBadge tone="amber">SIMULATED DEMO</StatusBadge>} /><div className="review-grid"><Panel className="diff-panel"><div className="panel-heading"><div><div className="eyebrow">ACTUAL DIFF</div><h2>customers.py</h2></div><span className="mono muted">2 changed lines</span></div><CodeDiff /><div className="diff-legend"><span><i className="legend-swatch intended" /> INTENDED</span><span><i className="legend-swatch unintended" /> UNINTENDED</span></div></Panel><div className="change-callouts"><Panel className="intended-card"><div className="callout-label"><CheckCircle2 size={15} /> INTENDED</div><h3>Enterprise discount</h3><p>The requested behavior changed within the allowed scope.</p><div className="mono">ENTERPRISE_DISCOUNT · 10% → 15%</div></Panel><Panel className="unintended-card"><div className="callout-label"><AlertTriangle size={15} /> UNINTENDED</div><h3>Loyalty discount</h3><p>A protected behavior changed as a side effect.</p><div className="mono">LOYALTY_DISCOUNT · 10% → 15%</div></Panel><Button onClick={() => go("drift")} icon={ScanSearch}>Analyze Changes</Button></div></div></div>;
}

function DriftPage({ go }: { go: (view: ViewKey) => void }) {
  return <div className="page-stack"><div className="drift-hero"><div className="drift-emblem"><AlertTriangle size={26} /></div><div className="eyebrow red-eyebrow">DRIFT DETECTION / CONTRACT VIOLATION</div><h1>Intent drift detected</h1><p>DEVGUARD blocked the change.</p><StatusBadge tone="red">BLOCKED / FAILED</StatusBadge></div><div className="drift-grid"><Panel className="drift-compare"><div className="compare-row requested"><div><span>REQUESTED</span><strong>ENTERPRISE_DISCOUNT</strong></div><div className="compare-values"><b>10%</b><ArrowRight size={16} /><b>15%</b></div><CheckCircle2 size={18} /></div><div className="compare-row unexpected"><div><span>UNEXPECTED</span><strong>LOYALTY_DISCOUNT</strong></div><div className="compare-values"><b>10%</b><ArrowRight size={16} /><b>15%</b></div><AlertTriangle size={18} /></div><div className="clause-row"><span className="mono">PROTECTED CLAUSE</span><strong>{driftResult.clause}</strong></div></Panel><Panel className="drift-explanation"><div className="panel-overline"><span className="red-bar" /> WHY DEVGUARD BLOCKED THIS</div><p>“{driftResult.detail}”</p><div className="boundary-visual"><div className="boundary-allowed"><span>ALLOWED</span><strong>Enterprise discount</strong><b>10% → 15%</b></div><div className="boundary-divider"><ArrowRight size={15} /></div><div className="boundary-protected"><span>PROTECTED</span><strong>Loyalty discount</strong><b>Tax · Coupon · Refund</b></div></div></Panel></div><div className="page-actions centered"><Button onClick={() => go("verify")} icon={ArrowRight}>Review Verification</Button></div></div>;
}

function VerifyPage({ go, verificationState, verificationStep, startVerification }: { go: (view: ViewKey) => void; verificationState: "idle" | "running" | "complete"; verificationStep: number; startVerification: () => void }) {
  return <div className="page-stack"><SectionHeader eyebrow="DRIFT DETECTION / CORRECTED CANDIDATE" title="Corrected Verification" description="A corrected execution changes only Enterprise. DEVGUARD reruns the deterministic verification boundary." action={verificationState === "complete" ? <StatusBadge tone="green">VERIFIED</StatusBadge> : <StatusBadge tone="amber">READY TO RUN</StatusBadge>} /><div className="corrected-banner"><div><span>ENTERPRISE_DISCOUNT</span><strong>10% → 15%</strong></div><div className="preserved-arrow"><ArrowRight size={18} /></div><div className="preserved"><span>LOYALTY_DISCOUNT</span><strong>10% → 10%</strong></div></div><div className="verify-grid"><Panel className="verify-diff"><div className="panel-heading"><div><div className="eyebrow">CORRECTED CANDIDATE</div><h2>Protected behavior preserved</h2></div><ShieldCheck size={17} className="success-text" /></div><CodeDiff corrected /><div className="preserved-list">{verificationResult.protectedBehaviorsPreserved.map((behavior) => <span key={behavior}><Check size={12} />{behavior}</span>)}</div></Panel><Panel className="verify-progress"><div className="panel-overline"><span className="green-bar" /> DETERMINISTIC VERIFICATION</div><h2>{verificationState === "complete" ? "Verification complete" : "Run the boundary checks."}</h2><p>{verificationState === "complete" ? "Protected behaviors preserved. The corrected candidate satisfies the contract." : "No performance percentage. No synthetic score. Just the checks the contract requires."}</p><div className="verification-list">{verificationSteps.map((step, index) => <div className={`verification-step ${verificationState === "running" && index === verificationStep ? "current" : ""} ${verificationState === "complete" || index < verificationStep ? "done" : ""}`} key={step}><span>{verificationState === "running" && index === verificationStep ? <Loader2 size={13} className="spin" /> : verificationState === "complete" || index < verificationStep ? <Check size={13} /> : String(index + 1).padStart(2, "0")}</span><strong>{step}</strong></div>)}</div><Button onClick={verificationState === "complete" ? () => go("proof") : startVerification} disabled={verificationState === "running"} icon={verificationState === "running" ? Loader2 : verificationState === "complete" ? ArrowRight : Play}>{verificationState === "running" ? "Verifying…" : verificationState === "complete" ? "Open Proof of Done" : "Run Verification"}</Button></Panel></div></div>;
}

function ProofPage({ proofOpen, setProofOpen, triggerNotice }: { proofOpen: string | null; setProofOpen: (section: string | null) => void; triggerNotice: (notice: Notice) => void }) {
  const sections = ["Behavioral Evidence", "Contract", "Impact Analysis", "Change Diff", "Drift Analysis", "Verification", "Test Results"];
  return <div className="page-stack"><SectionHeader eyebrow="VERIFICATION / FINAL ARTIFACT" title="Proof of Done" description="An engineering evidence report for the maintenance request — assembled from the underlying artifacts." action={<StatusBadge tone="green">VERIFIED</StatusBadge>} /><Panel className="proof-header" accent><div className="proof-status"><div className="proof-check"><Check size={22} /></div><div><span>FINAL STATUS</span><strong>VERIFIED</strong><p>{proofOfDone.verificationSummary}</p></div></div><div className="proof-meta"><div><span>PROOF ID</span><strong className="mono">PROOF-2026-041</strong></div><div><span>GENERATED</span><strong className="mono">2026-09-26 14:48 UTC</strong></div><div><span>REPOSITORY</span><strong>LegacyShop</strong></div></div></Panel><div className="proof-grid"><Panel className="proof-summary"><div className="panel-heading"><div><div className="eyebrow">EVIDENCE SUMMARY</div><h2>Request satisfied</h2></div><ShieldCheck size={17} className="success-text" /></div><div className="proof-facts"><div><span>Maintenance request</span><strong>{proofOfDone.request.id}</strong></div><div><span>Requested behavior</span><strong>{proofOfDone.request.requestedChange}</strong></div><div><span>Allowed scope</span><strong>Enterprise discount · 10% → 15%</strong></div><div><span>Protected behaviors</span><strong>Loyalty · Tax · Coupon · Refund</strong></div><div><span>Files changed</span><strong>{proofOfDone.filesChanged.join(" · ")}</strong></div><div><span>Test results</span><strong className="success-text">{proofOfDone.testResults}</strong></div><div><span>Intent drift result</span><strong>Blocked first candidate · corrected candidate passed</strong></div><div><span>Contract satisfied</span><strong className="success-text">Yes</strong></div></div></Panel><Panel className="proof-sections"><div className="panel-heading"><div><div className="eyebrow">UNDERLYING ARTIFACTS</div><h2>Evidence trail</h2></div><span className="mono muted">7 sections</span></div>{sections.map((section, index) => <div className={`proof-section ${proofOpen === section ? "open" : ""}`} key={section}><button onClick={() => setProofOpen(proofOpen === section ? null : section)}><span className="proof-section-index">0{index + 1}</span><strong>{section}</strong>{proofOpen === section ? <ChevronDown size={15} /> : <ChevronRight size={15} />}</button>{proofOpen === section && <div className="proof-section-content">{section === "Behavioral Evidence" && <p>18 evidence sources establish how customer type, discount, tax, coupon ordering, checkout, and refund behavior relate in the sample repository.</p>}{section === "Contract" && <p>Only Enterprise discount was allowed to change. Loyalty, tax, coupon ordering, and refund calculation were protected.</p>}{section === "Impact Analysis" && <p>ENTERPRISE_DISCOUNT mapped to customers.py, discount.py, and related tests without inventing a risk score.</p>}{section === "Change Diff" && <p>Corrected candidate changed Enterprise from 10% to 15% and preserved Loyalty at 10%.</p>}{section === "Drift Analysis" && <p>First candidate violated B002 by changing LOYALTY_DISCOUNT to 15%. DEVGUARD blocked it.</p>}{section === "Verification" && <p>Isolated working copy, candidate application, tests, baseline comparison, protected-behavior checks, and contract evaluation passed.</p>}{section === "Test Results" && <p className="success-text">26 tests passed · baseline preserved · no protected behavior drift.</p>}</div>}</div>)}</Panel></div><div className="page-actions"><Button onClick={() => triggerNotice({ tone: "success", text: "Proof export prepared as a frontend artifact. Backend-generated export can replace this action later." })} icon={Upload}>Export Proof</Button><span className="mono muted">EXPORT IS A DEMO ACTION</span></div></div>;
}

export default App;
