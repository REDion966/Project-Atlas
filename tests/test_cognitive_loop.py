from atlas.intelligence.cognitive_loop import CognitiveLoop


def test_cognitive_loop():

    loop = CognitiveLoop()

    cycle = loop.process(
        "Learn from completed task."
    )

    assert cycle.goal == "Learn from completed task."

    assert cycle.lesson == "Experience captured."