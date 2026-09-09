//! 4-Tier Memory Architecture in Rust:
//! - L1: Working Memory (active context, current goal, scratchpad)
//! - L2: Episodic Memory (execution traces, timeline of actions)
//! - L3: Semantic Memory (vulnerability knowledge, attack patterns)
//! - L4: Procedural Lessons Ledger (cross-session failure avoidance, negative heuristics)

use std::collections::HashMap;
use chrono::Utc;
use serde::{Deserialize, Serialize};
use uuid::Uuid;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkingMemory {
    pub current_goal: String,
    pub active_hypothesis_id: Option<String>,
    pub scratchpad: HashMap<String, String>,
}

impl WorkingMemory {
    pub fn new(goal: &str) -> Self {
        Self {
            current_goal: goal.to_string(),
            active_hypothesis_id: None,
            scratchpad: HashMap::new(),
        }
    }

    pub fn set_scratch(&mut self, key: &str, val: &str) {
        self.scratchpad.insert(key.to_string(), val.to_string());
    }

    pub fn get_scratch(&self, key: &str) -> Option<&String> {
        self.scratchpad.get(key)
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EpisodeEntry {
    pub episode_id: String,
    pub action_type: String,
    pub target: String,
    pub observation_snippet: String,
    pub timestamp: String,
    pub success: bool,
}

pub struct EpisodicMemory {
    episodes: Vec<EpisodeEntry>,
}

impl EpisodicMemory {
    pub fn new() -> Self {
        Self { episodes: Vec::new() }
    }

    pub fn record(
        &mut self,
        action_type: &str,
        target: &str,
        obs: &str,
        success: bool,
    ) -> String {
        let id = format!("ep-{}", &Uuid::new_v4().to_string()[..8]);
        self.episodes.push(EpisodeEntry {
            episode_id: id.clone(),
            action_type: action_type.to_string(),
            target: target.to_string(),
            observation_snippet: obs.chars().take(200).collect(),
            timestamp: Utc::now().to_rfc3339(),
            success,
        });
        id
    }

    pub fn count(&self) -> usize {
        self.episodes.len()
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum LessonType {
    Success,
    Failure,
    FalsePositive,
    DeadEnd,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Lesson {
    pub lesson_id: String,
    pub lesson_type: LessonType,
    pub target_pattern: String,
    pub technique: String,
    pub summary: String,
    pub guidance: String,
    pub times_encountered: u32,
    pub created_at: String,
}

pub struct LessonsLedger {
    lessons: HashMap<String, Lesson>,
}

impl LessonsLedger {
    pub fn new() -> Self {
        Self {
            lessons: HashMap::new(),
        }
    }

    pub fn record_lesson(
        &mut self,
        lesson_type: LessonType,
        target_pattern: &str,
        technique: &str,
        summary: &str,
        guidance: &str,
    ) -> Lesson {
        let key = format!("{}::{}", target_pattern, technique);
        if let Some(existing) = self.lessons.get_mut(&key) {
            existing.times_encountered += 1;
            existing.summary = summary.to_string();
            existing.guidance = guidance.to_string();
            return existing.clone();
        }

        let lesson = Lesson {
            lesson_id: format!("les-{}", &Uuid::new_v4().to_string()[..8]),
            lesson_type,
            target_pattern: target_pattern.to_string(),
            technique: technique.to_string(),
            summary: summary.to_string(),
            guidance: guidance.to_string(),
            times_encountered: 1,
            created_at: Utc::now().to_rfc3339(),
        };

        self.lessons.insert(key, lesson.clone());
        lesson
    }

    pub fn query_avoidance(&self, target_pattern: &str) -> Vec<&Lesson> {
        self.lessons
            .values()
            .filter(|l| {
                l.target_pattern == target_pattern
                    && (l.lesson_type == LessonType::Failure
                        || l.lesson_type == LessonType::DeadEnd
                        || l.lesson_type == LessonType::FalsePositive)
            })
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_working_memory_scratchpad() {
        let mut wm = WorkingMemory::new("Audit target");
        wm.set_scratch("auth_header", "Bearer 123");
        assert_eq!(wm.get_scratch("auth_header").unwrap(), "Bearer 123");
    }

    #[test]
    fn test_lessons_ledger_negative_heuristic_avoidance() {
        let mut ledger = LessonsLedger::new();
        ledger.record_lesson(
            LessonType::DeadEnd,
            "nginx_waf",
            "sqli_union",
            "Union SQLi blocked by ModSecurity regex 942100",
            "Do not retry standard UNION SELECT; pivot to boolean blind or time-based",
        );

        let avoid = ledger.query_avoidance("nginx_waf");
        assert_eq!(avoid.len(), 1);
        assert!(avoid[0].guidance.contains("Do not retry standard UNION SELECT"));
    }
}
