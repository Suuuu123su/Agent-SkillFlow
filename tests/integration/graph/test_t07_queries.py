from pathlib import Path

from skillflow.graph.models import BoundaryDepth, SecurityPath
from skillflow.graph.security import SecurityGraph
from skillflow.store.sqlite_store import SqliteEventStore
from tests.integration.graph.golden_fixture import GoldenGraphIds, build_golden_store


def load_graph(ids: GoldenGraphIds) -> SecurityGraph:
    with SqliteEventStore(ids.database_path) as store:
        return SecurityGraph.from_store(store, ids.run_id)


def golden_effect_path(paths: tuple[SecurityPath, ...], ids: GoldenGraphIds) -> SecurityPath:
    return next(
        path for path in paths if ids.skill_b_id in path.skill_ids and ids.tool_id in path.tool_ids
    )


def test_find_paths_recovers_complete_cross_session_golden_chain(tmp_path: Path) -> None:
    # Given: Skill A→Memory→Session 2→Skill B→Tool→Effect 的 Golden Store
    ids = build_golden_store(tmp_path)
    graph = load_graph(ids)

    # When: 从原始 Skill 查询最终 Effect
    path = golden_effect_path(graph.find_paths(ids.skill_a_id, ids.effect_id), ids)

    # Then: 主体、会话、边界和全部因果 Event 均可审计
    assert path.skill_ids == (ids.skill_a_id, ids.skill_b_id)
    assert path.tool_ids == (ids.tool_id,)
    assert path.cross_session_count == 1
    assert path.boundary_depth == BoundaryDepth(
        context=1,
        memory=2,
        session=1,
        skill=3,
        tool=2,
        total=9,
    )
    assert set(ids.causal_event_ids) <= set(path.evidence_event_ids)


def test_find_ancestors_returns_original_skill_for_context_value(tmp_path: Path) -> None:
    ids = build_golden_store(tmp_path)
    graph = load_graph(ids)

    paths = graph.find_ancestors(ids.context_id)

    assert any(ids.skill_a_id in path.skill_ids for path in paths)


def test_find_untrusted_paths_uses_artifact_trust_not_oracle_labels(tmp_path: Path) -> None:
    ids = build_golden_store(tmp_path)
    graph = load_graph(ids)

    paths = graph.find_untrusted_paths(ids.effect_id)

    assert any(path.nodes[0].node_id == ids.skill_a_output_id for path in paths)


def test_find_authorization_path_links_grant_decision_and_effect(tmp_path: Path) -> None:
    ids = build_golden_store(tmp_path)
    graph = load_graph(ids)

    paths = graph.find_authorization_path(ids.effect_id)

    assert any(
        ids.grant_id in path.grant_ids and ids.grant_event_id in path.evidence_event_ids
        for path in paths
    )


def test_find_revoked_ancestors_applies_event_time_semantics(tmp_path: Path) -> None:
    ids = build_golden_store(tmp_path)
    graph = load_graph(ids)

    paths = graph.find_revoked_ancestors(ids.effect_id)

    assert any(
        ids.skill_a_id in path.revoked_origin_ids
        and ids.revoke_event_id in path.revocation_event_ids
        for path in paths
    )


def test_find_cross_session_paths_counts_one_session_transition(tmp_path: Path) -> None:
    ids = build_golden_store(tmp_path)
    graph = load_graph(ids)

    paths = graph.find_cross_session_paths(ids.run_id)

    assert any(
        path.nodes[0].node_id == ids.skill_a_id and path.cross_session_count == 1 for path in paths
    )


def test_find_skill_to_effect_paths_reports_final_tool(tmp_path: Path) -> None:
    ids = build_golden_store(tmp_path)
    graph = load_graph(ids)

    paths = graph.find_skill_to_effect_paths(ids.skill_b_id)

    assert any(
        ids.tool_id in path.tool_ids and path.nodes[-1].node_id == ids.effect_id for path in paths
    )


def test_path_search_uses_visited_set_when_principal_cycle_exists(tmp_path: Path) -> None:
    ids = build_golden_store(tmp_path, include_cycle=True)
    graph = load_graph(ids)

    paths = graph.find_skill_to_effect_paths(ids.skill_a_id)

    assert paths
    assert all(len(path.nodes) == len(set(path.node_refs)) for path in paths)


def test_path_search_respects_explicit_max_depth(tmp_path: Path) -> None:
    ids = build_golden_store(tmp_path)
    graph = load_graph(ids)

    paths = graph.find_paths(ids.skill_a_id, ids.effect_id, max_depth=2)

    assert paths == ()
