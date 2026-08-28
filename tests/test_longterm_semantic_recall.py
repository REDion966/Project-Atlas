"""Track C — Deterministic semantic recall tests (SemanticRecallEngine)."""

from datetime import datetime

from atlas.longterm.episode_repository import EpisodicRepository
from atlas.longterm.models import (
    Episode,
    EpisodeKind,
    Procedure,
    ProcedureKind,
    ProcedureStep,
)
from atlas.longterm.procedure_repository import ProceduralRepository
from atlas.longterm.semantic_recall import SemanticRecallEngine


def _episode(
    episode_id: str,
    *,
    title: str = "",
    summary: str = "",
    outcome: str = "",
    tags: tuple[str, ...] = (),
    kind: EpisodeKind = EpisodeKind.PIPELINE,
    importance: float = 0.5,
) -> Episode:
    return Episode(
        episode_id=episode_id,
        kind=kind,
        title=title,
        summary=summary,
        outcome=outcome,
        started_at=datetime(2026, 1, 1, 12, 0, 0),
        ended_at=datetime(2026, 1, 1, 12, 0, 5),
        importance=importance,
        tags=tuple(tags),
    )


def _procedure(
    procedure_id: str,
    *,
    name: str = "",
    description: str = "",
    category: str = "utility",
    tags: tuple[str, ...] = (),
    steps: tuple[ProcedureStep, ...] = (),
    confidence: float = 0.9,
) -> Procedure:
    return Procedure(
        procedure_id=procedure_id,
        name=name,
        description=description,
        kind=ProcedureKind.DISTILLED,
        category=category,
        steps=tuple(steps),
        success_count=1,
        failure_count=0,
        confidence=confidence,
        created_at=datetime(2026, 1, 1, 12, 0, 0),
        last_used_at=datetime(2026, 1, 1, 12, 0, 5),
        tags=tuple(tags),
    )


def _engine(
    episodes: tuple[Episode, ...] = (),
    procedures: tuple[Procedure, ...] = (),
) -> SemanticRecallEngine:
    episode_repo = EpisodicRepository()
    for episode in episodes:
        episode_repo.store_episode(episode)
    procedure_repo = ProceduralRepository()
    for procedure in procedures:
        procedure_repo.store_procedure(procedure)
    return SemanticRecallEngine(
        episodes=episode_repo, procedures=procedure_repo
    )


class TestQueryHandling:
    def test_empty_query_returns_empty(self):
        engine = _engine(episodes=(_episode("ep1", tags=("alpha",)),))
        assert engine.recall("") == []

    def test_whitespace_query_returns_empty(self):
        engine = _engine(episodes=(_episode("ep1", tags=("alpha",)),))
        assert engine.recall("   ") == []

    def test_no_match_returns_empty(self):
        engine = _engine(episodes=(_episode("ep1", tags=("alpha",)),))
        assert engine.recall("unrelated topic") == []

    def test_short_tokens_ignored(self):
        engine = _engine(
            episodes=(
                _episode("ep-x", tags=("x",)),
                _episode("ep-alpha", tags=("alpha",)),
            )
        )
        results = engine.recall("x alpha")
        assert [r["item"]["episode_id"] for r in results] == ["ep-alpha"]
        assert results[0]["matched_tokens"] == ("alpha",)

    def test_zero_match_items_excluded(self):
        engine = _engine(
            episodes=(
                _episode("ep1", tags=("alpha",)),
                _episode("ep2", tags=("beta",)),
            )
        )
        results = engine.recall("alpha")
        assert [r["item"]["episode_id"] for r in results] == ["ep1"]


class TestScoring:
    def test_tag_match_beats_text_match(self):
        engine = _engine(
            episodes=(
                _episode("ep-text", summary="alpha deployment notes"),
                _episode("ep-tag", tags=("alpha",)),
            )
        )
        results = engine.recall("alpha")
        assert [r["item"]["episode_id"] for r in results] == [
            "ep-tag",
            "ep-text",
        ]
        assert results[0]["score"] == 3.0
        assert results[1]["score"] == 1.0

    def test_field_weights_applied(self):
        # tags (3.0) + title (2.0) on one item; summary (1.0) on the other.
        engine = _engine(
            episodes=(
                _episode("ep-multi", title="alpha pipeline", tags=("alpha",)),
                _episode("ep-summary", summary="alpha"),
            )
        )
        results = engine.recall("alpha")
        scores = {
            r["item"]["episode_id"]: r["score"] for r in results
        }
        assert scores["ep-multi"] == 5.0
        assert scores["ep-summary"] == 1.0

    def test_tool_weight(self):
        engine = _engine(
            procedures=(
                _procedure(
                    "proc1",
                    steps=(ProcedureStep(step_id="s1", tool_name="grep"),),
                ),
            )
        )
        results = engine.recall("grep")
        assert results[0]["score"] == 2.0
        assert results[0]["matched_fields"] == ("tool",)

    def test_category_and_outcome_weights(self):
        engine = _engine(
            episodes=(_episode("ep1", outcome="success"),),
            procedures=(_procedure("proc1", category="research"),),
        )
        results = engine.recall("success research")
        by_id = {r["item"].get("episode_id") or r["item"].get("procedure_id"): r for r in results}
        assert by_id["ep1"]["score"] == 1.5 * 0.5
        assert by_id["proc1"]["score"] == 1.5 * 0.5

    def test_coverage_multiplier(self):
        engine = _engine(
            episodes=(
                _episode("ep-half", tags=("alpha",)),
                _episode("ep-full", tags=("alpha", "beta")),
            )
        )
        results = engine.recall("alpha beta")
        scores = {
            r["item"]["episode_id"]: r["score"] for r in results
        }
        assert scores["ep-half"] == 1.5
        assert scores["ep-full"] == 6.0
        assert [r["item"]["episode_id"] for r in results] == [
            "ep-full",
            "ep-half",
        ]

    def test_scores_rounded_to_four_decimals(self):
        engine = _engine(episodes=(_episode("ep1", tags=("alpha",)),))
        results = engine.recall("alpha beta gamma")
        assert results[0]["score"] == round(3.0 / 3, 4)
        assert results[0]["score"] == 1.0


class TestOrdering:
    def test_deterministic_tie_break_by_id(self):
        engine = _engine(
            episodes=(
                _episode("ep-b", tags=("zeta",)),
                _episode("ep-a", tags=("zeta",)),
            )
        )
        results = engine.recall("zeta")
        assert [r["item"]["episode_id"] for r in results] == ["ep-a", "ep-b"]

    def test_episode_before_procedure_on_tie(self):
        engine = _engine(
            episodes=(_episode("ep1", tags=("zeta",)),),
            procedures=(_procedure("proc1", tags=("zeta",)),),
        )
        results = engine.recall("zeta")
        assert [r["type"] for r in results] == ["episode", "procedure"]

    def test_deterministic_across_separate_instances(self):
        episodes = (
            _episode("ep1", tags=("alpha",), title="alpha run"),
            _episode("ep2", summary="alpha beta"),
        )
        procedures = (
            _procedure("proc1", tags=("alpha",), category="research"),
        )
        first = _engine(episodes, procedures).recall("alpha beta")
        second = _engine(episodes, procedures).recall("alpha beta")
        assert first == second
        assert first != []


class TestBounds:
    def test_limit_truncates_results(self):
        episodes = tuple(
            _episode(f"ep-{i:03d}", tags=("bulk",)) for i in range(5)
        )
        engine = _engine(episodes=episodes)
        results = engine.recall("bulk", limit=3)
        assert len(results) == 3

    def test_hard_cap_at_500(self):
        episodes = tuple(
            _episode(f"ep-{i:03d}", tags=("bulk",)) for i in range(505)
        )
        engine = _engine(episodes=episodes)
        assert len(engine.recall("bulk", limit=10_000)) == 500
        assert len(engine.recall("bulk")) == 500


class TestResultShape:
    def test_explanation_fields_present(self):
        engine = _engine(episodes=(_episode("ep1", tags=("alpha",)),))
        results = engine.recall("alpha")
        assert set(results[0].keys()) == {
            "type",
            "score",
            "matched_tokens",
            "matched_fields",
            "item",
        }
        assert results[0]["type"] == "episode"
        assert results[0]["matched_tokens"] == ("alpha",)
        assert results[0]["matched_fields"] == ("tags",)

    def test_episode_provenance_retained(self):
        episode = _episode("ep1", tags=("alpha",), title="alpha run")
        engine = _engine(episodes=(episode,))
        results = engine.recall("alpha")
        assert results[0]["item"] == episode.to_dict()

    def test_procedure_provenance_retained(self):
        procedure = _procedure(
            "proc1",
            tags=("alpha",),
            steps=(ProcedureStep(step_id="s1", tool_name="grep"),),
        )
        engine = _engine(procedures=(procedure,))
        results = engine.recall("alpha")
        assert results[0]["item"] == procedure.to_dict()
        assert results[0]["type"] == "procedure"

    def test_both_types_returned(self):
        engine = _engine(
            episodes=(_episode("ep1", tags=("deploy",)),),
            procedures=(_procedure("proc1", tags=("deploy",)),),
        )
        results = engine.recall("deploy")
        assert {r["type"] for r in results} == {"episode", "procedure"}
        assert len(results) == 2


class TestPurity:
    def test_repositories_not_mutated(self):
        episode_repo = EpisodicRepository()
        procedure_repo = ProceduralRepository()
        episode_repo.store_episode(_episode("ep1", tags=("alpha",)))
        procedure_repo.store_procedure(_procedure("proc1", tags=("alpha",)))
        engine = SemanticRecallEngine(
            episodes=episode_repo, procedures=procedure_repo
        )

        engine.recall("alpha")
        engine.recall("nothing matches this")

        assert episode_repo.episode_count == 1
        assert procedure_repo.procedure_count == 1
        assert episode_repo.get_episode("ep1") is not None
        assert procedure_repo.get_procedure("proc1") is not None
