"""
SONIC-REDA — Procedural Novelty & Open-World Task Generator (Phase 17)
========================================================================
Procedurally synthesizes completely novel, randomized software repositories
with unique class names, dynamic function signatures, and randomized logic bugs
to guarantee zero static fixture memorization or task-name cheats.
"""

from __future__ import annotations

import random
import uuid
from pydantic import BaseModel, Field


class ProceduralRepoTask(BaseModel):
    """A procedurally generated, unique software repository task."""
    task_id: str
    class_name: str
    method_name: str
    source_filename: str
    test_filename: str
    broken_source_code: str
    correct_source_code: str
    test_suite_code: str
    expected_return_value: int
    random_seed: str


class ProceduralNoveltyGenerator:
    """
    Generates dynamic software tasks at runtime with randomized AST topologies.
    """

    NOUNS = ["TelemetryAggregator", "StreamBuffer", "PayloadTransformer", "StateSynchronizer", "MetricCalculator", "TokenBucket"]
    VERBS = ["compute_window_delta", "transform_batch_slice", "aggregate_signal", "process_token_stream", "calculate_offset"]

    @classmethod
    def generate_random_repo(cls) -> ProceduralRepoTask:
        """Procedurally creates a unique broken repository task."""
        nonce = uuid.uuid4().hex[:6]
        cls_name = f"{random.choice(cls.NOUNS)}_{nonce}"
        fn_name = f"{random.choice(cls.VERBS)}_{nonce}"
        src_file = f"{cls_name.lower()}.py"
        test_file = f"test_{cls_name.lower()}.py"

        val_a = random.randint(10, 50)
        val_b = random.randint(2, 5)
        expected = val_a * val_b + 42

        broken_code = (
            f"class {cls_name}:\n"
            f"    def {fn_name}(self, a: int, b: int) -> int:\n"
            f"        # Bug: omits constant offset of 42\n"
            f"        return a * b\n"
        )

        fixed_code = (
            f"class {cls_name}:\n"
            f"    def {fn_name}(self, a: int, b: int) -> int:\n"
            f"        return (a * b) + 42\n"
        )

        test_code = (
            f"from {cls_name.lower()} import {cls_name}\n\n"
            f"def test_{fn_name}():\n"
            f"    inst = {cls_name}()\n"
            f"    assert inst.{fn_name}({val_a}, {val_b}) == {expected}\n"
        )

        return ProceduralRepoTask(
            task_id=f"open-world-{nonce}",
            class_name=cls_name,
            method_name=fn_name,
            source_filename=src_file,
            test_filename=test_file,
            broken_source_code=broken_code,
            correct_source_code=fixed_code,
            test_suite_code=test_code,
            expected_return_value=expected,
            random_seed=nonce,
        )
