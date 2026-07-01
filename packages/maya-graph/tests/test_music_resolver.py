from maya_graph.music_resolver import MusicCandidate, MusicGraphResolver, MusicResolverConfig


def _candidate(label: str, qid: str | None = None, **attrs) -> MusicCandidate:
    return MusicCandidate(node_id="n1", node_type="canonical_work", label=label, qid=qid, attrs=attrs)


def test_exact_label_match_scores_high():
    resolver = MusicGraphResolver()
    score, signals = resolver.score("Despacito", _candidate("Despacito"))
    from maya_graph.music_resolver import MusicMatchSignalKind

    assert signals[MusicMatchSignalKind.LABEL_TEXT_SIMILARITY] == 1.0
    assert score > 0.5


def test_unrelated_label_scores_low():
    resolver = MusicGraphResolver()
    score, _ = resolver.score("Despacito", _candidate("Never Gonna Give You Up"))
    assert score < 0.3


def test_qid_exact_boosts_score():
    resolver = MusicGraphResolver()
    from maya_graph.music_resolver import MusicMatchSignalKind

    score, signals = resolver.score("Q130464775", _candidate("Despacito", qid="Q130464775"))
    assert signals[MusicMatchSignalKind.QID_EXACT] == 1.0
    no_qid_score, _ = resolver.score("Q130464775", _candidate("Despacito", qid="Q99999999"))
    assert score > no_qid_score


def test_decide_thresholds():
    resolver = MusicGraphResolver(MusicResolverConfig(auto_play_threshold=0.8, suggest_threshold=0.5))
    assert resolver.decide(0.9) == "use_graph"
    assert resolver.decide(0.6) == "weak_hit"
    assert resolver.decide(0.2) == "fallback_live"


def test_rank_orders_by_score_descending():
    resolver = MusicGraphResolver()
    candidates = [_candidate("Africa"), _candidate("Despacito"), _candidate("Despacito Remix")]
    ranked = resolver.rank("Despacito", candidates)
    assert ranked[0][0].label in ("Despacito", "Despacito Remix")
    assert ranked[0][1] >= ranked[-1][1]


def test_stale_recording_penalized():
    resolver = MusicGraphResolver()
    fresh_score, _ = resolver.score("Despacito", _candidate("Despacito", stale=False))
    stale_score, _ = resolver.score("Despacito", _candidate("Despacito", stale=True))
    assert fresh_score >= stale_score
