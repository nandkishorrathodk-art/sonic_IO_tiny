"""
SONIC-REDA — Distributed Worker Engine (Worker Plane)
========================================================
Consumes jobs from Redis queue, provisions/attaches to ComputeProvider sandboxes,
and executes ordinary browser or agent tasks.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sonic.browser.container_runtime import BrowserAction, ContainerizedBrowser
from sonic.logger import get_logger
from sonic.queue.job_queue import RedisJobQueue, get_job_queue
from sonic.queue.models import Job, JobEvent, JobStatus, JobType
from sonic.sandbox.factory import get_compute_provider
from sonic.sandbox.provider import ComputeProvider

logger = get_logger(__name__)


class SonicWorker:
    """
    Asynchronous worker processing jobs from the queue via ComputeProvider sandboxes.
    """

    def __init__(
        self,
        queue: RedisJobQueue | None = None,
        provider: ComputeProvider | None = None,
        worker_id: str = "worker-01",
    ):
        self.queue = queue or get_job_queue()
        self.provider = provider or get_compute_provider()
        self.worker_id = worker_id
        self._running = False
        self.browser = ContainerizedBrowser(self.provider)

    async def execute_job(self, job: Job) -> Job:
        """Execute a single job and update its lifecycle state."""
        from sonic.safety.runtime_stop import get_runtime_stop_state
        stop_state = get_runtime_stop_state()
        from sonic.safety.scope import get_scope_checker
        if not get_scope_checker().kill_switch_enabled or stop_state.is_stopped(job.tenant_id):
            job.status = JobStatus.CANCELLED
            job.error_message = (
                "safety kill switch is disabled"
                if not get_scope_checker().kill_switch_enabled
                else f"runtime kill switch asserted: {stop_state.reason(job.tenant_id)}"
            )
            job.completed_at = datetime.now(UTC).isoformat()
            await self.queue.update_job(job)
            return job
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(UTC).isoformat()
        await self.queue.update_job(job)

        await self.queue.emit_event(JobEvent(
            tenant_id=job.tenant_id,
            engagement_id=job.engagement_id,
            job_id=job.id,
            event_type="JobStarted",
            actor=self.worker_id,
            details={"workspace_id": job.workspace_id, "type": job.job_type.value},
        ))

        try:
            if job.job_type == JobType.BROWSER_SESSION:
                result_data = await self._run_browser_job(job)
            elif job.job_type == JobType.AGENT_STEP:
                result_data = await self._run_agent_step(job)
            else:
                result_data = {"status": "unsupported_job_type"}

            job.status = JobStatus.SUCCEEDED
            job.result = result_data
            job.completed_at = datetime.now(UTC).isoformat()

            await self.queue.emit_event(JobEvent(
                tenant_id=job.tenant_id,
                engagement_id=job.engagement_id,
                job_id=job.id,
                event_type="JobSucceeded",
                actor=self.worker_id,
            ))

        except Exception as e:
            logger.error("job_execution_failed", job_id=job.id, error=str(e))
            job.error_message = str(e)
            if job.retry_count < job.max_retries:
                job.retry_count += 1
                job.status = JobStatus.QUEUED
                logger.info("job_retrying", job_id=job.id, retry=job.retry_count)
            else:
                job.status = JobStatus.FAILED
                job.completed_at = datetime.now(UTC).isoformat()

            await self.queue.emit_event(JobEvent(
                tenant_id=job.tenant_id,
                engagement_id=job.engagement_id,
                job_id=job.id,
                event_type="JobFailed",
                actor=self.worker_id,
                details={"error": str(e), "retries": job.retry_count},
            ))

        await self.queue.update_job(job)
        return job

    async def _run_browser_job(self, job: Job) -> dict:
        raw_actions = job.payload.get("actions", [])
        actions = [
            BrowserAction(
                action=a.get("action", "navigate"),
                url=a.get("url"),
                selector=a.get("selector"),
                text=a.get("text"),
                script=a.get("script"),
                timeout_ms=a.get("timeout_ms", 15000),
            )
            for a in raw_actions
        ]

        res = await self.browser.execute_browser_script(
            workspace_id=job.workspace_id,
            actions=actions,
            timeout_seconds=job.timeout_seconds,
        )

        return {
            "url": res.current_url,
            "title": res.title,
            "status_code": res.status_code,
            "dom_length": len(res.dom_content),
            "has_screenshot": bool(res.screenshot_base64),
            "logs_count": len(res.console_logs),
            "success": res.success,
            "error": res.error_message,
        }

    async def _run_agent_step(self, job: Job) -> dict:
        """
        Execute a specialist agent step dispatched by the Director.

        Propagates tenant_id, engagement_id, task_id, agent_id,
        workspace_id, and execution_id throughout the chain.

        Returns structured AgentOutput-compatible dict.
        """
        agent_type = job.payload.get("agent_type", "")
        task_payload = job.payload.get("task_payload", {})
        target = job.payload.get("target", task_payload.get("target", ""))

        if not agent_type:
            raise ValueError("AGENT_STEP job missing 'agent_type' in payload")

        # Import agents lazily to avoid circular imports
        from sonic.agents.codefix import CodeFixAgent
        from sonic.agents.hypothesis import HypothesisGenerator
        from sonic.agents.static_reasoning import StaticReasoningAgent

        agent_classes = {
            "static": StaticReasoningAgent,
            "hypothesis": HypothesisGenerator,
            "codefix": CodeFixAgent,
        }

        agent_cls = agent_classes.get(agent_type)
        if not agent_cls:
            # "browser" agent_type is handled by a dedicated BrowserAgent job
            # path, not the generic BaseAgent dispatcher.
            if agent_type == "browser":
                raise ValueError(
                    "'browser' agent_type must be dispatched via a BROWSER job, "
                    "not an AGENT_STEP job"
                )
            raise ValueError(f"Unknown agent_type '{agent_type}' for AGENT_STEP")

        # Create agent with shared resources
        # Note: ModelRouter and GraphMemory are injected at worker init or resolved
        from sonic.llm.router import ModelRouter
        from sonic.memory.router import get_smart_memory
        from sonic.safety.scope import ScopeChecker

        memory = await get_smart_memory()
        router = ModelRouter()  # Uses globally configured providers
        scope_checker = ScopeChecker()

        agent = agent_cls(
            model_router=router,
            graph_memory=memory,
            scope_checker=scope_checker,
        )

        # Build task dict with full context propagation
        agent_task = {
            **task_payload,
            "target": target,
            "engagement_id": job.engagement_id,
            "tenant_id": job.tenant_id,
            "task_id": job.task_id,
            "execution_id": job.execution_id,
            "workspace_id": job.workspace_id,
        }

        logger.info(
            "agent_step_executing",
            agent_type=agent_type,
            task_id=job.task_id,
            engagement_id=job.engagement_id,
            tenant_id=job.tenant_id,
        )

        # Execute the agent
        result = await agent.run(agent_task)

        # Wrap result in AgentOutput-compatible structure
        return {
            "agent_type": agent_type,
            "agent_id": agent.agent_id,
            "task_id": job.task_id,
            "execution_id": job.execution_id,
            "observations": result.get("assets", []) if agent_type == "recon" else [],
            "facts": [],
            "hypotheses": result.get("hypotheses", []),
            "evidence_refs": [],
            "findings": result.get("findings", []),
            "failed_attempts": [],
            "recommended_next_actions": [],
            "metrics": {
                "actions_count": len(agent.action_log),
                "status": agent.status,
            },
            "raw_result": result,
        }

    async def run_once(self) -> Job | None:
        """Poll and execute one job from queue."""
        job = await self.queue.dequeue_job(timeout_seconds=0.5)
        if job:
            return await self.execute_job(job)
        return None
