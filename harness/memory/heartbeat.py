"""MemoryHeartbeatTask — periodic LLM-driven memory extraction from accumulated session summaries.

Runs via HeartbeatScheduler (default every 30 min). Scans recent PG session summaries
in batch and extracts cross-session preferences/facts to update L1 and L2 memory.

This replaces per-session LLM extraction: instead of running a Mini Model call on
every single conversation, we batch-process summaries periodically. Most conversations
produce no new facts — batching avoids wasted LLM calls on routine sessions.
"""

import structlog

from harness.memory.manager import MemoryManager
from harness.memory.types import MemoryFile, MidTermSummaryType
from runtime.config import AgentConfig

logger = structlog.get_logger()


class MemoryHeartbeatTask:
    """Periodic task: scan recent PG summaries, extract prefs/facts, update L1/L2.

    Uses the existing MemoryEvolution (Mini Model) to extract structured info
    from accumulated session summaries.
    """

    def __init__(self, memory_manager: MemoryManager, config: AgentConfig):
        self.memory_manager = memory_manager
        self.config = config
        self._max_summaries = getattr(config, "memory_heartbeat_summaries", 10)

    async def run(self) -> None:
        """Run one cycle of memory extraction for all recently active users.

        Called by HeartbeatScheduler every heartbeat_interval (default 30 min).
        """
        if not self.memory_manager.mid_term:
            return  # PG not connected — nothing to do

        # Get recently active users from PG mid-term
        try:
            user_ids = await self.memory_manager.mid_term.list_recent_users(hours=1)
        except Exception as e:
            logger.warning("memory_heartbeat_list_users_failed", error=str(e))
            return

        if not user_ids:
            return

        logger.info("memory_heartbeat_start", user_count=len(user_ids))

        for user_id in user_ids:
            try:
                await self._process_user(user_id)
            except Exception as e:
                logger.warning("memory_heartbeat_user_failed", user_id=user_id, error=str(e))

        logger.info("memory_heartbeat_complete", user_count=len(user_ids))

    async def _process_user(self, user_id: str) -> None:
        """Extract and persist memory for one user from recent summaries."""
        if not self.memory_manager.evolution:
            return

        summaries = await self.memory_manager.mid_term.search_recent(
            user_id, top_k=self._max_summaries, days=1,
        )

        if not summaries or len(summaries) < 2:
            # Not enough data to extract meaningful patterns
            return

        combined = "\n---\n".join(summaries)

        try:
            result = self.memory_manager.evolution.extract(combined)
        except Exception as e:
            logger.warning("memory_heartbeat_extract_failed", user_id=user_id, error=str(e))
            return

        preferences = result.get("preferences", [])
        facts = result.get("facts", [])

        if not preferences and not facts:
            return

        # L1: append to files
        if preferences:
            pref_text = "\n".join(f"- {p}" for p in preferences)
            self.memory_manager.append_memory(
                user_id, MemoryFile.USER, f"\n## Extracted Preferences (heartbeat)\n{pref_text}",
            )

        if facts:
            fact_text = "\n".join(f"- {f}" for f in facts)
            self.memory_manager.append_memory(
                user_id, MemoryFile.MEMORY, f"\n## Extracted Facts (heartbeat)\n{fact_text}",
            )

            # L2: write facts to PG for semantic search
            for fact in facts:
                await self.memory_manager.write_mid_term(
                    user_id,
                    content=fact,
                    summary_type=MidTermSummaryType.FACT,
                    metadata={"source": "heartbeat"},
                )

        logger.info("memory_heartbeat_user_processed",
            user_id=user_id, summary_count=len(summaries),
            pref_count=len(preferences), fact_count=len(facts))

        # Evolution check: scan accumulated summaries for Skill gaps
        await self._check_evolution(user_id, combined)

    async def _check_evolution(self, user_id: str, combined_summaries: str) -> None:
        """Check if accumulated session summaries suggest a new Skill is needed."""
        if not getattr(self.config, "auto_evolve_enabled", False):
            return

        try:
            from harness.evolution.auto_evolve import AutoEvolver
            from harness.multi_agent.subagent import SubAgentRunner
            from harness.skill.manager import SkillManager
            from harness.security.approval import ApprovalChecker
            from harness.evolution.three_agent import ThreeAgentVerifier
            from runtime.models import create_mini_model

            mini = create_mini_model(self.config)
            sm = SkillManager(self.config)
            ac = ApprovalChecker(mini_model=mini)
            subagent_runner = SubAgentRunner(self.config, self.memory_manager, sm, ac)
            verifier = ThreeAgentVerifier(subagent_runner, max_rounds=self.config.three_agent_max_rounds)
            evolver = AutoEvolver(subagent_runner, verifier, sm, self.config)

            check_result = evolver.check_evolution_need(combined_summaries, user_id)
            if check_result.needs_evolution:
                logger.info("auto_evolution_triggered",
                    user_id=user_id, skill_name=check_result.suggested_skill_name)
        except Exception as e:
            logger.warning("memory_heartbeat_evolution_check_failed",
                user_id=user_id, error=str(e))
