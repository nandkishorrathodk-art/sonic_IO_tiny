//! SONIC v2 ("AI Human Pentester") — High-Performance Native Kernel
//!
//! Replaces iterative ReAct with an empirical research operating system:
//! World State -> Unknowns -> Hypothesis/Counter-Hypothesis -> Experiment -> Falsifier -> Attack Graph.
//!
//! Subsystems:
//! - `safety`: SealedActionPolicy, SafetyKernel, and Zero Host Escape guarantees.
//! - `brain`: ResearchBrain (tool-decoupled), HypothesisEngine, DecisionEngine.
//! - `world`: Dynamic World Model, Attack Graph (multi-hop traversal), Asset Inventory.
//! - `kernel`: MissionKernel FSM, 5D Budget Engine, Priority Scheduler, Blackboard.
//! - `evidence`: VerificationLab (5-step gate) and CustodyChain.
//! - `perception`: Multimodal PerceptionFusion (DOM + Screenshot + Network).
//! - `evolution`: Guarded Canary Evolution Pipeline with safety immutability.

pub mod error;
pub mod safety;
pub mod brain;
pub mod world;
pub mod kernel;
pub mod evidence;
pub mod perception;
pub mod evolution;
pub mod memory;
pub mod specialists;
pub mod ipc;

pub use error::{KernelError, KernelResult};
pub use ipc::{IpcServer, JsonRpcRequest, JsonRpcResponse};
pub use safety::{KernelVerdict, SafetyAuthorization, SafetyKernel, SealedPolicy};
pub use brain::{DecisionAction, DecisionEngine, Experiment, ExperimentPlan, Hypothesis, HypothesisEngine, HypothesisStatus, ResearchBrain};
pub use world::{AssetInventory, AssetNode, AttackGraph, AttackNode, AttackPath, AttackTransitionEdge};
pub use kernel::{Blackboard, BudgetTracker, InformationGainCostScheduler, MissionBudget, MissionKernel, MissionState, ScheduledTask};
pub use evidence::{CustodyChain, VerificationLab, VerificationLabReport};
pub use perception::{InteractiveControl, PerceptionFusion, StructuredWorldState};
pub use evolution::{EvolutionPipeline, EvolutionStage, ImprovementProposal};
pub use memory::{EpisodicMemory, Lesson, LessonType, LessonsLedger, WorkingMemory};
pub use specialists::{SpecialistResult, SpecialistType, SpecialistWorker};
