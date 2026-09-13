//! JSON-RPC 2.0 / CLI Inter-Process Communication Engine.
//!
//! Allows Python (sonic-core), Docker agents, and external runners to query
//! the native Rust Safety Kernel, Perception Fusion, and Verification Lab
//! at microsecond speeds via standard JSON streams.

use std::io::{self, BufRead, Write};
use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::{
    perception::{DesktopPerception, PerceptionFusion},
    safety::SafetyKernel,
    specialists::{SpecialistType, SpecialistWorker},
    evidence::{CustodyChain, VerificationLab},
};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct JsonRpcRequest {
    pub jsonrpc: Option<String>,
    pub id: Option<Value>,
    pub method: String,
    #[serde(default)]
    pub params: Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct JsonRpcResponse {
    pub jsonrpc: String,
    pub id: Value,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub result: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<Value>,
}

pub struct IpcServer {
    safety_kernel: SafetyKernel,
    desktop_perception: DesktopPerception,
}

impl IpcServer {
    pub fn new(tenant_id: &str, workspace: &str) -> Self {
        Self {
            safety_kernel: SafetyKernel::new(tenant_id, workspace, true),
            desktop_perception: DesktopPerception::new(),
        }
    }

    pub fn handle_request(&mut self, req: JsonRpcRequest) -> JsonRpcResponse {
        let id = req.id.unwrap_or(Value::Null);

        let result = match req.method.as_str() {
            "health" => Ok(serde_json::json!({
                "status": "healthy",
                "version": "0.2.0",
                "engine": "sonic-kernel-rs",
                "safety_sealed": self.safety_kernel.policy.verify_seal(),
            })),

            "authorize" => {
                let action_type = req.params.get("action_type").and_then(|v| v.as_str()).unwrap_or("");
                let target = req.params.get("target").and_then(|v| v.as_str()).unwrap_or("");
                let is_isolated = req.params.get("is_isolated").and_then(|v| v.as_bool()).unwrap_or(true);

                let auth = self.safety_kernel.authorize(action_type, target, is_isolated);
                serde_json::to_value(&auth).map_err(|e| e.to_string())
            }

            "fuse_perception" => {
                let url = req.params.get("url").and_then(|v| v.as_str()).unwrap_or("");
                let title = req.params.get("title").and_then(|v| v.as_str()).unwrap_or("");
                let html = req.params.get("html").and_then(|v| v.as_str());

                let state = PerceptionFusion::fuse(url, title, None, html);
                serde_json::to_value(&state).map_err(|e| e.to_string())
            }

            "desktop_snapshot" => {
                let screenshot = req.params.get("screenshot")
                    .and_then(|v| v.as_str())
                    .map(str::as_bytes);
                let strings = |key: &str| -> Vec<String> {
                    req.params.get(key)
                        .and_then(|v| v.as_array())
                        .map(|items| items.iter().filter_map(|item| item.as_str().map(str::to_string)).collect())
                        .unwrap_or_default()
                };
                let snapshot = self.desktop_perception.publish(
                    req.params.get("width").and_then(|v| v.as_u64()).unwrap_or(0) as u32,
                    req.params.get("height").and_then(|v| v.as_u64()).unwrap_or(0) as u32,
                    req.params.get("active_window").and_then(|v| v.as_str()).unwrap_or(""),
                    strings("windows"),
                    strings("processes"),
                    strings("visible_text"),
                    strings("controls"),
                    screenshot,
                );
                serde_json::to_value(snapshot).map_err(|e| e.to_string())
            }

            "desktop_action_check" => {
                let expected_version = req.params.get("expected_version")
                    .and_then(|v| v.as_u64())
                    .unwrap_or(0);
                let check = self.desktop_perception.check_action(expected_version);
                serde_json::to_value(check).map_err(|e| e.to_string())
            }

            "compute_custody_hash" => {
                let payload = req.params.get("payload").and_then(|v| v.as_str()).unwrap_or("");
                let hash = CustodyChain::compute_hash(payload.as_bytes());
                Ok(serde_json::json!({ "custody_hash": hash }))
            }

            "verify_finding" => {
                let finding_id = req.params.get("finding_id").and_then(|v| v.as_str()).unwrap_or("finding-unknown");
                let poc = req.params.get("poc").and_then(|v| v.as_str()).unwrap_or("");
                let baseline = req.params.get("baseline").and_then(|v| v.as_str()).unwrap_or("");
                let probe = req.params.get("probe").and_then(|v| v.as_str()).unwrap_or("");
                let repro = req.params.get("reproduction").and_then(|v| v.as_str()).unwrap_or("");
                let impact = req.params.get("impact").and_then(|v| v.as_str());
                let expected_hash = req.params.get("expected_hash").and_then(|v| v.as_str()).unwrap_or("");

                let rep = VerificationLab::verify_candidate(
                    finding_id, poc, baseline, probe, repro, impact, expected_hash,
                );
                serde_json::to_value(&rep).map_err(|e| e.to_string())
            }

            "evaluate_probe" => {
                let spec_str = req.params.get("specialist").and_then(|v| v.as_str()).unwrap_or("web");
                let specialist = match spec_str {
                    "pwn" => SpecialistType::Pwn,
                    "crypto" => SpecialistType::Crypto,
                    "network" => SpecialistType::Network,
                    "auth" => SpecialistType::Auth,
                    "api" => SpecialistType::Api,
                    "forensics" => SpecialistType::Forensics,
                    "logic" => SpecialistType::Logic,
                    "recon" => SpecialistType::Recon,
                    _ => SpecialistType::Web,
                };
                let exp_id = req.params.get("experiment_id").and_then(|v| v.as_str()).unwrap_or("exp-01");
                let hyp_id = req.params.get("hypothesis_id").and_then(|v| v.as_str()).unwrap_or("hyp-01");
                let baseline = req.params.get("baseline").and_then(|v| v.as_str()).unwrap_or("");
                let probe = req.params.get("probe").and_then(|v| v.as_str()).unwrap_or("");

                let res = SpecialistWorker::evaluate_probe(specialist, exp_id, hyp_id, baseline, probe);
                serde_json::to_value(&res).map_err(|e| e.to_string())
            }

            "nexus_parliament_consensus" => {
                let weights: [f32; 5] = req.params
                    .get("weights")
                    .and_then(|v| v.as_array())
                    .map(|arr| {
                        let mut w = [1.0f32; 5];
                        for (i, v) in arr.iter().take(5).enumerate() {
                            w[i] = v.as_f64().unwrap_or(1.0) as f32;
                        }
                        w
                    })
                    .unwrap_or_else(crate::brain::nexus_default_weights);
                let votes: Vec<crate::brain::NexusVoteRec> = req.params
                    .get("votes")
                    .and_then(|v| serde_json::from_value(v.clone()).ok())
                    .unwrap_or_default();
                let decision = crate::brain::parliament_consensus(&weights, &votes);
                serde_json::to_value(&decision).map_err(|e| e.to_string())
            }

            "nexus_world_twin_roll_forward" => {
                let steps: Vec<crate::brain::WorldTwinStep> = req.params
                    .get("steps")
                    .and_then(|v| serde_json::from_value(v.clone()).ok())
                    .unwrap_or_default();
                let rollout = crate::brain::world_twin_roll_forward(&steps);
                serde_json::to_value(&rollout).map_err(|e| e.to_string())
            }

            unknown => Err(format!("Unknown JSON-RPC method '{}'", unknown)),
        };

        match result {
            Ok(val) => JsonRpcResponse {
                jsonrpc: "2.0".to_string(),
                id,
                result: Some(val),
                error: None,
            },
            Err(err_msg) => JsonRpcResponse {
                jsonrpc: "2.0".to_string(),
                id,
                result: None,
                error: Some(serde_json::json!({
                    "code": -32601,
                    "message": err_msg,
                })),
            },
        }
    }

    /// Runs a line-delimited JSON-RPC loop reading from standard input and writing to standard output.
    pub fn run_stdio_loop(&mut self) -> io::Result<()> {
        let stdin = io::stdin();
        let mut stdout = io::stdout();

        for line in stdin.lock().lines() {
            let line = line?;
            let trimmed = line.trim();
            if trimmed.is_empty() {
                continue;
            }

            match serde_json::from_str::<JsonRpcRequest>(trimmed) {
                Ok(req) => {
                    let resp = self.handle_request(req);
                    let serialized = serde_json::to_string(&resp)?;
                    writeln!(stdout, "{}", serialized)?;
                    stdout.flush()?;
                }
                Err(e) => {
                    let err_resp = JsonRpcResponse {
                        jsonrpc: "2.0".to_string(),
                        id: Value::Null,
                        result: None,
                        error: Some(serde_json::json!({
                            "code": -32700,
                            "message": format!("Parse error: {}", e),
                        })),
                    };
                    let serialized = serde_json::to_string(&err_resp)?;
                    writeln!(stdout, "{}", serialized)?;
                    stdout.flush()?;
                }
            }
        }

        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_ipc_server_health_and_authorize() {
        let mut server = IpcServer::new("tenant-test", "/workspace");

        // 1. Health query
        let req_health = JsonRpcRequest {
            jsonrpc: Some("2.0".to_string()),
            id: Some(serde_json::json!(1)),
            method: "health".to_string(),
            params: serde_json::json!({}),
        };
        let res_health = server.handle_request(req_health);
        assert!(res_health.result.is_some());
        assert_eq!(res_health.result.unwrap().get("status").unwrap(), "healthy");

        // 2. Authorize query (allowed sandbox command)
        let req_auth = JsonRpcRequest {
            jsonrpc: Some("2.0".to_string()),
            id: Some(serde_json::json!(2)),
            method: "authorize".to_string(),
            params: serde_json::json!({
                "action_type": "TERMINAL_EXEC",
                "target": "nmap -sV target",
                "is_isolated": true
            }),
        };
        let res_auth = server.handle_request(req_auth);
        assert!(res_auth.result.is_some());
        assert_eq!(res_auth.result.unwrap().get("verdict").unwrap(), "Allow");

        // 3. Authorize query (denied host escape)
        let req_escape = JsonRpcRequest {
            jsonrpc: Some("2.0".to_string()),
            id: Some(serde_json::json!(3)),
            method: "authorize".to_string(),
            params: serde_json::json!({
                "action_type": "TERMINAL_EXEC",
                "target": "whoami",
                "is_isolated": false
            }),
        };
        let res_escape = server.handle_request(req_escape);
        assert_eq!(res_escape.result.unwrap().get("verdict").unwrap(), "Deny");
    }

    #[test]
    fn test_ipc_desktop_snapshot_and_stale_action_check() {
        let mut server = IpcServer::new("tenant-test", "/workspace");
        let snapshot = server.handle_request(JsonRpcRequest {
            jsonrpc: Some("2.0".to_string()),
            id: Some(serde_json::json!(4)),
            method: "desktop_snapshot".to_string(),
            params: serde_json::json!({
                "width": 1280,
                "height": 800,
                "active_window": "Terminal",
                "windows": ["Terminal", "Desktop"],
                "processes": ["wm", "terminal"],
                "visible_text": ["Ready"],
                "controls": ["prompt"],
                "screenshot": "frame-a"
            }),
        });
        let version = snapshot.result.unwrap().get("version").unwrap().as_u64().unwrap();

        let current = server.handle_request(JsonRpcRequest {
            jsonrpc: Some("2.0".to_string()),
            id: Some(serde_json::json!(5)),
            method: "desktop_action_check".to_string(),
            params: serde_json::json!({"expected_version": version}),
        });
        assert_eq!(current.result.unwrap().get("allowed").unwrap(), true);

        let stale = server.handle_request(JsonRpcRequest {
            jsonrpc: Some("2.0".to_string()),
            id: Some(serde_json::json!(6)),
            method: "desktop_action_check".to_string(),
            params: serde_json::json!({"expected_version": version - 1}),
        });
        assert_eq!(stale.result.unwrap().get("allowed").unwrap(), false);
    }
}
