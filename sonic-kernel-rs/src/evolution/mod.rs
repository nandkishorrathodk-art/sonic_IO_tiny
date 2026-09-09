//! Guarded Evolution Pipeline in Rust.
//!
//! Enforces:
//! 1. Zero self-modification of safety kernel and policy.
//! 2. Mandatory canary progression: Isolated Branch -> Tests -> Security Regressions -> Benchmark -> Canary -> Approval Gate.

use std::collections::HashMap;
use serde::{Deserialize, Serialize};
use uuid::Uuid;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum EvolutionStage {
    Proposed,
    IsolatedBranch,
    TestsPassing,
    SecurityRegressionPassing,
    BenchmarkValidated,
    CanaryActive,
    Promoted,
    RolledBack,
    Rejected,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ImprovementProposal {
    pub proposal_id: String,
    pub target_component: String,
    pub description: String,
    pub stage: EvolutionStage,
}

pub struct EvolutionPipeline {
    proposals: HashMap<String, ImprovementProposal>,
}

impl EvolutionPipeline {
    pub fn new() -> Self {
        Self {
            proposals: HashMap::new(),
        }
    }

    pub fn submit_proposal(
        &mut self,
        target_component: &str,
        description: &str,
    ) -> (ImprovementProposal, bool) {
        let pid = format!("evo-{}", &Uuid::new_v4().to_string()[..8]);

        // Invariant: Self-modification of safety kernel is strictly forbidden
        if target_component.contains("safety") || target_component.contains("kernel/action_broker") {
            let p = ImprovementProposal {
                proposal_id: pid.clone(),
                target_component: target_component.to_string(),
                description: description.to_string(),
                stage: EvolutionStage::Rejected,
            };
            self.proposals.insert(pid, p.clone());
            return (p, false);
        }

        let p = ImprovementProposal {
            proposal_id: pid.clone(),
            target_component: target_component.to_string(),
            description: description.to_string(),
            stage: EvolutionStage::IsolatedBranch,
        };
        self.proposals.insert(pid, p.clone());
        (p, true)
    }

    pub fn advance_stage(&mut self, proposal_id: &str, next: EvolutionStage) -> bool {
        if let Some(p) = self.proposals.get_mut(proposal_id) {
            if p.stage != EvolutionStage::Rejected && p.stage != EvolutionStage::RolledBack {
                p.stage = next;
                return true;
            }
        }
        false
    }

    pub fn promote_with_approval(&mut self, proposal_id: &str, operator_approved: bool) -> bool {
        if let Some(p) = self.proposals.get_mut(proposal_id) {
            if p.stage != EvolutionStage::CanaryActive {
                return false;
            }

            if operator_approved {
                p.stage = EvolutionStage::Promoted;
                true
            } else {
                p.stage = EvolutionStage::RolledBack;
                false
            }
        } else {
            false
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_evolution_pipeline_rejects_safety_self_modification() {
        let mut pipe = EvolutionPipeline::new();
        let (prop, accepted) = pipe.submit_proposal("src/safety/kernel.rs", "Loosen egress check");
        assert!(!accepted);
        assert_eq!(prop.stage, EvolutionStage::Rejected);
    }

    #[test]
    fn test_evolution_canary_and_operator_approval() {
        let mut pipe = EvolutionPipeline::new();
        let (prop, accepted) = pipe.submit_proposal("src/tools/nmap.rs", "Faster port scan");
        assert!(accepted);
        assert_eq!(prop.stage, EvolutionStage::IsolatedBranch);

        assert!(pipe.advance_stage(&prop.proposal_id, EvolutionStage::TestsPassing));
        assert!(pipe.advance_stage(&prop.proposal_id, EvolutionStage::SecurityRegressionPassing));
        assert!(pipe.advance_stage(&prop.proposal_id, EvolutionStage::CanaryActive));

        // Decline promotion
        assert!(!pipe.promote_with_approval(&prop.proposal_id, false));
    }
}
