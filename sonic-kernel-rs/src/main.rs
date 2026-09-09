//! SONIC v2 ("AI Human Pentester") — Rust Native Kernel Daemon & CLI Entrypoint
//!
//! Autonomous, Epistemic Research Engine with Zero Host Escape & Tamper-Evident Safety Envelope.

use sonic_kernel::{
    AssetInventory, AttackGraph, Blackboard, CustodyChain, EpisodicMemory, EvolutionPipeline,
    HypothesisEngine, InformationGainCostScheduler, KernelVerdict, LessonType, LessonsLedger,
    MissionBudget, MissionKernel, MissionState, PerceptionFusion, ResearchBrain, SafetyKernel,
    SpecialistType, SpecialistWorker, VerificationLab,
};

fn main() {
    println!("================================================================================");
    println!("  SONIC v2 — AI Human Pentester (Native Rust Research Kernel)                   ");
    println!("================================================================================");

    let tenant_id = "tenant-enterprise-01";
    let target_url = "https://target-app.local";
    let workspace = "/home/sonic/sandboxes/target-app";

    // 1. Initialize Safety Kernel (Fail-closed, Sealed SHA-256 Policy, Zero Host Escape)
    println!("\n[1] Initializing Safety Kernel...");
    let mut safety = SafetyKernel::new(tenant_id, workspace, true);
    println!("    Policy Sealed Hash : {}", safety.policy.seal_hash);
    println!("    Seal Verified      : {}", safety.policy.verify_seal());
    println!("    Zero Host Escape   : ENFORCED (Isolated Sandbox Required)");

    // Test a prohibited host escape attempt
    let host_probe = safety.authorize("TERMINAL_EXEC", "whoami", false);
    println!("    [Safety Gate Test] Host execution attempt: Verdict={:?}, Reason={}", host_probe.verdict, host_probe.reason);
    assert_eq!(host_probe.verdict, KernelVerdict::Deny);

    // Test a permitted sandbox execution
    let sandbox_probe = safety.authorize("TERMINAL_EXEC", "nmap -sV -p 80,443 target", true);
    println!("    [Safety Gate Test] Sandbox execution: Verdict={:?}", sandbox_probe.verdict);
    assert_eq!(sandbox_probe.verdict, KernelVerdict::Allow);

    // 2. Initialize World Model & Attack Graph
    println!("\n[2] Initializing World Model & Attack Graph...");
    let mut assets = AssetInventory::new();
    let web_asset = assets.register_asset(
        target_url,
        "web_application",
        Some(443),
        vec!["nginx".to_string(), "react".to_string(), "fastapi".to_string()],
    );
    assets.add_endpoint(&web_asset.asset_id, "/api/v1/auth/login");
    assets.add_endpoint(&web_asset.asset_id, "/api/v1/users/profile");
    println!("    Registered Asset: ID={}, Type={}, Stack={:?}", web_asset.asset_id, web_asset.asset_type, web_asset.technology_stack);

    let mut attack_graph = AttackGraph::new();
    attack_graph.add_node("node_anon", &web_asset.asset_id, "public_login", "anonymous", 1.0);
    attack_graph.add_node("node_user", &web_asset.asset_id, "user_session", "authenticated_user", 0.95);
    attack_graph.add_node("node_admin", &web_asset.asset_id, "admin_session", "tenant_admin", 0.90);
    attack_graph.add_node("node_rce", &web_asset.asset_id, "remote_code_exec", "root_shell", 0.85);

    attack_graph.add_transition("node_anon", "node_user", "Brute force / Credential stuffing", 0.80);
    attack_graph.add_transition("node_user", "node_admin", "IDOR on /api/v1/admin/roles", 0.90);
    attack_graph.add_transition("node_admin", "node_rce", "Template injection in admin export", 0.85);

    let chains = attack_graph.find_attack_chains("node_anon", "node_rce");
    println!("    Discovered Exploitation Chains: {} path(s)", chains.len());
    for (i, chain) in chains.iter().enumerate() {
        println!("      Chain #{}: Hops={}, Combined Confidence={:.4}, Steps={:?}", i + 1, chain.total_hops, chain.combined_confidence, chain.nodes);
    }

    // 3. Initialize Mission Kernel with 5D Budget Engine & FSM
    println!("\n[3] Initializing Mission Kernel & 5D Budget Engine...");
    let budget = MissionBudget {
        time_limit_seconds: 1800.0,
        max_actions: 50,
        max_experiments: 10,
        max_tokens: 200_000,
        max_risk_score: 8.0,
    };
    let mut mission = MissionKernel::new(target_url, "Full Epistemic Penetration Audit", tenant_id, Some(budget));
    println!("    Mission ID         : {}", mission.mission_id);
    println!("    Initial State      : {:?}", mission.state);

    // Validate Scope
    let scoped = mission.validate_scope(true, "Authorized by security team ROE");
    println!("    Scope Validation   : {} -> State={:?}", scoped, mission.state);

    // 4. Initialize Brain & Hypothesis Engine
    println!("\n[4] Initializing Epistemic Research Brain...");
    let brain = ResearchBrain::new(tenant_id);
    let mut hyp_engine = HypothesisEngine::new();
    let (h1, _c1) = hyp_engine.create_hypothesis_pair(
        "IDOR exists in /api/v1/users/{id} allowing unauthorized role escalation",
        Some("Role checks are enforced server-side using claims in verified JWT"),
        "IDOR/BrokenAccessControl",
        "/api/v1/users/profile",
        4.5,
    );
    println!("    Generated Primary Hypothesis : {}", h1);
    println!("    Generated Counter-Hypothesis : Mandatory Falsification Anchor Active");

    // 5. Brain Reasoning Cycle (Decoupled Epistemic Planning)
    mission.transition_to(MissionState::Planning);
    println!("\n[5] Brain Reasoning Cycle (Zero Tool Handles)...");
    let plan = brain.plan_next_step(&hyp_engine, false, mission.findings_count);
    println!("    Generated Plan ID    : {}", plan.plan_id);
    println!("    Specialist Directed  : {}", plan.specialist_type);
    println!("    Epistemic Rationale  : {}", plan.rationale);

    // 6. Multimodal Perception Fusion Simulation
    println!("\n[6] Multimodal Perception Fusion...");
    let sample_html = r#"
        <html>
            <head><title>Secure Enterprise Portal - Dashboard</title></head>
            <body>
                <input name="user_id" value="1042" />
                <button>Update Profile</button>
            </body>
        </html>
    "#;
    let screenshot_bytes = b"SIMULATED_SCREENSHOT_RAW_BUFFER";
    let perception = PerceptionFusion::fuse(
        "https://target-app.local/profile",
        "Dashboard",
        Some(screenshot_bytes),
        Some(sample_html),
    );
    println!("    Observed Page State  : {}", perception.page_state);
    println!("    Extracted Controls   : {} control(s)", perception.controls.len());
    println!("    Screenshot SHA-256   : {}", perception.screenshot_hash);

    // 7. Verification Lab (5-Step Hardened Gate)
    println!("\n[7] Hardened Verification Lab (Anti-Hallucination Gate)...");
    let baseline_obs = "HTTP/1.1 200 OK\nContent-Type: application/json\n\n{\"user_id\": 1042, \"role\": \"user\"}";
    let probe_obs = "HTTP/1.1 200 OK\nContent-Type: application/json\n\n{\"user_id\": 1, \"role\": \"superadmin\", \"secret_token\": \"adm_key_live_99\"}";
    let repro_obs = "HTTP/1.1 200 OK\nContent-Type: application/json\n\n{\"user_id\": 1, \"role\": \"superadmin\", \"secret_token\": \"adm_key_live_99\"}";
    let custody_hash = CustodyChain::compute_hash(probe_obs.as_bytes());

    let report = VerificationLab::verify_candidate(
        "finding-idor-001",
        "curl -H 'X-Override-User: 1' https://target-app.local/api/v1/users/profile",
        baseline_obs,
        probe_obs,
        repro_obs,
        Some("Privilege escalation from unprivileged tenant user to platform superadmin with API secret access"),
        &custody_hash,
    );

    println!("    Verification Result  : VERIFIED={}", report.verified);
    println!("    Custody Hash Match   : {}", report.custody_hash);
    if report.verified {
        mission.findings_count += 1;
        hyp_engine.record_evidence(&h1, true, "Observed superadmin data exfiltration with distinct behavioral delta", 0.4);
    }

    // 8. Priority Information-Gain Scheduler & Blackboard
    println!("\n[8] Priority Scheduler & Multi-Specialist Coordination...");
    let mut scheduler = InformationGainCostScheduler::new(4);
    let task_id = scheduler.enqueue(
        "Verify Admin Role Persistence",
        "auth",
        5.0,  // Info Gain
        4.0,  // Impact
        0.9,  // Confidence
        1.0,  // Cost
        2.0,  // Time
        1.0,  // Risk
    );
    println!("    Enqueued High-Gain Task: {}", task_id);
    let next_task = scheduler.pop_next().unwrap();
    println!("    Dispatched Highest Value Task: {} (score={})", next_task.name, next_task.priority_score);

    let blackboard = Blackboard::new();
    blackboard.post("verified_finding", "finding-idor-001");
    println!("    Blackboard Shared State: verified_finding = {:?}", blackboard.get("verified_finding"));

    // 8.5. Subordinated Specialist & 4-Tier Memory
    println!("\n[8.5] Subordinated Specialist Execution & Procedural Lessons...");
    let spec_result = SpecialistWorker::simulate_probe(
        SpecialistType::Auth,
        "exp-idor-001",
        &h1,
        baseline_obs,
        probe_obs,
    );
    println!("    Specialist Probe     : Status={}, Divergence Detected={}", spec_result.status, spec_result.behavioral_difference_detected);

    let mut episodic = EpisodicMemory::new();
    episodic.record("SECURITY_TOOL", "/api/v1/users/profile", probe_obs, true);
    println!("    Episodic Memory Recorded: Total Episodes={}", episodic.count());

    let mut lessons = LessonsLedger::new();
    lessons.record_lesson(
        LessonType::Success,
        "fastapi_jwt",
        "header_override",
        "Override X-Override-User triggers unverified role mapping",
        "Prioritize header injection on secondary proxy routes",
    );
    let avoid = lessons.query_avoidance("nginx_waf");
    println!("    Lessons Avoidance Cache : {} negative heuristic(s) for nginx_waf", avoid.len());

    // 9. Guarded Evolution Pipeline
    println!("\n[9] Guarded Evolution Pipeline...");
    let mut evolution = EvolutionPipeline::new();
    let (prop_safe, safe_accepted) = evolution.submit_proposal("src/specialists/auth.rs", "Add JWT key confusion probe");
    println!("    Tool Evolution Proposal (Auth Specialist): Accepted={}, Stage={:?}", safe_accepted, prop_safe.stage);

    let (prop_malicious, evil_accepted) = evolution.submit_proposal("src/safety/kernel.rs", "Bypass egress filter");
    println!("    Malicious Evolution Attempt (Safety Kernel): Accepted={}, Stage={:?}", evil_accepted, prop_malicious.stage);
    assert!(!evil_accepted);

    // 10. Finalize Mission
    mission.transition_to(MissionState::Verifying);
    mission.transition_to(MissionState::Reporting);
    mission.transition_to(MissionState::Completed);
    println!("\n[10] Mission Successfully Completed!");
    println!("     Final State: {:?}", mission.state);
    println!("     Verified Findings Count: {}", mission.findings_count);
    println!("================================================================================");
    println!("  SONIC Rust Kernel Daemon Initialized & All Invariants Intact!                 ");
    println!("================================================================================");
}
