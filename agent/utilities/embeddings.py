class JinaEmbeddings:
    """jina-embeddings-v5 via sentence-transformers (LangChain Embeddings interface).

    Jina v5 picks a LoRA adapter per task and uses separate query/document prompts,
    so they are passed at encode time instead of as text prefixes.
    """

    def __init__(self, model: str, device: str = "cpu", task: str = "retrieval",
                 truncate_dim: int = 768, batch_size: int = 32, max_length: int = 512):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model, device=device, trust_remote_code=True)
        self.model.max_seq_length = max_length
        self.task, self.truncate_dim, self.batch_size = task, truncate_dim, batch_size

    def _encode(self, texts, prompt_name):
        return self.model.encode(
            list(texts), task=self.task, prompt_name=prompt_name, batch_size=self.batch_size,
            truncate_dim=self.truncate_dim, normalize_embeddings=True, convert_to_numpy=True,
        ).tolist()

    def embed_documents(self, texts):
        return self._encode(texts, "document")

    def embed_query(self, text):
        return self._encode([text], "query")[0]


def create_embedding(name: str, **kwargs):
    # Backends are imported lazily so that using one does not require the others.
    if name == "jina":
        return JinaEmbeddings(
            kwargs["model"],
            device=kwargs.get("device", "cpu"),
            task=kwargs.get("task", "retrieval"),
            truncate_dim=kwargs.get("truncate_dim", 768),
            batch_size=kwargs.get("batch_size", 32),
            max_length=kwargs.get("max_length", 512),
        )
    if name == "HuggingFace":
        from langchain_huggingface import HuggingFaceEmbeddings

        return HuggingFaceEmbeddings(
            model_name=kwargs["model"],
            model_kwargs={
                "device": kwargs.get("device", "cpu"),
                "trust_remote_code": True,
                "processor_kwargs": {
                    "fix_mistral_regex": True,
                    "extra_special_tokens": {},
                },
                "config_kwargs": {"use_fast": False},
            },
            encode_kwargs={
                "normalize_embeddings": True,
                "truncate_dim": kwargs.get("truncate_dim", 768),  # [1024 / 768]
                "batch_size": kwargs.get("batch_size", 32),
            },
        )
    if name == "ollama":
        from langchain_ollama import OllamaEmbeddings

        return OllamaEmbeddings(
            model=kwargs["model"],
            base_url=kwargs.get("url"),
        )
    raise ValueError("Invalid embedding name.")
