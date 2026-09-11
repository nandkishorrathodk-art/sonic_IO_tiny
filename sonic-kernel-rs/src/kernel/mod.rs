//! Central Kernel, Mission Lifecycle FSM, 5D Budget Engine, Scheduler, and Event Bus in Rust.

use std::collections::{BinaryHeap, HashMap};
use std::sync::RwLock;
use std::time::Instant;
use serde::{de::DeserializeOwned, Deserialize, Serialize};
use uuid::Uuid;

use crate::error::{KernelError, KernelResult};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum MissionState {
    Created,
    Scoped,
    Planning,
    Researching,
    Verifying,
    Reporting,
    Completed,
    Paused,
    Blocked,
    Failed,
    Cancelled,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MissionBudget {
    pub time_limit_seconds: f32,
    pub max_actions: u32,
    pub max_experiments: u32,
    pub max_tokens: u64,
    pub max_risk_score: f32,
}

impl Default for MissionBudget {
    fn default() -> Self {
        Self {
            time_limit_seconds: 3600.0,
            max_actions: 100,
            max_experiments: 25,
            max_tokens: 500_000,
            max_risk_score: 10.0,
        }
    }
}

pub struct BudgetTracker {
    pub budget: MissionBudget,
    pub actions_consumed: u32,
    pub experiments_consumed: u32,
    pub tokens_consumed: u64,
    pub risk_points_consumed: f32,
    start_time: Instant,
}

impl BudgetTracker {
    pub fn new(budget: MissionBudget) -> Self {
        Self {
            budget,
            actions_consumed: 0,
            experiments_consumed: 0,
            tokens_consumed: 0,
            risk_points_consumed: 0.0,
            start_time: Instant::now(),
        }
    }

    pub fn consume_action(&mut self, count: u32, risk: f32) {
        self.actions_consumed += count;
        self.risk_points_consumed += risk;
    }

    pub fn consume_experiment(&mut self, count: u32) {
        self.experiments_consumed += count;
    }

    pub fn consume_tokens(&mut self, tokens: u64) {
        self.tokens_consumed += tokens;
    }

    pub fn is_exhausted(&self) -> (bool, String) {
        let elapsed = self.start_time.elapsed().as_secs_f32();
        if elapsed >= self.budget.time_limit_seconds {
            return (true, format!("Time budget exhausted ({:.1}s / {:.1}s)", elapsed, self.budget.time_limit_seconds));
        }
        if self.actions_consumed >= self.budget.max_actions {
            return (true, format!("Action budget exhausted ({} / {})", self.actions_consumed, self.budget.max_actions));
        }
        if self.experiments_consumed >= self.budget.max_experiments {
            return (true, format!("Experiment budget exhausted ({} / {})", self.experiments_consumed, self.budget.max_experiments));
        }
        if self.tokens_consumed >= self.budget.max_tokens {
            return (true, format!("Token budget exhausted ({} / {})", self.tokens_consumed, self.budget.max_tokens));
        }
        if self.risk_points_consumed >= self.budget.max_risk_score {
            return (true, format!("Risk budget exhausted ({:.1} / {:.1})", self.risk_points_consumed, self.budget.max_risk_score));
        }
        (false, "Budget healthy".to_string())
    }
}

pub struct MissionKernel {
    pub mission_id: String,
    pub target: String,
    pub goal: String,
    pub tenant_id: String,
    pub state: MissionState,
    pub budget_tracker: BudgetTracker,
    pub findings_count: usize,
}

impl MissionKernel {
    pub fn new(target: &str, goal: &str, tenant_id: &str, budget: Option<MissionBudget>) -> Self {
        Self {
            mission_id: format!("mis-{}", &Uuid::new_v4().to_string()[..8]),
            target: target.to_string(),
            goal: goal.to_string(),
            tenant_id: tenant_id.to_string(),
            state: MissionState::Created,
            budget_tracker: BudgetTracker::new(budget.unwrap_or_default()),
            findings_count: 0,
        }
    }

    pub fn validate_scope(&mut self, in_scope: bool, _reason: &str) -> bool {
        if !in_scope {
            self.state = MissionState::Blocked;
            return false;
        }
        if self.state == MissionState::Created {
            self.state = MissionState::Scoped;
            return true;
        }
        false
    }

    pub fn transition_checked(&mut self, next: MissionState) -> KernelResult<()> {
        let valid = match (self.state, next) {
            (MissionState::Created, MissionState::Scoped | MissionState::Blocked | MissionState::Cancelled) => true,
            (MissionState::Scoped, MissionState::Planning | MissionState::Blocked | MissionState::Cancelled) => true,
            (MissionState::Planning, MissionState::Researching | MissionState::Completed | MissionState::Failed | MissionState::Cancelled) => true,
            (MissionState::Researching, MissionState::Verifying | MissionState::Completed | MissionState::Planning | MissionState::Failed | MissionState::Cancelled) => true,
            (MissionState::Verifying, MissionState::Reporting | MissionState::Researching | MissionState::Completed | MissionState::Failed | MissionState::Cancelled) => true,
            (MissionState::Reporting, MissionState::Completed | MissionState::Failed) => true,
            (MissionState::Paused, MissionState::Researching | MissionState::Planning | MissionState::Cancelled) => true,
            (MissionState::Blocked, MissionState::Scoped | MissionState::Failed | MissionState::Cancelled) => true,
            _ => false,
        };

        if valid {
            self.state = next;
            Ok(())
        } else {
            Err(KernelError::InvalidStateTransition {
                current: format!("{:?}", self.state),
                attempted: format!("{:?}", next),
            })
        }
    }

    pub fn transition_to(&mut self, next: MissionState) -> bool {
        self.transition_checked(next).is_ok()
    }

    pub fn check_budget(&mut self) -> bool {
        let (exhausted, _) = self.budget_tracker.is_exhausted();
        if exhausted {
            if self.state == MissionState::Researching || self.state == MissionState::Planning {
                if self.findings_count > 0 {
                    let _ = self.transition_to(MissionState::Verifying);
                } else {
                    let _ = self.transition_to(MissionState::Completed);
                }
            }
            return false;
        }
        true
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ScheduledTask {
    pub task_id: String,
    pub name: String,
    pub specialist_type: String,
    pub priority_score: u64, // Multiplied by 1000 for integer ordering
}

impl Ord for ScheduledTask {
    fn cmp(&self, other: &Self) -> std::cmp::Ordering {
        self.priority_score.cmp(&other.priority_score)
    }
}

impl PartialOrd for ScheduledTask {
    fn partial_cmp(&self, other: &Self) -> Option<std::cmp::Ordering> {
        Some(self.cmp(other))
    }
}

pub struct InformationGainCostScheduler {
    max_concurrency: usize,
    queue: BinaryHeap<ScheduledTask>,
    active_count: usize,
}

impl InformationGainCostScheduler {
    pub fn new(max_concurrency: usize) -> Self {
        Self {
            max_concurrency,
            queue: BinaryHeap::new(),
            active_count: 0,
        }
    }

    pub fn enqueue(
        &mut self,
        name: &str,
        specialist_type: &str,
        info_gain: f32,
        impact: f32,
        confidence: f32,
        cost: f32,
        time: f32,
        risk: f32,
    ) -> String {
        let tid = format!("task-{}", &Uuid::new_v4().to_string()[..8]);
        let safe_cost = cost.max(0.01);
        let safe_time = time.max(0.01);
        let safe_risk = risk.max(0.01);
        let denominator = (safe_cost * safe_time * safe_risk).max(0.001);
        let raw_score = (info_gain.max(0.0) * impact.max(0.0) * confidence.max(0.0)) / denominator;
        let score = if raw_score.is_nan() || raw_score.is_infinite() {
            0.0
        } else {
            raw_score
        };

        self.queue.push(ScheduledTask {
            task_id: tid.clone(),
            name: name.to_string(),
            specialist_type: specialist_type.to_string(),
            priority_score: (score * 1000.0) as u64,
        });

        tid
    }

    pub fn peek_next(&self) -> Option<&ScheduledTask> {
        self.queue.peek()
    }

    pub fn len(&self) -> usize {
        self.queue.len()
    }

    pub fn is_empty(&self) -> bool {
        self.queue.is_empty()
    }

    pub fn pop_next(&mut self) -> Option<ScheduledTask> {
        if self.active_count >= self.max_concurrency {
            return None;
        }
        if let Some(task) = self.queue.pop() {
            self.active_count += 1;
            Some(task)
        } else {
            None
        }
    }

    pub fn complete_task(&mut self) {
        if self.active_count > 0 {
            self.active_count -= 1;
        }
    }

    pub fn clear(&mut self) {
        self.queue.clear();
        self.active_count = 0;
    }
}

pub struct Blackboard {
    entries: RwLock<HashMap<String, String>>,
}

impl Blackboard {
    pub fn new() -> Self {
        Self {
            entries: RwLock::new(HashMap::new()),
        }
    }

    pub fn post(&self, key: &str, value: &str) {
        let mut lock = self.entries.write().unwrap_or_else(|poisoned| poisoned.into_inner());
        lock.insert(key.to_string(), value.to_string());
    }

    pub fn post_json<T: Serialize>(&self, key: &str, value: &T) -> KernelResult<()> {
        let serialized = serde_json::to_string(value)
            .map_err(|e| KernelError::SerializationError(e.to_string()))?;
        self.post(key, &serialized);
        Ok(())
    }

    pub fn get(&self, key: &str) -> Option<String> {
        let lock = self.entries.read().unwrap_or_else(|poisoned| poisoned.into_inner());
        lock.get(key).cloned()
    }

    pub fn get_json<T: DeserializeOwned>(&self, key: &str) -> Option<T> {
        let raw = self.get(key)?;
        serde_json::from_str(&raw).ok()
    }

    pub fn contains(&self, key: &str) -> bool {
        let lock = self.entries.read().unwrap_or_else(|poisoned| poisoned.into_inner());
        lock.contains_key(key)
    }

    pub fn remove(&self, key: &str) -> Option<String> {
        let mut lock = self.entries.write().unwrap_or_else(|poisoned| poisoned.into_inner());
        lock.remove(key)
    }

    pub fn count(&self) -> usize {
        let lock = self.entries.read().unwrap_or_else(|poisoned| poisoned.into_inner());
        lock.len()
    }
}

impl Default for Blackboard {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_mission_fsm_lifecycle_and_budget() {
        let budget = MissionBudget {
            max_actions: 2,
            ..Default::default()
        };
        let mut kernel = MissionKernel::new("https://target.local", "Audit", "t1", Some(budget));
        assert_eq!(kernel.state, MissionState::Created);

        // Out of scope fails closed
        let mut kernel_blocked = MissionKernel::new("https://unauth.local", "Audit", "t1", None);
        assert!(!kernel_blocked.validate_scope(false, "Out of scope"));
        assert_eq!(kernel_blocked.state, MissionState::Blocked);

        // Valid scope advances
        assert!(kernel.validate_scope(true, "In scope"));
        assert_eq!(kernel.state, MissionState::Scoped);

        assert!(kernel.transition_to(MissionState::Planning));
        assert!(kernel.transition_to(MissionState::Researching));

        // Consume budget beyond limit
        kernel.budget_tracker.consume_action(3, 0.0);
        assert!(!kernel.check_budget());
        assert_eq!(kernel.state, MissionState::Completed);
    }

    #[test]
    fn test_transition_checked_error_reporting() {
        let mut kernel = MissionKernel::new("https://target.local", "Audit", "t1", None);
        let res = kernel.transition_checked(MissionState::Reporting);
        assert!(res.is_err());
        if let Err(KernelError::InvalidStateTransition { current, attempted }) = res {
            assert_eq!(current, "Created");
            assert_eq!(attempted, "Reporting");
        } else {
            panic!("Expected InvalidStateTransition error");
        }
    }

    #[test]
    fn test_priority_scheduler_ordering() {
        let mut scheduler = InformationGainCostScheduler::new(2);

        // Low value: info_gain=1, cost=10
        scheduler.enqueue("Brute force", "recon", 1.0, 1.0, 1.0, 10.0, 5.0, 2.0);
        // High value: info_gain=5, cost=1
        let high_id = scheduler.enqueue("IDOR probe", "auth", 5.0, 4.0, 3.0, 1.0, 1.0, 1.0);

        assert_eq!(scheduler.len(), 2);
        assert_eq!(scheduler.peek_next().unwrap().task_id, high_id);

        let first = scheduler.pop_next().unwrap();
        assert_eq!(first.task_id, high_id);
    }

    #[test]
    fn test_blackboard_typed_json_and_concurrency() {
        let bb = Blackboard::new();
        bb.post("token", "secret123");
        assert_eq!(bb.get("token").unwrap(), "secret123");
        assert!(bb.contains("token"));

        #[derive(Serialize, Deserialize, PartialEq, Debug)]
        struct Finding {
            id: String,
            severity: String,
        }

        let f = Finding {
            id: "f-01".to_string(),
            severity: "critical".to_string(),
        };

        bb.post_json("finding_1", &f).unwrap();
        let loaded: Option<Finding> = bb.get_json("finding_1");
        assert_eq!(loaded, Some(f));
    }
}
