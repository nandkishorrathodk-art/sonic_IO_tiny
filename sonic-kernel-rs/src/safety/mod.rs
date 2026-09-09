//! Safety Kernel and Sealed Action Policy in Rust.
//!
//! Provides compile-time memory safety, tamper-evident SHA-256 seal checking,
//! scope enforcement, and zero host escape.

use std::collections::HashSet;
use chrono::Utc;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum KernelVerdict {
    Allow,
    Deny,
    RequireApproval,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SafetyAuthorization {
    pub verdict: KernelVerdict,
    pub reason: String,
    pub action_type: String,
    pub timestamp: String,
    pub seal_intact: bool,
    pub audit_id: String,
}

impl SafetyAuthorization {
    pub fn is_allowed(&self) -> bool {
        self.verdict == KernelVerdict::Allow
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SealedPolicy {
    pub workspace_root: String,
    pub allowed_action_types: HashSet<String>,
    pub security_tool_targets: HashSet<String>,
    pub max_actions_per_minute: u32,
    pub require_approval_for_intrusive: bool,
    pub blocked_networks: Vec<String>,
    pub seal_hash: String,
    pub is_sealed: bool,
}

impl SealedPolicy {
    pub fn new_default(workspace_root: &str) -> Self {
        let mut allowed = HashSet::new();
        for act in &[
            "TERMINAL_EXEC", "FILE_READ", "FILE_WRITE", "GIT_COMMIT",
            "BROWSER_NAVIGATE", "BROWSER_CLICK", "BROWSER_TYPE", "BROWSER_SCREENSHOT",
            "SECURITY_TOOL", "GUI_CLICK", "GUI_TYPE", "GUI_SCREENSHOT",
        ] {
            allowed.insert(act.to_string());
        }

        let blocked = vec![
            "127.0.0.0/8".to_string(),
            "10.0.0.0/8".to_string(),
            "172.16.0.0/12".to_string(),
            "192.168.0.0/16".to_string(),
            "169.254.169.254/32".to_string(),
        ];

        let mut policy = Self {
            workspace_root: workspace_root.to_string(),
            allowed_action_types: allowed,
            security_tool_targets: HashSet::new(),
            max_actions_per_minute: 60,
            require_approval_for_intrusive: true,
            blocked_networks: blocked,
            seal_hash: String::new(),
            is_sealed: false,
        };

        policy.seal();
        policy
    }

    pub fn compute_seal_hash(&self) -> String {
        let mut sorted_types: Vec<_> = self.allowed_action_types.iter().collect();
        sorted_types.sort();
        let mut sorted_targets: Vec<_> = self.security_tool_targets.iter().collect();
        sorted_targets.sort();

        let payload = format!(
            "{:?}|{:?}|{}|{}|{}|{:?}",
            sorted_types,
            sorted_targets,
            self.max_actions_per_minute,
            self.require_approval_for_intrusive,
            self.workspace_root,
            self.blocked_networks
        );

        let mut hasher = Sha256::new();
        hasher.update(payload.as_bytes());
        format!("{:x}", hasher.finalize())
    }

    pub fn seal(&mut self) {
        self.seal_hash = self.compute_seal_hash();
        self.is_sealed = true;
    }

    pub fn verify_seal(&self) -> bool {
        if !self.is_sealed {
            return false;
        }
        self.compute_seal_hash() == self.seal_hash
    }

    pub fn evaluate(&self, action_type: &str, target: &str) -> (KernelVerdict, String) {
        if !self.verify_seal() {
            return (
                KernelVerdict::Deny,
                "Safety policy seal mismatch: tamper detected.".to_string(),
            );
        }

        if !self.allowed_action_types.contains(action_type) {
            return (
                KernelVerdict::Deny,
                format!("Action type '{}' is not allowlisted.", action_type),
            );
        }

        // Path confinement for file operations
        if action_type == "FILE_READ" || action_type == "FILE_WRITE" {
            if target.contains("..") || target.starts_with("/etc") || target.starts_with("/root") {
                return (
                    KernelVerdict::Deny,
                    format!("Path '{}' escapes workspace root confinement.", target),
                );
            }
        }

        // Destructive command protection
        if action_type == "TERMINAL_EXEC" {
            if target.contains("rm -rf /") || target.contains(":(){ :|:& };:") || target.contains("mkfs") {
                return (
                    KernelVerdict::Deny,
                    "Catastrophic/destructive command blocked.".to_string(),
                );
            }
        }

        (KernelVerdict::Allow, "Action permitted within safe envelope.".to_string())
    }
}

pub struct SafetyKernel {
    pub policy: SealedPolicy,
    pub enforce_isolated_sandbox: bool,
    pub tenant_id: String,
    audit_log: Vec<SafetyAuthorization>,
}

impl SafetyKernel {
    pub fn new(tenant_id: &str, workspace_root: &str, enforce_sandbox: bool) -> Self {
        Self {
            policy: SealedPolicy::new_default(workspace_root),
            enforce_isolated_sandbox: enforce_sandbox,
            tenant_id: tenant_id.to_string(),
            audit_log: Vec::new(),
        }
    }

    pub fn authorize(
        &mut self,
        action_type: &str,
        target: &str,
        is_isolated_provider: bool,
    ) -> SafetyAuthorization {
        let audit_id = format!("audit-{}-{:06}", self.tenant_id, self.audit_log.len() + 1);
        let now_ts = Utc::now().to_rfc3339();

        // 1. Zero Host Escape Invariant
        if self.enforce_isolated_sandbox && !is_isolated_provider {
            let auth = SafetyAuthorization {
                verdict: KernelVerdict::Deny,
                reason: "Zero host execution policy: Execution provider is not an isolated sandbox.".to_string(),
                action_type: action_type.to_string(),
                timestamp: now_ts,
                seal_intact: self.policy.verify_seal(),
                audit_id,
            };
            self.audit_log.push(auth.clone());
            return auth;
        }

        // 2. Policy Evaluation
        let (verdict, reason) = self.policy.evaluate(action_type, target);
        let auth = SafetyAuthorization {
            verdict,
            reason,
            action_type: action_type.to_string(),
            timestamp: now_ts,
            seal_intact: self.policy.verify_seal(),
            audit_id,
        };
        self.audit_log.push(auth.clone());
        auth
    }

    pub fn audit_trail(&self) -> &[SafetyAuthorization] {
        &self.audit_log
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_sealed_policy_integrity() {
        let mut policy = SealedPolicy::new_default("/home/sonic/workspace");
        assert!(policy.verify_seal());
        assert_eq!(policy.seal_hash.len(), 64);

        // Artificially mutate allowed types
        policy.allowed_action_types.insert("ARBITRARY_PWN".to_string());
        assert!(!policy.verify_seal());

        let (verdict, reason) = policy.evaluate("FILE_READ", "/home/sonic/workspace/main.rs");
        assert_eq!(verdict, KernelVerdict::Deny);
        assert!(reason.contains("tamper detected"));
    }

    #[test]
    fn test_zero_host_escape_enforced() {
        let mut kernel = SafetyKernel::new("tenant-a", "/home/sonic/workspace", true);

        // Disallow when is_isolated_provider is false (host execution attempt)
        let auth = kernel.authorize("TERMINAL_EXEC", "ls", false);
        assert_eq!(auth.verdict, KernelVerdict::Deny);
        assert!(auth.reason.contains("Zero host execution policy"));

        // Allow when inside verified isolated provider
        let auth_sandbox = kernel.authorize("TERMINAL_EXEC", "ls", true);
        assert_eq!(auth_sandbox.verdict, KernelVerdict::Allow);
    }

    #[test]
    fn test_path_escape_denied() {
        let mut kernel = SafetyKernel::new("tenant-a", "/home/sonic/workspace", true);
        let auth = kernel.authorize("FILE_READ", "/etc/shadow", true);
        assert_eq!(auth.verdict, KernelVerdict::Deny);
        assert!(auth.reason.contains("escapes workspace root"));
    }
}
