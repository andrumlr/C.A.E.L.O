class LocalProvider:
    def generate(self, prompt: str) -> str:
        # Keep local mode deterministic so frontend/backend wiring can be tested.
        if "USER:" in prompt:
            user_text = prompt.rsplit("USER:", 1)[-1].strip()
            if "ASSISTANT:" in user_text:
                user_text = user_text.split("ASSISTANT:", 1)[0].strip()
            if user_text:
                return f"Caelo local reply: {user_text}"
        return "Caelo local reply: ready."
