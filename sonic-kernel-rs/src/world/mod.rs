//! World Model, Asset Topology, and Attack Graph in Rust.
//!
//! Provides multi-hop exploitation chain discovery, depth-bounded traversal,
//! and joint confidence calculation.

use std::collections::{HashMap, HashSet};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AttackNode {
    pub node_id: String,
    pub asset_id: String,
    pub observed_state: String,
    pub privilege_obtained: String,
    pub confidence: f32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AttackTransitionEdge {
    pub edge_id: String,
    pub from_node: String,
    pub to_node: String,
    pub action_signature: String,
    pub confidence: f32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AttackPath {
    pub steps: Vec<AttackTransitionEdge>,
    pub nodes: Vec<String>,
    pub combined_confidence: f32,
    pub total_hops: usize,
}

pub struct AttackGraph {
    nodes: HashMap<String, AttackNode>,
    adj: HashMap<String, Vec<AttackTransitionEdge>>,
}

impl AttackGraph {
    pub fn new() -> Self {
        Self {
            nodes: HashMap::new(),
            adj: HashMap::new(),
        }
    }

    pub fn add_node(
        &mut self,
        node_id: &str,
        asset_id: &str,
        observed_state: &str,
        privilege_obtained: &str,
        confidence: f32,
    ) -> AttackNode {
        let node = AttackNode {
            node_id: node_id.to_string(),
            asset_id: asset_id.to_string(),
            observed_state: observed_state.to_string(),
            privilege_obtained: privilege_obtained.to_string(),
            confidence: confidence.clamp(0.01, 1.0),
        };
        self.nodes.insert(node_id.to_string(), node.clone());
        self.adj.entry(node_id.to_string()).or_default();
        node
    }

    pub fn get_node(&self, node_id: &str) -> Option<&AttackNode> {
        self.nodes.get(node_id)
    }

    pub fn node_count(&self) -> usize {
        self.nodes.len()
    }

    pub fn edge_count(&self) -> usize {
        self.adj.values().map(|v| v.len()).sum()
    }

    pub fn add_transition(
        &mut self,
        from_id: &str,
        to_id: &str,
        action: &str,
        confidence: f32,
    ) -> AttackTransitionEdge {
        let edge = AttackTransitionEdge {
            edge_id: format!("edge-{}", &Uuid::new_v4().to_string()[..8]),
            from_node: from_id.to_string(),
            to_node: to_id.to_string(),
            action_signature: action.to_string(),
            confidence: confidence.clamp(0.01, 1.0),
        };

        self.adj.entry(from_id.to_string()).or_default().push(edge.clone());
        edge
    }

    pub fn find_attack_chains(&self, start_id: &str, objective_id: &str) -> Vec<AttackPath> {
        let mut paths = Vec::new();
        let mut visited = HashSet::new();
        let mut current_edges = Vec::new();

        visited.insert(start_id.to_string());
        self.dfs(start_id, objective_id, &mut current_edges, &mut visited, &mut paths, 20);

        // Sort descending by combined confidence
        paths.sort_by(|a, b| {
            b.combined_confidence
                .partial_cmp(&a.combined_confidence)
                .unwrap_or(std::cmp::Ordering::Equal)
        });

        paths
    }

    pub fn find_highest_confidence_path(&self, start_id: &str, objective_id: &str) -> Option<AttackPath> {
        self.find_attack_chains(start_id, objective_id).into_iter().next()
    }

    fn dfs(
        &self,
        current: &str,
        objective: &str,
        current_edges: &mut Vec<AttackTransitionEdge>,
        visited: &mut HashSet<String>,
        results: &mut Vec<AttackPath>,
        max_hops: usize,
    ) {
        if current_edges.len() > max_hops {
            return;
        }

        if current == objective && !current_edges.is_empty() {
            let mut conf = 1.0;
            let mut node_seq = vec![current_edges[0].from_node.clone()];
            for edge in current_edges.iter() {
                conf *= edge.confidence;
                node_seq.push(edge.to_node.clone());
            }

            results.push(AttackPath {
                steps: current_edges.clone(),
                nodes: node_seq,
                combined_confidence: (conf * 10000.0).round() / 10000.0,
                total_hops: current_edges.len(),
            });
            return;
        }

        if let Some(neighbors) = self.adj.get(current) {
            for edge in neighbors {
                if !visited.contains(&edge.to_node) {
                    visited.insert(edge.to_node.clone());
                    current_edges.push(edge.clone());
                    self.dfs(&edge.to_node, objective, current_edges, visited, results, max_hops);
                    current_edges.pop();
                    visited.remove(&edge.to_node);
                }
            }
        }
    }
}

impl Default for AttackGraph {
    fn default() -> Self {
        Self::new()
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AssetNode {
    pub asset_id: String,
    pub identifier: String,
    pub asset_type: String,
    pub port: Option<u16>,
    pub technology_stack: Vec<String>,
    pub endpoints: Vec<String>,
}

pub struct AssetInventory {
    assets: HashMap<String, AssetNode>,
}

impl AssetInventory {
    pub fn new() -> Self {
        Self {
            assets: HashMap::new(),
        }
    }

    pub fn register_asset(
        &mut self,
        identifier: &str,
        asset_type: &str,
        port: Option<u16>,
        technologies: Vec<String>,
    ) -> AssetNode {
        for a in self.assets.values_mut() {
            if a.identifier == identifier && a.port == port {
                for t in technologies {
                    if !a.technology_stack.contains(&t) {
                        a.technology_stack.push(t);
                    }
                }
                return a.clone();
            }
        }

        let asset_id = format!("asset-{}", &Uuid::new_v4().to_string()[..8]);
        let node = AssetNode {
            asset_id: asset_id.clone(),
            identifier: identifier.to_string(),
            asset_type: asset_type.to_string(),
            port,
            technology_stack: technologies,
            endpoints: Vec::new(),
        };

        self.assets.insert(asset_id, node.clone());
        node
    }

    pub fn add_endpoint(&mut self, asset_id: &str, endpoint: &str) {
        if let Some(a) = self.assets.get_mut(asset_id) {
            if !a.endpoints.contains(&endpoint.to_string()) {
                a.endpoints.push(endpoint.to_string());
            }
        }
    }
}

impl Default for AssetInventory {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_attack_graph_multi_hop_traversal() {
        let mut graph = AttackGraph::new();

        graph.add_node("n0", "web", "public_login", "anonymous", 1.0);
        graph.add_node("n1", "web", "user_session", "low_priv", 0.9);
        graph.add_node("n2", "api", "leaked_admin_key", "elevated", 0.95);
        graph.add_node("n3", "db", "root_shell", "system_admin", 0.9);

        graph.add_transition("n0", "n1", "Weak password reset", 0.9);
        graph.add_transition("n1", "n2", "IDOR on API keys", 0.95);
        graph.add_transition("n2", "n3", "DB connection via leaked key", 0.9);

        // Direct low-confidence bypass
        graph.add_transition("n0", "n3", "Direct unauthenticated blind SQLi", 0.3);

        let chains = graph.find_attack_chains("n0", "n3");
        assert_eq!(chains.len(), 2);

        // Best path should be the chained 3-hop path
        let best = graph.find_highest_confidence_path("n0", "n3").unwrap();
        assert_eq!(best.total_hops, 3);
        assert!((best.combined_confidence - 0.7695).abs() < 0.001);
        assert_eq!(best.nodes, vec!["n0", "n1", "n2", "n3"]);
        assert_eq!(graph.node_count(), 4);
        assert_eq!(graph.edge_count(), 4);
    }
}
