//! Hardened Verification Lab and Cryptographic Chain of Custody in Rust.
//!
//! Enforces empirical reproduction, behavioral deltas, and cryptographic integrity.

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

pub struct CustodyChain;

impl CustodyChain {
    pub fn compute_hash(data: &[u8]) -> String {
        let mut hasher = Sha256::new();
        hasher.update(data);
        format!("{:x}", hasher.finalize())
    }

    /// Constant-time comparison of two hexadecimal hashes to prevent timing attacks.
    pub fn constant_time_eq(a: &str, b: &str) -> bool {
        if a.len() != b.len() {
            return false;
        }
        let mut result = 0u8;
        for (byte_a, byte_b) in a.bytes().zip(b.bytes()) {
            result |= byte_a ^ byte_b;
        }
        result == 0
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VerificationLabReport {
    pub finding_id: String,
    pub verified: bool,
    pub rejection_reasons: Vec<String>,
    pub custody_hash: String,
}

pub struct VerificationLab;

impl VerificationLab {
    pub fn verify_candidate(
        finding_id: &str,
        poc: &str,
        baseline_obs: &str,
        probe_obs: &str,
        reproduction_obs: &str,
        impact_consequence: Option<&str>,
        expected_custody_hash: &str,
    ) -> VerificationLabReport {
        let mut rejections = Vec::new();

        // 1. Trigger payload validation
        if poc.trim().len() < 5 {
            rejections.push("Trigger validation failed: Missing or trivial PoC payload.".to_string());
        }

        // 2. Behavioral difference check (Exit 0 or HTTP 200 is NOT sufficient)
        if baseline_obs.trim() == probe_obs.trim() {
            rejections.push(
                "Behavioral delta failed: Probe produced zero divergence from baseline observation. Claim is false positive.".to_string(),
            );
        }

        // 3. Clean sandbox reproduction check
        if reproduction_obs.trim().is_empty() || reproduction_obs.trim() == baseline_obs.trim() {
            rejections.push(
                "Clean sandbox reproduction failed: Secondary isolated run could not reproduce behavior.".to_string(),
            );
        }

        // 4. Custody hash validation using constant-time check
        let actual_hash = CustodyChain::compute_hash(probe_obs.as_bytes());
        if !CustodyChain::constant_time_eq(&actual_hash, expected_custody_hash) {
            rejections.push(format!(
                "Custody integrity failed: Stored hash '{}' does not match payload content.",
                expected_custody_hash
            ));
        }

        // 5. Impact assessment (safe idiomatic Option handling)
        if impact_consequence.map_or(true, |c| c.trim().is_empty()) {
            rejections.push("Impact assessment failed: No concrete CIA impact proven.".to_string());
        }

        let verified = rejections.is_empty();
        VerificationLabReport {
            finding_id: finding_id.to_string(),
            verified,
            rejection_reasons: rejections,
            custody_hash: actual_hash,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_verification_lab_rejects_identical_baseline_and_probe() {
        let obs = "HTTP 200 OK: Content unchanged";
        let hash = CustodyChain::compute_hash(obs.as_bytes());

        let rep = VerificationLab::verify_candidate(
            "f-1",
            "curl https://target/api",
            obs,
            obs, // Identical
            obs,
            Some("Exfiltration"),
            &hash,
        );

        assert!(!rep.verified);
        assert!(rep.rejection_reasons.iter().any(|r| r.contains("Behavioral delta failed")));
    }

    #[test]
    fn test_verification_lab_accepts_proven_finding() {
        let base = "HTTP 403 Forbidden: Access Denied";
        let probe = "HTTP 200 OK: Leaked Administrator API Keys";
        let repro = "HTTP 200 OK: Leaked Administrator API Keys (Clean Container)";
        let hash = CustodyChain::compute_hash(probe.as_bytes());

        let rep = VerificationLab::verify_candidate(
            "f-valid",
            "curl -H 'X-Override: admin' https://target/keys",
            base,
            probe,
            repro,
            Some("Confidentiality breach: Administrator credentials leaked."),
            &hash,
        );

        assert!(rep.verified);
        assert_eq!(rep.rejection_reasons.len(), 0);
        assert_eq!(rep.custody_hash.len(), 64);
    }
}
