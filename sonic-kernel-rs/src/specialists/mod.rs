//! Subordinated Specialists in Rust.
//!
//! Specialists do not make strategy decisions. They are bounded workers
//! that execute single experiments planned by the Brain, measure empirical
//! behavioral differences (status codes, length delta, token divergence, token leak detection),
//! and return structured evidence payloads.

use std::collections::HashMap;
use std::sync::OnceLock;
use regex::Regex;
use serde::{Deserialize, Serialize};

static LEAK_PATTERNS: OnceLock<Regex> = OnceLock::new();

fn get_leak_patterns() -> &'static Regex {
    LEAK_PATTERNS.get_or_init(|| {
        Regex::new(r#"(?i)(?:flag\{[^\}]+\}|ctf\{[^\}]+\}|adm_key_[a-z0-9_]+|Bearer\s+[A-Za-z0-9\-\._~\+\/]+=*|BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY)"#).unwrap()
    })
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum SpecialistType {
    Recon,
    Web,
    Api,
    Auth,
    Logic,
    Pwn,
    Crypto,
    Network,
    Forensics,
}

impl SpecialistType {
    pub fn as_str(&self) -> &'static str {
        match self {
            SpecialistType::Recon => "recon",
            SpecialistType::Web => "web",
            SpecialistType::Api => "api",
            SpecialistType::Auth => "auth",
            SpecialistType::Logic => "logic",
            SpecialistType::Pwn => "pwn",
            SpecialistType::Crypto => "crypto",
            SpecialistType::Network => "network",
            SpecialistType::Forensics => "forensics",
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SpecialistResult {
    pub experiment_id: String,
    pub hypothesis_id: String,
    pub specialist: SpecialistType,
    pub status: String,
    pub baseline_observation: String,
    pub probe_observation: String,
    pub behavioral_difference_detected: bool,
    pub difference_description: String,
    pub secret_or_flag_detected: bool,
    pub evidence_payload: HashMap<String, String>,
}

pub struct SpecialistWorker;

impl SpecialistWorker {
    /// Empirical probe evaluation: measures behavioral divergence, length delta,
    /// and scans for flag or secret leaks.
    pub fn evaluate_probe(
        specialist: SpecialistType,
        experiment_id: &str,
        hypothesis_id: &str,
        baseline: &str,
        probe_response: &str,
    ) -> SpecialistResult {
        let diff = baseline.trim() != probe_response.trim();
        let leak_re = get_leak_patterns();
        let has_leak = leak_re.is_match(probe_response);

        let mut payload = HashMap::new();
        payload.insert("raw_probe".to_string(), probe_response.to_string());
        payload.insert("baseline_len".to_string(), baseline.len().to_string());
        payload.insert("probe_len".to_string(), probe_response.len().to_string());

        if let Some(mat) = leak_re.find(probe_response) {
            payload.insert("extracted_artifact".to_string(), mat.as_str().to_string());
        }

        let desc = if has_leak {
            format!(
                "Specialist {:?} detected critical artifact/leak: '{}' with delta len={}",
                specialist,
                payload.get("extracted_artifact").unwrap_or(&"".to_string()),
                (probe_response.len() as isize - baseline.len() as isize).abs()
            )
        } else if diff {
            format!(
                "Specialist {:?} detected behavioral divergence: response length baseline={}, probe={}, delta={}",
                specialist,
                baseline.len(),
                probe_response.len(),
                (probe_response.len() as isize - baseline.len() as isize).abs()
            )
        } else {
            "No behavioral difference detected (potential false positive).".to_string()
        };

        SpecialistResult {
            experiment_id: experiment_id.to_string(),
            hypothesis_id: hypothesis_id.to_string(),
            specialist,
            status: if diff || has_leak { "completed".to_string() } else { "dead_end".to_string() },
            baseline_observation: baseline.to_string(),
            probe_observation: probe_response.to_string(),
            behavioral_difference_detected: diff || has_leak,
            difference_description: desc,
            secret_or_flag_detected: has_leak,
            evidence_payload: payload,
        }
    }

    /// Backwards-compatible alias for simulate_probe.
    pub fn simulate_probe(
        specialist: SpecialistType,
        experiment_id: &str,
        hypothesis_id: &str,
        baseline: &str,
        probe_response: &str,
    ) -> SpecialistResult {
        Self::evaluate_probe(specialist, experiment_id, hypothesis_id, baseline, probe_response)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_specialist_behavioral_divergence_detection() {
        let baseline = "HTTP 200 OK: Welcome Guest";
        let probe = "HTTP 200 OK: Welcome Admin [ROLE=SUPERADMIN]";

        let res = SpecialistWorker::evaluate_probe(
            SpecialistType::Auth,
            "exp-1",
            "hyp-1",
            baseline,
            probe,
        );

        assert!(res.behavioral_difference_detected);
        assert_eq!(res.status, "completed");
        assert!(res.difference_description.contains("divergence"));
    }

    #[test]
    fn test_specialist_flag_detection() {
        let baseline = "HTTP 200 OK: Try harder";
        let probe = "HTTP 200 OK: Success! flag{ctf_r3sponse_pwn3d_42}";

        let res = SpecialistWorker::evaluate_probe(
            SpecialistType::Pwn,
            "exp-flag",
            "hyp-flag",
            baseline,
            probe,
        );

        assert!(res.behavioral_difference_detected);
        assert!(res.secret_or_flag_detected);
        assert_eq!(
            res.evidence_payload.get("extracted_artifact").unwrap(),
            "flag{ctf_r3sponse_pwn3d_42}"
        );
    }

    #[test]
    fn test_specialist_identical_response_is_dead_end() {
        let baseline = "HTTP 403 Forbidden";
        let probe = "HTTP 403 Forbidden";

        let res = SpecialistWorker::evaluate_probe(
            SpecialistType::Web,
            "exp-2",
            "hyp-2",
            baseline,
            probe,
        );

        assert!(!res.behavioral_difference_detected);
        assert!(!res.secret_or_flag_detected);
        assert_eq!(res.status, "dead_end");
    }
}

