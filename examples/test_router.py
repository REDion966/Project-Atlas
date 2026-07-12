from atlas.ai.router.ai_router import AIRouter
from atlas.ai.providers.mock_provider import MockProvider

router = AIRouter()

# Register provider
router.registry.register(MockProvider())

print("Registered Providers")
print("---------------------")
print(router.registry.providers())
print()

# Select provider
router.use("Mock Provider")

print("Active Provider")
print("---------------------")
print(router.provider().name())
print()

response = router.chat([])

print("Chat")
print("---------------------")
print(response.text)
print()

completion = router.complete("Hello Atlas")

print("Completion")
print("---------------------")
print(completion.text)
print()

print("Models")
print("---------------------")
print(router.models())