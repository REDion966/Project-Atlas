from atlas.services.ai_service import AIService

ai = AIService()

ai.start()

response = ai.chat([])

print(response.text)

completion = ai.complete("Hello Atlas")

print(completion.text)

print(ai.models())