"""Music play resolve contracts — shared by Homepage and Discord."""

from __future__ import annotations

from typing import Literal, Optional

from maya_contracts.common import StrictModel


class PlayResolveRequest(StrictModel):
    """Free-text play query from a launcher (Homepage `/play`, Discord `/play`)."""

    query: str
    zone: str = "default"


MatchedVia = Literal[
    "demo_catalog",
    "exact",
    "fuzzy",
    "crate",
    "ontology",
    "url",
    "wikidata",
    "ytdlp_search",
    # Resolved via the canonical_work/recording layer on the ontology graph
    # (packages/maya-graph music_lookup_tool.py). Distinct from "ontology",
    # which is reserved for the artist/track/genre display graph.
    "graph",
]


class VideoRef(StrictModel):
    """A candidate playable video, typically harvested from a Discogs master.

    The RadioPlayer cycles through these in order, using the YouTube IFrame
    API ``onError`` to skip embed-disabled videos before falling back to
    ``watch_url``.
    """

    youtube_id: str
    title: Optional[str] = None
    duration_seconds: Optional[float] = None
    embed_url: str
    watch_url: str
    source: str = "discogs"


class DiscogsRef(StrictModel):
    """Pointer back into the Discogs property graph for a resolved track."""

    master_id: Optional[int] = None
    release_id: Optional[int] = None
    url: Optional[str] = None
    year: Optional[int] = None


class TrackInfo(StrictModel):
    """A resolved playable track. Public-safe metadata only."""

    track_id: str
    title: str
    artist: str
    album: Optional[str] = None
    duration_seconds: Optional[float] = None
    preview_url: Optional[str] = None
    artwork_url: Optional[str] = None
    # Optional embeddable stream (YouTube embed URL, public CC stream, etc.).
    # The Homepage RadioPlayer prefers `stream_url` over `preview_url` when set
    # and renders an <iframe> for YouTube hosts.
    stream_url: Optional[str] = None
    # Optional canonical "open in source" URL. Always populated for YouTube
    # tracks so the UI can fall back to an external link when the uploader
    # has disabled in-player embedding (YouTube IFrame API error 150 / 101).
    watch_url: Optional[str] = None
    # Candidate videos harvested from ontology enrichment (Discogs master ->
    # videos[]). Player cycles through them on embed-error 150/101.
    videos: list[VideoRef] = []
    # Pointer back into the ontology graph (Discogs master/release pair).
    discogs: Optional[DiscogsRef] = None


class PlaySource(StrictModel):
    """A resolved, playable audio source for the Discord `/play` pipeline.

    Distinct from ``TrackInfo``: this is the minimal shape needed to hand a
    URL to a player (mpv), not a public-catalog display record. ``wikidata_qid``
    is set only when the query was disambiguated via a Wikidata entity lookup;
    playback never depends on Wikidata being reachable — it only sharpens the
    yt-dlp search query when available.
    """

    matched_via: MatchedVia
    stream_url: str
    title: Optional[str] = None
    webpage_url: Optional[str] = None
    duration_seconds: Optional[float] = None
    wikidata_qid: Optional[str] = None
    track: Optional[TrackInfo] = None


class RecordingRef(StrictModel):
    """A concrete playable resource for a canonical work, from the graph."""

    domain_id: str
    webpage_url: Optional[str] = None
    stream_url: Optional[str] = None
    title: Optional[str] = None
    duration_seconds: Optional[float] = None
    source: Optional[str] = None


class MusicGraphLookupInput(StrictModel):
    """Input to the ``music_graph_lookup`` tool (packages/maya-graph)."""

    query: str


class MusicGraphLookupOutput(StrictModel):
    """Output of the ``music_graph_lookup`` tool."""

    work_qid: Optional[str] = None
    label: Optional[str] = None
    recording: Optional[RecordingRef] = None
    confidence: float = 0.0


class PlayResolveResponse(StrictModel):
    """Resolver result — caller spawns a player widget around this payload."""

    matched_via: MatchedVia
    query: str
    zone: str
    tracks: list[TrackInfo]
    explanation: Optional[str] = None
