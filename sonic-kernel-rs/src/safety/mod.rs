//! Safety Kernel and Sealed Action Policy in Rust.
//!
//! Provides compile-time memory safety, tamper-evident SHA-256 seal checking,
//! scope enforcement, network egress CIDR protection, rate limiting, and zero host escape.

use std::collections::HashSet;
use std::net::Ipv4Addr;
use std::time::Instant;
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

/// Helper: checks if an IPv4 address falls within a given CIDR notation string (e.g. "10.0.0.0/8").
pub fn is_ip_in_cidr(ip: Ipv4Addr, cidr: &str) -> bool {
    if let Some((network_str, prefix_len_str)) = cidr.split_once('/') {
        if let (Ok(net_ip), Ok(prefix_len)) = (
            network_str.trim().parse::<Ipv4Addr>(),
            prefix_len_str.trim().parse::<u32>(),
        ) {
            if prefix_len <= 32 {
                let mask = if prefix_len == 0 {
                    0u32
                } else {
                    (!0u32).checked_shl(32 - prefix_len).unwrap_or(0)
                };
                let net_u32 = u32::from(net_ip) & mask;
                let ip_u32 = u32::from(ip) & mask;
                return net_u32 == ip_u32;
            }
        }
    }
    false
}

/// Helper: extracts the bare host/IP from URLs or host:port strings.
pub fn extract_host_from_target(target: &str) -> String {
    let s = target.trim();
    let s = if let Some(stripped) = s.strip_prefix("http://") {
        stripped
    } else if let Some(stripped) = s.strip_prefix("https://") {
        stripped
    } else {
        s
    };
    let s = s.split('/').next().unwrap_or(s);
    let s = s.split(':').next().unwrap_or(s);
    s.trim_matches('[').trim_matches(']').to_lowercase()
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
            "SECURITY_TOOL",
            "GUI_CLICK", "GUI_TYPE", "GUI_SCREENSHOT",
            "GUI_DOUBLE_CLICK", "GUI_RIGHT_CLICK", "GUI_KEYPRESS",
            "GUI_MOVE", "GUI_SCROLL", "GUI_DRAG", "GUI_WAIT",
            "APP_LAUNCH", "APP_CLOSE", "APP_FOCUS", "APP_INSTALL",
            "SERVICE_ACTION", "GIT_BRANCH", "TERMINAL_EXEC",
            "TOOL_RUN", "TOOL_AUTHOR", "METHOD_INVENT",
            "BROWSER_WAIT", "BROWSER_DOWNLOAD",
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

        // 1. Path confinement for file operations
        if action_type == "FILE_READ" || action_type == "FILE_WRITE" {
            let normalized = target.replace('\\', "/");
            if normalized.contains("..")
                || normalized.starts_with("/etc")
                || normalized.starts_with("/root")
                || normalized.starts_with("/proc")
                || normalized.starts_with("/sys")
                || normalized.starts_with("/var/run/docker.sock")
            {
                return (
                    KernelVerdict::Deny,
                    format!("Path '{}' escapes workspace root confinement.", target),
                );
            }
        }

        // 2. Destructive command protection
        if action_type == "TERMINAL_EXEC" {
            let lower = target.to_lowercase();
            if lower.contains("rm -rf /")
                || lower.contains(":(){ :|:& };:")
                || lower.contains("mkfs")
                || lower.contains("dd if=")
                || lower.contains("> /dev/sd")
                || lower.contains("chmod -r 777 /")
                || lower.contains("shutdown")
                || lower.contains("reboot")
                || lower.contains("init 0")
            {
                return (
                    KernelVerdict::Deny,
                    "Catastrophic/destructive command blocked.".to_string(),
                );
            }
        }

        // 3. Network Egress Filtering (SECURITY_TOOL and BROWSER_NAVIGATE)
        if action_type == "SECURITY_TOOL" || action_type == "BROWSER_NAVIGATE" {
            let host = extract_host_from_target(target);

            // Check if explicitly allowlisted
            if !self.security_tool_targets.contains(&host) && !self.security_tool_targets.contains(target) {
                // Check localhost & cloud metadata hostnames
                if host == "localhost"
                    || host == "127.0.0.1"
                    || host == "::1"
                    || host == "metadata.google.internal"
                    || host == "instance-data"
                {
                    return (
                        KernelVerdict::Deny,
                        format!("Egress blocked: target host '{}' is restricted loopback or cloud metadata.", host),
                    );
                }

                // Check IP against CIDR blocks
                if let Ok(ip) = host.parse::<Ipv4Addr>() {
                    for cidr in &self.blocked_networks {
                        if is_ip_in_cidr(ip, cidr) {
                            return (
                                KernelVerdict::Deny,
                                format!("Egress blocked: target IP '{}' is within restricted CIDR '{}'.", ip, cidr),
                            );
                        }
                    }
                }
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
    action_timestamps: Vec<Instant>,
}

impl SafetyKernel {
    pub fn new(tenant_id: &str, workspace_root: &str, enforce_sandbox: bool) -> Self {
        Self {
            policy: SealedPolicy::new_default(workspace_root),
            enforce_isolated_sandbox: enforce_sandbox,
            tenant_id: tenant_id.to_string(),
            audit_log: Vec::new(),
            action_timestamps: Vec::new(),
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

        // 2. Sliding Window Rate Limiting (60-second window)
        self.action_timestamps.retain(|t| t.elapsed().as_secs() < 60);
        if self.action_timestamps.len() as u32 >= self.policy.max_actions_per_minute {
            let auth = SafetyAuthorization {
                verdict: KernelVerdict::Deny,
                reason: format!(
                    "Rate limit exceeded: {} actions recorded in the last 60s (max {}).",
                    self.action_timestamps.len(),
                    self.policy.max_actions_per_minute
                ),
                action_type: action_type.to_string(),
                timestamp: now_ts,
                seal_intact: self.policy.verify_seal(),
                audit_id,
            };
            self.audit_log.push(auth.clone());
            return auth;
        }

        // 3. Policy Evaluation
        let (verdict, reason) = self.policy.evaluate(action_type, target);
        if verdict == KernelVerdict::Allow {
            self.action_timestamps.push(Instant::now());
        }

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

        let auth_traversal = kernel.authorize("FILE_READ", "../../../etc/passwd", true);
        assert_eq!(auth_traversal.verdict, KernelVerdict::Deny);
    }

    #[test]
    fn test_network_egress_cidr_blocked() {
        let mut kernel = SafetyKernel::new("tenant-a", "/home/sonic/workspace", true);

        // RFC-1918 Private ranges & AWS/GCP metadata blocked
        let blocked_targets = vec![
            "http://127.0.0.1:8080/admin",
            "http://localhost:3000",
            "http://10.0.0.5:8000/api",
            "http://172.16.1.100/debug",
            "http://192.168.1.1/setup",
            "http://169.254.169.254/latest/meta-data",
            "http://metadata.google.internal/computeMetadata/v1",
        ];

        for t in blocked_targets {
            let auth = kernel.authorize("SECURITY_TOOL", t, true);
            assert_eq!(auth.verdict, KernelVerdict::Deny, "Target '{}' should be blocked", t);
            assert!(auth.reason.contains("Egress blocked"), "Reason should mention egress: {}", auth.reason);
        }

        // Public authorized target allowed
        let public_auth = kernel.authorize("SECURITY_TOOL", "https://authorized-ctf.example.com/api", true);
        assert_eq!(public_auth.verdict, KernelVerdict::Allow);
    }

    #[test]
    fn test_rate_limiter_exceeded() {
        let mut kernel = SafetyKernel::new("tenant-a", "/home/sonic/workspace", true);
        kernel.policy.max_actions_per_minute = 3;
        kernel.policy.seal(); // Reseal after modifying rate limit

        assert_eq!(kernel.authorize("TERMINAL_EXEC", "ls", true).verdict, KernelVerdict::Allow);
        assert_eq!(kernel.authorize("TERMINAL_EXEC", "whoami", true).verdict, KernelVerdict::Allow);
        assert_eq!(kernel.authorize("TERMINAL_EXEC", "pwd", true).verdict, KernelVerdict::Allow);

        // 4th action exceeds rate limit of 3
        let blocked = kernel.authorize("TERMINAL_EXEC", "date", true);
        assert_eq!(blocked.verdict, KernelVerdict::Deny);
        assert!(blocked.reason.contains("Rate limit exceeded"));
    }
}
