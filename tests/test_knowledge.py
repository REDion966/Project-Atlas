from atlas.knowledge.knowledge_manager import KnowledgeManager


def test_knowledge_manager():

    manager = KnowledgeManager()

    manager.remember(

        "Python",

        "Python is a programming language.",

        "Atlas"

    )

    results = manager.query("programming")

    assert len(results) == 1

    assert results[0].title == "Python"