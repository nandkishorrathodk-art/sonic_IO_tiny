"""
Tests for Phase 12: Autonomous Researcher Data Models.
"""

import pytest
from sonic.researcher.models import (
    ResearchQuestion,
    ResearchQuestionStatus,
    ResearcherHypothesis,
    ResearcherHypothesisStatus,
    HypothesisPortfolio,
    InvestigationTrack,
    TrackStatus,
    ResearchLead,
    ResearchLeadStatus,
)


def test_research_question_creation_and_state():
    rq = ResearchQuestion(
        tenant_id="tenant-1",
        engagement_id="eng-1",
        question="Is GraphQL introspection enabled?",
        importance=0.9,
        uncertainty=0.85,
    )
    assert rq.status == ResearchQuestionStatus.OPEN
    assert rq.importance == 0.9
    assert rq.uncertainty == 0.85


def test_hypothesis_portfolio_management():
    portfolio = HypothesisPortfolio()
    h1 = ResearcherHypothesis(
        tenant_id="tenant-1",
        engagement_id="eng-1",
        statement="Introspection is enabled on /graphql",
        confidence=0.7,
        expected_value=0.8,
        status=ResearcherHypothesisStatus.ACTIVE,
    )
    h2 = ResearcherHypothesis(
        tenant_id="tenant-1",
        engagement_id="eng-1",
        statement="GraphQL schema is hidden behind custom header",
        confidence=0.3,
        expected_value=0.4,
        status=ResearcherHypothesisStatus.PROPOSED,
    )
    portfolio.add_hypothesis(h1)
    portfolio.add_hypothesis(h2)

    assert len(portfolio.get_active_hypotheses()) == 2
    ranked = portfolio.rank_hypotheses()
    assert ranked[0].id == h1.id
