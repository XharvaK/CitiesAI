from citiesai.knowledge import knowledge_status, reset_knowledge_cache


def test_reset_knowledge_cache_does_not_break_loaders() -> None:
    reset_knowledge_cache()
    status = knowledge_status()
    assert status["wiki_chunks"] > 0
