from atlas.learning.learning_manager import LearningManager


def test_learning_manager():

    manager = LearningManager()

    result = manager.learn(
        "Task completed successfully."
    )

    assert result.success

    assert result.knowledge == "Experience captured."