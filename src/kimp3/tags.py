"""Public tag API kept for backwards-compatible imports."""

from kimp3.covers import get_album_cover
from kimp3.lastfm import TaggedTrack, clear_cache, get_cache_stats, get_genre, init_lastfm
from kimp3.lyrics import get_lyrics
from kimp3.tag_processing import get_llm_tags, process_lastfm_tags, tags_list_to_str_list

__all__ = [
    "TaggedTrack",
    "clear_cache",
    "get_album_cover",
    "get_cache_stats",
    "get_genre",
    "get_llm_tags",
    "get_lyrics",
    "init_lastfm",
    "process_lastfm_tags",
    "tags_list_to_str_list",
]
