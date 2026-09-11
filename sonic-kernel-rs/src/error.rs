//! Unified error handling and Result types for the SONIC native Rust kernel.

use std::fmt;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum KernelError {
    PolicyViolation {
        action_type: String,
        reason: String,
    },
    TamperDetected {
        expected: String,
        computed: String,
    },
    InvalidStateTransition {
        current: String,
        attempted: String,
    },
    BudgetExhausted(String),
    RateLimitExceeded {
        actions_this_minute: u32,
        max_allowed: u32,
    },
    EgressBlocked {
        target: String,
        matched_cidr: String,
    },
    LockPoisoned(String),
    SerializationError(String),
    InvalidNodeOrAsset(String),
    Internal(String),
}

impl fmt::Display for KernelError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            KernelError::PolicyViolation { action_type, reason } => {
                write!(f, "Safety policy violation for '{}': {}", action_type, reason)
            }
            KernelError::TamperDetected { expected, computed } => {
                write!(f, "Safety policy seal tampered! Expected {}, got {}", expected, computed)
            }
            KernelError::InvalidStateTransition { current, attempted } => {
                write!(f, "Invalid mission FSM transition: cannot move from '{}' to '{}'", current, attempted)
            }
            KernelError::BudgetExhausted(reason) => {
                write!(f, "5D mission budget exhausted: {}", reason)
            }
            KernelError::RateLimitExceeded { actions_this_minute, max_allowed } => {
                write!(f, "Rate limit exceeded: {} actions in current minute (max {})", actions_this_minute, max_allowed)
            }
            KernelError::EgressBlocked { target, matched_cidr } => {
                write!(f, "Network egress blocked: target '{}' falls within restricted range '{}'", target, matched_cidr)
            }
            KernelError::LockPoisoned(msg) => {
                write!(f, "Kernel lock poisoned: {}", msg)
            }
            KernelError::SerializationError(msg) => {
                write!(f, "Kernel serialization error: {}", msg)
            }
            KernelError::InvalidNodeOrAsset(msg) => {
                write!(f, "Invalid node or asset in attack topology: {}", msg)
            }
            KernelError::Internal(msg) => {
                write!(f, "Internal kernel error: {}", msg)
            }
        }
    }
}

impl std::error::Error for KernelError {}

pub type KernelResult<T> = Result<T, KernelError>;

