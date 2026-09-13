//! Subordinated Specialists in Rust.
//!
//! Specialists do not make strategy decisions. They are bounded workers
//! that execute single experiments planned by the Brain, measure behavioral differences,
//! and return structured evidence payloads.

use std::collections::HashMap;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum SpecialistType {
    Recon,
    Web,
    Api,
    Auth,
    Logic,
}

impl SpecialistType {
    pub fn as_str(&self) -> &'static str {
        match self {
            SpecialistType::Recon => "recon",
            SpecialistType::Web => "web",
            SpecialistType::Api => "api",
            SpecialistType::Auth => "auth",
            SpecialistType::Logic => "logic",
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
    pub evidence_payload: HashMap<String, String>,
}

pub struct SpecialistWorker;

impl SpecialistWorker {
    pub fn simulate_probe(
        specialist: SpecialistType,
        experiment_id: &str,
        hypothesis_id: &str,
        baseline: &str,
        probe_response: &str,
    ) -> SpecialistResult {
        let diff = baseline.trim() != probe_response.trim();
        let desc = if diff {
            format!(
                "Specialist {:?} detected divergence: response length baseline={}, probe={}",
                specialist,
                baseline.len(),
                probe_response.len()
            )
        } else {
            "No behavioral difference detected (potential false positive).".to_string()
        };

        let mut payload = HashMap::new();
        payload.insert("raw_probe".to_string(), probe_response.to_string());

        SpecialistResult {
            experiment_id: experiment_id.to_string(),
            hypothesis_id: hypothesis_id.to_string(),
            specialist,
            status: if diff { "completed".to_string() } else { "dead_end".to_string() },
            baseline_observation: baseline.to_string(),
            probe_observation: probe_response.to_string(),
            behavioral_difference_detected: diff,
            difference_description: desc,
            evidence_payload: payload,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_specialist_behavioral_divergence_detection() {
        let baseline = "HTTP 200 OK: Welcome Guest";
        let probe = "HTTP 200 OK: Welcome Admin [ROLE=SUPERADMIN]";

        let res = SpecialistWorker::simulate_probe(
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
    fn test_specialist_identical_response_is_dead_end() {
        let baseline = "HTTP 403 Forbidden";
        let probe = "HTTP 403 Forbidden";

        let res = SpecialistWorker::simulate_probe(
            SpecialistType::Web,
            "exp-2",
            "hyp-2",
            baseline,
            probe,
        );

        assert!(!res.behavioral_difference_detected);
        assert_eq!(res.status, "dead_end");
    }
}
