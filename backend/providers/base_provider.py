class BaseProvider:
    def generate(self, prompt: str) -> str:
        raise NotImplementedError
