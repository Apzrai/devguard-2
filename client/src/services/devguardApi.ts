export type EvidenceSource = "OBSERVED" | "DOCUMENTED" | "TESTED" | "INFERRED";

export interface ProtectedBehavior {
  id: string;
  title: string;
  description: string;
  source: EvidenceSource;
}

export interface RepositoryAnalysis {
  repository: string;
  label: string;
  branch: string;
  commit: string;
  language: string;
  testFramework: string;
  filesAnalyzed: number;
  testsDiscovered: number;
  behavioralRules: number;
  protectedBehaviors: number;
  evidenceSources: number;
}

export interface MaintenanceRequest {
  id: string;
  requestor: string;
  targetBehavior: string;
  requestedChange: string;
}

export interface BehavioralContract {
  status: string;
  allowedBehavior: string;
  from: string;
  to: string;
  protectedBehaviors: ProtectedBehavior[];
}

export interface ImpactAnalysis {
  requestedSymbol: string;
  expectedImpact: string[];
  protectedDependencies: string[];
}

export interface BobExecution {
  status: string;
  filesModified: string[];
  diffSummary: string;
  mode: "simulated" | "live";
}

export interface DriftResult {
  status: "blocked" | "clear";
  requested: string;
  unexpected: string;
  clause: string;
  detail: string;
}

export interface VerificationResult {
  status: "verified" | "pending";
  protectedBehaviorsPreserved: string[];
  correctedChange: string;
}

export interface ProofOfDone {
  status: "verified" | "blocked";
  request: MaintenanceRequest;
  filesChanged: string[];
  testResults: string;
  verificationSummary: string;
}

export const repositoryAnalysis: RepositoryAnalysis = {
  repository: "LegacyShop",
  label: "SAMPLE LEGACY REPOSITORY",
  branch: "main",
  commit: "4f9c1a2",
  language: "Python",
  testFramework: "pytest",
  filesAnalyzed: 8,
  testsDiscovered: 26,
  behavioralRules: 14,
  protectedBehaviors: 4,
  evidenceSources: 18,
};

export const maintenanceRequest: MaintenanceRequest = {
  id: "REQ-2026-041",
  requestor: "mira.chen",
  targetBehavior: "Enterprise discount",
  requestedChange: "Change the Enterprise discount from 10% to 15%.",
};

export const behavioralContract: BehavioralContract = {
  status: "CONTRACT ESTABLISHED",
  allowedBehavior: "Enterprise discount",
  from: "10%",
  to: "15%",
  protectedBehaviors: [
    { id: "B002", title: "Loyalty discount", description: "Loyalty customers retain the existing 10% discount.", source: "TESTED" },
    { id: "B006", title: "Tax calculation", description: "Tax is calculated after discount resolution.", source: "OBSERVED" },
    { id: "B009", title: "Coupon ordering", description: "Coupons apply after customer-type discounts.", source: "DOCUMENTED" },
    { id: "B011", title: "Refund calculation", description: "Refunds mirror the final checkout amount.", source: "TESTED" },
  ],
};

export const impactAnalysis: ImpactAnalysis = {
  requestedSymbol: "ENTERPRISE_DISCOUNT",
  expectedImpact: ["customers.py", "discount.py", "related tests"],
  protectedDependencies: ["LOYALTY_DISCOUNT", "TAX", "COUPON ORDER", "REFUND CALCULATION"],
};

export const driftResult: DriftResult = {
  status: "blocked",
  requested: "ENTERPRISE_DISCOUNT · 10% → 15%",
  unexpected: "LOYALTY_DISCOUNT · 10% → 15%",
  clause: "B002 — LOYALTY customer discount violated",
  detail: "The requested Enterprise behavior changed, but a protected Loyalty behavior changed as well.",
};

export const verificationResult: VerificationResult = {
  status: "verified",
  protectedBehaviorsPreserved: ["Loyalty discount", "Tax calculation", "Coupon ordering", "Refund calculation"],
  correctedChange: "Enterprise discount · 10% → 15%",
};

export const proofOfDone: ProofOfDone = {
  status: "verified",
  request: maintenanceRequest,
  filesChanged: ["discount.py", "tests/test_discount.py"],
  testResults: "26 tests passed · baseline preserved",
  verificationSummary: "Corrected execution satisfied the behavioral contract with no protected behavior drift.",
};

export const demoService = {
  getRepositoryAnalysis: async () => repositoryAnalysis,
  getMaintenanceRequest: async () => maintenanceRequest,
  getBehavioralContract: async () => behavioralContract,
  getImpactAnalysis: async () => impactAnalysis,
  getDriftResult: async () => driftResult,
  getVerificationResult: async () => verificationResult,
  getProofOfDone: async () => proofOfDone,
};
