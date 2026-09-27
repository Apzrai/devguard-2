const API_BASE_URL = "https://devguard-2.onrender.com";

export type EvidenceSource =
  | "OBSERVED"
  | "DOCUMENTED"
  | "TESTED"
  | "INFERRED";

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

const defaultMaintenance = {
  description: "Update the Enterprise discount from 10% to 15%.",
  target_behavior_id: "B003",
  target_symbol: "ENTERPRISE_DISCOUNT",
  target_file: "customers.py",
  current_value: "0.10",
  requested_value: "0.15",
  requestor: "developer",
  notes: "",
};

async function request<T>(
  endpoint: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(
      `DEVGUARD API error ${response.status}: ${errorText}`,
    );
  }

  return response.json() as Promise<T>;
}

export const devguardService = {
  async getRepositoryAnalysis(): Promise<RepositoryAnalysis> {
    return request<RepositoryAnalysis>("/api/repository/analyze", {
      method: "POST",
      body: JSON.stringify({}),
    });
  },

  async getMaintenanceRequest(): Promise<MaintenanceRequest> {
    return request<MaintenanceRequest>("/api/maintenance", {
      method: "POST",
      body: JSON.stringify(defaultMaintenance),
    });
  },

  async getBehavioralContract(): Promise<BehavioralContract> {
    return request<BehavioralContract>("/api/contract", {
      method: "POST",
      body: JSON.stringify({
        maintenance: defaultMaintenance,
      }),
    });
  },

  async getImpactAnalysis(): Promise<ImpactAnalysis> {
    return request<ImpactAnalysis>("/api/impact", {
      method: "POST",
      body: JSON.stringify({
        maintenance: defaultMaintenance,
      }),
    });
  },

  async getDriftResult(): Promise<DriftResult> {
    return request<DriftResult>("/api/drift", {
      method: "POST",
      body: JSON.stringify({
        maintenance: defaultMaintenance,
        bob_backend: "mock",
        bob_scenario: "failure",
      }),
    });
  },

  async getVerificationResult(): Promise<VerificationResult> {
    return request<VerificationResult>("/api/verify", {
      method: "POST",
      body: JSON.stringify({
        maintenance: defaultMaintenance,
        bob_backend: "mock",
        bob_scenario: "success",
      }),
    });
  },

  async getProofOfDone(): Promise<ProofOfDone> {
    return request<ProofOfDone>(
      "/api/proof?bob_backend=mock&bob_scenario=success",
      {
        method: "GET",
      },
    );
  },
};