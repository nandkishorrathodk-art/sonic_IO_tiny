//! Decoupled Research Brain, Epistemic Hypotheses, Falsifier, and Dead-End Engine.
//!
//! Architectural Invariant:
//! The Research Brain has ZERO tool execution handles. It only consumes
//! the World Model state and emits an ExperimentPlan.

use std::collections::{HashMap, HashSet};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum HypothesisStatus {
    Active,
    Confirmed,
    Falsified,
    Disputed,
    Expired,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UnknownEntity {
    pub unknown_id: String,
    pub description: String,
    pub domain: String,
    pub priority: f32,
    pub resolved: bool,
    pub resolution_evidence: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Hypothesis {
    pub hypothesis_id: String,
    pub statement: String,
    pub vulnerability_class: String,
    pub target_asset: String,
    pub confidence: f32,
    pub uncertainty: f32,
    pub expected_info_gain: f32,
    pub cost_estimate: f32,
    pub counter_id: Option<String>,
    pub is_counter: bool,
    pub status: HypothesisStatus,
    pub supporting_evidence: Vec<String>,
    pub contradicting_evidence: Vec<String>,
}

impl Hypothesis {
    pub fn update_confidence(&mut self, delta: f32, evidence: &str, is_supporting: bool) {
        if is_supporting {
            self.supporting_evidence.push(evidence.to_string());
            self.confidence = (self.confidence + delta).clamp(0.01, 0.99);
        } else {
            self.contradicting_evidence.push(evidence.to_string());
            self.confidence = (self.confidence - delta).clamp(0.01, 0.99);
        }

        let total = self.supporting_evidence.len() + self.contradicting_evidence.len();
        self.uncertainty = (1.0 / (1.0 + 0.5 * total as f32)).max(0.05);

        if self.confidence >= 0.85 && total >= 2 {
            self.status = HypothesisStatus::Confirmed;
        } else if self.confidence <= 0.15 {
            self.status = HypothesisStatus::Falsified;
        } else if self.status == HypothesisStatus::Confirmed && self.confidence < 0.70 {
            self.status = HypothesisStatus::Disputed;
        }
    }
}

pub struct HypothesisEngine {
    hypotheses: HashMap<String, Hypothesis>,
}

impl HypothesisEngine {
    pub fn new() -> Self {
        Self {
            hypotheses: HashMap::new(),
        }
    }

    pub fn create_hypothesis_pair(
        &mut self,
        statement: &str,
        counter_statement: Option<&str>,
        vulnerability_class: &str,
        target_asset: &str,
        info_gain: f32,
    ) -> (String, String) {
        let h_id = format!("hyp-{}", &Uuid::new_v4().to_string()[..8]);
        let c_id = format!("hyp-c-{}", &Uuid::new_v4().to_string()[..8]);

        let default_counter = format!(
            "Target '{}' does not exhibit '{}' exploitability (properly gated or benign).",
            target_asset, vulnerability_class
        );
        let counter_stmt = counter_statement.unwrap_or(&default_counter);

        let primary = Hypothesis {
            hypothesis_id: h_id.clone(),
            statement: statement.to_string(),
            vulnerability_class: vulnerability_class.to_string(),
            target_asset: target_asset.to_string(),
            confidence: 0.5,
            uncertainty: 0.5,
            expected_info_gain: info_gain,
            cost_estimate: 1.0,
            counter_id: Some(c_id.clone()),
            is_counter: false,
            status: HypothesisStatus::Active,
            supporting_evidence: Vec::new(),
            contradicting_evidence: Vec::new(),
        };

        let counter = Hypothesis {
            hypothesis_id: c_id.clone(),
            statement: counter_stmt.to_string(),
            vulnerability_class: vulnerability_class.to_string(),
            target_asset: target_asset.to_string(),
            confidence: 0.5,
            uncertainty: 0.5,
            expected_info_gain: info_gain,
            cost_estimate: 1.0,
            counter_id: Some(h_id.clone()),
            is_counter: true,
            status: HypothesisStatus::Active,
            supporting_evidence: Vec::new(),
            contradicting_evidence: Vec::new(),
        };

        self.hypotheses.insert(h_id.clone(), primary);
        self.hypotheses.insert(c_id.clone(), counter);

        (h_id, c_id)
    }

    pub fn get(&self, id: &str) -> Option<&Hypothesis> {
        self.hypotheses.get(id)
    }

    pub fn get_mut(&mut self, id: &str) -> Option<&mut Hypothesis> {
        self.hypotheses.get_mut(id)
    }

    pub fn record_evidence(&mut self, hyp_id: &str, is_supporting: bool, evidence: &str, weight: f32) {
        let counter_id = if let Some(h) = self.hypotheses.get_mut(hyp_id) {
            h.update_confidence(weight, evidence, is_supporting);
            h.counter_id.clone()
        } else {
            None
        };

        if let Some(cid) = counter_id {
            if let Some(c) = self.hypotheses.get_mut(&cid) {
                c.update_confidence(weight, evidence, !is_supporting);
            }
        }
    }

    pub fn rank_by_value(&self) -> Vec<&Hypothesis> {
        let mut active: Vec<&Hypothesis> = self
            .hypotheses
            .values()
            .filter(|h| !h.is_counter && h.status == HypothesisStatus::Active)
            .collect();

        active.sort_by(|a, b| {
            let score_a = (a.expected_info_gain * a.uncertainty) / a.cost_estimate.max(0.1);
            let score_b = (b.expected_info_gain * b.uncertainty) / b.cost_estimate.max(0.1);
            score_b.partial_cmp(&score_a).unwrap_or(std::cmp::Ordering::Equal)
        });

        active
    }
}

impl Default for HypothesisEngine {
    fn default() -> Self {
        Self::new()
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Experiment {
    pub experiment_id: String,
    pub hypothesis_id: String,
    pub target_asset: String,
    pub specialist_type: String,
    pub action_intent: String,
    pub parameters: HashMap<String, String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExperimentPlan {
    pub plan_id: String,
    pub selected_hypothesis: Option<Hypothesis>,
    pub experiment: Option<Experiment>,
    pub specialist_type: String,
    pub rationale: String,
    pub goal_satisfied: bool,
    pub stopping_reason: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DecisionAction {
    Proceed,
    Pivot,
    Terminate,
}

pub struct DecisionEngine {
    failure_threshold: u32,
    failures: HashMap<String, u32>,
    dead_ends: HashSet<String>,
}

impl DecisionEngine {
    pub fn new(threshold: u32) -> Self {
        Self {
            failure_threshold: threshold,
            failures: HashMap::new(),
            dead_ends: HashSet::new(),
        }
    }

    pub fn record_failure(&mut self, asset: &str, strategy: &str) -> DecisionAction {
        let key = format!("{}::{}", asset, strategy);
        let count = self.failures.entry(key.clone()).or_insert(0);
        *count += 1;

        if *count >= self.failure_threshold {
            self.dead_ends.insert(key);
            DecisionAction::Pivot
        } else {
            DecisionAction::Proceed
        }
    }

    pub fn is_dead_end(&self, asset: &str, strategy: &str) -> bool {
        self.dead_ends.contains(&format!("{}::{}", asset, strategy))
    }
}

pub struct ResearchBrain {
    pub tenant_id: String,
}

impl ResearchBrain {
    pub fn new(tenant_id: &str) -> Self {
        Self {
            tenant_id: tenant_id.to_string(),
        }
    }

    pub fn plan_next_step(
        &self,
        hypothesis_engine: &HypothesisEngine,
        budget_exhausted: bool,
        verified_findings_count: usize,
    ) -> ExperimentPlan {
        let plan_id = format!("plan-{}", &Uuid::new_v4().to_string()[..8]);

        if budget_exhausted {
            return ExperimentPlan {
                plan_id,
                selected_hypothesis: None,
                experiment: None,
                specialist_type: "none".to_string(),
                rationale: "Budget exhausted; terminating investigation cleanly.".to_string(),
                goal_satisfied: true,
                stopping_reason: "budget_exhausted".to_string(),
            };
        }

        if verified_findings_count >= 3 {
            return ExperimentPlan {
                plan_id,
                selected_hypothesis: None,
                experiment: None,
                specialist_type: "none".to_string(),
                rationale: "Goal satisfied: sufficient verified findings collected.".to_string(),
                goal_satisfied: true,
                stopping_reason: "sufficient_findings".to_string(),
            };
        }

        let ranked = hypothesis_engine.rank_by_value();
        if let Some(top) = ranked.first() {
            let c_lower = top.vulnerability_class.to_lowercase();
            let spec = if c_lower.contains("pwn") || c_lower.contains("binary") || c_lower.contains("buffer") || c_lower.contains("rop") {
                "pwn"
            } else if c_lower.contains("crypto") || c_lower.contains("cipher") || c_lower.contains("hash") {
                "crypto"
            } else if c_lower.contains("network") || c_lower.contains("port") || c_lower.contains("sniff") {
                "network"
            } else if c_lower.contains("auth") || c_lower.contains("idor") || c_lower.contains("jwt") || c_lower.contains("session") {
                "auth"
            } else if c_lower.contains("api") || c_lower.contains("graphql") || c_lower.contains("rest") {
                "api"
            } else if c_lower.contains("forensic") || c_lower.contains("stego") {
                "forensics"
            } else {
                "web"
            };

            let exp = Experiment {
                experiment_id: format!("exp-{}", &Uuid::new_v4().to_string()[..8]),
                hypothesis_id: top.hypothesis_id.clone(),
                target_asset: top.target_asset.clone(),
                specialist_type: spec.to_string(),
                action_intent: format!("Test hypothesis: {}", top.statement),
                parameters: HashMap::new(),
            };

            ExperimentPlan {
                plan_id,
                selected_hypothesis: Some((*top).clone()),
                experiment: Some(exp),
                specialist_type: spec.to_string(),
                rationale: format!("Selected highest-gain hypothesis '{}' with gain={}", top.statement, top.expected_info_gain),
                goal_satisfied: false,
                stopping_reason: String::new(),
            }
        } else {
            ExperimentPlan {
                plan_id,
                selected_hypothesis: None,
                experiment: None,
                specialist_type: "none".to_string(),
                rationale: "No active hypotheses remaining.".to_string(),
                goal_satisfied: true,
                stopping_reason: "saturation".to_string(),
            }
        }
    }
}

// ---------------------------------------------------------------------------
// NEXUS स्वरूप-0 -- Native Multi-Mind Parliament + World Twin (ASI substrate)
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum NexusVote {
    Support,
    Oppose,
    Abstain,
    Veto,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NexusVoteRec {
    pub branch: u8,        // 0=Strategist 1=Skeptic 2=Historian 3=RiskGovernor 4=MethodInventor
    pub vote: NexusVote,
    pub confidence: f32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NexusDecision {
    pub outcome: String,          // "approve" | "oppose" | "undecided" | "vetoed"
    pub credibility: f32,
    pub support_weight: f32,
    pub oppose_weight: f32,
    pub vetoed: bool,
}

/// Native weighted consensus for the Multi-Mind Parliament. Weighted votes are
/// summed in float32 (parallel semantics to the Python fast_parliament_consensus).
pub fn parliament_consensus(weights: &[f32; 5], votes: &[NexusVoteRec]) -> NexusDecision {
    let mut total = 0.0f32;
    let mut support = 0.0f32;
    let mut oppose = 0.0f32;
    let mut vetoed = false;

    for rec in votes {
        let branch_weight = weights.get(rec.branch as usize).copied().unwrap_or(0.0);
        let w = branch_weight * rec.confidence;
        total += w;
        match rec.vote {
            NexusVote::Support => support += w,
            NexusVote::Oppose | NexusVote::Veto => {
                oppose += w;
                if rec.vote == NexusVote::Veto {
                    vetoed = true;
                }
            }
            NexusVote::Abstain => {}
        }
    }

    let credibility = if total > 0.0 { (support / total).clamp(0.0, 1.0) } else { 0.0 };
    // Veto always wins (mirrors the Python hard gate).
    let outcome = if vetoed {
        "vetoed"
    } else if credibility >= 0.6 && oppose < support {
        "approve"
    } else if oppose > support {
        "oppose"
    } else {
        "undecided"
    };

    NexusDecision {
        outcome: outcome.to_string(),
        credibility,
        support_weight: support,
        oppose_weight: oppose,
        vetoed,
    }
}

/// Default parliament branch weights — MUST match $ python fast_parliament_consensus
pub fn nexus_default_weights() -> [f32; 5] {
    [1.0, 1.0, 0.6, 1.2, 0.4]
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorldTwinStep {
    pub action: String,
    pub expected_info_gain: f32,
    pub cost: f32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorldTwinRollout {
    pub total_gain: f32,
    pub total_cost: f32,
    pub depth: usize,
    pub actions: Vec<String>,
}

/// Native World-Twin roll-forward accumulation (parallel to fast_roll_forward_gain).
pub fn world_twin_roll_forward(steps: &[WorldTwinStep]) -> WorldTwinRollout {
    steps.iter().fold(
        WorldTwinRollout {
            total_gain: 0.0,
            total_cost: 0.0,
            depth: steps.len(),
            actions: Vec::with_capacity(steps.len()),
        },
        |mut acc, s| {
            acc.total_gain += s.expected_info_gain;
            acc.total_cost += s.cost;
            acc.actions.push(s.action.clone());
            acc
        },
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_mandatory_counter_hypothesis_balance() {
        let mut engine = HypothesisEngine::new();
        let (h_id, c_id) = engine.create_hypothesis_pair(
            "Endpoint leaks JWT secret in debug trace",
            None,
            "AuthBypass",
            "/debug",
            3.5,
        );

        assert_eq!(engine.get(&h_id).unwrap().confidence, 0.5);
        assert_eq!(engine.get(&c_id).unwrap().confidence, 0.5);

        // Record supporting evidence on primary
        engine.record_evidence(&h_id, true, "Observed raw HS256 key in response", 0.3);

        assert!(engine.get(&h_id).unwrap().confidence > 0.7);
        assert!(engine.get(&c_id).unwrap().confidence < 0.3);
    }

    #[test]
    fn test_dead_end_detector() {
        let mut dec = DecisionEngine::new(3);
        assert_eq!(dec.record_failure("/api", "sqli"), DecisionAction::Proceed);
        assert_eq!(dec.record_failure("/api", "sqli"), DecisionAction::Proceed);
        assert_eq!(dec.record_failure("/api", "sqli"), DecisionAction::Pivot);
        assert!(dec.is_dead_end("/api", "sqli"));
    }

    #[test]
    fn test_brain_pure_reasoning_emits_plan() {
        let brain = ResearchBrain::new("t1");
        let mut engine = HypothesisEngine::new();
        engine.create_hypothesis_pair("IDOR on profile", None, "auth", "/api/profile", 4.0);

        let plan = brain.plan_next_step(&engine, false, 0);
        assert!(!plan.goal_satisfied);
        assert!(plan.experiment.is_some());
        assert_eq!(plan.specialist_type, "auth");
    }

    #[test]
    fn test_pwn_specialist_dispatch() {
        let brain = ResearchBrain::new("t1");
        let mut engine = HypothesisEngine::new();
        engine.create_hypothesis_pair("Stack buffer overflow in parse_header", None, "BinaryPwn", "/bin/target", 5.0);

        let plan = brain.plan_next_step(&engine, false, 0);
        assert_eq!(plan.specialist_type, "pwn");
    }

    #[test]
    fn test_nexus_parliament_approves_consensus() {
        use super::{nexus_default_weights, parliament_consensus, NexusVote, NexusVoteRec};
        let w = nexus_default_weights();
        let votes = vec![
            NexusVoteRec { branch: 0, vote: NexusVote::Support, confidence: 0.8 },
            NexusVoteRec { branch: 1, vote: NexusVote::Support, confidence: 0.6 },
            NexusVoteRec { branch: 3, vote: NexusVote::Support, confidence: 0.9 },
        ];
        let d = parliament_consensus(&w, &votes);
        assert_eq!(d.outcome, "approve");
        assert!(d.credibility >= 0.6);
        assert!(!d.vetoed);
    }

    #[test]
    fn test_nexus_parliament_veto_wins() {
        use super::{nexus_default_weights, parliament_consensus, NexusVote, NexusVoteRec};
        let w = nexus_default_weights();
        let votes = vec![
            NexusVoteRec { branch: 0, vote: NexusVote::Support, confidence: 0.9 },
            NexusVoteRec { branch: 3, vote: NexusVote::Veto, confidence: 1.0 },
        ];
        let d = parliament_consensus(&w, &votes);
        assert_eq!(d.outcome, "vetoed");
        assert!(d.vetoed);
    }

    #[test]
    fn test_nexus_world_twin_roll_forward() {
        use super::{world_twin_roll_forward, WorldTwinStep};
        let steps = vec![
            WorldTwinStep { action: "recon".into(), expected_info_gain: 0.8, cost: 0.2 },
            WorldTwinStep { action: "exploit".into(), expected_info_gain: 0.5, cost: 0.4 },
        ];
        let r = world_twin_roll_forward(&steps);
        assert_eq!(r.depth, 2);
        assert_eq!(r.total_gain, 1.3);
        assert_eq!(r.total_cost, 0.6);
    }
}
